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
_singleflight_locks: dict[str, "_SingleflightLockState"] = {}
LOGGER = get_logger(__name__)


class _SingleflightLockState:
    def __init__(self, cache_key: str) -> None:
        self.cache_key = cache_key
        self._lock = asyncio.Lock()
        self._user_count = 0

    async def __aenter__(self) -> "_SingleflightLockState":
        async with _singleflight_lock_guard:
            self._user_count += 1
        await self._lock.acquire()
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        self._lock.release()
        async with _singleflight_lock_guard:
            self._user_count -= 1
            if self._user_count == 0 and _singleflight_locks.get(self.cache_key) is self:
                # 锁空闲后立即回收，避免带参数缓存键长期驻留进程内存。
                _singleflight_locks.pop(self.cache_key, None)


def _log_cache_warning(*, cache_key: str, operation: str, error: Exception) -> None:
    LOGGER.warning(
        "缓存降级：event=stock_cache_failed cache_key=%s operation=%s error_type=%s",
        cache_key,
        operation,
        type(error).__name__,
    )


class _SingleflightLockContext:
    def __init__(self, cache_key: str) -> None:
        self.cache_key = cache_key
        self._state: _SingleflightLockState | None = None

    async def __aenter__(self) -> _SingleflightLockState:
        state = await get_singleflight_lock(self.cache_key)
        self._state = state
        return await state.__aenter__()

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        if self._state is not None:
            await self._state.__aexit__(exc_type, exc, traceback)


def singleflight_lock(cache_key: str) -> _SingleflightLockContext:
    # 单飞锁避免同一 cache_key 并发回源，保护三方配额与数据库压力。
    return _SingleflightLockContext(cache_key)


async def get_singleflight_lock(cache_key: str) -> _SingleflightLockState:
    async with _singleflight_lock_guard:
        state = _singleflight_locks.get(cache_key)
        if state is None:
            state = _SingleflightLockState(cache_key)
            _singleflight_locks[cache_key] = state
        return state


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
        # 缓存损坏时可选择清理，避免后续重复解析失败。
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
        # 数据结构不匹配时直接降级为未命中，交由上层回源。
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
        # ensure_ascii=False 保留中文字段，避免二次解码时出现转义噪声。
        await resolved_getter().set(
            cache_key,
            json.dumps(cache_payload, ensure_ascii=False),
            ex=ttl_seconds,
        )
    except Exception as exc:
        _log_cache_warning(cache_key=cache_key, operation="write_cache", error=exc)
        return
