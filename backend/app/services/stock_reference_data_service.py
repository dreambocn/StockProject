import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.core.logging import get_logger


RowT = TypeVar("RowT")
ReadCacheFn = Callable[[str], Awaitable[list[RowT] | None]]
WriteCacheFn = Callable[[str, list[RowT], int], Awaitable[None]]
LoadRowsFn = Callable[[], Awaitable[list[RowT]]]
FetchRowsFn = Callable[[], Awaitable[list[RowT]]]
GetLockFn = Callable[[str], Awaitable[asyncio.Lock]]
LOGGER = get_logger(__name__)


def _log_cache_warning(*, cache_key: str, operation: str, error: Exception) -> None:
    LOGGER.warning(
        "缓存降级：event=stock_reference_cache_failed cache_key=%s operation=%s error_type=%s",
        cache_key,
        operation,
        type(error).__name__,
    )


async def get_trade_calendar_rows(
    *,
    cache_key: str,
    cache_ttl_seconds: int,
    read_cache: ReadCacheFn[RowT],
    write_cache: WriteCacheFn[RowT],
    load_from_db: LoadRowsFn[RowT],
    fetch_from_remote_and_persist: FetchRowsFn[RowT],
    get_singleflight_lock: GetLockFn,
) -> list[RowT]:
    cached_rows = await read_cache(cache_key)
    if cached_rows is not None:
        return cached_rows

    db_rows = await load_from_db()
    if db_rows:
        try:
            await write_cache(cache_key, db_rows, cache_ttl_seconds)
        except Exception as exc:
            _log_cache_warning(
                cache_key=cache_key,
                operation="write_trade_cal_cache_from_db",
                error=exc,
            )
            pass
        return db_rows

    # 单飞锁避免并发请求同时回源，降低三方接口压力。
    lock = await get_singleflight_lock(cache_key)
    async with lock:
        try:
            # 关键流程：仅在本地缓存和数据库都未命中时才回源，
            # 回源成功后立即写缓存，后续请求优先命中本地路径。
            remote_rows = await fetch_from_remote_and_persist()
            try:
                await write_cache(cache_key, remote_rows, cache_ttl_seconds)
            except Exception as exc:
                _log_cache_warning(
                    cache_key=cache_key,
                    operation="write_trade_cal_cache_from_remote",
                    error=exc,
                )
                pass
            return remote_rows
        except Exception:
            return db_rows


async def get_adj_factor_rows(
    *,
    cache_key: str,
    cache_ttl_seconds: int,
    read_cache: ReadCacheFn[RowT],
    write_cache: WriteCacheFn[RowT],
    load_from_db: LoadRowsFn[RowT],
    fetch_from_remote_and_load: FetchRowsFn[RowT],
    has_enough_db_rows: Callable[[list[RowT]], bool],
    get_singleflight_lock: GetLockFn,
) -> list[RowT]:
    cached_rows = await read_cache(cache_key)
    if cached_rows is not None:
        return cached_rows

    db_rows = await load_from_db()
    if has_enough_db_rows(db_rows):
        try:
            await write_cache(cache_key, db_rows, cache_ttl_seconds)
        except Exception as exc:
            _log_cache_warning(
                cache_key=cache_key,
                operation="write_adj_factor_cache_from_db",
                error=exc,
            )
            pass
        return db_rows

    # 关键边界：复权因子回源耗时高，使用单飞锁避免并发重复拉取。
    lock = await get_singleflight_lock(cache_key)
    async with lock:
        try:
            # 关键流程：当数据库样本不足时回源补齐并写缓存；
            # 失败时回退数据库，保证接口始终可用。
            remote_rows = await fetch_from_remote_and_load()
            try:
                await write_cache(cache_key, remote_rows, cache_ttl_seconds)
            except Exception as exc:
                _log_cache_warning(
                    cache_key=cache_key,
                    operation="write_adj_factor_cache_from_remote",
                    error=exc,
                )
                pass
            return remote_rows
        except Exception:
            return db_rows
