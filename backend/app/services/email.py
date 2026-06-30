"""Email service and transport implementations for authentication emails."""

from __future__ import annotations

import base64
import hashlib
import html
import json
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Protocol

import aiosmtplib
import structlog
from cryptography.fernet import Fernet

from app.config import get_settings

logger = structlog.get_logger()


class EmailDeliveryError(Exception):
    """Raised when email dispatch via SMTP fails."""


@dataclass
class EmailMessageData:
    """Dataclass holding email recipient and content details."""

    to_email: str
    to_name: str | None
    subject: str
    text_body: str
    html_body: str
    message_id: str | None = None


class EmailTransport(Protocol):
    """Protocol for sending email messages."""

    async def send(self, message: EmailMessageData) -> None:
        """Send an email message."""
        ...


class SmtpEmailTransport:
    """SMTP transport implementation using aiosmtplib."""

    async def send(self, message: EmailMessageData) -> None:
        """Send email via SMTP server configured in settings."""
        settings = get_settings()
        if not settings.smtp_host:
            logger.warning("smtp_host_not_configured_skipping_send", recipient=message.to_email)
            return

        mime_msg = MIMEMultipart("alternative")
        mime_msg["Subject"] = message.subject
        sender = (
            f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
            if settings.smtp_from_name
            else settings.smtp_from_email
        )
        mime_msg["From"] = sender
        recipient = f"{message.to_name} <{message.to_email}>" if message.to_name else message.to_email
        mime_msg["To"] = recipient

        if message.message_id:
            mime_msg["Message-ID"] = message.message_id

        mime_msg.attach(MIMEText(message.text_body, "plain", "utf-8"))
        mime_msg.attach(MIMEText(message.html_body, "html", "utf-8"))

        try:
            await aiosmtplib.send(
                mime_msg,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_username or None,
                password=settings.smtp_password or None,
                use_tls=settings.smtp_use_tls,
                start_tls=settings.smtp_start_tls,
                timeout=settings.smtp_timeout_seconds,
            )
            logger.info("email_sent_successfully", recipient=message.to_email)
        except Exception as e:
            logger.error("smtp_delivery_failed", recipient=message.to_email, error=str(e))
            raise EmailDeliveryError(f"Failed to send email to {message.to_email}: {e}") from e


def _get_fernet(key_str: str) -> Fernet:
    """Validate and return Fernet cipher suite from key_str."""
    try:
        return Fernet(key_str.encode("utf-8"))
    except Exception:
        # Fallback for arbitrary test strings
        key_bytes = hashlib.sha256(key_str.encode("utf-8")).digest()
        fernet_key = base64.urlsafe_b64encode(key_bytes)
        return Fernet(fernet_key)


def encrypt_email_payload(data: dict) -> str:
    """Encrypt sensitive outbox payload data."""
    settings = get_settings()
    fernet = _get_fernet(settings.email_outbox_encryption_key)
    raw_json = json.dumps(data).encode("utf-8")
    return fernet.encrypt(raw_json).decode("utf-8")


def decrypt_email_payload(encrypted_str: str) -> dict:
    """Decrypt outbox payload data."""
    settings = get_settings()
    fernet = _get_fernet(settings.email_outbox_encryption_key)
    decrypted_bytes = fernet.decrypt(encrypted_str.encode("utf-8"))
    res = json.loads(decrypted_bytes.decode("utf-8"))
    return res if isinstance(res, dict) else {}


class EmailService:
    """High-level email service for formatting and dispatching auth emails."""

    def __init__(self, transport: EmailTransport | None = None) -> None:
        self.transport = transport or SmtpEmailTransport()

    async def send_verification_email(
        self,
        to_email: str,
        raw_token: str,
        to_name: str | None = None,
        message_id: str | None = None,
    ) -> None:
        """Format and send email verification message."""
        settings = get_settings()
        safe_name = html.escape(to_name or to_email.split("@")[0])
        verify_url = f"{settings.public_frontend_url}/auth/verify-email?token={raw_token}"
        hours = settings.email_verification_ttl_seconds // 3600

        subject = "【EduAgentX】验证您的电子邮箱"
        text_body = (
            f"尊敬的 {to_name or '用户'}，您好！\n\n"
            f"请点击下方链接完成邮箱验证（链接在 {hours} 小时内有效）：\n"
            f"{verify_url}\n\n"
            f"如果您未请求注册或验证该账户，请忽略此邮件。\n"
        )
        html_body = (
            f"<div style='font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;'>"
            f"<h2>验证您的电子邮箱</h2>"
            f"<p>尊敬的 <strong>{safe_name}</strong>，您好！</p>"
            f"<p>欢迎使用 EduAgentX 智能学习平台。请点击下方按钮完成邮箱验证（有效期 {hours} 小时）：</p>"
            f"<p style='margin: 30px 0;'><a href='{verify_url}' style='background-color: #3b82f6; color: white; "
            f"padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold;'>验证电子邮箱</a></p>"
            f"<p style='color: #6b7280; font-size: 14px;'>若按钮无法点击，请复制并打开以下链接：<br>{verify_url}</p>"
            f"<hr style='border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;' />"
            f"<p style='color: #9ca3af; font-size: 12px;'>若您未发起此请求，请忽略本邮件。</p>"
            f"</div>"
        )

        message = EmailMessageData(
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            message_id=message_id,
        )
        await self.transport.send(message)

    async def send_password_reset_email(
        self,
        to_email: str,
        raw_token: str,
        to_name: str | None = None,
        message_id: str | None = None,
    ) -> None:
        """Format and send password reset message."""
        settings = get_settings()
        safe_name = html.escape(to_name or to_email.split("@")[0])
        reset_url = f"{settings.public_frontend_url}/auth/reset-password?token={raw_token}"
        minutes = settings.password_reset_ttl_seconds // 60

        subject = "【EduAgentX】重置您的密码"
        text_body = (
            f"尊敬的 {to_name or '用户'}，您好！\n\n"
            f"我们收到了重置您 EduAgentX 账户密码的请求。请点击下方链接设置新密码（链接在 {minutes} 分钟内有效）：\n"
            f"{reset_url}\n\n"
            f"如果您未请求重置密码，请忽略此邮件，您的密码将保持不变。\n"
        )
        html_body = (
            f"<div style='font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;'>"
            f"<h2>重置您的密码</h2>"
            f"<p>尊敬的 <strong>{safe_name}</strong>，您好！</p>"
            f"<p>我们收到了重置您 EduAgentX 账户密码的请求。请点击下方按钮设置新密码（有效期 {minutes} 分钟）：</p>"
            f"<p style='margin: 30px 0;'><a href='{reset_url}' style='background-color: #ef4444; color: white; "
            f"padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold;'>重置密码</a></p>"
            f"<p style='color: #6b7280; font-size: 14px;'>若按钮无法点击，请复制并打开以下链接：<br>{reset_url}</p>"
            f"<hr style='border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;' />"
            f"<p style='color: #9ca3af; font-size: 12px;'>若您未发起此请求，请忽略本邮件，您的密码将保持安全。</p>"
            f"</div>"
        )

        message = EmailMessageData(
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            message_id=message_id,
        )
        await self.transport.send(message)
