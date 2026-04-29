import asyncio
import importlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from conftest import build_sqlite_test_context, init_sqlite_schema

from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.analysis_generation_session import AnalysisGenerationSession
from app.models.analysis_report import AnalysisReport
from app.models.stock_daily_snapshot import StockDailySnapshot
from app.models.stock_instrument import StockInstrument
from app.services import analysis_repository


def _prepare_client(tmp_path: Path):
    engine, session_maker = build_sqlite_test_context(tmp_path, "analysis-session-test.db")
    init_sqlite_schema(engine)

    async def override_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    client = TestClient(app)
    return client, engine, session_maker


def _cleanup_client(engine) -> None:
    app.dependency_overrides.clear()


async def _seed_instrument(session_maker, *, ts_code: str) -> None:
    async with session_maker() as session:
        existed = await session.get(StockInstrument, ts_code)
        if existed is None:
            session.add(
                StockInstrument(
                    ts_code=ts_code,
                    symbol="600519",
                    name="贵州茅台",
                    fullname="贵州茅台酒股份有限公司",
                    list_status="L",
                )
            )
        await session.commit()


async def _seed_report(
    session_maker,
    *,
    ts_code: str,
    generated_at: datetime,
    trigger_source: str = "manual",
    used_web_search: bool = False,
) -> None:
    async with session_maker() as session:
        instrument = await session.get(StockInstrument, ts_code)
        if instrument is None:
            session.add(
                StockInstrument(
                    ts_code=ts_code,
                    symbol="600519",
                    name="贵州茅台",
                    fullname="贵州茅台酒股份有限公司",
                    list_status="L",
                )
            )
        snapshot = await session.get(StockDailySnapshot, (ts_code, generated_at.date()))
        if snapshot is None:
            session.add(
                StockDailySnapshot(
                    ts_code=ts_code,
                    trade_date=generated_at.date(),
                    close=1688.88,
                )
            )
        session.add(
            AnalysisReport(
                ts_code=ts_code,
                status="ready",
                summary="# 测试摘要\n\n- 已有归档",
                risk_points=["风险提示"],
                factor_breakdown=[],
                topic=None,
                generated_at=generated_at,
                started_at=generated_at - timedelta(minutes=1),
                completed_at=generated_at,
                trigger_source=trigger_source,
                used_web_search=used_web_search,
                web_search_status="used" if used_web_search else "disabled",
                content_format="markdown",
            )
        )
        await session.commit()


def test_create_analysis_session_reuses_active_session(tmp_path: Path) -> None:
    client, engine, _session_maker = _prepare_client(tmp_path)
    try:
        asyncio.run(_seed_instrument(_session_maker, ts_code="600519.SH"))
        first_response = client.post(
            "/api/analysis/stocks/600519.SH/sessions",
            json={
                "topic": None,
                "force_refresh": True,
                "use_web_search": False,
                "trigger_source": "manual",
            },
        )
        second_response = client.post(
            "/api/analysis/stocks/600519.SH/sessions",
            json={
                "topic": None,
                "force_refresh": True,
                "use_web_search": False,
                "trigger_source": "manual",
            },
        )
    finally:
        _cleanup_client(engine)

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    first_payload = first_response.json()
    second_payload = second_response.json()
    assert first_payload["session_id"]
    assert first_payload["session_id"] == second_payload["session_id"]
    assert second_payload["reused"] is True


def test_create_analysis_session_uses_fresh_report_cache(tmp_path: Path) -> None:
    client, engine, session_maker = _prepare_client(tmp_path)
    try:
        asyncio.run(
            _seed_report(
                session_maker,
                ts_code="600519.SH",
                generated_at=datetime.now(UTC),
            )
        )
        response = client.post(
            "/api/analysis/stocks/600519.SH/sessions",
            json={
                "force_refresh": False,
                "use_web_search": False,
                "trigger_source": "manual",
            },
        )
    finally:
        _cleanup_client(engine)

    assert response.status_code == 200
    payload = response.json()
    assert payload["cached"] is True
    assert payload["report_id"]
    assert payload["session_id"] is None


def test_create_analysis_session_force_refresh_still_uses_hourly_report_cache(
    tmp_path: Path,
) -> None:
    client, engine, session_maker = _prepare_client(tmp_path)
    try:
        asyncio.run(
            _seed_report(
                session_maker,
                ts_code="600519.SH",
                generated_at=datetime.now(UTC),
            )
        )
        response = client.post(
            "/api/analysis/stocks/600519.SH/sessions",
            json={
                "force_refresh": True,
                "use_web_search": False,
                "trigger_source": "manual",
            },
        )
    finally:
        _cleanup_client(engine)

    assert response.status_code == 200
    payload = response.json()
    assert payload["cached"] is True
    assert payload["session_id"] is None
    assert payload["report_id"]


