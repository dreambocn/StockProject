from contextvars import ContextVar, Token
import logging
from logging.config import dictConfig


_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def setup_logging(level: str = "INFO") -> None:
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                }
            },
            "root": {
                "handlers": ["console"],
                "level": level,
            },
        }
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def set_request_id(request_id: str) -> Token[str]:
    return _request_id_ctx.set(request_id)


def reset_request_id(token: Token[str]) -> None:
    _request_id_ctx.reset(token)


def get_request_id() -> str:
    return _request_id_ctx.get()


def log_request_started(
    logger: logging.Logger,
    method: str,
    path: str,
) -> None:
    logger.info(
        "event=request_started request_id=%s method=%s path=%s",
        get_request_id(),
        method,
        path,
    )


def log_request_finished(
    logger: logging.Logger,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
) -> None:
    logger.info(
        "event=request_finished request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
        get_request_id(),
        method,
        path,
        status_code,
        duration_ms,
    )


def log_request_failed(
    logger: logging.Logger,
    method: str,
    path: str,
    duration_ms: float,
    error: Exception,
) -> None:
    logger.exception(
        "event=request_failed request_id=%s method=%s path=%s duration_ms=%.2f error=%s",
        get_request_id(),
        method,
        path,
        duration_ms,
        error.__class__.__name__,
    )


def log_request(
    logger: logging.Logger,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
) -> None:
    log_request_finished(logger, method, path, status_code, duration_ms)
