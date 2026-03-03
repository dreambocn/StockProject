import logging

from app.core.logging import (
    log_request_failed,
    log_request_finished,
    log_request_started,
    reset_request_id,
    set_request_id,
)


def test_request_logging_helpers_emit_expected_messages(caplog) -> None:
    logger = logging.getLogger("tests.logging")

    token = set_request_id("req-001")
    with caplog.at_level(logging.INFO):
        log_request_started(logger, "GET", "/api/health")
        log_request_finished(logger, "GET", "/api/health", 200, 12.34)
    reset_request_id(token)

    assert "event=request_started" in caplog.text
    assert "event=request_finished" in caplog.text
    assert "request_id=req-001" in caplog.text
    assert "method=GET" in caplog.text
    assert "path=/api/health" in caplog.text
    assert "status=200" in caplog.text
    assert "duration_ms=12.34" in caplog.text


def test_failed_request_logging_emits_error_event(caplog) -> None:
    logger = logging.getLogger("tests.logging")

    token = set_request_id("req-err-001")
    with caplog.at_level(logging.ERROR):
        try:
            raise RuntimeError("boom")
        except RuntimeError as exc:
            log_request_failed(logger, "GET", "/api/fail", 4.56, exc)
    reset_request_id(token)

    assert "event=request_failed" in caplog.text
    assert "request_id=req-err-001" in caplog.text
    assert "error=RuntimeError" in caplog.text
