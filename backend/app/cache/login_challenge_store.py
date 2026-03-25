from typing import Protocol


class LoginChallengeStore(Protocol):
    # 登录风控存储协议：用于失败计数与验证码挑战，便于切换实现。
    async def record_failed_login(
        self, identity_key: str, window_seconds: int
    ) -> int: ...

    async def get_failed_login_count(self, identity_key: str) -> int: ...

    async def reset_failed_login_count(self, identity_key: str) -> None: ...

    async def set_captcha_challenge(
        self, captcha_id: str, answer: str, expires_seconds: int
    ) -> None: ...

    # 校验时只比较答案，不返回挑战本身，避免泄露缓存内容。
    async def validate_captcha_challenge(
        self, captcha_id: str, answer: str
    ) -> bool: ...

    # 登录成功或超时后撤销挑战，避免重复使用。
    async def revoke_captcha_challenge(self, captcha_id: str) -> None: ...
