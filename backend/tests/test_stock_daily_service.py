import asyncio
from datetime import date

from app.schemas.stocks import StockDailySnapshotResponse
from app.services.stock_daily_service import get_stock_daily_rows


class MemoryDailyCache:
    def __init__(self) -> None:
        self.data: dict[str, list[StockDailySnapshotResponse]] = {}
        self.writes: list[tuple[str, list[StockDailySnapshotResponse], int]] = []

    async def read(self, key: str) -> list[StockDailySnapshotResponse] | None:
        return self.data.get(key)

    async def write(
        self,
        key: str,
        rows: list[StockDailySnapshotResponse],
        ttl_seconds: int,
    ) -> None:
        self.writes.append((key, rows, ttl_seconds))
        self.data[key] = rows


def _daily_row(
    *, ts_code: str, trade_date: date, close: float
) -> StockDailySnapshotResponse:
    return StockDailySnapshotResponse(
        ts_code=ts_code,
        trade_date=trade_date,
        open=None,
        high=None,
        low=None,
        close=close,
        pre_close=None,
        change=None,
        pct_chg=None,
        vol=None,
        amount=None,
        turnover_rate=None,
        volume_ratio=None,
        pe=None,
        pb=None,
        total_mv=None,
        circ_mv=None,
    )


def test_daily_service_prefers_cache_hit() -> None:
    async def _run() -> None:
        cache = MemoryDailyCache()
        expected = [
            _daily_row(ts_code="000001.SZ", trade_date=date(2026, 3, 3), close=11.1)
        ]
        cache.data["daily:1"] = expected

        db_calls = 0
        remote_calls = 0

        async def load_db() -> list[StockDailySnapshotResponse]:
            nonlocal db_calls
            db_calls += 1
            return []

        async def load_daily_fallback() -> list[StockDailySnapshotResponse]:
            return []

        async def fetch_remote() -> list[StockDailySnapshotResponse]:
            nonlocal remote_calls
            remote_calls += 1
            return []

        async def get_lock(_cache_key: str) -> asyncio.Lock:
            return asyncio.Lock()

        result = await get_stock_daily_rows(
            cache_key="daily:1",
            cache_ttl_seconds=600,
            period="daily",
            limit=60,
            trade_date=None,
            read_cache=cache.read,
            write_cache=cache.write,
            load_kline_from_db=load_db,
            load_daily_snapshot_fallback=load_daily_fallback,
            fetch_remote_and_persist=fetch_remote,
            get_singleflight_lock=get_lock,
        )

        assert result == expected
        assert db_calls == 0
        assert remote_calls == 0

    asyncio.run(_run())


def test_daily_service_returns_db_when_enough() -> None:
    async def _run() -> None:
        cache = MemoryDailyCache()
        db_rows = [
            _daily_row(ts_code="000001.SZ", trade_date=date(2026, 3, 3), close=11.1)
        ]
        remote_calls = 0

        async def load_db() -> list[StockDailySnapshotResponse]:
            return db_rows

        async def load_daily_fallback() -> list[StockDailySnapshotResponse]:
            return []

        async def fetch_remote() -> list[StockDailySnapshotResponse]:
            nonlocal remote_calls
            remote_calls += 1
            return []

        async def get_lock(_cache_key: str) -> asyncio.Lock:
            return asyncio.Lock()

        result = await get_stock_daily_rows(
            cache_key="daily:2",
            cache_ttl_seconds=600,
            period="daily",
            limit=1,
            trade_date=None,
            read_cache=cache.read,
            write_cache=cache.write,
            load_kline_from_db=load_db,
            load_daily_snapshot_fallback=load_daily_fallback,
            fetch_remote_and_persist=fetch_remote,
            get_singleflight_lock=get_lock,
        )

        assert result == db_rows
        assert remote_calls == 0
        assert len(cache.writes) == 1

    asyncio.run(_run())


