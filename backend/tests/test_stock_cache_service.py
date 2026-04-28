import asyncio
import json

from app.schemas.stocks import StockDailySnapshotResponse
from app.services.stock_cache_service import (
    _singleflight_locks,
    get_singleflight_lock,
    read_cached_model_rows,
    singleflight_lock,
    write_cached_model_rows,
)


class WarningCollector:
    def __init__(self) -> None:
        self.records: list[tuple[str, tuple[object, ...]]] = []

    def warning(self, msg: str, *args: object) -> None:
        self.records.append((msg, args))


class FakeRedisClient:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int | None]] = []
        self.delete_calls: list[str] = []

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.set_calls.append((key, value, ex))
        self._store[key] = value
        return True

    async def delete(self, key: str) -> int:
        self.delete_calls.append(key)
        if key in self._store:
            del self._store[key]
            return 1
        return 0


def test_singleflight_lock_reused_for_same_key() -> None:
    async def _run() -> None:
        lock_a = await get_singleflight_lock("stocks:daily:a")
        lock_b = await get_singleflight_lock("stocks:daily:a")
        lock_c = await get_singleflight_lock("stocks:daily:b")

        assert lock_a is lock_b
        assert lock_a is not lock_c

    asyncio.run(_run())


def test_singleflight_lock_context_cleans_idle_key() -> None:
    async def _run() -> None:
        _singleflight_locks.clear()

        async with singleflight_lock("stocks:daily:cleanup"):
            assert "stocks:daily:cleanup" in _singleflight_locks

        assert "stocks:daily:cleanup" not in _singleflight_locks

    asyncio.run(_run())


def test_singleflight_lock_context_serializes_same_key_and_cleans_after_waiters() -> None:
    async def _run() -> None:
        _singleflight_locks.clear()
        active_count = 0
        max_active_count = 0

        async def run_locked() -> None:
            nonlocal active_count, max_active_count
            async with singleflight_lock("stocks:daily:shared"):
                active_count += 1
                max_active_count = max(max_active_count, active_count)
                await asyncio.sleep(0.01)
                active_count -= 1

        await asyncio.gather(run_locked(), run_locked(), run_locked())

        assert max_active_count == 1
        assert "stocks:daily:shared" not in _singleflight_locks

    asyncio.run(_run())


def test_read_cached_model_rows_returns_valid_payload(monkeypatch) -> None:
    async def _run() -> None:
        fake_redis = FakeRedisClient()
        fake_redis._store["daily:ok"] = json.dumps(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "2026-03-03",
                    "open": 11.0,
                    "high": 11.2,
                    "low": 10.8,
                    "close": 11.1,
                    "pre_close": 10.95,
                    "change": 0.15,
                    "pct_chg": 1.37,
                    "vol": 123456,
                    "amount": 789012,
                    "turnover_rate": None,
                    "volume_ratio": None,
                    "pe": None,
                    "pb": None,
                    "total_mv": None,
                    "circ_mv": None,
                }
            ],
            ensure_ascii=False,
        )
        monkeypatch.setattr(
            "app.services.stock_cache_service.get_redis_client",
            lambda: fake_redis,
        )

        rows = await read_cached_model_rows("daily:ok", StockDailySnapshotResponse)

        assert rows is not None
        assert len(rows) == 1
        assert rows[0].ts_code == "000001.SZ"
        assert rows[0].trade_date.isoformat() == "2026-03-03"

    asyncio.run(_run())


def test_read_cached_model_rows_deletes_invalid_json_when_enabled(
    monkeypatch,
) -> None:
    async def _run() -> None:
        fake_redis = FakeRedisClient()
        fake_redis._store["daily:invalid"] = "{invalid-json"
        monkeypatch.setattr(
            "app.services.stock_cache_service.get_redis_client",
            lambda: fake_redis,
        )

        rows = await read_cached_model_rows(
            "daily:invalid",
            StockDailySnapshotResponse,
            delete_on_decode_error=True,
        )

        assert rows is None
        assert fake_redis.delete_calls == ["daily:invalid"]

    asyncio.run(_run())


