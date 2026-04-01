import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.system_job_run import SystemJobRun
from app.models.user import User


def _create_context(tmp_path: Path):
    db_path = tmp_path / "admin-news.db"
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


def _create_user(session_maker: async_sessionmaker, *, user_level: str) -> User:
    async def _create() -> User:
        async with session_maker() as session:
            user = User(
                username=f"{user_level}-news-user",
                email=f"{user_level}-news@example.com",
                password_hash=hash_password("StrongP@ss1"),
                user_level=user_level,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    return asyncio.run(_create())


def test_admin_news_impact_refresh_route_creates_job(tmp_path: Path, monkeypatch) -> None:
    engine, session_maker, client = _create_context(tmp_path)
    try:
        async def fake_refresh_news_impact_snapshots(
            session,
            *,
            trigger_source: str,
        ):
            job = SystemJobRun(
                job_type="news_impact_refresh",
                status="success",
                trigger_source=trigger_source,
                resource_type="news_impact_map",
                resource_key="default",
                summary="热点影响面板快照刷新完成",
                metrics_json={
                    "refreshed_topic_count": 6,
                    "source_version": "hot=20260303100500|evidence=20260303103000|theme=20260303110000",
                },
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            return {
                "job_id": job.id,
                "job_type": "news_impact_refresh",
                "status": "success",
                "source_version": "hot=20260303100500|evidence=20260303103000|theme=20260303110000",
                "refreshed_topic_count": 6,
            }

        monkeypatch.setattr(
            "app.api.routes.admin.refresh_news_impact_snapshots",
            fake_refresh_news_impact_snapshots,
        )
        monkeypatch.setattr(
            "app.api.routes.admin.get_settings",
            lambda: SimpleNamespace(policy_sync_enabled=True),
        )

        admin_user = _create_user(session_maker, user_level="admin")
        access_token = create_access_token(admin_user.id)

        response = client.post(
            "/api/admin/news/impact/refresh",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "success"
        assert payload["job_type"] == "news_impact_refresh"
        assert payload["refreshed_topic_count"] == 6

        async def _load_jobs() -> list[SystemJobRun]:
            async with session_maker() as session:
                return (
                    await session.execute(
                        select(SystemJobRun).where(
                            SystemJobRun.job_type == "news_impact_refresh"
                        )
                    )
                ).scalars().all()

        jobs = asyncio.run(_load_jobs())
        assert len(jobs) == 1
        assert jobs[0].resource_key == "default"
    finally:
        client.close()
        _cleanup_context(engine)
