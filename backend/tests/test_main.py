import importlib
import logging

from fastapi.testclient import TestClient
import pytest

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


def test_health_endpoint_returns_ok(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="app.request"):
        response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["services"]["postgres"]["host"] == "192.168.31.199"
    assert payload["services"]["redis"]["host"] == "192.168.31.199"
    assert response.headers.get("x-request-id")
    assert "event=request_started" in caplog.text
    assert "event=request_finished" in caplog.text


def test_stocks_endpoint_returns_seed_data() -> None:
    response = client.get("/api/stocks")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert payload[0]["symbol"] == "AAPL"
    assert "price" in payload[0]


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
