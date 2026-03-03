import asyncio

from app.cache.redis import RedisLoginChallengeStore


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
