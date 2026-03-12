import asyncio

from app.services.stock_reference_data_service import (
    get_adj_factor_rows,
    get_trade_calendar_rows,
)


class MemoryCache:
    def __init__(self) -> None:
        self.data: dict[str, list[str]] = {}
        self.writes: list[tuple[str, list[str], int]] = []

    async def read(self, key: str) -> list[str] | None:
        return self.data.get(key)

    async def write(self, key: str, rows: list[str], ttl: int) -> None:
        self.writes.append((key, rows, ttl))
        self.data[key] = rows


def test_trade_calendar_service_prefers_cache_then_db_then_remote() -> None:
    async def _run() -> None:
        lock_map: dict[str, asyncio.Lock] = {}

        async def get_lock(cache_key: str) -> asyncio.Lock:
            lock_map.setdefault(cache_key, asyncio.Lock())
            return lock_map[cache_key]

        cache = MemoryCache()
        cache.data["trade-cal:1"] = ["cached"]

        remote_called = 0

        async def load_db() -> list[str]:
            return ["db"]

        async def fetch_remote() -> list[str]:
            nonlocal remote_called
            remote_called += 1
            return ["remote"]

        cache_result = await get_trade_calendar_rows(
            cache_key="trade-cal:1",
            cache_ttl_seconds=60,
            read_cache=cache.read,
            write_cache=cache.write,
            load_from_db=load_db,
            fetch_from_remote_and_persist=fetch_remote,
            get_singleflight_lock=get_lock,
        )
        assert cache_result == ["cached"]
        assert remote_called == 0

        cache.data.clear()
        db_result = await get_trade_calendar_rows(
            cache_key="trade-cal:1",
            cache_ttl_seconds=60,
            read_cache=cache.read,
            write_cache=cache.write,
            load_from_db=load_db,
            fetch_from_remote_and_persist=fetch_remote,
            get_singleflight_lock=get_lock,
        )
        assert db_result == ["db"]
        assert remote_called == 0

        cache.data.clear()

        async def load_db_empty() -> list[str]:
            return []

        remote_result = await get_trade_calendar_rows(
            cache_key="trade-cal:1",
            cache_ttl_seconds=60,
            read_cache=cache.read,
            write_cache=cache.write,
            load_from_db=load_db_empty,
            fetch_from_remote_and_persist=fetch_remote,
            get_singleflight_lock=get_lock,
        )
        assert remote_result == ["remote"]
        assert remote_called == 1

    asyncio.run(_run())


def test_trade_calendar_service_falls_back_to_db_on_remote_error() -> None:
    async def _run() -> None:
        async def get_lock(_cache_key: str) -> asyncio.Lock:
            return asyncio.Lock()

        cache = MemoryCache()

        async def load_db() -> list[str]:
            return ["db"]

        async def fetch_remote() -> list[str]:
            raise RuntimeError("remote failed")

        result = await get_trade_calendar_rows(
            cache_key="trade-cal:2",
            cache_ttl_seconds=60,
            read_cache=cache.read,
            write_cache=cache.write,
            load_from_db=load_db,
            fetch_from_remote_and_persist=fetch_remote,
            get_singleflight_lock=get_lock,
        )

        assert result == ["db"]

    asyncio.run(_run())


def test_adj_factor_service_uses_db_threshold_before_remote() -> None:
    async def _run() -> None:
        cache = MemoryCache()
        lock_map: dict[str, asyncio.Lock] = {}

        async def get_lock(cache_key: str) -> asyncio.Lock:
            lock_map.setdefault(cache_key, asyncio.Lock())
            return lock_map[cache_key]

        remote_called = 0

        async def load_db_enough() -> list[str]:
            return ["db"]

        async def fetch_remote() -> list[str]:
            nonlocal remote_called
            remote_called += 1
            return ["remote"]

        result_enough = await get_adj_factor_rows(
            cache_key="adj:1",
            cache_ttl_seconds=120,
            read_cache=cache.read,
            write_cache=cache.write,
            load_from_db=load_db_enough,
            fetch_from_remote_and_load=fetch_remote,
            has_enough_db_rows=lambda rows: len(rows) >= 1,
            get_singleflight_lock=get_lock,
        )
        assert result_enough == ["db"]
        assert remote_called == 0

        cache.data.clear()

        async def load_db_not_enough() -> list[str]:
            return []

        result_remote = await get_adj_factor_rows(
            cache_key="adj:1",
            cache_ttl_seconds=120,
            read_cache=cache.read,
            write_cache=cache.write,
            load_from_db=load_db_not_enough,
            fetch_from_remote_and_load=fetch_remote,
            has_enough_db_rows=lambda rows: len(rows) >= 1,
            get_singleflight_lock=get_lock,
        )
        assert result_remote == ["remote"]
        assert remote_called == 1

    asyncio.run(_run())


def test_adj_factor_service_falls_back_to_db_on_remote_error() -> None:
    async def _run() -> None:
        cache = MemoryCache()

        async def get_lock(_cache_key: str) -> asyncio.Lock:
            return asyncio.Lock()

        async def load_db() -> list[str]:
            return ["db"]

        async def fetch_remote() -> list[str]:
            raise RuntimeError("remote failed")

        result = await get_adj_factor_rows(
            cache_key="adj:2",
            cache_ttl_seconds=120,
            read_cache=cache.read,
            write_cache=cache.write,
            load_from_db=load_db,
            fetch_from_remote_and_load=fetch_remote,
            has_enough_db_rows=lambda _rows: False,
            get_singleflight_lock=get_lock,
        )

        assert result == ["db"]

    asyncio.run(_run())
