from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import TypeVar

import redis.asyncio as redis
from redis.exceptions import RedisError

from app.cache.email_verification_store import EmailVerificationStore
from app.cache.login_challenge_store import LoginChallengeStore
from app.cache.token_store import TokenStore
from app.core.logging import get_logger
from app.core.settings import get_settings


settings = get_settings()
logger = get_logger("app.auth_cache")

AUTH_CACHE_UNAVAILABLE_MESSAGE = "auth service unavailable"
T = TypeVar("T")


class AuthCacheUnavailableError(RuntimeError):
    """认证缓存不可用时抛出的统一异常。"""


async def _run_auth_cache_operation(
    *,
    store: str,
    operation: str,
    action: Callable[[], Awaitable[T]],
) -> T:
    try:
        return await action()
    except (RedisError, OSError) as exc:
        logger.warning(
            "event=auth_cache_unavailable store=%s operation=%s error_type=%s",
            store,
            operation,
            exc.__class__.__name__,
        )
        raise AuthCacheUnavailableError(AUTH_CACHE_UNAVAILABLE_MESSAGE) from exc


class _RedisAuthStoreBase:
    store_name = "auth_store"

    def __init__(self, client: redis.Redis) -> None:
        self.client = client

    async def _run(
        self,
        operation: str,
        action: Callable[[], Awaitable[T]],
    ) -> T:
        return await _run_auth_cache_operation(
            store=self.store_name,
            operation=operation,
            action=action,
        )


@lru_cache
def get_redis_client() -> redis.Redis:
    # 进程内复用 Redis 客户端，避免重复创建连接池。
    return redis.from_url(settings.redis_url, decode_responses=True)


class RedisTokenStore(_RedisAuthStoreBase, TokenStore):
    store_name = "token_store"

    async def set_refresh_token(
        self, jti: str, user_id: str, expires_seconds: int
    ) -> None:
        async def _operation() -> None:
            # 刷新令牌写入双索引：jti->user 与 user->jtis。
            # 这样既能做单 token 校验，也能在改密/重置后按用户全量撤销。
            async with self.client.pipeline(transaction=True) as pipe:
                await (
                    pipe.set(f"auth:refresh:{jti}", user_id, ex=expires_seconds)
                    .sadd(f"auth:user_refresh:{user_id}", jti)
                    .execute()
                )

        await self._run("set_refresh_token", _operation)

    async def validate_refresh_token(self, jti: str, user_id: str) -> bool:
        async def _operation() -> bool:
            # refresh token 校验以 jti -> user_id 绑定为准，避免仅凭 token 存在性通过。
            value = await self.client.get(f"auth:refresh:{jti}")
            return value == user_id

        return await self._run("validate_refresh_token", _operation)

    async def revoke_refresh_token(self, jti: str) -> None:
        async def _operation() -> None:
            refresh_key = f"auth:refresh:{jti}"
            user_id = await self.client.get(refresh_key)

            # 单 token 撤销也要同步维护用户索引，避免索引长期残留脏数据。
            if user_id is None:
                # 键不存在时仍确保删除，避免异常情况下残留空键。
                await self.client.delete(refresh_key)
                return

            async with self.client.pipeline(transaction=True) as pipe:
                await (
                    pipe.delete(refresh_key)
                    .srem(f"auth:user_refresh:{user_id}", jti)
                    .execute()
                )

        await self._run("revoke_refresh_token", _operation)

    async def revoke_all_refresh_tokens_for_user(self, user_id: str) -> None:
        async def _operation() -> None:
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

        await self._run("revoke_all_refresh_tokens_for_user", _operation)


class RedisLoginChallengeStore(_RedisAuthStoreBase, LoginChallengeStore):
    store_name = "login_challenge_store"

    async def record_failed_login(self, identity_key: str, window_seconds: int) -> int:
        async def _operation() -> int:
            # 首次失败时设置窗口期 TTL，形成滑动风控窗口。
            key = f"auth:login_fail:{identity_key}"
            count = await self.client.incr(key)
            if count == 1:
                await self.client.expire(key, window_seconds)
            return int(count)

        return await self._run("record_failed_login", _operation)

    async def get_failed_login_count(self, identity_key: str) -> int:
        async def _operation() -> int:
            key = f"auth:login_fail:{identity_key}"
            value = await self.client.get(key)
            return int(value) if value is not None else 0

        return await self._run("get_failed_login_count", _operation)

    async def reset_failed_login_count(self, identity_key: str) -> None:
        async def _operation() -> None:
            key = f"auth:login_fail:{identity_key}"
            await self.client.delete(key)

        await self._run("reset_failed_login_count", _operation)

    async def set_captcha_challenge(
        self, captcha_id: str, answer: str, expires_seconds: int
    ) -> None:
        async def _operation() -> None:
            # 仅缓存验证码答案，避免在客户端暴露可验证信息。
            await self.client.set(
                f"auth:captcha:{captcha_id}", answer, ex=expires_seconds
            )

        await self._run("set_captcha_challenge", _operation)

    async def validate_captcha_challenge(self, captcha_id: str, answer: str) -> bool:
        async def _operation() -> bool:
            value = await self.client.get(f"auth:captcha:{captcha_id}")
            return value == answer

        return await self._run("validate_captcha_challenge", _operation)

    async def revoke_captcha_challenge(self, captcha_id: str) -> None:
        async def _operation() -> None:
            await self.client.delete(f"auth:captcha:{captcha_id}")

        await self._run("revoke_captcha_challenge", _operation)


