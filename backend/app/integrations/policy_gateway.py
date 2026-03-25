from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.settings import get_settings
from app.integrations.tushare_gateway import TushareGateway


def _pick_text(row: dict[str, object], *keys: str) -> str | None:
    # 逐个候选字段寻找可用文本，兼容不同数据源字段命名。
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _normalize_policy_row(
    row: dict[str, object],
    *,
    title_keys: tuple[str, ...],
    summary_keys: tuple[str, ...],
    time_keys: tuple[str, ...],
    link_keys: tuple[str, ...],
    source_label: str,
) -> dict[str, Any] | None:
    # 标题缺失则放弃该条，避免生成无意义事件。
    title = _pick_text(row, *title_keys)
    if not title:
        return None

    published_at = _pick_text(row, *time_keys)
    return {
        "title": title,
        "summary": _pick_text(row, *summary_keys),
        "published_at": published_at or datetime.now(UTC).isoformat(),
        "link": _pick_text(row, *link_keys),
        "source": source_label,
    }


async def fetch_policy_events() -> list[dict[str, Any]]:
    settings = get_settings()
    # 未配置 tushare token 直接返回空，避免污染日志与异常。
    if not settings.tushare_token.strip():
        return []

    gateway = TushareGateway(settings.tushare_token)
    start_date = (datetime.now(UTC) - timedelta(days=7)).strftime("%Y%m%d")
    rows: list[dict[str, Any]] = []

    try:
        cctv_rows = await gateway.fetch_cctv_news(date=start_date)
        for row in cctv_rows:
            normalized = _normalize_policy_row(
                row,
                title_keys=("title", "content"),
                summary_keys=("content",),
                time_keys=("pub_time", "date"),
                link_keys=("url",),
                source_label="tushare_cctv_news",
            )
            if normalized is not None:
                rows.append(normalized)
    except Exception:
        # 上游不稳定时降级为忽略，保证其他数据源仍可返回。
        pass

    try:
        eco_rows = await gateway.fetch_economic_calendar(start_date=start_date)
        for row in eco_rows:
            normalized = _normalize_policy_row(
                row,
                title_keys=("event", "title", "country"),
                summary_keys=("content", "actual", "consensus"),
                time_keys=("date", "published_at"),
                link_keys=("url",),
                source_label="tushare_eco_cal",
            )
            if normalized is not None:
                rows.append(normalized)
    except Exception:
        # 避免单一来源失败导致整体查询失败。
        pass

    rows.sort(key=lambda item: str(item.get("published_at") or ""), reverse=True)
    return rows
