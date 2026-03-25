from typing import Protocol


class EmailVerificationStore(Protocol):
    # 邮箱验证码存储协议：约束冷却、写入、校验、消费四个关键流程。
    async def try_acquire_send_cooldown(
        self, scene: str, email: str, cooldown_seconds: int
    ) -> bool: ...

    # 发送失败时释放冷却，避免用户被误伤进入长时间等待。
    async def release_send_cooldown(self, scene: str, email: str) -> None: ...

    # 写入验证码时必须带 TTL，确保过期后自动失效。
    async def set_email_verification_code(
        self, scene: str, email: str, code: str, expires_seconds: int
    ) -> None: ...

    # 校验仅返回真假，不暴露错误细节给上层。
    async def validate_email_verification_code(
        self, scene: str, email: str, code: str
    ) -> bool: ...

    # 校验通过后立刻消费，保证验证码一次性使用。
    async def consume_email_verification_code(self, scene: str, email: str) -> None: ...

    # 风控黑名单检查与计数接口用于上层限流逻辑。
    async def is_ip_blocked(self, ip: str) -> bool: ...

    async def check_and_increment_ip_limits(
        self,
        scene: str,
        ip: str,
        minute_limit: int,
        day_limit: int,
        block_seconds: int,
    ) -> bool: ...
