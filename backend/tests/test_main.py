import asyncio
import importlib
import logging

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.api.routes.health as health_routes
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app


client = TestClient(app)


def _build_client_with_cors(
    monkeypatch, origins: str, credentials: str = "true"
) -> TestClient:
    import app.core.settings as settings_module
    import app.main as main_module

    monkeypatch.setenv("CORS_ALLOW_ORIGINS", origins)
    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", credentials)
    settings_module.get_settings.cache_clear()
    main_module = importlib.reload(main_module)

    return TestClient(main_module.app)


def test_health_liveness_endpoint_returns_ok(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="app.request"):
        response = client.get("/api/health/liveness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert response.headers.get("x-request-id")
    assert "event=request_started" in caplog.text
    assert "event=request_finished" in caplog.text


def test_health_readiness_endpoint_returns_ok_when_dependencies_healthy(
    monkeypatch,
) -> None:
    async def _probe_ok() -> dict[str, object]:
        return {
            "status": "ok",
            "latency_ms": 1.0,
            "error_type": None,
        }

    monkeypatch.setattr(health_routes, "_probe_postgres", _probe_ok)
    monkeypatch.setattr(health_routes, "_probe_redis", _probe_ok)
    monkeypatch.setattr(health_routes, "_probe_smtp", _probe_ok)

    response = client.get("/api/health/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["services"]["postgres"]["status"] == "ok"
    assert payload["services"]["redis"]["status"] == "ok"
    assert payload["services"]["smtp"]["status"] == "ok"
    assert payload["services"]["postgres"]["error_type"] is None


def test_health_readiness_returns_fail_when_postgres_unavailable(monkeypatch) -> None:
    async def _probe_postgres_fail() -> dict[str, object]:
        return {
            "status": "fail",
            "latency_ms": 2.0,
            "error_type": "OperationalError",
        }

    async def _probe_ok() -> dict[str, object]:
        return {
            "status": "ok",
            "latency_ms": 1.0,
            "error_type": None,
        }

    monkeypatch.setattr(health_routes, "_probe_postgres", _probe_postgres_fail)
    monkeypatch.setattr(health_routes, "_probe_redis", _probe_ok)
    monkeypatch.setattr(health_routes, "_probe_smtp", _probe_ok)

    response = client.get("/api/health/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "fail"
    assert payload["services"]["postgres"]["status"] == "fail"
    assert payload["services"]["postgres"]["error_type"] == "OperationalError"
    assert payload["services"]["redis"]["status"] == "ok"


def test_health_readiness_returns_degraded_when_smtp_unavailable(monkeypatch) -> None:
    async def _probe_ok() -> dict[str, object]:
        return {
            "status": "ok",
            "latency_ms": 1.0,
            "error_type": None,
        }

    async def _probe_smtp_fail() -> dict[str, object]:
        return {
            "status": "fail",
            "latency_ms": 1.0,
            "error_type": "RuntimeError",
        }

    monkeypatch.setattr(health_routes, "_probe_postgres", _probe_ok)
    monkeypatch.setattr(health_routes, "_probe_redis", _probe_ok)
    monkeypatch.setattr(health_routes, "_probe_smtp", _probe_smtp_fail)

    response = client.get("/api/health/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["services"]["smtp"]["status"] == "fail"
    assert payload["services"]["smtp"]["error_type"] == "RuntimeError"
    assert "password" not in str(payload).lower()


def test_health_endpoint_maps_to_readiness(monkeypatch) -> None:
    async def _probe_ok() -> dict[str, object]:
        return {
            "status": "ok",
            "latency_ms": 1.0,
            "error_type": None,
        }

    monkeypatch.setattr(health_routes, "_probe_postgres", _probe_ok)
    monkeypatch.setattr(health_routes, "_probe_redis", _probe_ok)
    monkeypatch.setattr(health_routes, "_probe_smtp", _probe_ok)

    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "services" in payload


def test_stocks_endpoint_returns_list_response(tmp_path) -> None:
    db_path = tmp_path / "main-stock-test.db"
    db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = create_async_engine(db_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def override_get_db_session():
        async with session_maker() as session:
            yield session

    asyncio.run(_prepare())
    app.dependency_overrides[get_db_session] = override_get_db_session

    try:
        response = client.get("/api/stocks")

        assert response.status_code == 200
        payload = response.json()
        assert isinstance(payload, list)
        if payload:
            assert "ts_code" in payload[0]
            assert "symbol" in payload[0]
            assert "name" in payload[0]
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_cors_allows_whitelisted_origin(monkeypatch) -> None:
    client_with_cors = _build_client_with_cors(monkeypatch, "http://localhost:5173")
    response = client_with_cors.options(
        "/api/stocks",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert (
        response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    )
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_allows_localhost_with_different_dev_port(monkeypatch) -> None:
    client_with_cors = _build_client_with_cors(monkeypatch, "http://localhost:5173")
    response = client_with_cors.options(
        "/api/auth/register/email-code",
        headers={
            "Origin": "http://localhost:5174",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert (
        response.headers.get("access-control-allow-origin") == "http://localhost:5174"
    )


def test_cors_blocks_non_allowlisted_origin(monkeypatch) -> None:
    client_with_cors = _build_client_with_cors(monkeypatch, "http://localhost:5173")
    response = client_with_cors.options(
        "/api/stocks",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert response.headers.get("access-control-allow-origin") is None


def test_app_startup_rejects_wildcard_origin_with_credentials(monkeypatch) -> None:
    import app.core.settings as settings_module
    import app.main as main_module

    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "*")
    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "true")
    settings_module.get_settings.cache_clear()

    with pytest.raises(ValueError, match="CORS_ALLOW_ORIGINS"):
        importlib.reload(main_module)
