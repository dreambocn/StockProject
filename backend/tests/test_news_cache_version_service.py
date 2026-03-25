import asyncio
from datetime import UTC, datetime

import pytest

from app.services.news_cache_version_service import (
    build_news_cache_version_key,
    build_versioned_news_cache_key,
    format_news_cache_version,
    read_news_cache_version,
    resolve_news_cache_data_key,
    should_try_legacy_news_cache,
    write_news_cache_version,
)


class FakeRedisClient:
    def __init__(self) -> None:
        self._store: dict[str, str | bytes] = {}

    async def get(self, key: str) -> str | bytes | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        _ = ex
        self._store[key] = value
        return True


def test_build_news_cache_version_key_supports_hot_policy_stock() -> None:
    hot_key = build_news_cache_version_key(scope="hot", cache_variant="global")
    policy_key = build_news_cache_version_key(
        scope="policy",
        cache_variant="policy_source",
    )
    stock_key = build_news_cache_version_key(
        scope="stock",
        cache_variant="with_announcements",
        ts_code="600029.sh",
    )

    assert hot_key == "news:hot:global:version"
    assert policy_key == "news:policy:policy_source:version"
    assert stock_key == "stocks:news:600029.SH:with_announcements:version"


def test_build_news_cache_version_key_requires_ts_code_for_stock() -> None:
    with pytest.raises(ValueError, match="ts_code is required when scope=stock"):
        build_news_cache_version_key(scope="stock", cache_variant="with_announcements")


def test_build_versioned_news_cache_key_requires_non_empty_version() -> None:
    with pytest.raises(ValueError, match="version must not be empty"):
        build_versioned_news_cache_key(base_cache_key="news:hot:all:50", version=" ")


def test_format_news_cache_version_normalizes_utc() -> None:
    version = format_news_cache_version(
        fetched_at=datetime(2026, 3, 25, 10, 30, 45, tzinfo=UTC),
    )
    assert version == "20260325103045"


def test_resolve_news_cache_data_key_supports_version_and_legacy() -> None:
    versioned_key = resolve_news_cache_data_key(
        base_cache_key="news:hot:all:50",
        version="20260325103045",
    )
    legacy_key = resolve_news_cache_data_key(
        base_cache_key="news:hot:all:50",
        version=None,
    )

    assert versioned_key == "news:hot:all:50:v:20260325103045"
    assert legacy_key == "news:hot:all:50"


def test_should_try_legacy_news_cache_depends_on_version_and_flag() -> None:
    assert should_try_legacy_news_cache(version=None, legacy_fallback_enabled=True) is True
    assert should_try_legacy_news_cache(version="20260325103045", legacy_fallback_enabled=True) is False
    assert should_try_legacy_news_cache(version=None, legacy_fallback_enabled=False) is False


def test_read_and_write_news_cache_version_roundtrip() -> None:
    async def _run() -> None:
        fake_redis = FakeRedisClient()
        version_key = "news:hot:global:version"

        await write_news_cache_version(
            version_key=version_key,
            version="20260325103045",
            redis_client_getter=lambda: fake_redis,
        )
        loaded_version = await read_news_cache_version(
            version_key=version_key,
            redis_client_getter=lambda: fake_redis,
        )
        assert loaded_version == "20260325103045"

        fake_redis._store[version_key] = b"20260325110000"
        loaded_bytes_version = await read_news_cache_version(
            version_key=version_key,
            redis_client_getter=lambda: fake_redis,
        )
        assert loaded_bytes_version == "20260325110000"

    asyncio.run(_run())


def test_read_news_cache_version_returns_none_when_redis_errors() -> None:
    class BrokenRedisClient:
        async def get(self, key: str) -> str | None:
            _ = key
            raise RuntimeError("redis read failed")

    async def _run() -> None:
        loaded_version = await read_news_cache_version(
            version_key="news:hot:global:version",
            redis_client_getter=lambda: BrokenRedisClient(),
        )
        assert loaded_version is None

    asyncio.run(_run())