def test_create_analysis_session_uses_recent_report_across_trigger_sources(
    tmp_path: Path,
) -> None:
    client, engine, session_maker = _prepare_client(tmp_path)
    try:
        asyncio.run(
            _seed_report(
                session_maker,
                ts_code="600519.SH",
                generated_at=datetime.now(UTC),
                trigger_source="watchlist_daily",
            )
        )
        response = client.post(
            "/api/analysis/stocks/600519.SH/sessions",
            json={
                "force_refresh": True,
                "use_web_search": False,
                "trigger_source": "manual",
            },
        )
    finally:
        _cleanup_client(engine)

    assert response.status_code == 200
    payload = response.json()
    assert payload["cached"] is True
    assert payload["session_id"] is None
    assert payload["report_id"]


def test_create_analysis_session_keeps_functional_multi_agent_cache_isolated(
    tmp_path: Path,
) -> None:
    client, engine, session_maker = _prepare_client(tmp_path)
    try:
        asyncio.run(
            _seed_report(
                session_maker,
                ts_code="600519.SH",
                generated_at=datetime.now(UTC),
            )
        )
        response = client.post(
            "/api/analysis/stocks/600519.SH/sessions",
            json={
                "force_refresh": False,
                "use_web_search": False,
                "trigger_source": "manual",
                "analysis_mode": "functional_multi_agent",
            },
        )
    finally:
        _cleanup_client(engine)

    assert response.status_code == 200
    payload = response.json()
    assert payload["cached"] is False
    assert payload["session_id"]
    assert payload["status"] == "queued"


def test_analysis_reports_route_returns_latest_first(tmp_path: Path) -> None:
    client, engine, session_maker = _prepare_client(tmp_path)
    try:
        asyncio.run(
            _seed_report(
                session_maker,
                ts_code="600519.SH",
                generated_at=datetime(2026, 3, 23, 10, 0, tzinfo=UTC),
            )
        )
        asyncio.run(
            _seed_report(
                session_maker,
                ts_code="600519.SH",
                generated_at=datetime(2026, 3, 23, 12, 0, tzinfo=UTC),
            )
        )
        response = client.get("/api/analysis/stocks/600519.SH/reports?limit=10")
    finally:
        _cleanup_client(engine)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ts_code"] == "600519.SH"
    assert len(payload["items"]) == 2
    assert payload["items"][0]["generated_at"] >= payload["items"][1]["generated_at"]
    assert payload["items"][0]["content_format"] == "markdown"


