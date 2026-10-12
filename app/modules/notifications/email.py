import logging
import smtplib
import httpx
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

    def send_member_invite(
        self,
        recipient: str,
        full_name: str,
        community_name: str,
        inviter_name: str,
        invite_link: str,
        expires_in_days: int,
    ) -> None: ...

    def send_email_verification_link(
        self,
        recipient: str,
        first_name: str,
        verify_link: str,
        expires_in_hours: int,
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

    def send_member_invite(
        self,
        recipient: str,
        full_name: str,
        community_name: str,
        inviter_name: str,
        invite_link: str,
        expires_in_days: int,
    ) -> None:
        logger.warning(
            "DEVELOPMENT EMAIL MEMBER INVITE to %s:\n"
            "  Name: %s\n"
            "  Community: %s\n"
            "  Invited by: %s\n"
            "  Link: %s\n"
            "  Expires in %s days",
            recipient, full_name, community_name, inviter_name,
            invite_link, expires_in_days,
        )

    def send_email_verification_link(
        self,
        recipient: str,
        first_name: str,
        verify_link: str,
        expires_in_hours: int,
    ) -> None:
        logger.warning(
            "DEVELOPMENT EMAIL VERIFY LINK to %s (%s):\n"
            "  Link: %s\n"
            "  Expires in %s hours",
            recipient,
            first_name,
            verify_link,
            expires_in_hours,
        )


class SmtpEmailService:
    def send_login_otp(
        self, recipient: str, code: str, expires_in_minutes: int
    ) -> None:
        subject = "Your LIFESOURCE verification code"
        body = (
            f"Your LIFESOURCE verification code is {code}.\n\n"
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

    def send_member_invite(
        self,
        recipient: str,
        full_name: str,
        community_name: str,
        inviter_name: str,
        invite_link: str,
        expires_in_days: int,
    ) -> None:
        subject = f"You're invited to join {community_name} on LIFESOURCE"
        body = (
            f"Hi {full_name},\n\n"
            f"{inviter_name} has invited you to join {community_name} on LIFESOURCE.\n\n"
            f"Accept your invitation here:\n{invite_link}\n\n"
            f"This link expires in {expires_in_days} days.\n\n"
            f"— LIFESOURCE"
        )
        self._send(recipient, subject, body)

    def send_email_verification_link(
        self,
        recipient: str,
        first_name: str,
        verify_link: str,
        expires_in_hours: int,
    ) -> None:
        subject = "Verify your LIFESOURCE account"
        body = (
            f"Hi {first_name},\n\n"
            f"Welcome to LIFESOURCE. Please verify your email to continue "
            f"your donor registration.\n\n"
            f"Verify your email:\n{verify_link}\n\n"
            f"This link expires in {expires_in_hours} hours.\n\n"
            f"If you didn't create this account, you can ignore this email.\n\n"
            f"— LIFESOURCE"
        )
        self._send(recipient, subject, body)

class BrevoEmailService:
    """Sends transactional email via Brevo's HTTP API (works on Render)."""

    BASE_URL = "https://api.brevo.com/v3/smtp/email"

    def _send(
        self,
        recipient: str,
        recipient_name: str,
        subject: str,
        html: str,
    ) -> None:
        if not settings.BREVO_API_KEY:
            raise EmailDeliveryError("BREVO_API_KEY is not configured")

        headers = {
            "api-key": settings.BREVO_API_KEY.get_secret_value(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "sender": {
                "name": settings.EMAIL_FROM_NAME,
                "email": settings.EMAIL_FROM_ADDRESS,
            },
            "to": [{"email": recipient, "name": recipient_name or recipient}],
            "subject": subject,
            "htmlContent": html,
        }

        try:
            response = httpx.post(
                self.BASE_URL,
                json=payload,
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.exception("BREVO SEND FAILED to %s: %s", recipient, exc)
            raise EmailDeliveryError("Unable to deliver email via Brevo") from exc

    def send_login_otp(
        self, recipient: str, code: str, expires_in_minutes: int
    ) -> None:
        subject = "Your LIFESOURCE verification code"
        html = f"""
        <p>Your verification code is:</p>
        <h2 style="font-size: 32px; letter-spacing: 4px;">{code}</h2>
        <p>It expires in {expires_in_minutes} minutes.</p>
        <p>If you didn't try to sign in, secure your account immediately.</p>
        """
        self._send(recipient, recipient, subject, html)

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
        html = f"""
        <p>Hi {first_name},</p>
        <p>{inviter_name} has invited you to become the Community Admin
        for <b>{community_name}</b>.</p>
        <p><a href="{invite_link}">Accept invitation</a></p>
        <p>This link expires in {expires_in_days} days.</p>
        <p>— LIFESOURCE</p>
        """
        self._send(recipient, first_name, subject, html)

    def send_member_invite(
        self,
        recipient: str,
        full_name: str,
        community_name: str,
        inviter_name: str,
        invite_link: str,
        expires_in_days: int,
    ) -> None:
        subject = f"You're invited to join {community_name} on LIFESOURCE"
        html = f"""
        <p>Hi {full_name},</p>
        <p>{inviter_name} has invited you to join <b>{community_name}</b>.</p>
        <p><a href="{invite_link}">Accept invitation</a></p>
        <p>This link expires in {expires_in_days} days.</p>
        <p>— LIFESOURCE</p>
        """
        self._send(recipient, full_name, subject, html)

    def send_email_verification_link(
        self,
        recipient: str,
        first_name: str,
        verify_link: str,
        expires_in_hours: int,
    ) -> None:
        subject = "Verify your LIFESOURCE account"
        html = f"""
        <p>Hi {first_name},</p>
        <p>Welcome to LIFESOURCE. Please verify your email to continue your
        donor registration.</p>
        <p><a href="{verify_link}">Verify my email</a></p>
        <p>Or copy this link into your browser:<br>{verify_link}</p>
        <p>This link expires in {expires_in_hours} hours.</p>
        <p>If you didn't create this account, ignore this email.</p>
        <p>— LIFESOURCE</p>
        """
        self._send(recipient, first_name, subject, html)

@lru_cache
def get_email_service() -> EmailService:
    if settings.EMAIL_BACKEND == "console":
        return ConsoleEmailService()
    if settings.EMAIL_BACKEND == "smtp":
        return SmtpEmailService()
    if settings.EMAIL_BACKEND == "brevo":
        return BrevoEmailService()
    raise RuntimeError(f"Unsupported EMAIL_BACKEND: {settings.EMAIL_BACKEND}")