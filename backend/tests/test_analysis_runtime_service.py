import asyncio

from app.services.analysis_runtime_service import (
    cache_active_session_id,
    cache_fresh_report_id,
    clear_cached_active_session_id,
    get_cached_active_session_id,
    get_cached_fresh_report_id,
)


class WarningCollector:
    def __init__(self) -> None:
        self.records: list[tuple[str, tuple[object, ...]]] = []

    def warning(self, msg: str, *args: object) -> None:
        self.records.append((msg, args))


class BrokenRedisClient:
    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        _ = key, value, ex
        raise RuntimeError("redis set failed")

    async def get(self, key: str) -> str | None:
        _ = key
        raise RuntimeError("redis get failed")

    async def delete(self, key: str) -> int:
        _ = key
        raise RuntimeError("redis delete failed")


def test_analysis_runtime_logs_warning_for_cache_failures(monkeypatch) -> None:
    async def _run() -> None:
        logger = WarningCollector()
        monkeypatch.setattr(
            "app.services.analysis_runtime_service.get_redis_client",
            lambda: BrokenRedisClient(),
        )
        monkeypatch.setattr("app.services.analysis_runtime_service.LOGGER", logger)

        await cache_active_session_id("akey", "sid", 60)
        await cache_fresh_report_id("akey", "rid", 60)
        _active = await get_cached_active_session_id("akey")
        _fresh = await get_cached_fresh_report_id("akey")
        await clear_cached_active_session_id("akey", session_id="sid")

        assert _active is None
        assert _fresh is None
        assert len(logger.records) == 5

        operations = [record[1][2] for record in logger.records]
        assert operations == [
            "set_active_session_id",
            "set_fresh_report_id",
            "get_active_session_id",
            "get_fresh_report_id",
            "clear_active_session_id",
        ]
        for message, args in logger.records:
            assert "event=%s analysis_key=%s operation=%s error_type=%s" in message
            assert args[0] == "analysis_runtime_cache_failed"
            assert args[1] == "akey"
            assert args[3] == "RuntimeError"

    asyncio.run(_run())
