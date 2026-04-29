import asyncio
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from conftest import build_sqlite_test_context, init_sqlite_schema

from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.system_job_run import SystemJobRun
from app.models.user import User


def _create_context(tmp_path: Path):
    engine, session_maker = build_sqlite_test_context(tmp_path, "admin-jobs.db")
    init_sqlite_schema(engine)

    async def override_get_db_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    return engine, session_maker, TestClient(app)


def _cleanup_context(engine) -> None:
    app.dependency_overrides.clear()


def _create_user(session_maker: async_sessionmaker, *, user_level: str) -> User:
    async def _create() -> User:
        async with session_maker() as session:
            user = User(
                username=f"{user_level}-user",
                email=f"{user_level}@example.com",
                password_hash=hash_password("StrongP@ss1"),
                user_level=user_level,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    return asyncio.run(_create())


def test_admin_jobs_routes_support_list_summary_and_detail(tmp_path: Path) -> None:
    engine, session_maker, client = _create_context(tmp_path)
    try:
        admin_user = _create_user(session_maker, user_level="admin")
        access_token = create_access_token(admin_user.id)

        async def _seed() -> None:
            async with session_maker() as session:
                session.add_all(
                    [
                        SystemJobRun(
                            id="job-success",
                            job_type="analysis_generate",
                            status="success",
                            trigger_source="manual",
                            resource_type="stock",
                            resource_key="600519.SH",
                            linked_entity_type="analysis_generation_session",
                            linked_entity_id="session-1",
                            summary="已完成",
                        ),
                        SystemJobRun(
                            id="job-failed",
                            job_type="news_fetch",
                            status="failed",
                            trigger_source="api.news.hot",
                            resource_type="hot",
                            resource_key="global",
                            error_type="RuntimeError",
                            error_message="upstream failed",
                            summary="失败",
                        ),
                    ]
                )
                await session.commit()

        asyncio.run(_seed())

        list_response = client.get(
            "/api/admin/jobs?job_type=analysis_generate",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 1
        assert list_response.json()["items"][0]["id"] == "job-success"

        summary_response = client.get(
            "/api/admin/jobs/summary",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert summary_response.status_code == 200
        payload = summary_response.json()
        assert payload["status_counts"]["success"] == 1
        assert payload["status_counts"]["failed"] == 1
        assert payload["type_counts"]["analysis_generate"] == 1
        assert payload["recent_failures"][0]["id"] == "job-failed"

        detail_response = client.get(
            "/api/admin/jobs/job-success",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert detail_response.status_code == 200
        assert detail_response.json()["linked_entity"]["entity_id"] == "session-1"
    finally:
        client.close()
        _cleanup_context(engine)


def test_admin_jobs_routes_reject_non_admin(tmp_path: Path) -> None:
    engine, session_maker, client = _create_context(tmp_path)
    try:
        normal_user = _create_user(session_maker, user_level="user")
        access_token = create_access_token(normal_user.id)
        response = client.get(
            "/api/admin/jobs",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 403
    finally:
        client.close()
        _cleanup_context(engine)