def test_create_analysis_session_does_not_schedule_process_local_task(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, engine, session_maker = _prepare_client(tmp_path)
    try:
        asyncio.run(_seed_instrument(session_maker, ts_code="600519.SH"))

        created_flags = {"analysis_task_called": False}

        async def fake_run_analysis_session_by_id(session_id: str) -> None:
            _ = session_id
            created_flags["analysis_task_called"] = True

        monkeypatch.setattr(
            "app.services.analysis_service.run_analysis_session_by_id",
            fake_run_analysis_session_by_id,
        )

        response = client.post(
            "/api/analysis/stocks/600519.SH/sessions",
            json={
                "force_refresh": True,
                "use_web_search": False,
                "trigger_source": "manual",
            },
        )
    finally:
        _cleanup_client(engine)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"
    assert created_flags["analysis_task_called"] is False


def test_analysis_worker_claim_prefers_queued_then_recovers_stale_running(
    tmp_path: Path,
) -> None:
    client, engine, session_maker = _prepare_client(tmp_path)
    try:
        asyncio.run(_seed_instrument(session_maker, ts_code="600519.SH"))

        async def run_test() -> None:
            now = datetime.now(UTC)
            async with session_maker() as session:
                queued_row = AnalysisGenerationSession(
                    analysis_key="600519.SH|||0|manual",
                    ts_code="600519.SH",
                    topic=None,
                    anchor_event_id=None,
                    use_web_search=False,
                    trigger_source="manual",
                    trigger_source_group="manual",
                    status="queued",
                    created_at=now - timedelta(minutes=10),
                    updated_at=now - timedelta(minutes=10),
                )
                stale_running_row = AnalysisGenerationSession(
                    analysis_key="600519.SH|commodity_supply||0|manual",
                    ts_code="600519.SH",
                    topic="commodity_supply",
                    anchor_event_id=None,
                    use_web_search=False,
                    trigger_source="manual",
                    trigger_source_group="manual",
                    status="running",
                    started_at=now - timedelta(minutes=40),
                    created_at=now - timedelta(minutes=40),
                    updated_at=now - timedelta(minutes=40),
                    error_message="上次执行中断",
                )
                session.add_all([queued_row, stale_running_row])
                await session.commit()
                queued_id = queued_row.id
                stale_running_id = stale_running_row.id

            async with session_maker() as session:
                claimed_queued = (
                    await analysis_repository.claim_next_analysis_session_for_worker(
                        session,
                        stale_before=now - timedelta(seconds=900),
                    )
                )
                await session.commit()
            assert claimed_queued == queued_id

            async with session_maker() as session:
                queued_after_claim = await session.get(
                    AnalysisGenerationSession,
                    queued_id,
                )
                assert queued_after_claim is not None
                queued_after_claim.status = "completed"
                await session.commit()

            async with session_maker() as session:
                claimed_stale = (
                    await analysis_repository.claim_next_analysis_session_for_worker(
                        session,
                        stale_before=datetime.now(UTC) - timedelta(seconds=900),
                    )
                )
                await session.commit()
            assert claimed_stale == stale_running_id

            async with session_maker() as session:
                stale_after_claim = await session.get(
                    AnalysisGenerationSession,
                    stale_running_id,
                )
                assert stale_after_claim is not None
                assert stale_after_claim.status == "running"
                assert stale_after_claim.error_message is None
                assert stale_after_claim.started_at is not None

        asyncio.run(run_test())
    finally:
        _cleanup_client(engine)


def test_analysis_worker_iteration_claims_and_runs_session(monkeypatch) -> None:
    called: dict[str, object] = {
        "claimed": False,
        "ran_session_id": None,
    }

    class _FakeSessionContext:
        async def __aenter__(self):
            class _FakeSession:
                async def commit(self) -> None:
                    return None

            return _FakeSession()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_claim_next_analysis_session_for_worker(
        session,
        *,
        stale_before: datetime,
    ) -> str | None:
        assert session is not None
        assert isinstance(stale_before, datetime)
        called["claimed"] = True
        return "session-queued-1"

    async def fake_run_analysis_session_by_id(session_id: str) -> None:
        called["ran_session_id"] = session_id

    worker_module = importlib.import_module("scripts.run_analysis_worker")
    monkeypatch.setattr(
        worker_module,
        "SessionLocal",
        lambda: _FakeSessionContext(),
    )
    monkeypatch.setattr(
        worker_module,
        "claim_next_analysis_session_for_worker",
        fake_claim_next_analysis_session_for_worker,
    )
    monkeypatch.setattr(
        worker_module,
        "run_analysis_session_by_id",
        fake_run_analysis_session_by_id,
    )

    claimed_session_id = asyncio.run(worker_module.run_analysis_worker_iteration())

    assert called["claimed"] is True
    assert called["ran_session_id"] == "session-queued-1"
    assert claimed_session_id == "session-queued-1"


def test_analysis_worker_iteration_skips_when_no_queued_session(monkeypatch) -> None:
    called: dict[str, bool] = {
        "run_called": False,
    }

    class _FakeSessionContext:
        async def __aenter__(self):
            class _FakeSession:
                async def commit(self) -> None:
                    return None

            return _FakeSession()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_claim_next_analysis_session_for_worker(
        session,
        *,
        stale_before: datetime,
    ) -> str | None:
        assert session is not None
        assert isinstance(stale_before, datetime)
        return None

    async def fake_run_analysis_session_by_id(session_id: str) -> None:
        _ = session_id
        called["run_called"] = True

    worker_module = importlib.import_module("scripts.run_analysis_worker")
    monkeypatch.setattr(
        worker_module,
        "SessionLocal",
        lambda: _FakeSessionContext(),
    )
    monkeypatch.setattr(
        worker_module,
        "claim_next_analysis_session_for_worker",
        fake_claim_next_analysis_session_for_worker,
    )
    monkeypatch.setattr(
        worker_module,
        "run_analysis_session_by_id",
        fake_run_analysis_session_by_id,
    )

    claimed_session_id = asyncio.run(worker_module.run_analysis_worker_iteration())

    assert claimed_session_id is None
    assert called["run_called"] is False
