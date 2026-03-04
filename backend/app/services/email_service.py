from typing import Protocol


class EmailSender(Protocol):
    async def send_register_verification_code(
        self, email: str, code: str, expires_seconds: int
    ) -> None: ...

    async def send_change_password_verification_code(
        self, email: str, code: str, expires_seconds: int
    ) -> None: ...

    async def send_reset_password_verification_code(
        self, email: str, code: str, expires_seconds: int
    ) -> None: ...

    async def send_password_changed_notice(self, email: str) -> None: ...
