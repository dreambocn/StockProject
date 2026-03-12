import asyncio
import json

from app.schemas.stocks import StockDailySnapshotResponse
from app.services.stock_cache_service import (
    get_singleflight_lock,
    read_cached_model_rows,
    write_cached_model_rows,
)


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