def test_daily_service_fetches_remote_when_db_not_enough() -> None:
    async def _run() -> None:
        cache = MemoryDailyCache()
        remote_rows = [
            _daily_row(ts_code="000001.SZ", trade_date=date(2026, 3, 4), close=11.5)
        ]
        remote_calls = 0

        async def load_db() -> list[StockDailySnapshotResponse]:
            return []

        async def load_daily_fallback() -> list[StockDailySnapshotResponse]:
            return []

        async def fetch_remote() -> list[StockDailySnapshotResponse]:
            nonlocal remote_calls
            remote_calls += 1
            return remote_rows

        lock_map: dict[str, asyncio.Lock] = {}

        async def get_lock(cache_key: str) -> asyncio.Lock:
            lock_map.setdefault(cache_key, asyncio.Lock())
            return lock_map[cache_key]

        result = await get_stock_daily_rows(
            cache_key="daily:3",
            cache_ttl_seconds=600,
            period="daily",
            limit=60,
            trade_date=None,
            read_cache=cache.read,
            write_cache=cache.write,
            load_kline_from_db=load_db,
            load_daily_snapshot_fallback=load_daily_fallback,
            fetch_remote_and_persist=fetch_remote,
            get_singleflight_lock=get_lock,
        )

        assert result == remote_rows
        assert remote_calls == 1
        assert len(cache.writes) == 1

    asyncio.run(_run())


def test_daily_service_falls_back_to_db_on_remote_error() -> None:
    async def _run() -> None:
        cache = MemoryDailyCache()
        db_rows = [
            _daily_row(ts_code="000001.SZ", trade_date=date(2026, 3, 3), close=11.1)
        ]

        async def load_db() -> list[StockDailySnapshotResponse]:
            return db_rows

        async def load_daily_fallback() -> list[StockDailySnapshotResponse]:
            return []

        async def fetch_remote() -> list[StockDailySnapshotResponse]:
            raise RuntimeError("remote failed")

        async def get_lock(_cache_key: str) -> asyncio.Lock:
            return asyncio.Lock()

        result = await get_stock_daily_rows(
            cache_key="daily:4",
            cache_ttl_seconds=600,
            period="daily",
            limit=60,
            trade_date=None,
            read_cache=cache.read,
            write_cache=cache.write,
            load_kline_from_db=load_db,
            load_daily_snapshot_fallback=load_daily_fallback,
            fetch_remote_and_persist=fetch_remote,
            get_singleflight_lock=get_lock,
        )

        assert result == db_rows

    asyncio.run(_run())


def test_daily_service_uses_snapshot_fallback_for_daily_period() -> None:
    async def _run() -> None:
        cache = MemoryDailyCache()
        fallback_rows = [
            _daily_row(ts_code="000001.SZ", trade_date=date(2026, 3, 2), close=10.9)
        ]
        snapshot_calls = 0

        async def load_db() -> list[StockDailySnapshotResponse]:
            return []

        async def load_daily_fallback() -> list[StockDailySnapshotResponse]:
            nonlocal snapshot_calls
            snapshot_calls += 1
            return fallback_rows

        async def fetch_remote() -> list[StockDailySnapshotResponse]:
            raise RuntimeError("remote failed")

        async def get_lock(_cache_key: str) -> asyncio.Lock:
            return asyncio.Lock()

        result = await get_stock_daily_rows(
            cache_key="daily:5",
            cache_ttl_seconds=600,
            period="daily",
            limit=60,
            trade_date=None,
            read_cache=cache.read,
            write_cache=cache.write,
            load_kline_from_db=load_db,
            load_daily_snapshot_fallback=load_daily_fallback,
            fetch_remote_and_persist=fetch_remote,
            get_singleflight_lock=get_lock,
        )

        assert result == fallback_rows
        assert snapshot_calls == 1

    asyncio.run(_run())


def test_daily_service_returns_empty_for_non_daily_period_on_remote_error() -> None:
    async def _run() -> None:
        cache = MemoryDailyCache()
        snapshot_calls = 0

        async def load_db() -> list[StockDailySnapshotResponse]:
            return []

        async def load_daily_fallback() -> list[StockDailySnapshotResponse]:
            nonlocal snapshot_calls
            snapshot_calls += 1
            return []

        async def fetch_remote() -> list[StockDailySnapshotResponse]:
            raise RuntimeError("remote failed")

        async def get_lock(_cache_key: str) -> asyncio.Lock:
            return asyncio.Lock()

        result = await get_stock_daily_rows(
            cache_key="daily:6",
            cache_ttl_seconds=600,
            period="weekly",
            limit=60,
            trade_date=None,
            read_cache=cache.read,
            write_cache=cache.write,
            load_kline_from_db=load_db,
            load_daily_snapshot_fallback=load_daily_fallback,
            fetch_remote_and_persist=fetch_remote,
            get_singleflight_lock=get_lock,
        )

        assert result == []
        assert snapshot_calls == 0

    asyncio.run(_run())
