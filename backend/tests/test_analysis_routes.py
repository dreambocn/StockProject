from pathlib import Path
import asyncio

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db_session
from app.main import app


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
