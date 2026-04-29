import asyncio
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from conftest import build_sqlite_test_context, init_sqlite_schema

from app.api.deps.auth import get_current_user
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.analysis_report import AnalysisReport
from app.models.stock_instrument import StockInstrument
from app.models.user import User


def _prepare_watchlist_client(tmp_path: Path):
    engine, session_maker = build_sqlite_test_context(tmp_path, "watchlist-test.db")
    init_sqlite_schema(engine)

    async def _seed_user() -> User:
        async with session_maker() as session:
            user = User(
                username="watcher",
                email="watcher@example.com",
                password_hash="hashed",
            )
            session.add(user)
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
                AnalysisReport(
                    ts_code="600519.SH",
                    status="ready",
                    summary="# 日报\n\n- 自动分析结果",
                    risk_points=["估值波动"],
                    factor_breakdown=[],
                    trigger_source="watchlist_daily",
                    used_web_search=False,
                    web_search_status="disabled",
                    content_format="markdown",
                    generated_at=datetime.now(UTC),
                    started_at=datetime.now(UTC),
                    completed_at=datetime.now(UTC),
                )
            )
            await session.commit()
            await session.refresh(user)
            return user

    seeded_user = asyncio.run(_seed_user())

    async def override_session():
        async with session_maker() as session:
            yield session

    async def override_current_user():
        return seeded_user

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_current_user] = override_current_user
    client = TestClient(app)
    return client, engine


def _cleanup_watchlist_client(engine) -> None:
    app.dependency_overrides.clear()


def test_watchlist_crud_and_feed(tmp_path: Path) -> None:
    client, engine = _prepare_watchlist_client(tmp_path)
    try:
        create_response = client.post(
            "/api/watchlist/items",
            json={
                "ts_code": "600519.SH",
                "hourly_sync_enabled": True,
                "daily_analysis_enabled": True,
                "web_search_enabled": False,
            },
        )
        list_response = client.get("/api/watchlist")
        patch_response = client.patch(
            "/api/watchlist/items/600519.SH",
            json={"web_search_enabled": True},
        )
        feed_response = client.get("/api/watchlist/feed")
        delete_response = client.delete("/api/watchlist/items/600519.SH")
    finally:
        _cleanup_watchlist_client(engine)

    assert create_response.status_code == 201
    assert list_response.status_code == 200
    assert patch_response.status_code == 200
    assert feed_response.status_code == 200
    assert delete_response.status_code == 200

    list_payload = list_response.json()
    assert len(list_payload["items"]) == 1
    assert list_payload["items"][0]["ts_code"] == "600519.SH"

    patch_payload = patch_response.json()
    assert patch_payload["web_search_enabled"] is True

    feed_payload = feed_response.json()
    assert len(feed_payload["items"]) == 1
    assert feed_payload["items"][0]["latest_report"]["trigger_source"] == "watchlist_daily"

