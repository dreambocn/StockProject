import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

# 直接执行脚本时补齐 backend 根目录到 sys.path，确保 `app.*` 可导入。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.init_db import ensure_database_schema
from app.db.session import SessionLocal
from app.services.analysis_evaluation_repository import (
    upsert_evaluation_case,
    upsert_evaluation_dataset,
)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


async def import_dataset_from_file(dataset_path: Path) -> dict[str, object]:
    payload = json.loads(dataset_path.read_text(encoding='utf-8'))
    cases = payload.get('cases') or []

    async with SessionLocal() as session:
        dataset = await upsert_evaluation_dataset(
            session,
            dataset_key=str(payload['dataset_key']),
            label=str(payload['label']),
            description=payload.get('description'),
            sample_count=len(cases),
            date_from=_parse_date(payload.get('date_from')),
            date_to=_parse_date(payload.get('date_to')),
        )
        for case_payload in cases:
            # 关键流程：按 dataset_key + case_key 幂等写入，便于人工标注样本反复修订后重新导入。
            await upsert_evaluation_case(
                session,
                dataset_id=dataset.id,
                case_key=str(case_payload['case_key']),
                ts_code=str(case_payload['ts_code']).strip().upper(),
                topic=case_payload.get('topic'),
                anchor_event_title=str(case_payload['anchor_event_title']),
                expected_top_factor_key=str(case_payload['expected_top_factor_key']),
                notes=case_payload.get('notes'),
            )
        await session.commit()
        return {
            'dataset_key': dataset.dataset_key,
            'sample_count': len(cases),
        }


async def main() -> None:
    parser = argparse.ArgumentParser(description='导入分析评估样本集')
    parser.add_argument(
        '--file',
        default=str(
            PROJECT_ROOT / 'data' / 'evaluations' / 'analysis_eval_dataset_v1.json'
        ),
        help='样本集 JSON 文件路径',
    )
    args = parser.parse_args()

    await ensure_database_schema()
    summary = await import_dataset_from_file(Path(args.file))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
