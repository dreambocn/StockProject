from contextvars import ContextVar, Token
import logging
from logging.config import dictConfig


_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def setup_logging(level: str = "INFO") -> None:
    # 全局统一日志格式，保证后端各模块日志可被同一规则检索和聚合。
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
    logger = logging.getLogger(name)
    logger.disabled = False
    logger.propagate = True
    return logger


def _ensure_logger_active(logger: logging.Logger) -> logging.Logger:
    # 测试与热重载场景下 logger 可能被其他配置改写，这里统一恢复为可捕获状态。
    logger.disabled = False
    logger.propagate = True
    return logger


def set_request_id(request_id: str) -> Token[str]:
    # 将 request_id 写入上下文，避免函数层层传参。
    return _request_id_ctx.set(request_id)


def reset_request_id(token: Token[str]) -> None:
    # 恢复上下文快照，避免异步任务间串号。
    _request_id_ctx.reset(token)


def get_request_id() -> str:
    # 未设置时返回 "-"，避免非请求线程抛异常。
    return _request_id_ctx.get()


def log_request_started(
    logger: logging.Logger,
    method: str,
    path: str,
) -> None:
    # 请求入口日志：用于统计流量与定位请求链路起点。
    logger = _ensure_logger_active(logger)
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
    # 请求完成日志：记录状态码与耗时，便于 SLA 监控。
    logger = _ensure_logger_active(logger)
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
    # 异常日志走 exception，保留堆栈以便故障定位。
    logger = _ensure_logger_active(logger)
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
