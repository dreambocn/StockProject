import asyncio
from datetime import UTC, datetime, timedelta

from app.schemas.news import HotNewsItemResponse
from app.services.news_cache_service import get_news_rows


class WarningCollector:
    def __init__(self) -> None:
        self.records: list[tuple[str, tuple[object, ...]]] = []

    def warning(self, msg: str, *args: object) -> None:
        self.records.append((msg, args))


class MemoryNewsCache:
    def __init__(self) -> None:
        self.data: dict[str, list[HotNewsItemResponse]] = {}
        self.writes: list[tuple[str, list[HotNewsItemResponse], int]] = []

    async def read(self, key: str) -> list[HotNewsItemResponse] | None:
        return self.data.get(key)

    async def write(
        self,
        key: str,
        rows: list[HotNewsItemResponse],
        ttl_seconds: int,
    ) -> None:
        self.writes.append((key, rows, ttl_seconds))
        self.data[key] = rows


def _hot_row(title: str) -> HotNewsItemResponse:
    return HotNewsItemResponse(
        title=title,
        summary="summary",
        published_at=datetime(2026, 3, 3, 9, 0, tzinfo=UTC),
        url=f"https://example.com/{title}",
        source="eastmoney_global",
        macro_topic="other",
    )


def test_news_service_uses_db_within_refresh_window() -> None:
    async def _run() -> None:
        cache = MemoryNewsCache()
        db_rows = [_hot_row("cached")]
        remote_calls = 0
        written_rows: list[list[HotNewsItemResponse]] = []

        async def load_from_db() -> list[HotNewsItemResponse]:
            return db_rows

        async def get_last_fetch_at() -> datetime | None:
            return datetime(2026, 3, 3, 8, 30, tzinfo=UTC)

        async def fetch_remote_and_persist() -> list[HotNewsItemResponse]:
            nonlocal remote_calls
            remote_calls += 1
            rows = [_hot_row("remote")]
            written_rows.append(rows)
            return rows

        async def get_lock(_cache_key: str) -> asyncio.Lock:
            return asyncio.Lock()

        result = await get_news_rows(
            cache_key="news:hot:all:50",
            cache_ttl_seconds=3600,
            refresh_window_seconds=3600,
            now=datetime(2026, 3, 3, 9, 0, tzinfo=UTC),
            read_cache=cache.read,
            write_cache=cache.write,
            load_from_db=load_from_db,
            get_last_fetch_at=get_last_fetch_at,
            fetch_remote_and_persist=fetch_remote_and_persist,
            get_singleflight_lock=get_lock,
        )

        assert result == db_rows
        assert remote_calls == 0
        assert written_rows == []
        assert len(cache.writes) == 1

    asyncio.run(_run())


def test_news_service_refreshes_remote_after_window_expires() -> None:
    async def _run() -> None:
        cache = MemoryNewsCache()
        db_rows = [_hot_row("stale")]
        remote_rows = [_hot_row("fresh")]
        remote_calls = 0

        async def load_from_db() -> list[HotNewsItemResponse]:
            return db_rows

        async def get_last_fetch_at() -> datetime | None:
            return datetime(2026, 3, 3, 7, 30, tzinfo=UTC)

        async def fetch_remote_and_persist() -> list[HotNewsItemResponse]:
            nonlocal remote_calls
            remote_calls += 1
            return remote_rows

        async def get_lock(_cache_key: str) -> asyncio.Lock:
            return asyncio.Lock()

        result = await get_news_rows(
            cache_key="news:hot:all:50",
            cache_ttl_seconds=3600,
            refresh_window_seconds=3600,
            now=datetime(2026, 3, 3, 9, 0, tzinfo=UTC),
            read_cache=cache.read,
            write_cache=cache.write,
            load_from_db=load_from_db,
            get_last_fetch_at=get_last_fetch_at,
            fetch_remote_and_persist=fetch_remote_and_persist,
            get_singleflight_lock=get_lock,
        )

        assert result == remote_rows
        assert remote_calls == 1
        assert len(cache.writes) == 1

    asyncio.run(_run())


def test_news_service_falls_back_to_db_when_remote_fails() -> None:
    async def _run() -> None:
        cache = MemoryNewsCache()
        db_rows = [_hot_row("fallback")]

        async def load_from_db() -> list[HotNewsItemResponse]:
            return db_rows

        async def get_last_fetch_at() -> datetime | None:
            return datetime.now(UTC) - timedelta(hours=2)

        async def fetch_remote_and_persist() -> list[HotNewsItemResponse]:
            raise RuntimeError("upstream failed")

        async def get_lock(_cache_key: str) -> asyncio.Lock:
            return asyncio.Lock()

        result = await get_news_rows(
            cache_key="news:hot:all:50",
            cache_ttl_seconds=3600,
            refresh_window_seconds=3600,
            now=datetime(2026, 3, 3, 9, 0, tzinfo=UTC),
            read_cache=cache.read,
            write_cache=cache.write,
            load_from_db=load_from_db,
            get_last_fetch_at=get_last_fetch_at,
            fetch_remote_and_persist=fetch_remote_and_persist,
            get_singleflight_lock=get_lock,
        )

        assert result == db_rows

    asyncio.run(_run())


def test_news_service_logs_warning_when_db_cache_write_fails(monkeypatch) -> None:
    async def _run() -> None:
        cache = MemoryNewsCache()
        db_rows = [_hot_row("cached")]
        logger = WarningCollector()
        monkeypatch.setattr("app.services.news_cache_service.LOGGER", logger)

        async def load_from_db() -> list[HotNewsItemResponse]:
            return db_rows

        async def get_last_fetch_at() -> datetime | None:
            return datetime(2026, 3, 3, 8, 30, tzinfo=UTC)

        async def fetch_remote_and_persist() -> list[HotNewsItemResponse]:
            return [_hot_row("remote")]

        async def get_lock(_cache_key: str) -> asyncio.Lock:
            return asyncio.Lock()

        async def broken_write_cache(
            key: str, rows: list[HotNewsItemResponse], ttl_seconds: int
        ) -> None:
            _ = key, rows, ttl_seconds
            raise RuntimeError("redis 写入失败")

        result = await get_news_rows(
            cache_key="news:hot:all:50",
            cache_ttl_seconds=3600,
            refresh_window_seconds=3600,
            now=datetime(2026, 3, 3, 9, 0, tzinfo=UTC),
            read_cache=cache.read,
            write_cache=broken_write_cache,
            load_from_db=load_from_db,
            get_last_fetch_at=get_last_fetch_at,
            fetch_remote_and_persist=fetch_remote_and_persist,
            get_singleflight_lock=get_lock,
        )

        assert result == db_rows
        assert len(logger.records) == 1
        message, args = logger.records[0]
        assert "event=news_cache_failed" in message
        assert args[0] == "news:hot:all:50"
        assert args[1] == "write_cache_from_db"
        assert args[2] == "RuntimeError"

    asyncio.run(_run())
