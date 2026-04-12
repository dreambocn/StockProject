import asyncio

from redis.exceptions import ConnectionError as RedisConnectionError

from app.cache.redis import (
    AuthCacheUnavailableError,
    RedisEmailVerificationStore,
    RedisLoginChallengeStore,
    RedisTokenStore,
)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expire_calls: list[tuple[str, int]] = []

    async def incr(self, key: str) -> int:
        current = int(self.values.get(key, "0")) + 1
        self.values[key] = str(current)
        return current

    async def expire(self, key: str, seconds: int) -> None:
        self.expire_calls.append((key, seconds))

    async def get(self, key: str):
        return self.values.get(key)

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def set(self, key: str, value: str, ex: int) -> None:
        self.values[key] = value
        self.expire_calls.append((key, ex))


class FakeRedisWithNx(FakeRedis):
    async def set(self, key: str, value: str, ex: int, nx: bool = False):
        if nx and key in self.values:
            return False
        self.values[key] = value
        self.expire_calls.append((key, ex))
        return True


class BrokenPipeline:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def set(self, *args, **kwargs):
        _ = args, kwargs
        return self

    def sadd(self, *args, **kwargs):
        _ = args, kwargs
        return self

    def delete(self, *args, **kwargs):
        _ = args, kwargs
        return self

    def srem(self, *args, **kwargs):
        _ = args, kwargs
        return self

    async def execute(self):
        raise RedisConnectionError("redis://secret@dangerous-host:6379/0")


class BrokenRedis:
    async def incr(self, key: str) -> int:
        _ = key
        raise RedisConnectionError("redis://secret@dangerous-host:6379/0")

    async def expire(self, key: str, seconds: int) -> None:
        _ = key, seconds
        raise RedisConnectionError("redis://secret@dangerous-host:6379/0")

    async def get(self, key: str):
        _ = key
        raise RedisConnectionError("redis://secret@dangerous-host:6379/0")

    async def delete(self, *keys: str) -> None:
        _ = keys
        raise RedisConnectionError("redis://secret@dangerous-host:6379/0")

    async def set(self, *args, **kwargs):
        _ = args, kwargs
        raise RedisConnectionError("redis://secret@dangerous-host:6379/0")

    async def exists(self, key: str) -> int:
        _ = key
        raise RedisConnectionError("redis://secret@dangerous-host:6379/0")

    async def smembers(self, key: str):
        _ = key
        raise RedisConnectionError("redis://secret@dangerous-host:6379/0")

    def pipeline(self, transaction: bool = True):
        _ = transaction
        return BrokenPipeline()


def test_record_failed_login_and_reset() -> None:
    async def run_test() -> None:
        client = FakeRedis()
        store = RedisLoginChallengeStore(client)  # type: ignore[arg-type]

        key = "user-ip"
        first_count = await store.record_failed_login(key, 900)
        second_count = await store.record_failed_login(key, 900)
        current = await store.get_failed_login_count(key)

        assert first_count == 1
        assert second_count == 2
        assert current == 2
        assert client.expire_calls[0] == (f"auth:login_fail:{key}", 900)

        await store.reset_failed_login_count(key)
        assert await store.get_failed_login_count(key) == 0

    asyncio.run(run_test())


def test_set_validate_and_revoke_captcha_challenge() -> None:
    async def run_test() -> None:
        client = FakeRedis()
        store = RedisLoginChallengeStore(client)  # type: ignore[arg-type]

        captcha_id = "c1"
        await store.set_captcha_challenge(captcha_id, "AB12", 300)
        assert await store.validate_captcha_challenge(captcha_id, "AB12") is True
        assert await store.validate_captcha_challenge(captcha_id, "ZZ99") is False

        await store.revoke_captcha_challenge(captcha_id)
        assert await store.validate_captcha_challenge(captcha_id, "AB12") is False

    asyncio.run(run_test())


def test_email_verification_store_code_and_cooldown() -> None:
    async def run_test() -> None:
        client = FakeRedisWithNx()
        store = RedisEmailVerificationStore(client)  # type: ignore[arg-type]

        allowed = await store.try_acquire_send_cooldown("register", "a@example.com", 60)
        denied = await store.try_acquire_send_cooldown("register", "a@example.com", 60)

        assert allowed is True
        assert denied is False

        await store.set_email_verification_code(
            "register", "a@example.com", "123456", 300
        )
        assert (
            await store.validate_email_verification_code(
                "register", "a@example.com", "123456"
            )
            is True
        )
        assert (
            await store.validate_email_verification_code(
                "register", "a@example.com", "000000"
            )
            is False
        )

        await store.consume_email_verification_code("register", "a@example.com")
        assert (
            await store.validate_email_verification_code(
                "register", "a@example.com", "123456"
            )
            is False
        )

        await store.release_send_cooldown("register", "a@example.com")
        assert (
            await store.try_acquire_send_cooldown("register", "a@example.com", 60)
            is True
        )

    asyncio.run(run_test())


def test_login_challenge_store_wraps_redis_errors() -> None:
    async def run_test() -> None:
        store = RedisLoginChallengeStore(BrokenRedis())  # type: ignore[arg-type]

        with pytest.raises(AuthCacheUnavailableError) as exc_info:
            await store.get_failed_login_count("user-ip")

        assert str(exc_info.value) == "auth service unavailable"
        assert "dangerous-host" not in str(exc_info.value)

    import pytest

    asyncio.run(run_test())


def test_email_verification_store_wraps_redis_errors() -> None:
    async def run_test() -> None:
        store = RedisEmailVerificationStore(BrokenRedis())  # type: ignore[arg-type]

        with pytest.raises(AuthCacheUnavailableError) as exc_info:
            await store.try_acquire_send_cooldown("register", "a@example.com", 60)

        assert str(exc_info.value) == "auth service unavailable"
        assert "dangerous-host" not in str(exc_info.value)

    import pytest

    asyncio.run(run_test())


def test_token_store_wraps_redis_errors() -> None:
    async def run_test() -> None:
        store = RedisTokenStore(BrokenRedis())  # type: ignore[arg-type]

        with pytest.raises(AuthCacheUnavailableError) as exc_info:
            await store.set_refresh_token("jti-1", "user-1", 300)

        assert str(exc_info.value) == "auth service unavailable"
        assert "dangerous-host" not in str(exc_info.value)

    import pytest

    asyncio.run(run_test())
