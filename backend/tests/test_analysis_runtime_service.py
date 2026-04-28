import asyncio

from app.services.analysis_runtime_service import (
    lock_registry,
    cache_active_session_id,
    cache_fresh_report_id,
    clear_cached_active_session_id,
    get_cached_active_session_id,
    get_cached_fresh_report_id,
    session_lock,
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


def test_analysis_session_lock_context_cleans_idle_key() -> None:
    async def _run() -> None:
        lock_registry._locks.clear()

        async with session_lock("analysis-key-cleanup"):
            assert "analysis-key-cleanup" in lock_registry._locks

        assert "analysis-key-cleanup" not in lock_registry._locks

    asyncio.run(_run())


def test_analysis_session_lock_context_serializes_same_key_and_cleans_after_waiters() -> None:
    async def _run() -> None:
        lock_registry._locks.clear()
        active_count = 0
        max_active_count = 0

        async def run_locked() -> None:
            nonlocal active_count, max_active_count
            async with session_lock("analysis-key-shared"):
                active_count += 1
                max_active_count = max(max_active_count, active_count)
                await asyncio.sleep(0.01)
                active_count -= 1

        await asyncio.gather(run_locked(), run_locked(), run_locked())

        assert max_active_count == 1
        assert "analysis-key-shared" not in lock_registry._locks

    asyncio.run(_run())
