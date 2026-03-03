import logging

from fastapi.testclient import TestClient

from app.main import app


def test_exception_path_is_logged(caplog) -> None:
    path = "/api/_test_error"

    if not any(getattr(route, "path", None) == path for route in app.router.routes):

        @app.get(path)
        async def _test_error() -> dict[str, str]:
            raise RuntimeError("boom")

    client = TestClient(app, raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR, logger="app.request"):
        response = client.get(path)

    assert response.status_code == 500
    assert "event=request_failed" in caplog.text
    assert "path=/api/_test_error" in caplog.text
    assert "error=RuntimeError" in caplog.text