class RedisEmailVerificationStore(_RedisAuthStoreBase, EmailVerificationStore):
    store_name = "email_verification_store"

    def _build_code_key(self, scene: str, email: str) -> str:
        # 邮箱统一归一化，避免大小写差异导致同邮箱多份验证码。
        normalized_email = email.strip().lower()
        return f"auth:email_code:{scene}:{normalized_email}"

    def _build_cooldown_key(self, scene: str, email: str) -> str:
        normalized_email = email.strip().lower()
        return f"auth:email_code_cooldown:{scene}:{normalized_email}"

    def _build_ip_minute_limit_key(self, scene: str, ip: str) -> str:
        normalized_ip = ip.strip().lower()
        return f"auth:email_code:ip:{scene}:{normalized_ip}"

    def _build_ip_day_limit_key(self, scene: str, ip: str) -> str:
        normalized_ip = ip.strip().lower()
        return f"auth:email_code:ip_day:{scene}:{normalized_ip}"

    def _build_ip_block_key(self, ip: str) -> str:
        normalized_ip = ip.strip().lower()
        return f"auth:block_ip:{normalized_ip}"

    async def try_acquire_send_cooldown(
        self, scene: str, email: str, cooldown_seconds: int
    ) -> bool:
        async def _operation() -> bool:
            # 使用 NX 原子写入冷却标记，防止并发请求重复发码。
            key = self._build_cooldown_key(scene, email)
            is_set = await self.client.set(key, "1", ex=cooldown_seconds, nx=True)
            return bool(is_set)

        return await self._run("try_acquire_send_cooldown", _operation)

    async def release_send_cooldown(self, scene: str, email: str) -> None:
        async def _operation() -> None:
            key = self._build_cooldown_key(scene, email)
            await self.client.delete(key)

        await self._run("release_send_cooldown", _operation)

    async def set_email_verification_code(
        self, scene: str, email: str, code: str, expires_seconds: int
    ) -> None:
        async def _operation() -> None:
            key = self._build_code_key(scene, email)
            await self.client.set(key, code, ex=expires_seconds)

        await self._run("set_email_verification_code", _operation)

    async def validate_email_verification_code(
        self, scene: str, email: str, code: str
    ) -> bool:
        async def _operation() -> bool:
            key = self._build_code_key(scene, email)
            value = await self.client.get(key)
            return value == code

        return await self._run("validate_email_verification_code", _operation)

    async def consume_email_verification_code(self, scene: str, email: str) -> None:
        async def _operation() -> None:
            # 验证码消费后立即删除，防止重放攻击。
            key = self._build_code_key(scene, email)
            await self.client.delete(key)

        await self._run("consume_email_verification_code", _operation)

    async def is_ip_blocked(self, ip: str) -> bool:
        async def _operation() -> bool:
            # 拉黑名单优先检查，命中后直接拒绝，避免继续消耗风控/邮件资源。
            block_key = self._build_ip_block_key(ip)
            return bool(await self.client.exists(block_key))

        return await self._run("is_ip_blocked", _operation)

    async def check_and_increment_ip_limits(
        self,
        scene: str,
        ip: str,
        minute_limit: int,
        day_limit: int,
        block_seconds: int,
    ) -> bool:
        async def _operation() -> bool:
            minute_key = self._build_ip_minute_limit_key(scene, ip)
            day_key = self._build_ip_day_limit_key(scene, ip)

            minute_count = int(await self.client.incr(minute_key))
            if minute_count == 1:
                await self.client.expire(minute_key, 60)

            day_count = int(await self.client.incr(day_key))
            if day_count == 1:
                await self.client.expire(day_key, 24 * 60 * 60)

            # 任一窗口超限都进入 IP 拉黑，短时间内阻断持续刷接口行为。
            if minute_count > minute_limit or day_count > day_limit:
                await self.client.set(
                    self._build_ip_block_key(ip), "1", ex=block_seconds
                )
                return False

            return True

        return await self._run("check_and_increment_ip_limits", _operation)
