import asyncio
import json
from collections.abc import Callable
from typing import Any
from typing import TypeVar

from pydantic import BaseModel

from app.cache.redis import get_redis_client
from app.core.logging import get_logger


ModelT = TypeVar("ModelT", bound=BaseModel)
RedisClientGetter = Callable[[], Any]

_singleflight_lock_guard = asyncio.Lock()
_singleflight_locks: dict[str, asyncio.Lock] = {}
LOGGER = get_logger(__name__)


def _log_cache_warning(*, cache_key: str, operation: str, error: Exception) -> None:
    LOGGER.warning(
        "缓存降级：event=stock_cache_failed cache_key=%s operation=%s error_type=%s",
        cache_key,
        operation,
        type(error).__name__,
    )


async def get_singleflight_lock(cache_key: str) -> asyncio.Lock:
    async with _singleflight_lock_guard:
        existing_lock = _singleflight_locks.get(cache_key)
        if existing_lock is None:
            existing_lock = asyncio.Lock()
            _singleflight_locks[cache_key] = existing_lock
        return existing_lock


async def read_cached_model_rows(
    cache_key: str,
    model_type: type[ModelT],
    *,
    delete_on_decode_error: bool = False,
    redis_client_getter: RedisClientGetter | None = None,
) -> list[ModelT] | None:
    resolved_getter = redis_client_getter or get_redis_client

    try:
        raw_payload = await resolved_getter().get(cache_key)
    except Exception as exc:
        _log_cache_warning(cache_key=cache_key, operation="read_cache", error=exc)
        return None

    if raw_payload is None:
        return None

    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        if delete_on_decode_error:
            try:
                await resolved_getter().delete(cache_key)
            except Exception as exc:
                _log_cache_warning(
                    cache_key=cache_key,
                    operation="delete_corrupted_cache",
                    error=exc,
                )
                pass
        return None

    try:
        return [model_type.model_validate(item) for item in payload]
    except Exception as exc:
        _log_cache_warning(
            cache_key=cache_key,
            operation="decode_model_rows",
            error=exc,
        )
        return None


async def write_cached_model_rows(
    cache_key: str,
    rows: list[BaseModel],
    *,
    ttl_seconds: int,
    redis_client_getter: RedisClientGetter | None = None,
) -> None:
    resolved_getter = redis_client_getter or get_redis_client
    cache_payload = [item.model_dump(mode="json") for item in rows]
    try:
        await resolved_getter().set(
            cache_key,
            json.dumps(cache_payload, ensure_ascii=False),
            ex=ttl_seconds,
        )
    except Exception as exc:
        _log_cache_warning(cache_key=cache_key, operation="write_cache", error=exc)
        return
