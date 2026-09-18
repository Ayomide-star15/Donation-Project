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
    def send_login_otp(self, recipient: str, code: str, expires_in_minutes: int) -> None: ...


class ConsoleEmailService:
    """Local-only adapter. Production configuration explicitly rejects this backend."""

    def send_login_otp(self, recipient: str, code: str, expires_in_minutes: int) -> None:
        logger.warning(
            "DEVELOPMENT EMAIL OTP for %s: %s (expires in %s minutes)",
            recipient,
            code,
            expires_in_minutes,
        )


class SmtpEmailService:
    def send_login_otp(self, recipient: str, code: str, expires_in_minutes: int) -> None:
        if not settings.SMTP_HOST:
            raise EmailDeliveryError("SMTP_HOST is not configured")

        message = EmailMessage()
        message["Subject"] = "Your LifeLink verification code"
        message["From"] = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>"
        message["To"] = recipient
        message.set_content(
            f"Your LifeLink verification code is {code}.\n\n"
            f"It expires in {expires_in_minutes} minutes.\n"
            "If you did not attempt to sign in, secure your account immediately."
        )
        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
                if settings.SMTP_USE_TLS:
                    smtp.starttls()
                if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                    smtp.login(
                        settings.SMTP_USERNAME,
                        settings.SMTP_PASSWORD.get_secret_value(),
                    )
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise EmailDeliveryError("Unable to deliver authentication email") from exc


@lru_cache
def get_email_service() -> EmailService:
    if settings.EMAIL_BACKEND == "console":
        return ConsoleEmailService()
    if settings.EMAIL_BACKEND == "smtp":
        return SmtpEmailService()
    raise RuntimeError(f"Unsupported EMAIL_BACKEND: {settings.EMAIL_BACKEND}")
