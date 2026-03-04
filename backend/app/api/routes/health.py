from time import perf_counter

from fastapi import APIRouter
from sqlalchemy import text

from app.cache.redis import get_redis_client
from app.core.settings import get_settings
from app.db.session import engine


router = APIRouter()
settings = get_settings()


def _probe_ok(latency_ms: float) -> dict[str, str | float | None]:
    return {
        "status": "ok",
        "latency_ms": round(latency_ms, 2),
        "error_type": None,
    }


def _probe_fail(latency_ms: float, error_type: str) -> dict[str, str | float | None]:
    return {
        "status": "fail",
        "latency_ms": round(latency_ms, 2),
        "error_type": error_type,
    }


async def _probe_postgres() -> dict[str, str | float | None]:
    started = perf_counter()
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        return _probe_fail((perf_counter() - started) * 1000, type(exc).__name__)

    return _probe_ok((perf_counter() - started) * 1000)


async def _probe_redis() -> dict[str, str | float | None]:
    started = perf_counter()
    try:
        await get_redis_client().ping()
    except Exception as exc:  # noqa: BLE001
        return _probe_fail((perf_counter() - started) * 1000, type(exc).__name__)

    return _probe_ok((perf_counter() - started) * 1000)


async def _probe_smtp() -> dict[str, str | float | None]:
    started = perf_counter()

    # 运维可观测边界：readiness 仅做 SMTP 配置完整性探针，
    # 避免在健康检查中引入外部网络抖动导致的级联超时。
    if (
        not settings.smtp_host
        or not settings.smtp_username
        or not settings.smtp_password
    ):
        return _probe_fail((perf_counter() - started) * 1000, "RuntimeError")

    return _probe_ok((perf_counter() - started) * 1000)


def _resolve_readiness_status(
    services: dict[str, dict[str, str | float | None]],
) -> str:
    # 关键分级策略：数据库或 Redis 失败时直接标记 fail；
    # SMTP 失败仅标记 degraded，避免邮件能力抖动阻断核心鉴权链路可用性判断。
    critical_services = ("postgres", "redis")
    if any(services[name]["status"] == "fail" for name in critical_services):
        return "fail"
    if services["smtp"]["status"] == "fail":
        return "degraded"

    return "ok"


@router.get("/health/liveness")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/readiness")
async def readiness() -> dict[str, object]:
    postgres_status = await _probe_postgres()
    redis_status = await _probe_redis()
    smtp_status = await _probe_smtp()
    services = {
        "postgres": postgres_status,
        "redis": redis_status,
        "smtp": smtp_status,
    }
    return {
        "status": _resolve_readiness_status(services),
        "services": services,
    }


@router.get("/health")
async def health() -> dict[str, object]:
    # 兼容旧入口：沿用 /health 路径并返回 readiness 语义。
    return await readiness()
