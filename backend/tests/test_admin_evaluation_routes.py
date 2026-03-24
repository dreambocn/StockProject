import asyncio
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.user import User
from app.services.analysis_evaluation_repository import (
    create_evaluation_run,
    upsert_evaluation_case,
    upsert_evaluation_case_result,
    upsert_evaluation_dataset,
)


@pytest.fixture
def admin_evaluation_test_context(tmp_path: Path):
    db_path = tmp_path / 'admin-evaluation-test.db'
    db_url = f'sqlite+aiosqlite:///{db_path.as_posix()}'
    engine = create_async_engine(db_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _create_tables() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(_create_tables())

    async def override_get_db_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    with TestClient(app) as client:
        yield {
            'client': client,
            'session_maker': session_maker,
        }

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def _create_user(
    session_maker: async_sessionmaker,
    *,
    username: str,
    email: str,
    user_level: str,
) -> User:
    async def _create() -> User:
        async with session_maker() as session:
            user = User(
                username=username,
                email=email,
                password_hash=hash_password('StrongP@ss1'),
                user_level=user_level,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    return asyncio.run(_create())


def _seed_run_pair(
    session_maker: async_sessionmaker,
    *,
    only_baseline: bool = False,
) -> tuple[str, str | None]:
    async def _seed() -> tuple[str, str | None]:
        async with session_maker() as session:
            dataset = await upsert_evaluation_dataset(
                session,
                dataset_key='analysis_eval_dataset_v1',
                label='人工标注样本集 v1',
                description='用于管理员页面测试',
                sample_count=1,
                date_from=date(2026, 1, 1),
                date_to=date(2026, 3, 24),
            )
            evaluation_case = await upsert_evaluation_case(
                session,
                dataset_id=dataset.id,
                case_key='case-admin-route',
                ts_code='600519.SH',
                topic='monetary_policy',
                anchor_event_title='消费支持政策持续加码',
                expected_top_factor_key='policy',
                notes='管理员路由测试',
            )
            baseline_run = await create_evaluation_run(
                session,
                run_key='route-baseline-001',
                dataset_id=dataset.id,
                experiment_group_key='prompt_profile_compare_v1',
                variant_key='baseline',
                variant_label='基线方案',
                prompt_profile_key='production_current',
                model_name='gpt-5.1-codex-mini',
                sample_count=1,
                event_top1_hit_rate=0.0,
                factor_top1_accuracy=0.0,
                citation_metadata_completeness_rate=0.0,
                avg_latency_ms=1800,
                created_at=datetime(2026, 3, 24, 9, 0, tzinfo=UTC),
            )
            await upsert_evaluation_case_result(
                session,
                run_id=baseline_run.id,
                case_id=evaluation_case.id,
                event_top1_hit=False,
                factor_top1_hit=False,
                citation_metadata_completeness_rate=0.0,
                latency_ms=1800,
                top_event_title='其他事件',
                top_factor_key='news',
                web_source_count=0,
                result_snapshot={'summary': '基线摘要'},
            )

            candidate_run_id: str | None = None
            if not only_baseline:
                candidate_run = await create_evaluation_run(
                    session,
                    run_key='route-optimized-001',
                    dataset_id=dataset.id,
                    experiment_group_key='prompt_profile_compare_v1',
                    variant_key='optimized',
                    variant_label='优化方案',
                    prompt_profile_key='evidence_first_v2',
                    model_name='gpt-5.1-codex-mini',
                    sample_count=1,
                    event_top1_hit_rate=1.0,
                    factor_top1_accuracy=1.0,
                    citation_metadata_completeness_rate=1.0,
                    avg_latency_ms=1500,
                    created_at=datetime(2026, 3, 24, 9, 5, tzinfo=UTC),
                )
                candidate_run_id = candidate_run.id
                await upsert_evaluation_case_result(
                    session,
                    run_id=candidate_run.id,
                    case_id=evaluation_case.id,
                    event_top1_hit=True,
                    factor_top1_hit=True,
                    citation_metadata_completeness_rate=1.0,
                    latency_ms=1500,
                    top_event_title='消费支持政策持续加码',
                    top_factor_key='policy',
                    web_source_count=2,
                    result_snapshot={'summary': '优化摘要'},
                )

            await session.commit()
            return baseline_run.id, candidate_run_id

    return asyncio.run(_seed())


def test_admin_evaluation_catalog_rejects_non_admin(
    admin_evaluation_test_context,
) -> None:
    user = _create_user(
        admin_evaluation_test_context['session_maker'],
        username='normal-user',
        email='normal@example.com',
        user_level='user',
    )
    access_token = create_access_token(user.id)

    response = admin_evaluation_test_context['client'].get(
        '/api/admin/evaluations/catalog',
        headers={'Authorization': f'Bearer {access_token}'},
    )

    assert response.status_code == 403


def test_admin_evaluation_catalog_returns_empty_state(
    admin_evaluation_test_context,
) -> None:
    admin_user = _create_user(
        admin_evaluation_test_context['session_maker'],
        username='root-admin',
        email='root@example.com',
        user_level='admin',
    )
    access_token = create_access_token(admin_user.id)

    response = admin_evaluation_test_context['client'].get(
        '/api/admin/evaluations/catalog',
        headers={'Authorization': f'Bearer {access_token}'},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['datasets'] == []
    assert payload['experiment_groups'] == []


def test_admin_evaluation_overview_auto_selects_latest_pair(
    admin_evaluation_test_context,
) -> None:
    admin_user = _create_user(
        admin_evaluation_test_context['session_maker'],
        username='route-admin',
        email='route-admin@example.com',
        user_level='admin',
    )
    access_token = create_access_token(admin_user.id)
    baseline_run_id, candidate_run_id = _seed_run_pair(
        admin_evaluation_test_context['session_maker']
    )

    response = admin_evaluation_test_context['client'].get(
        '/api/admin/evaluations/overview?dataset_key=analysis_eval_dataset_v1&experiment_group_key=prompt_profile_compare_v1',
        headers={'Authorization': f'Bearer {access_token}'},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['empty'] is False
    assert payload['baseline_run']['id'] == baseline_run_id
    assert payload['candidate_run']['id'] == candidate_run_id
    assert payload['distribution_chart']['improved'] == 1


def test_admin_evaluation_overview_returns_422_when_variant_pair_incomplete(
    admin_evaluation_test_context,
) -> None:
    admin_user = _create_user(
        admin_evaluation_test_context['session_maker'],
        username='route-admin-2',
        email='route-admin-2@example.com',
        user_level='admin',
    )
    access_token = create_access_token(admin_user.id)
    _seed_run_pair(
        admin_evaluation_test_context['session_maker'],
        only_baseline=True,
    )

    response = admin_evaluation_test_context['client'].get(
        '/api/admin/evaluations/overview?dataset_key=analysis_eval_dataset_v1&experiment_group_key=prompt_profile_compare_v1',
        headers={'Authorization': f'Bearer {access_token}'},
    )

    assert response.status_code == 422
