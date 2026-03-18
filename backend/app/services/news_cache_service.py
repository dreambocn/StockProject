import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import TypeVar

from pydantic import BaseModel


ModelT = TypeVar("ModelT", bound=BaseModel)
ReadNewsCacheFn = Callable[[str], Awaitable[list[ModelT] | None]]
WriteNewsCacheFn = Callable[[str, list[ModelT], int], Awaitable[None]]
LoadNewsRowsFn = Callable[[], Awaitable[list[ModelT]]]
ReadLatestFetchAtFn = Callable[[], Awaitable[datetime | None]]
FetchNewsRowsFn = Callable[[], Awaitable[list[ModelT]]]
GetLockFn = Callable[[str], Awaitable[asyncio.Lock]]


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def get_news_rows(
    *,
    cache_key: str,
    cache_ttl_seconds: int,
    refresh_window_seconds: int,
    now: datetime | None,
    read_cache: ReadNewsCacheFn[ModelT],
    write_cache: WriteNewsCacheFn[ModelT],
    load_from_db: LoadNewsRowsFn[ModelT],
    get_last_fetch_at: ReadLatestFetchAtFn,
    fetch_remote_and_persist: FetchNewsRowsFn[ModelT],
    get_singleflight_lock: GetLockFn,
) -> list[ModelT]:
    cached_rows = await read_cache(cache_key)
    if cached_rows is not None:
        return cached_rows

    resolved_now = now or datetime.now(UTC)
    db_rows = await load_from_db()
    last_fetch_at = await get_last_fetch_at()
    if db_rows and last_fetch_at is not None:
        last_fetch_at = _normalize_datetime(last_fetch_at)
        # 关键流程：只要数据库中的这批新闻在刷新窗口内，就直接返回数据库并回写缓存，
        # 避免热点页/详情页频繁触发三方资讯抓取，稳定首屏时延。
        if resolved_now - last_fetch_at <= timedelta(seconds=refresh_window_seconds):
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

        db_rows_after_lock = await load_from_db()
        last_fetch_at_after_lock = await get_last_fetch_at()
        if db_rows_after_lock and last_fetch_at_after_lock is not None:
            last_fetch_at_after_lock = _normalize_datetime(last_fetch_at_after_lock)
            if resolved_now - last_fetch_at_after_lock <= timedelta(
                seconds=refresh_window_seconds
            ):
                try:
                    await write_cache(cache_key, db_rows_after_lock, cache_ttl_seconds)
                except Exception:
                    pass
                return db_rows_after_lock

        try:
            remote_rows = await fetch_remote_and_persist()
            try:
                await write_cache(cache_key, remote_rows, cache_ttl_seconds)
            except Exception:
                pass
            return remote_rows
        except Exception:
            # 关键降级：回源失败时优先使用数据库旧新闻，保证 AI 分析与页面阅读至少有最近一批可用数据。
            if db_rows_after_lock:
                return db_rows_after_lock
            raise
