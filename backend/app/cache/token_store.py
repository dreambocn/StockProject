from typing import Protocol


class TokenStore(Protocol):
    # 刷新令牌存储协议：统一抽象发放、校验、撤销三个关键动作。
    async def set_refresh_token(
        self, jti: str, user_id: str, expires_seconds: int
    ) -> None: ...

    async def validate_refresh_token(self, jti: str, user_id: str) -> bool: ...

    async def revoke_refresh_token(self, jti: str) -> None: ...
