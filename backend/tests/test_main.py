import logging

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


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
