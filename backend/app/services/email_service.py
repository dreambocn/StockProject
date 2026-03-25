from typing import Protocol


class EmailSender(Protocol):
    # 邮件能力协议：上层仅依赖业务语义方法，不耦合具体 SMTP/第三方实现。
    async def send_register_verification_code(
        self, email: str, code: str, expires_seconds: int
    ) -> None: ...

    async def send_change_password_verification_code(
        self, email: str, code: str, expires_seconds: int
    ) -> None: ...

    async def send_reset_password_verification_code(
        self, email: str, code: str, expires_seconds: int
    ) -> None: ...

    # 密码变更成功通知用于提升安全感知，失败不影响主流程。
    async def send_password_changed_notice(self, email: str) -> None: ...
