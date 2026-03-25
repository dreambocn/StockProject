import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# 直接执行脚本时把 backend 根目录加入模块搜索路径，避免 `app.*` 导入失败。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.init_db import ensure_database_schema
from app.db.session import SessionLocal
from app.models.analysis_event_link import AnalysisEventLink
from app.models.analysis_report import AnalysisReport
from app.models.news_event import NewsEvent
from app.services.analysis_event_selection_service import (
    build_analysis_event_logical_key,
)


async def dedupe_analysis_event_links(
    session: AsyncSession,
    *,
    analysis_report_id: str | None = None,
    ts_code: str | None = None,
    apply_changes: bool,
) -> dict[str, int | bool | str | None]:
    resolved_ts_code = (ts_code or "").strip().upper() or None
    if analysis_report_id:
        report = await session.get(AnalysisReport, analysis_report_id)
        if report is None:
            raise ValueError("未找到对应的分析报告，无法定位去重范围")
        resolved_ts_code = report.ts_code.strip().upper()

    if not resolved_ts_code:
        raise ValueError("必须提供 analysis_report_id 或 ts_code 之一")

    statement = (
        select(AnalysisEventLink, NewsEvent)
        .join(NewsEvent, AnalysisEventLink.event_id == NewsEvent.id)
        .where(AnalysisEventLink.ts_code == resolved_ts_code)
        .order_by(AnalysisEventLink.created_at.desc(), NewsEvent.id.desc())
    )
    rows = (await session.execute(statement)).all()

    grouped_rows: dict[tuple[object, ...], list[tuple[AnalysisEventLink, NewsEvent]]] = (
        defaultdict(list)
    )
    for link_row, news_row in rows:
        grouped_rows[build_analysis_event_logical_key(news_row)].append((link_row, news_row))

    duplicate_groups = 0
    kept_rows = 0
    deleted_rows = 0
    for group_rows in grouped_rows.values():
        if not group_rows:
            continue
        duplicate_groups += 1 if len(group_rows) > 1 else 0
        kept_rows += 1
        redundant_rows = group_rows[1:]
        deleted_rows += len(redundant_rows)
        if not apply_changes:
            continue
        for link_row, _news_row in redundant_rows:
            await session.delete(link_row)

    if apply_changes:
        await session.commit()

    return {
        "analysis_report_id": analysis_report_id,
        "ts_code": resolved_ts_code,
        "scanned_rows": len(rows),
        "duplicate_groups": duplicate_groups,
        "kept_rows": kept_rows,
        "deleted_rows": deleted_rows if apply_changes else 0,
        "pending_delete_rows": deleted_rows if not apply_changes else 0,
        "applied": apply_changes,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="清理分析事件链接中的重复逻辑事件")
    parser.add_argument(
        "--analysis-report-id",
        dest="analysis_report_id",
        help="按分析报告所属股票范围定位去重目标",
    )
    parser.add_argument(
        "--ts-code",
        dest="ts_code",
        help="直接按股票代码定位去重目标，例如 600519.SH",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="默认仅演练；传入后才会真正删除重复链接",
    )
    return parser


async def _main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    await ensure_database_schema()

    async with SessionLocal() as session:
        result = await dedupe_analysis_event_links(
            session,
            analysis_report_id=args.analysis_report_id,
            ts_code=args.ts_code,
            apply_changes=args.apply,
        )

    print(
        "扫描完成："
        f"股票={result['ts_code']} "
        f"重复组={result['duplicate_groups']} "
        f"保留={result['kept_rows']} "
        f"待删除={result['pending_delete_rows']} "
        f"已删除={result['deleted_rows']} "
        f"已执行={'是' if result['applied'] else '否'}"
    )


if __name__ == "__main__":
    asyncio.run(_main())
