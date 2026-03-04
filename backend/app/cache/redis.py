from functools import lru_cache

import redis.asyncio as redis

from app.cache.email_verification_store import EmailVerificationStore
from app.cache.login_challenge_store import LoginChallengeStore
from app.cache.token_store import TokenStore
from app.core.settings import get_settings


settings = get_settings()


@lru_cache
def get_redis_client() -> redis.Redis:
    # 进程内复用 Redis 客户端，避免重复创建连接池。
    return redis.from_url(settings.redis_url, decode_responses=True)


class RedisTokenStore(TokenStore):
    def __init__(self, client: redis.Redis) -> None:
        self.client = client

    async def set_refresh_token(
        self, jti: str, user_id: str, expires_seconds: int
    ) -> None:
        # 刷新令牌写入双索引：jti->user 与 user->jtis。
        # 这样既能做单 token 校验，也能在改密/重置后按用户全量撤销。
        async with self.client.pipeline(transaction=True) as pipe:
            await (
                pipe.set(f"auth:refresh:{jti}", user_id, ex=expires_seconds)
                .sadd(f"auth:user_refresh:{user_id}", jti)
                .execute()
            )

    async def validate_refresh_token(self, jti: str, user_id: str) -> bool:
        value = await self.client.get(f"auth:refresh:{jti}")
        return value == user_id

    async def revoke_refresh_token(self, jti: str) -> None:
        refresh_key = f"auth:refresh:{jti}"
        user_id = await self.client.get(refresh_key)

        # 单 token 撤销也要同步维护用户索引，避免索引长期残留脏数据。
        if user_id is None:
            await self.client.delete(refresh_key)
            return

        async with self.client.pipeline(transaction=True) as pipe:
            await (
                pipe.delete(refresh_key)
                .srem(f"auth:user_refresh:{user_id}", jti)
                .execute()
            )

    async def revoke_all_refresh_tokens_for_user(self, user_id: str) -> None:
        user_refresh_index_key = f"auth:user_refresh:{user_id}"
        jtis = await self.client.smembers(user_refresh_index_key)
        refresh_keys = [f"auth:refresh:{jti}" for jti in jtis]

        # 鉴权安全边界：改密/重置后立刻废弃该用户全部 refresh token。
        # access token 仍按短期过期策略自然失效，避免跨层强制状态同步。
        async with self.client.pipeline(transaction=True) as pipe:
            if refresh_keys:
                pipe.delete(*refresh_keys)
            pipe.delete(user_refresh_index_key)
            await pipe.execute()


class RedisLoginChallengeStore(LoginChallengeStore):
    def __init__(self, client: redis.Redis) -> None:
        self.client = client

    async def record_failed_login(self, identity_key: str, window_seconds: int) -> int:
        # 首次失败时设置窗口期 TTL，形成滑动风控窗口。
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
        # 仅缓存验证码答案，避免在客户端暴露可验证信息。
        await self.client.set(f"auth:captcha:{captcha_id}", answer, ex=expires_seconds)

    async def validate_captcha_challenge(self, captcha_id: str, answer: str) -> bool:
        value = await self.client.get(f"auth:captcha:{captcha_id}")
        return value == answer

    async def revoke_captcha_challenge(self, captcha_id: str) -> None:
        await self.client.delete(f"auth:captcha:{captcha_id}")


class RedisEmailVerificationStore(EmailVerificationStore):
    def __init__(self, client: redis.Redis) -> None:
        self.client = client

    def _build_code_key(self, scene: str, email: str) -> str:
        # 邮箱统一归一化，避免大小写差异导致同邮箱多份验证码。
        normalized_email = email.strip().lower()
        return f"auth:email_code:{scene}:{normalized_email}"

    def _build_cooldown_key(self, scene: str, email: str) -> str:
        normalized_email = email.strip().lower()
        return f"auth:email_code_cooldown:{scene}:{normalized_email}"

    async def try_acquire_send_cooldown(
        self, scene: str, email: str, cooldown_seconds: int
    ) -> bool:
        # 使用 NX 原子写入冷却标记，防止并发请求重复发码。
        key = self._build_cooldown_key(scene, email)
        is_set = await self.client.set(key, "1", ex=cooldown_seconds, nx=True)
        return bool(is_set)

    async def release_send_cooldown(self, scene: str, email: str) -> None:
        key = self._build_cooldown_key(scene, email)
        await self.client.delete(key)

    async def set_email_verification_code(
        self, scene: str, email: str, code: str, expires_seconds: int
    ) -> None:
        key = self._build_code_key(scene, email)
        await self.client.set(key, code, ex=expires_seconds)

    async def validate_email_verification_code(
        self, scene: str, email: str, code: str
    ) -> bool:
        key = self._build_code_key(scene, email)
        value = await self.client.get(key)
        return value == code

    async def consume_email_verification_code(self, scene: str, email: str) -> None:
        # 验证码消费后立即删除，防止重放攻击。
        key = self._build_code_key(scene, email)
        await self.client.delete(key)
