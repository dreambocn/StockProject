import asyncio
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from conftest import build_sqlite_test_context, init_sqlite_schema

from app.core.security import create_access_token, hash_password
from app.db.session import get_db_session
from app.main import app
from app.models.user import User
from app.services.evaluation_service import EvaluationService


def _create_context(tmp_path: Path):
    engine, session_maker = build_sqlite_test_context(tmp_path, "admin-evaluations.db")
    init_sqlite_schema(engine)

    async def override_get_db_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    return engine, session_maker, TestClient(app)


def _create_user(session_maker: async_sessionmaker, *, user_level: str) -> User:
    async def _create() -> User:
        async with session_maker() as session:
            user = User(
                username=f"{user_level}-evaluation-user",
                email=f"{user_level}-evaluation@example.com",
                password_hash=hash_password("StrongP@ss1"),
                user_level=user_level,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    return asyncio.run(_create())


def test_admin_evaluations_routes_support_dataset_run_and_detail(
    tmp_path: Path,
    monkeypatch,
) -> None:
    engine, session_maker, client = _create_context(tmp_path)
    service = EvaluationService(storage_dir=tmp_path / "evaluation-runs")
    service.import_default_dataset()
    monkeypatch.setattr(
        "app.api.routes.admin.get_evaluation_service",
        lambda: service,
    )
    try:
        admin_user = _create_user(session_maker, user_level="admin")
        access_token = create_access_token(admin_user.id)

        datasets_response = client.get(
            "/api/admin/evaluations/datasets",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert datasets_response.status_code == 200
        assert datasets_response.json()[0]["dataset"] == "default_research_cases"

        run_response = client.post(
            "/api/admin/evaluations/runs",
            json={
                "dataset": "default_research_cases",
                "profiles": ["production_current", "evidence_first_v2"],
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert run_response.status_code == 201
        run_payload = run_response.json()
        assert run_payload["summary"]["metric_breakdown"]["evidence_first_v2"][
            "risk_notice_coverage"
        ] >= run_payload["summary"]["metric_breakdown"]["production_current"][
            "risk_notice_coverage"
        ]

        runs_response = client.get(
            "/api/admin/evaluations/runs?dataset=default_research_cases&prompt_profile=evidence_first_v2&event_type=政策驱动",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert runs_response.status_code == 200
        assert runs_response.json()[0]["run_id"] == run_payload["run_id"]

        detail_response = client.get(
            f"/api/admin/evaluations/runs/{run_payload['run_id']}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert detail_response.status_code == 200
        assert detail_response.json()["case_results"][0]["case_tags"]
    finally:
        client.close()
        app.dependency_overrides.clear()
        _ = engine


def test_admin_evaluations_routes_reject_non_admin(tmp_path: Path) -> None:
    engine, session_maker, client = _create_context(tmp_path)
    try:
        normal_user = _create_user(session_maker, user_level="user")
        access_token = create_access_token(normal_user.id)
        response = client.get(
            "/api/admin/evaluations/datasets",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 403
    finally:
        client.close()
        app.dependency_overrides.clear()
        _ = engine
