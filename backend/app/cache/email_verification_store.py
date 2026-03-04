from typing import Protocol


class EmailVerificationStore(Protocol):
    async def try_acquire_send_cooldown(
        self, scene: str, email: str, cooldown_seconds: int
    ) -> bool: ...

    async def release_send_cooldown(self, scene: str, email: str) -> None: ...

    async def set_email_verification_code(
        self, scene: str, email: str, code: str, expires_seconds: int
    ) -> None: ...

    async def validate_email_verification_code(
        self, scene: str, email: str, code: str
    ) -> bool: ...

    async def consume_email_verification_code(self, scene: str, email: str) -> None: ...
