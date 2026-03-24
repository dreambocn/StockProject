import asyncio
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.analysis_evaluation_case import AnalysisEvaluationCase
from app.models.analysis_evaluation_dataset import AnalysisEvaluationDataset
from app.services.analysis_evaluation_repository import (
    build_evaluation_case_detail,
    build_evaluation_catalog,
    build_evaluation_overview,
    create_evaluation_run,
    upsert_evaluation_case,
    upsert_evaluation_case_result,
    upsert_evaluation_dataset,
)


def _build_session_maker(tmp_path):
    db_path = tmp_path / 'analysis-evaluation.db'
    db_url = f'sqlite+aiosqlite:///{db_path.as_posix()}'
    engine = create_async_engine(db_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _create_tables() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(_create_tables())
    return engine, session_maker


def test_upsert_dataset_and_cases_are_idempotent(tmp_path) -> None:
    engine, session_maker = _build_session_maker(tmp_path)

    async def run_test() -> None:
        async with session_maker() as session:
            dataset = await upsert_evaluation_dataset(
                session,
                dataset_key='analysis_eval_dataset_v1',
                label='人工标注样本集 v1',
                description='第一次导入',
                sample_count=2,
                date_from=date(2026, 1, 1),
                date_to=date(2026, 3, 24),
            )
            await session.flush()
            first_dataset_id = dataset.id

            await upsert_evaluation_case(
                session,
                dataset_id=dataset.id,
                case_key='case-maotai-policy',
                ts_code='600519.SH',
                topic='monetary_policy',
                anchor_event_title='消费支持政策持续加码',
                expected_top_factor_key='policy',
                notes='第一次备注',
            )
            await session.commit()

        async with session_maker() as session:
            dataset = await upsert_evaluation_dataset(
                session,
                dataset_key='analysis_eval_dataset_v1',
                label='人工标注样本集 v1',
                description='第二次导入',
                sample_count=3,
                date_from=date(2026, 1, 1),
                date_to=date(2026, 3, 24),
            )
            assert dataset.id == first_dataset_id
            assert dataset.sample_count == 3
            assert dataset.description == '第二次导入'

            evaluation_case = await upsert_evaluation_case(
                session,
                dataset_id=dataset.id,
                case_key='case-maotai-policy',
                ts_code='600519.SH',
                topic='monetary_policy',
                anchor_event_title='消费支持政策持续加码',
                expected_top_factor_key='policy',
                notes='更新备注',
            )
            await session.commit()

            datasets = (
                await session.execute(select(AnalysisEvaluationDataset))
            ).scalars().all()
            cases = (
                await session.execute(select(AnalysisEvaluationCase))
            ).scalars().all()

            assert len(datasets) == 1
            assert len(cases) == 1
            assert cases[0].id == evaluation_case.id
            assert cases[0].notes == '更新备注'

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())


