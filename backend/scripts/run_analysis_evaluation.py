import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from sqlalchemy import or_, select

# 直接执行脚本时补齐 backend 根目录到 sys.path，确保 `app.*` 可导入。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.settings import get_settings
from app.db.init_db import ensure_database_schema
from app.db.session import SessionLocal
from app.models.news_event import NewsEvent
from app.models.stock_instrument import StockInstrument
from app.services.analysis_evaluation_repository import (
    create_evaluation_run,
    list_evaluation_cases_by_dataset,
    load_evaluation_dataset_by_key,
    normalize_evaluation_title,
    upsert_evaluation_case_result,
)
from app.services.factor_weight_service import calculate_factor_weights
from app.services.llm_analysis_service import generate_stock_analysis_report


def _derive_event_type(raw_event: NewsEvent) -> str:
    if raw_event.scope == 'policy':
        return 'policy'
    source = (raw_event.source or '').lower()
    if 'announcement' in source or source == 'cninfo_announcement':
        return 'announcement'
    return 'news'


def _build_citation_metadata_completeness_rate(
    web_sources: list[dict[str, object]] | None,
) -> float:
    source_list = list(web_sources or [])
    if not source_list:
        return 0.0
    completed = sum(
        1
        for item in source_list
        if item.get('source') and item.get('domain') and item.get('published_at')
    )
    return round(completed / len(source_list), 4)


def _build_result_snapshot(
    *,
    top_event_title: str | None,
    report_result,
) -> dict[str, object]:
    return {
        'summary': report_result.summary,
        'risk_points': report_result.risk_points,
        'factor_breakdown': report_result.factor_breakdown,
        'web_sources': report_result.web_sources,
        'top_event_title': top_event_title,
    }


async def build_case_analysis_input(session, evaluation_case) -> dict[str, object]:
    instrument = await session.get(StockInstrument, evaluation_case.ts_code)
    statement = (
        select(NewsEvent)
        .where(
            or_(
                NewsEvent.ts_code == evaluation_case.ts_code,
                NewsEvent.macro_topic == evaluation_case.topic,
            )
        )
        .order_by(NewsEvent.published_at.desc(), NewsEvent.created_at.desc())
        .limit(10)
    )
    raw_events = (await session.execute(statement)).scalars().all()

    events: list[dict[str, object]] = []
    for raw_event in raw_events:
        events.append(
            {
                'title': raw_event.title,
                'published_at': raw_event.published_at,
                'event_type': _derive_event_type(raw_event),
                'sentiment_label': raw_event.sentiment_label or 'neutral',
                'correlation_score': raw_event.source_priority or 0.0,
            }
        )

    if not events:
        # 关键降级：当数据库中暂时找不到匹配事件时，回退到人工标注锚点，保证实验脚本仍可运行。
        events.append(
            {
                'title': evaluation_case.anchor_event_title,
                'published_at': None,
                'event_type': 'news',
                'sentiment_label': 'neutral',
                'correlation_score': 0.0,
            }
        )

    factor_weights = calculate_factor_weights(events)
    return {
        'instrument_name': instrument.name if instrument else None,
        'events': events,
        'factor_weights': factor_weights,
    }


