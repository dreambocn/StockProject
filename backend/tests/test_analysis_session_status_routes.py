import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.analysis_generation_session import AnalysisGenerationSession


def _prepare_client(tmp_path: Path):
    db_path = tmp_path / 'analysis-session-status.db'
    db_url = f'sqlite+aiosqlite:///{db_path.as_posix()}'
    engine = create_async_engine(db_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _create_tables() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(_create_tables())

    async def override_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    return TestClient(app), engine


def _cleanup_client(engine) -> None:
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def test_analysis_session_status_route_returns_progress_fields(tmp_path: Path) -> None:
    client, engine = _prepare_client(tmp_path)
    try:
        async def _seed() -> None:
            override_session = app.dependency_overrides[get_db_session]
            async for session in override_session():
                session.add(
                    AnalysisGenerationSession(
                        id='session-progress-1',
                        analysis_key='000001.SZ||0|manual',
                        ts_code='000001.SZ',
                        topic=None,
                        anchor_event_id=None,
                        use_web_search=False,
                        trigger_source='manual',
                        trigger_source_group='manual',
                        status='running',
                        current_stage='linking_events',
                        stage_message='正在计算事件关联指标',
                        progress_current=3,
                        progress_total=9,
                        summary_preview='## 预览摘要',
                        report_id=None,
                        error_message=None,
                        started_at=datetime(2026, 4, 1, 12, 0, tzinfo=UTC),
                        completed_at=None,
                        heartbeat_at=datetime(2026, 4, 1, 12, 1, tzinfo=UTC),
                    )
                )
                await session.commit()
                break

        asyncio.run(_seed())
        response = client.get('/api/analysis/sessions/session-progress-1')
    finally:
        _cleanup_client(engine)

    assert response.status_code == 200
    payload = response.json()
    assert payload['session_id'] == 'session-progress-1'
    assert payload['status'] == 'running'
    assert payload['current_stage'] == 'linking_events'
    assert payload['stage_message'] == '正在计算事件关联指标'
    assert payload['progress_current'] == 3
    assert payload['progress_total'] == 9
    assert payload['summary_preview'] == '## 预览摘要'
    assert payload['heartbeat_at'] == '2026-04-01T12:01:00Z'
