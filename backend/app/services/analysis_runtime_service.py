import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.cache.redis import get_redis_client
from app.core.logging import get_logger


class AnalysisSessionEventBus:
    def __init__(self) -> None:
        self._channels: dict[str, set[asyncio.Queue[tuple[str, dict[str, object]]]]] = {}
        self._guard = asyncio.Lock()

    async def publish(
        self, session_id: str, event: str, payload: dict[str, object]
    ) -> None:
        async with self._guard:
            subscribers = list(self._channels.get(session_id, set()))
        for queue in subscribers:
            queue.put_nowait((event, payload))

    @asynccontextmanager
    async def subscribe(
        self, session_id: str
    ) -> AsyncIterator[asyncio.Queue[tuple[str, dict[str, object]]]]:
        queue: asyncio.Queue[tuple[str, dict[str, object]]] = asyncio.Queue()
        async with self._guard:
            self._channels.setdefault(session_id, set()).add(queue)
        try:
            yield queue
        finally:
            async with self._guard:
                subscribers = self._channels.get(session_id)
                if subscribers is not None:
                    subscribers.discard(queue)
                    if not subscribers:
                        self._channels.pop(session_id, None)


class AnalysisSessionLockRegistry:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    async def get_lock(self, analysis_key: str) -> asyncio.Lock:
        async with self._guard:
            if analysis_key not in self._locks:
                self._locks[analysis_key] = asyncio.Lock()
            return self._locks[analysis_key]


event_bus = AnalysisSessionEventBus()
lock_registry = AnalysisSessionLockRegistry()
LOGGER = get_logger(__name__)


def _active_session_cache_key(analysis_key: str) -> str:
    return f"analysis:active:{analysis_key}"


def _fresh_report_cache_key(analysis_key: str) -> str:
    return f"analysis:fresh:{analysis_key}"


def _log_cache_warning(
    *,
    event: str,
    analysis_key: str,
    operation: str,
    error: Exception,
) -> None:
    LOGGER.warning(
        "缓存降级：event=%s analysis_key=%s operation=%s error_type=%s",
        event,
        analysis_key,
        operation,
        type(error).__name__,
    )


async def get_analysis_lock(analysis_key: str) -> asyncio.Lock:
    return await lock_registry.get_lock(analysis_key)


async def cache_active_session_id(
    analysis_key: str, session_id: str, ttl_seconds: int
) -> None:
    try:
        await get_redis_client().set(
            _active_session_cache_key(analysis_key),
            session_id,
            ex=ttl_seconds,
        )
    except Exception as exc:
        _log_cache_warning(
            event="analysis_runtime_cache_failed",
            analysis_key=analysis_key,
            operation="set_active_session_id",
            error=exc,
        )
        return


async def get_cached_active_session_id(analysis_key: str) -> str | None:
    try:
        value = await get_redis_client().get(_active_session_cache_key(analysis_key))
    except Exception as exc:
        _log_cache_warning(
            event="analysis_runtime_cache_failed",
            analysis_key=analysis_key,
            operation="get_active_session_id",
            error=exc,
        )
        return None
    return str(value) if value else None


async def clear_cached_active_session_id(
    analysis_key: str, session_id: str | None = None
) -> None:
    try:
        key = _active_session_cache_key(analysis_key)
        if session_id is not None:
            cached = await get_redis_client().get(key)
            if cached and str(cached) != session_id:
                return
        await get_redis_client().delete(key)
    except Exception as exc:
        _log_cache_warning(
            event="analysis_runtime_cache_failed",
            analysis_key=analysis_key,
            operation="clear_active_session_id",
            error=exc,
        )
        return


async def cache_fresh_report_id(
    analysis_key: str, report_id: str, ttl_seconds: int
) -> None:
    try:
        await get_redis_client().set(
            _fresh_report_cache_key(analysis_key),
            report_id,
            ex=ttl_seconds,
        )
    except Exception as exc:
        _log_cache_warning(
            event="analysis_runtime_cache_failed",
            analysis_key=analysis_key,
            operation="set_fresh_report_id",
            error=exc,
        )
        return


async def get_cached_fresh_report_id(analysis_key: str) -> str | None:
    try:
        value = await get_redis_client().get(_fresh_report_cache_key(analysis_key))
    except Exception as exc:
        _log_cache_warning(
            event="analysis_runtime_cache_failed",
            analysis_key=analysis_key,
            operation="get_fresh_report_id",
            error=exc,
        )
        return None
    return str(value) if value else None