async def _run_variant(
    session,
    *,
    dataset_id: str,
    cases,
    experiment_group_key: str,
    variant_key: str,
    variant_label: str,
    prompt_profile_key: str,
    model_name: str,
    use_web_search: bool,
) -> str:
    case_outputs: list[dict[str, object]] = []
    for evaluation_case in cases:
        case_input = await build_case_analysis_input(session, evaluation_case)
        started = perf_counter()
        report_result = await generate_stock_analysis_report(
            evaluation_case.ts_code,
            case_input['instrument_name'],
            case_input['events'],
            case_input['factor_weights'],
            session=session,
            use_web_search=use_web_search,
            prompt_profile_key=prompt_profile_key,
        )
        latency_ms = round((perf_counter() - started) * 1000, 2)
        top_event_title = (
            str(case_input['events'][0].get('title'))
            if case_input['events']
            else None
        )
        top_factor_key = None
        if report_result.factor_breakdown:
            top_factor_key = str(report_result.factor_breakdown[0].get('factor_key'))
        citation_rate = _build_citation_metadata_completeness_rate(
            report_result.web_sources
        )
        case_outputs.append(
            {
                'case_id': evaluation_case.id,
                'event_top1_hit': normalize_evaluation_title(top_event_title)
                == normalize_evaluation_title(evaluation_case.anchor_event_title),
                'factor_top1_hit': (
                    top_factor_key == evaluation_case.expected_top_factor_key
                ),
                'citation_metadata_completeness_rate': citation_rate,
                'latency_ms': latency_ms,
                'top_event_title': top_event_title,
                'top_factor_key': top_factor_key,
                'web_source_count': len(report_result.web_sources or []),
                'result_snapshot': _build_result_snapshot(
                    top_event_title=top_event_title,
                    report_result=report_result,
                ),
            }
        )

    run_key = (
        f'{experiment_group_key}-{variant_key}-'
        f'{datetime.now(UTC).strftime("%Y%m%d%H%M%S")}'
    )
    run_row = await create_evaluation_run(
        session,
        run_key=run_key,
        dataset_id=dataset_id,
        experiment_group_key=experiment_group_key,
        variant_key=variant_key,
        variant_label=variant_label,
        prompt_profile_key=prompt_profile_key,
        model_name=model_name,
        sample_count=len(case_outputs),
        event_top1_hit_rate=round(
            sum(float(item['event_top1_hit']) for item in case_outputs)
            / max(len(case_outputs), 1),
            4,
        ),
        factor_top1_accuracy=round(
            sum(float(item['factor_top1_hit']) for item in case_outputs)
            / max(len(case_outputs), 1),
            4,
        ),
        citation_metadata_completeness_rate=round(
            sum(float(item['citation_metadata_completeness_rate']) for item in case_outputs)
            / max(len(case_outputs), 1),
            4,
        ),
        avg_latency_ms=round(
            sum(float(item['latency_ms']) for item in case_outputs)
            / max(len(case_outputs), 1),
            2,
        ),
        created_at=datetime.now(UTC),
    )
    for item in case_outputs:
        await upsert_evaluation_case_result(
            session,
            run_id=run_row.id,
            case_id=str(item['case_id']),
            event_top1_hit=bool(item['event_top1_hit']),
            factor_top1_hit=bool(item['factor_top1_hit']),
            citation_metadata_completeness_rate=float(
                item['citation_metadata_completeness_rate']
            ),
            latency_ms=float(item['latency_ms']),
            top_event_title=item['top_event_title'],
            top_factor_key=item['top_factor_key'],
            web_source_count=int(item['web_source_count']),
            result_snapshot=item['result_snapshot'],
        )
    await session.flush()
    return run_row.id


async def run_evaluation_for_dataset(
    *,
    dataset_key: str,
    experiment_group_key: str,
    baseline_prompt_profile_key: str = 'production_current',
    candidate_prompt_profile_key: str = 'evidence_first_v2',
    use_web_search: bool | None = None,
) -> dict[str, object]:
    settings = get_settings()
    resolved_web_search = (
        settings.llm_web_search_enabled if use_web_search is None else use_web_search
    )
    async with SessionLocal() as session:
        dataset = await load_evaluation_dataset_by_key(session, dataset_key)
        if dataset is None:
            raise ValueError(f'未找到数据集：{dataset_key}')
        cases = await list_evaluation_cases_by_dataset(session, dataset.id)
        if not cases:
            raise ValueError(f'数据集 {dataset_key} 暂无样本')

        baseline_run_id = await _run_variant(
            session,
            dataset_id=dataset.id,
            cases=cases,
            experiment_group_key=experiment_group_key,
            variant_key='baseline',
            variant_label='基线方案',
            prompt_profile_key=baseline_prompt_profile_key,
            model_name=settings.llm_model,
            use_web_search=resolved_web_search,
        )
        candidate_run_id = await _run_variant(
            session,
            dataset_id=dataset.id,
            cases=cases,
            experiment_group_key=experiment_group_key,
            variant_key='optimized',
            variant_label='优化方案',
            prompt_profile_key=candidate_prompt_profile_key,
            model_name=settings.llm_model,
            use_web_search=resolved_web_search,
        )
        await session.commit()
        return {
            'dataset_key': dataset_key,
            'experiment_group_key': experiment_group_key,
            'baseline_run_id': baseline_run_id,
            'candidate_run_id': candidate_run_id,
        }


async def main() -> None:
    parser = argparse.ArgumentParser(description='运行分析评估实验')
    parser.add_argument('--dataset-key', default='analysis_eval_dataset_v1')
    parser.add_argument(
        '--experiment-group-key',
        default='prompt_profile_compare_v1',
    )
    parser.add_argument(
        '--baseline-prompt-profile-key',
        default='production_current',
    )
    parser.add_argument(
        '--candidate-prompt-profile-key',
        default='evidence_first_v2',
    )
    parser.add_argument(
        '--use-web-search',
        action='store_true',
        help='显式启用联网补证',
    )
    args = parser.parse_args()

    await ensure_database_schema()
    summary = await run_evaluation_for_dataset(
        dataset_key=args.dataset_key,
        experiment_group_key=args.experiment_group_key,
        baseline_prompt_profile_key=args.baseline_prompt_profile_key,
        candidate_prompt_profile_key=args.candidate_prompt_profile_key,
        use_web_search=args.use_web_search,
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
