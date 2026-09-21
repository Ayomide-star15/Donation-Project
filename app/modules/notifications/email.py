import logging
import smtplib
from email.message import EmailMessage
from functools import lru_cache
from typing import Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailDeliveryError(RuntimeError):
    pass


class EmailService(Protocol):
    def send_login_otp(
        self, recipient: str, code: str, expires_in_minutes: int
    ) -> None: ...

    def send_community_admin_invite(
        self,
        recipient: str,
        first_name: str,
        community_name: str,
        inviter_name: str,
        invite_link: str,
        expires_in_days: int,
    ) -> None: ...


class ConsoleEmailService:
    """Local-only adapter. Production configuration explicitly rejects this backend."""

    def send_login_otp(
        self, recipient: str, code: str, expires_in_minutes: int
    ) -> None:
        logger.warning(
            "DEVELOPMENT EMAIL OTP for %s: %s (expires in %s minutes)",
            recipient,
            code,
            expires_in_minutes,
        )

    def send_community_admin_invite(
        self,
        recipient: str,
        first_name: str,
        community_name: str,
        inviter_name: str,
        invite_link: str,
        expires_in_days: int,
    ) -> None:
        logger.warning(
            "DEVELOPMENT EMAIL INVITE to %s:\n"
            "  Community: %s\n"
            "  Invited by: %s\n"
            "  Link: %s\n"
            "  Expires in %s days",
            recipient,
            community_name,
            inviter_name,
            invite_link,
            expires_in_days,
        )


class SmtpEmailService:
    def send_login_otp(
        self, recipient: str, code: str, expires_in_minutes: int
    ) -> None:
        subject = "Your LifeLink verification code"
        body = (
            f"Your LifeLink verification code is {code}.\n\n"
            f"It expires in {expires_in_minutes} minutes.\n"
            "If you did not attempt to sign in, secure your account immediately."
        )
        self._send(recipient, subject, body)

    def send_community_admin_invite(
        self,
        recipient: str,
        first_name: str,
        community_name: str,
        inviter_name: str,
        invite_link: str,
        expires_in_days: int,
    ) -> None:
        subject = f"You're invited to administer {community_name} on LIFESOURCE"
        body = (
            f"Hi {first_name},\n\n"
            f"{inviter_name} has invited you to become the Community Admin for "
            f"{community_name} on LIFESOURCE.\n\n"
            f"Accept your invitation here:\n{invite_link}\n\n"
            f"This link expires in {expires_in_days} days.\n\n"
            f"If you weren't expecting this, you can safely ignore this email.\n\n"
            f"— LIFESOURCE"
        )
        self._send(recipient, subject, body)

    def _send(self, recipient: str, subject: str, body: str) -> None:
        if not settings.SMTP_HOST:
            raise EmailDeliveryError("SMTP_HOST is not configured")

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>"
        message["To"] = recipient
        message.set_content(body)

        try:
            with smtplib.SMTP(
                settings.SMTP_HOST, settings.SMTP_PORT, timeout=10
            ) as smtp:
                if settings.SMTP_USE_TLS:
                    smtp.starttls()
                if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                    smtp.login(
                        settings.SMTP_USERNAME,
                        settings.SMTP_PASSWORD.get_secret_value(),
                    )
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise EmailDeliveryError("Unable to deliver email") from exc


@lru_cache
def get_email_service() -> EmailService:
    if settings.EMAIL_BACKEND == "console":
        return ConsoleEmailService()
    if settings.EMAIL_BACKEND == "smtp":
        return SmtpEmailService()
    raise RuntimeError(f"Unsupported EMAIL_BACKEND: {settings.EMAIL_BACKEND}")