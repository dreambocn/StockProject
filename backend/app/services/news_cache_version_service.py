from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.cache.redis import get_redis_client
from app.core.logging import get_logger


RedisClientGetter = Callable[[], Any]
LOGGER = get_logger(__name__)

NEWS_SCOPE_HOT = "hot"
NEWS_SCOPE_POLICY = "policy"
NEWS_SCOPE_STOCK = "stock"


def _log_cache_warning(*, cache_key: str, operation: str, error: Exception) -> None:
    LOGGER.warning(
        "缓存降级：event=news_cache_version_failed cache_key=%s operation=%s error_type=%s",
        cache_key,
        operation,
        type(error).__name__,
    )


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def format_news_cache_version(*, fetched_at: datetime | None, now: datetime | None = None) -> str:
    # 关键流程：版本号与抓取批次保持同一时间锚，避免随机版本导致排障不可追溯。
    resolved_time = fetched_at or now or datetime.now(UTC)
    normalized_time = _normalize_datetime(resolved_time)
    return normalized_time.strftime("%Y%m%d%H%M%S")


def build_news_cache_version_key(
    *,
    scope: str,
    cache_variant: str,
    ts_code: str | None = None,
) -> str:
    normalized_scope = scope.strip().lower()
    normalized_variant = cache_variant.strip().lower()
    if not normalized_variant:
        raise ValueError("cache_variant must not be empty")

    if normalized_scope == NEWS_SCOPE_HOT:
        return f"news:hot:{normalized_variant}:version"
    if normalized_scope == NEWS_SCOPE_POLICY:
        return f"news:policy:{normalized_variant}:version"
    if normalized_scope == NEWS_SCOPE_STOCK:
        normalized_ts_code = (ts_code or "").strip().upper()
        if not normalized_ts_code:
            raise ValueError("ts_code is required when scope=stock")
        return f"stocks:news:{normalized_ts_code}:{normalized_variant}:version"
    raise ValueError(f"unsupported news scope: {scope}")


def build_versioned_news_cache_key(*, base_cache_key: str, version: str) -> str:
    normalized_base_key = base_cache_key.strip()
    normalized_version = version.strip()
    if not normalized_base_key:
        raise ValueError("base_cache_key must not be empty")
    if not normalized_version:
        raise ValueError("version must not be empty")
    return f"{normalized_base_key}:v:{normalized_version}"


def resolve_news_cache_data_key(*, base_cache_key: str, version: str | None) -> str:
    normalized_version = (version or "").strip()
    if not normalized_version:
        return base_cache_key
    return build_versioned_news_cache_key(
        base_cache_key=base_cache_key,
        version=normalized_version,
    )


def should_try_legacy_news_cache(
    *,
    version: str | None,
    legacy_fallback_enabled: bool,
) -> bool:
    if not legacy_fallback_enabled:
        return False
    return not (version or "").strip()


async def read_news_cache_version(
    *,
    version_key: str,
    redis_client_getter: RedisClientGetter | None = None,
) -> str | None:
    resolved_getter = redis_client_getter or get_redis_client
    try:
        raw_value = await resolved_getter().get(version_key)
    except Exception as exc:
        _log_cache_warning(cache_key=version_key, operation="read_version", error=exc)
        return None

    if raw_value is None:
        return None

    if isinstance(raw_value, bytes):
        normalized_value = raw_value.decode("utf-8", errors="ignore").strip()
    else:
        normalized_value = str(raw_value).strip()

    return normalized_value or None


async def write_news_cache_version(
    *,
    version_key: str,
    version: str,
    redis_client_getter: RedisClientGetter | None = None,
) -> None:
    normalized_version = version.strip()
    if not normalized_version:
        raise ValueError("version must not be empty")

    resolved_getter = redis_client_getter or get_redis_client
    try:
        await resolved_getter().set(version_key, normalized_version)
    except Exception as exc:
        _log_cache_warning(cache_key=version_key, operation="write_version", error=exc)
