from pathlib import Path
import asyncio
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.analysis_event_link import AnalysisEventLink
from app.models.analysis_report import AnalysisReport
from app.models.news_event import NewsEvent
from app.models.stock_instrument import StockInstrument


def _prepare_analysis_client(tmp_path: Path):
    db_path = tmp_path / "analysis-test.db"
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
    return client, engine


def _cleanup_analysis_client(engine):
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def test_analysis_summary_route_returns_pending_when_empty(tmp_path: Path) -> None:
    client, engine = _prepare_analysis_client(tmp_path)
    try:
        response = client.get("/api/analysis/stocks/600519.SH/summary")
    finally:
        _cleanup_analysis_client(engine)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ts_code"] == "600519.SH"
    assert isinstance(payload.get("events"), list)
    assert payload["events"] == []
    assert payload["report"] is None
    assert payload["status"] in {"pending", "partial"}


def test_analysis_summary_route_supports_event_id_and_returns_anchor_fields(
    tmp_path: Path,
) -> None:
    client, engine = _prepare_analysis_client(tmp_path)
    try:
        async def _seed() -> None:
            override_session = app.dependency_overrides[get_db_session]
            async for session in override_session():
                session.add(
                    StockInstrument(
                        ts_code="600519.SH",
                        symbol="600519",
                        name="贵州茅台",
                        fullname="贵州茅台酒股份有限公司",
                        list_status="L",
                    )
                )
                session.add(
                    NewsEvent(
                        id="evt-hot-1",
                        scope="hot",
                        cache_variant="global",
                        title="国际油价高位震荡",
                        summary="原油供需偏紧",
                        published_at=datetime(2026, 3, 3, 10, 0, tzinfo=timezone.utc),
                        url="https://finance.example.com/h/1",
                        publisher="测试源",
                        source="eastmoney_global",
                        macro_topic="commodity_supply",
                        fetched_at=datetime(2026, 3, 3, 10, 5, tzinfo=timezone.utc),
                    )
                )
                session.add(
                    AnalysisEventLink(
                        event_id="evt-hot-1",
                        ts_code="600519.SH",
                        correlation_score=0.9,
                        confidence="high",
                        link_status="linked",
                    )
                )
                session.add(
                    AnalysisReport(
                        ts_code="600519.SH",
                        status="ready",
                        summary="测试报告",
                        risk_points=["风险提示"],
                        factor_breakdown=[],
                        topic="commodity_supply",
                        anchor_event_id="evt-hot-1",
                        anchor_event_title="国际油价高位震荡",
                        structured_sources=[{"provider": "akshare", "count": 1}],
                        generated_at=datetime(2026, 3, 3, 10, 10, tzinfo=timezone.utc),
                    )
                )
                await session.commit()
                break

        asyncio.run(_seed())
        response = client.get(
            "/api/analysis/stocks/600519.SH/summary",
            params={"topic": "commodity_supply", "event_id": "evt-hot-1"},
        )
    finally:
        _cleanup_analysis_client(engine)

    assert response.status_code == 200
    payload = response.json()
    assert payload["topic"] == "commodity_supply"
    assert payload["report"]["anchor_event_id"] == "evt-hot-1"
    assert payload["report"]["anchor_event_title"] == "国际油价高位震荡"
    assert payload["report"]["structured_sources"] == [{"provider": "akshare", "count": 1}]
