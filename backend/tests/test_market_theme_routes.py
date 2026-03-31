import asyncio
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.market_theme import MarketTheme
from app.models.market_theme_membership import MarketThemeMembership
from app.models.stock_instrument import StockInstrument


def _create_context(tmp_path: Path):
    db_path = tmp_path / "market-theme.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _create_tables() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(_create_tables())

    async def override_get_db_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    return engine, session_maker, TestClient(app)


def _cleanup_context(engine) -> None:
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def test_stock_theme_route_and_impact_map_include_theme_enhancement(tmp_path: Path) -> None:
    engine, session_maker, client = _create_context(tmp_path)
    try:
        async def _seed() -> None:
            async with session_maker() as session:
                session.add(
                    StockInstrument(
                        ts_code="600938.SH",
                        symbol="600938",
                        name="中国海油",
                        fullname="中国海洋石油有限公司",
                        industry="石油开采",
                        list_status="L",
                    )
                )
                session.add(
                    MarketTheme(
                        id="theme-1",
                        theme_code="oil-chain",
                        theme_name="油气产业链",
                        theme_type="concept",
                        source="manual",
                        source_updated_at=datetime(2026, 3, 31, 8, 0, tzinfo=UTC),
                    )
                )
                session.add(
                    MarketThemeMembership(
                        theme_id="theme-1",
                        ts_code="600938.SH",
                        match_score=88,
                        evidence_summary="受益于油价上行",
                        evidence_json=[{"text": "受益于油价上行"}],
                    )
                )
                await session.commit()

        asyncio.run(_seed())

        theme_response = client.get("/api/stocks/600938.SH/themes")
        assert theme_response.status_code == 200
        assert theme_response.json()[0]["theme_name"] == "油气产业链"

        impact_response = client.get("/api/news/impact-map?topic=commodity_supply")
        assert impact_response.status_code == 200
        candidates = impact_response.json()[0]["a_share_candidates"]
        matched = next(item for item in candidates if item["ts_code"] == "600938.SH")
        assert matched["theme_matches"] == ["油气产业链"]
        assert matched["theme_evidence"] == ["受益于油价上行"]
    finally:
        client.close()
        _cleanup_context(engine)
