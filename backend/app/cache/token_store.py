from typing import Protocol


class TokenStore(Protocol):
    async def set_refresh_token(
        self, jti: str, user_id: str, expires_seconds: int
    ) -> None: ...

    async def validate_refresh_token(self, jti: str, user_id: str) -> bool: ...

    async def revoke_refresh_token(self, jti: str) -> None: ...