def test_overview_and_case_detail_aggregate_run_pair(tmp_path) -> None:
    engine, session_maker = _build_session_maker(tmp_path)

    async def run_test() -> None:
        async with session_maker() as session:
            dataset = await upsert_evaluation_dataset(
                session,
                dataset_key='analysis_eval_dataset_v1',
                label='人工标注样本集 v1',
                description='用于提示词对比',
                sample_count=3,
                date_from=date(2026, 1, 1),
                date_to=date(2026, 3, 24),
            )
            case_1 = await upsert_evaluation_case(
                session,
                dataset_id=dataset.id,
                case_key='case-improved',
                ts_code='600519.SH',
                topic='monetary_policy',
                anchor_event_title='消费支持政策持续加码',
                expected_top_factor_key='policy',
                notes='应明显改善',
            )
            case_2 = await upsert_evaluation_case(
                session,
                dataset_id=dataset.id,
                case_key='case-regressed',
                ts_code='000001.SZ',
                topic='regulation_policy',
                anchor_event_title='银行监管边际收紧',
                expected_top_factor_key='policy',
                notes='可能退化',
            )
            case_3 = await upsert_evaluation_case(
                session,
                dataset_id=dataset.id,
                case_key='case-unchanged',
                ts_code='601899.SH',
                topic='commodity_supply',
                anchor_event_title='铜矿供给扰动升温',
                expected_top_factor_key='news',
                notes='保持不变',
            )

            baseline_run = await create_evaluation_run(
                session,
                run_key='run-baseline-001',
                dataset_id=dataset.id,
                experiment_group_key='prompt_profile_compare_v1',
                variant_key='baseline',
                variant_label='基线方案',
                prompt_profile_key='production_current',
                model_name='gpt-5.1-codex-mini',
                sample_count=3,
                event_top1_hit_rate=1 / 3,
                factor_top1_accuracy=2 / 3,
                citation_metadata_completeness_rate=1 / 3,
                avg_latency_ms=1800,
                created_at=datetime(2026, 3, 24, 9, 0, tzinfo=UTC),
            )
            candidate_run = await create_evaluation_run(
                session,
                run_key='run-optimized-001',
                dataset_id=dataset.id,
                experiment_group_key='prompt_profile_compare_v1',
                variant_key='optimized',
                variant_label='优化方案',
                prompt_profile_key='evidence_first_v2',
                model_name='gpt-5.1-codex-mini',
                sample_count=3,
                event_top1_hit_rate=2 / 3,
                factor_top1_accuracy=2 / 3,
                citation_metadata_completeness_rate=2 / 3,
                avg_latency_ms=1500,
                created_at=datetime(2026, 3, 24, 9, 5, tzinfo=UTC),
            )

            await upsert_evaluation_case_result(
                session,
                run_id=baseline_run.id,
                case_id=case_1.id,
                event_top1_hit=False,
                factor_top1_hit=False,
                citation_metadata_completeness_rate=0.0,
                latency_ms=1900,
                top_event_title='其他旧事件',
                top_factor_key='news',
                web_source_count=0,
                result_snapshot={'summary': '基线摘要 1'},
            )
            await upsert_evaluation_case_result(
                session,
                run_id=candidate_run.id,
                case_id=case_1.id,
                event_top1_hit=True,
                factor_top1_hit=True,
                citation_metadata_completeness_rate=1.0,
                latency_ms=1400,
                top_event_title='消费支持政策持续加码',
                top_factor_key='policy',
                web_source_count=3,
                result_snapshot={'summary': '优化摘要 1'},
            )
            await upsert_evaluation_case_result(
                session,
                run_id=baseline_run.id,
                case_id=case_2.id,
                event_top1_hit=True,
                factor_top1_hit=True,
                citation_metadata_completeness_rate=1.0,
                latency_ms=1700,
                top_event_title='银行监管边际收紧',
                top_factor_key='policy',
                web_source_count=2,
                result_snapshot={'summary': '基线摘要 2'},
            )
            await upsert_evaluation_case_result(
                session,
                run_id=candidate_run.id,
                case_id=case_2.id,
                event_top1_hit=False,
                factor_top1_hit=False,
                citation_metadata_completeness_rate=0.0,
                latency_ms=1200,
                top_event_title='其他事件',
                top_factor_key='news',
                web_source_count=1,
                result_snapshot={'summary': '优化摘要 2'},
            )
            await upsert_evaluation_case_result(
                session,
                run_id=baseline_run.id,
                case_id=case_3.id,
                event_top1_hit=True,
                factor_top1_hit=True,
                citation_metadata_completeness_rate=0.5,
                latency_ms=1800,
                top_event_title='铜矿供给扰动升温',
                top_factor_key='news',
                web_source_count=2,
                result_snapshot={'summary': '基线摘要 3'},
            )
            await upsert_evaluation_case_result(
                session,
                run_id=candidate_run.id,
                case_id=case_3.id,
                event_top1_hit=True,
                factor_top1_hit=True,
                citation_metadata_completeness_rate=0.5,
                latency_ms=1900,
                top_event_title='铜矿供给扰动升温',
                top_factor_key='news',
                web_source_count=2,
                result_snapshot={'summary': '优化摘要 3'},
            )
            await session.commit()

        async with session_maker() as session:
            catalog = await build_evaluation_catalog(session)
            overview = await build_evaluation_overview(
                session,
                dataset_key='analysis_eval_dataset_v1',
                experiment_group_key='prompt_profile_compare_v1',
            )
            detail = await build_evaluation_case_detail(
                session,
                case_key='case-improved',
                baseline_run_id=baseline_run.id,
                candidate_run_id=candidate_run.id,
            )

            assert len(catalog['datasets']) == 1
            assert len(catalog['experiment_groups']) == 1
            assert catalog['experiment_groups'][0]['experiment_group_key'] == 'prompt_profile_compare_v1'

            assert overview['empty'] is False
            assert overview['baseline_run']['id'] == baseline_run.id
            assert overview['candidate_run']['id'] == candidate_run.id
            assert overview['distribution_chart']['improved'] == 1
            assert overview['distribution_chart']['regressed'] == 1
            assert overview['distribution_chart']['unchanged'] == 1
            assert overview['top_improved_cases'][0]['case_key'] == 'case-improved'
            assert overview['top_regressed_cases'][0]['case_key'] == 'case-regressed'
            assert len(overview['recent_cases']) == 3
            assert (
                overview['metric_cards']['event_top1_hit_rate']['candidate_value']
                == candidate_run.event_top1_hit_rate
            )

            assert detail['case']['case_key'] == 'case-improved'
            assert detail['baseline_result']['result_snapshot']['summary'] == '基线摘要 1'
            assert detail['candidate_result']['result_snapshot']['summary'] == '优化摘要 1'
            assert detail['candidate_result']['classification'] == 'improved'

    try:
        asyncio.run(run_test())
    finally:
        asyncio.run(engine.dispose())
