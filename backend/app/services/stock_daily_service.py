import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar


DailyRowT = TypeVar("DailyRowT")
ReadDailyCacheFn = Callable[[str], Awaitable[list[DailyRowT] | None]]
WriteDailyCacheFn = Callable[[str, list[DailyRowT], int], Awaitable[None]]
LoadDailyRowsFn = Callable[[], Awaitable[list[DailyRowT]]]
FetchDailyRowsFn = Callable[[], Awaitable[list[DailyRowT]]]
GetLockFn = Callable[[str], Awaitable[asyncio.Lock]]


async def get_stock_daily_rows(
    *,
    cache_key: str,
    cache_ttl_seconds: int,
    period: str,
    limit: int,
    trade_date: str | None,
    read_cache: ReadDailyCacheFn[DailyRowT],
    write_cache: WriteDailyCacheFn[DailyRowT],
    load_kline_from_db: LoadDailyRowsFn[DailyRowT],
    load_daily_snapshot_fallback: LoadDailyRowsFn[DailyRowT],
    fetch_remote_and_persist: FetchDailyRowsFn[DailyRowT],
    get_singleflight_lock: GetLockFn,
) -> list[DailyRowT]:
    cached_rows = await read_cache(cache_key)
    if cached_rows is not None:
        return cached_rows

    db_rows = await load_kline_from_db()
    # 关键业务分支：按请求语义判断 DB 是否“足够”——
    # 指定 trade_date 时只要有结果即可，否则需要达到 limit 条数。
    has_enough_db_rows = len(db_rows) > 0 if trade_date else len(db_rows) >= limit
    if has_enough_db_rows:
        try:
            await write_cache(cache_key, db_rows, cache_ttl_seconds)
        except Exception:
            pass
        return db_rows

    lock = await get_singleflight_lock(cache_key)
    async with lock:
        cached_rows_after_lock = await read_cache(cache_key)
        if cached_rows_after_lock is not None:
            return cached_rows_after_lock

        try:
            # 关键状态流转：只有在缓存与数据库都不足时才回源，
            # 并在成功后立即写缓存，避免同参数请求短时间内重复打三方。
            remote_rows = await fetch_remote_and_persist()
            try:
                await write_cache(cache_key, remote_rows, cache_ttl_seconds)
            except Exception:
                pass
            return remote_rows
        except Exception:
            # 降级分支：三方失败时优先回退 DB；若 DB 也空且是日线请求，
            # 再退化到 daily snapshots，保证详情页仍有可展示数据。
            if db_rows:
                return db_rows
            if period != "daily":
                return []
            return await load_daily_snapshot_fallback()
