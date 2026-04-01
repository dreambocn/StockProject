import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.system_job_run import SystemJobRun
from app.models.user import User


def _create_context(tmp_path: Path):
    db_path = tmp_path / "admin-policy.db"
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
                username=f"{user_level}-policy-user",
                email=f"{user_level}-policy@example.com",
                password_hash=hash_password("StrongP@ss1"),
                user_level=user_level,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    return asyncio.run(_create())


def test_admin_policy_sync_route_creates_policy_sync_job(tmp_path: Path, monkeypatch) -> None:
    engine, session_maker, client = _create_context(tmp_path)
    try:
        async def fake_sync_policy_documents(
            session,
            *,
            trigger_source: str,
            force_refresh: bool,
            providers=None,
            now=None,
            settings=None,
        ):
            _ = (providers, now, settings)
            job = SystemJobRun(
                job_type="policy_sync",
                status="success",
                trigger_source=trigger_source,
                resource_type="policy_document",
                resource_key="all",
                summary="政策同步完成",
                metrics_json={
                    "provider_count": 1,
                    "raw_count": 2,
                    "normalized_count": 2,
                    "inserted_count": 2,
                    "updated_count": 0,
                    "deduped_count": 0,
                    "failed_provider_count": 0,
                },
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            return {
                "job_id": job.id,
                "status": "success",
                "provider_count": 1,
                "raw_count": 2,
                "normalized_count": 2,
                "inserted_count": 2,
                "updated_count": 0,
                "deduped_count": 0,
                "failed_provider_count": 0,
                "document_ids": [],
                "force_refresh": force_refresh,
            }

        monkeypatch.setattr(
            "app.api.routes.admin.sync_policy_documents",
            fake_sync_policy_documents,
        )
        monkeypatch.setattr(
            "app.api.routes.admin.get_settings",
            lambda: SimpleNamespace(policy_sync_enabled=True),
        )

        admin_user = _create_user(session_maker, user_level="admin")
        access_token = create_access_token(admin_user.id)

        response = client.post(
            "/api/admin/policy/sync",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"force_refresh": True},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "success"
        assert payload["inserted_count"] == 2
        assert payload["job_type"] == "policy_sync"
    finally:
        client.close()
        _cleanup_context(engine)
