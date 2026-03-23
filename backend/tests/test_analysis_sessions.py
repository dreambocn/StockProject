import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.analysis_report import AnalysisReport
from app.models.stock_daily_snapshot import StockDailySnapshot
from app.models.stock_instrument import StockInstrument


def _prepare_client(tmp_path: Path):
    db_path = tmp_path / "analysis-session-test.db"
    db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
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
    client = TestClient(app)
    return client, engine, session_maker


def _cleanup_client(engine) -> None:
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


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


async def _seed_report(session_maker, *, ts_code: str, generated_at: datetime) -> None:
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
                trigger_source="manual",
                used_web_search=False,
                web_search_status="disabled",
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