def test_write_cached_model_rows_serializes_payload(monkeypatch) -> None:
    async def _run() -> None:
        fake_redis = FakeRedisClient()
        monkeypatch.setattr(
            "app.services.stock_cache_service.get_redis_client",
            lambda: fake_redis,
        )

        await write_cached_model_rows(
            "daily:write",
            [
                StockDailySnapshotResponse(
                    ts_code="000001.SZ",
                    trade_date="2026-03-03",
                    open=11.0,
                    high=11.2,
                    low=10.8,
                    close=11.1,
                    pre_close=10.95,
                    change=0.15,
                    pct_chg=1.37,
                    vol=123456,
                    amount=789012,
                    turnover_rate=None,
                    volume_ratio=None,
                    pe=None,
                    pb=None,
                    total_mv=None,
                    circ_mv=None,
                )
            ],
            ttl_seconds=600,
        )

        assert len(fake_redis.set_calls) == 1
        key, payload, ttl = fake_redis.set_calls[0]
        assert key == "daily:write"
        assert ttl == 600
        decoded = json.loads(payload)
        assert decoded[0]["ts_code"] == "000001.SZ"
        assert decoded[0]["trade_date"] == "2026-03-03"

    asyncio.run(_run())


def test_read_cached_model_rows_logs_warning_when_redis_get_fails(monkeypatch) -> None:
    class BrokenRedisClient(FakeRedisClient):
        async def get(self, key: str) -> str | None:
            _ = key
            raise RuntimeError("redis 读取失败")

    async def _run() -> None:
        fake_redis = BrokenRedisClient()
        logger = WarningCollector()
        monkeypatch.setattr(
            "app.services.stock_cache_service.get_redis_client",
            lambda: fake_redis,
        )
        monkeypatch.setattr("app.services.stock_cache_service.LOGGER", logger)

        rows = await read_cached_model_rows("daily:broken", StockDailySnapshotResponse)

        assert rows is None
        assert len(logger.records) == 1
        message, args = logger.records[0]
        assert "event=stock_cache_failed" in message
        assert args[0] == "daily:broken"
        assert args[1] == "read_cache"
        assert args[2] == "RuntimeError"

    asyncio.run(_run())


def test_write_cached_model_rows_logs_warning_when_redis_set_fails(monkeypatch) -> None:
    class BrokenRedisClient(FakeRedisClient):
        async def set(self, key: str, value: str, ex: int | None = None) -> bool:
            _ = key, value, ex
            raise RuntimeError("redis 写入失败")

    async def _run() -> None:
        fake_redis = BrokenRedisClient()
        logger = WarningCollector()
        monkeypatch.setattr(
            "app.services.stock_cache_service.get_redis_client",
            lambda: fake_redis,
        )
        monkeypatch.setattr("app.services.stock_cache_service.LOGGER", logger)

        await write_cached_model_rows(
            "daily:write-fail",
            [
                StockDailySnapshotResponse(
                    ts_code="000001.SZ",
                    trade_date="2026-03-03",
                    open=11.0,
                    high=11.2,
                    low=10.8,
                    close=11.1,
                    pre_close=10.95,
                    change=0.15,
                    pct_chg=1.37,
                    vol=123456,
                    amount=789012,
                    turnover_rate=None,
                    volume_ratio=None,
                    pe=None,
                    pb=None,
                    total_mv=None,
                    circ_mv=None,
                )
            ],
            ttl_seconds=600,
        )

        assert len(logger.records) == 1
        message, args = logger.records[0]
        assert "event=stock_cache_failed" in message
        assert args[0] == "daily:write-fail"
        assert args[1] == "write_cache"
        assert args[2] == "RuntimeError"

    asyncio.run(_run())
