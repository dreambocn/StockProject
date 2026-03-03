from functools import lru_cache

import redis.asyncio as redis

from app.cache.login_challenge_store import LoginChallengeStore
from app.cache.token_store import TokenStore
from app.core.settings import get_settings


settings = get_settings()


@lru_cache
def get_redis_client() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


class RedisTokenStore(TokenStore):
    def __init__(self, client: redis.Redis) -> None:
        self.client = client

    async def set_refresh_token(
        self, jti: str, user_id: str, expires_seconds: int
    ) -> None:
        await self.client.set(f"auth:refresh:{jti}", user_id, ex=expires_seconds)

    async def validate_refresh_token(self, jti: str, user_id: str) -> bool:
        value = await self.client.get(f"auth:refresh:{jti}")
        return value == user_id

    async def revoke_refresh_token(self, jti: str) -> None:
        await self.client.delete(f"auth:refresh:{jti}")


class RedisLoginChallengeStore(LoginChallengeStore):
    def __init__(self, client: redis.Redis) -> None:
        self.client = client

    async def record_failed_login(self, identity_key: str, window_seconds: int) -> int:
        key = f"auth:login_fail:{identity_key}"
        count = await self.client.incr(key)
        if count == 1:
            await self.client.expire(key, window_seconds)
        return int(count)

    async def get_failed_login_count(self, identity_key: str) -> int:
        key = f"auth:login_fail:{identity_key}"
        value = await self.client.get(key)
        return int(value) if value is not None else 0

    async def reset_failed_login_count(self, identity_key: str) -> None:
        key = f"auth:login_fail:{identity_key}"
        await self.client.delete(key)

    async def set_captcha_challenge(
        self, captcha_id: str, answer: str, expires_seconds: int
    ) -> None:
        await self.client.set(f"auth:captcha:{captcha_id}", answer, ex=expires_seconds)

    async def validate_captcha_challenge(self, captcha_id: str, answer: str) -> bool:
        value = await self.client.get(f"auth:captcha:{captcha_id}")
        return value == answer

    async def revoke_captcha_challenge(self, captcha_id: str) -> None:
        await self.client.delete(f"auth:captcha:{captcha_id}")
