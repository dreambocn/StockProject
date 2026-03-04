import asyncio
import smtplib
from email.message import EmailMessage

from app.core.logging import get_logger
from app.core.settings import Settings
from app.services.email_service import EmailSender


logger = get_logger("app.email")


class SmtpEmailSender(EmailSender):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send_register_verification_code(
        self, email: str, code: str, expires_seconds: int
    ) -> None:
        subject = "【AI STOCK LAB】注册邮箱验证码"
        text_body = (
            f"您的注册验证码为：{code}\n\n"
            f"验证码 {expires_seconds // 60} 分钟内有效，请勿泄露给他人。"
        )
        html_body = self._build_html_email(
            title="注册验证码",
            lead="您正在注册 AI STOCK LAB 账号，请使用以下验证码完成验证：",
            code=code,
            tip=f"验证码将在 {expires_seconds // 60} 分钟后失效，请尽快完成操作。",
        )
        await self._send_email(email, subject, text_body, html_body)

    async def send_change_password_verification_code(
        self, email: str, code: str, expires_seconds: int
    ) -> None:
        subject = "【AI STOCK LAB】修改密码验证码"
        text_body = (
            f"您的修改密码验证码为：{code}\n\n"
            f"验证码 {expires_seconds // 60} 分钟内有效，请勿泄露给他人。"
        )
        html_body = self._build_html_email(
            title="修改密码验证码",
            lead="您正在进行账号密码修改，请使用以下验证码完成验证：",
            code=code,
            tip=f"验证码将在 {expires_seconds // 60} 分钟后失效；如非本人操作，请忽略并及时检查账号安全。",
        )
        await self._send_email(email, subject, text_body, html_body)

    async def send_reset_password_verification_code(
        self, email: str, code: str, expires_seconds: int
    ) -> None:
        subject = "【AI STOCK LAB】重置密码验证码"
        text_body = (
            f"您的重置密码验证码为：{code}\n\n"
            f"验证码 {expires_seconds // 60} 分钟内有效，请勿泄露给他人。"
        )
        html_body = self._build_html_email(
            title="重置密码验证码",
            lead="您正在进行密码重置，请使用以下验证码完成验证：",
            code=code,
            tip=f"验证码将在 {expires_seconds // 60} 分钟后失效；如非本人操作，请忽略本邮件。",
        )
        await self._send_email(email, subject, text_body, html_body)

    async def send_password_changed_notice(self, email: str) -> None:
        subject = "【AI STOCK LAB】密码修改成功通知"
        text_body = (
            "您的账号密码已修改成功。\n\n"
            "如果这不是您本人操作，请立即重置密码并联系管理员。"
        )
        html_body = self._build_html_email(
            title="密码修改成功",
            lead="您的账号密码已成功更新。",
            code=None,
            tip="如果这不是您本人操作，请立即重置密码并联系管理员。",
        )
        await self._send_email(email, subject, text_body, html_body)

    async def _send_email(
        self, to_email: str, subject: str, text_body: str, html_body: str
    ) -> None:
        # 在发送前做配置硬校验，避免进入 SMTP 连接后才暴露低可读错误。
        self._ensure_smtp_configured()

        message = EmailMessage()
        message["From"] = self.settings.smtp_from_address
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(text_body)
        # 保留 text + html 双格式，兼容不同邮箱客户端渲染能力。
        message.add_alternative(html_body, subtype="html")

        try:
            # smtplib 是阻塞 I/O，放入线程池避免阻塞事件循环。
            await asyncio.to_thread(self._send_via_smtp, message)
        except Exception as exc:  # noqa: BLE001
            # 日志保留最小可排障信息，不记录敏感凭据。
            logger.warning(
                "event=email.send.failed host=%s port=%s to=%s reason=%s",
                self.settings.smtp_host,
                self.settings.smtp_port,
                to_email,
                type(exc).__name__,
            )
            raise RuntimeError("email service unavailable") from exc

    def _send_via_smtp(self, message: EmailMessage) -> None:
        # 根据配置切换 SSL 与 STARTTLS，兼容常见 SMTP 服务商。
        if self.settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(
                self.settings.smtp_host,
                self.settings.smtp_port,
                timeout=10,
            ) as server:
                server.login(self.settings.smtp_username, self.settings.smtp_password)
                server.send_message(message)
            return

        with smtplib.SMTP(
            self.settings.smtp_host,
            self.settings.smtp_port,
            timeout=10,
        ) as server:
            server.starttls()
            server.login(self.settings.smtp_username, self.settings.smtp_password)
            server.send_message(message)

    def _ensure_smtp_configured(self) -> None:
        # 关键配置缺失时直接失败，避免出现“发送成功假象”。
        if (
            not self.settings.smtp_host
            or not self.settings.smtp_username
            or not self.settings.smtp_password
        ):
            raise RuntimeError("email service unavailable")

    def _build_html_email(
        self,
        *,
        title: str,
        lead: str,
        code: str | None,
        tip: str,
    ) -> str:
        # 验证码模块化插入，通知类邮件可复用同一模板但不展示 code 区块。
        code_block = ""
        if code:
            code_block = (
                '<div style="margin:20px 0;padding:12px 16px;background:#f3f7ff;'
                'border:1px solid #d7e4ff;border-radius:10px;text-align:center;">'
                f'<span style="font-size:28px;font-weight:700;letter-spacing:6px;'
                f"font-family:'IBM Plex Mono','Consolas',monospace;color:#1f4ea8;\">{code}</span>"
                "</div>"
            )

        return (
            "<!doctype html>"
            '<html lang="zh-CN">'
            '<head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" /></head>'
            "<body style=\"margin:0;padding:0;background:#eef3fb;font-family:'Microsoft YaHei',Arial,sans-serif;color:#1f2937;\">"
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="padding:24px 0;">'
            '<tr><td align="center">'
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:620px;background:#ffffff;border:1px solid #dfe8f7;border-radius:14px;overflow:hidden;">'
            '<tr><td style="padding:18px 24px;background:linear-gradient(120deg,#0f2f67,#1b4f9a);color:#ffffff;">'
            '<div style="font-size:12px;letter-spacing:1.2px;opacity:0.9;">AI STOCK LAB</div>'
            f'<div style="margin-top:6px;font-size:20px;font-weight:700;">{title}</div>'
            "</td></tr>"
            '<tr><td style="padding:24px;">'
            f'<p style="margin:0 0 14px;font-size:15px;line-height:1.7;">{lead}</p>'
            f"{code_block}"
            f'<p style="margin:0;color:#4b5563;font-size:14px;line-height:1.7;">{tip}</p>'
            '<hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0 14px;" />'
            '<p style="margin:0;color:#6b7280;font-size:12px;line-height:1.7;">'
            "这是一封系统自动发送的邮件，请勿直接回复。"
            "</p>"
            "</td></tr>"
            "</table>"
            "</td></tr>"
            "</table>"
            "</body></html>"
        )
