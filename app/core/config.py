from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "LifeLink API"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"
    DATABASE_URL: str

    OTP_PEPPER: SecretStr
    OTP_MODE: Literal["random", "fixed"] = "random"
    FIXED_OTP_CODE: str | None = None
    OTP_EXPIRY_MINUTES: int = 5
    OTP_MAX_ATTEMPTS: int = 5
    OTP_MAX_RESENDS: int = 3
    OTP_RESEND_COOLDOWN_SECONDS: int = 60

    SESSION_HOURS: int = 8
    SESSION_IDLE_MINUTES: int = 60

    FRONTEND_URL: str = "http://localhost:3000"
    API_PUBLIC_URL: str = "http://127.0.0.1:8000"
    SESSION_COOKIE_NAME: str = "lifelink_session"
    COOKIE_SECURE: bool = False
    COOKIE_DOMAIN: str | None = None

    EMAIL_BACKEND: str = "console"
    EMAIL_FROM_ADDRESS: str = "no-reply@lifelink.local"
    EMAIL_FROM_NAME: str = "LifeLink"
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 1025
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: SecretStr | None = None
    SMTP_USE_TLS: bool = False

    @field_validator("COOKIE_DOMAIN", mode="before")
    @classmethod
    def empty_cookie_domain_is_none(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def use_psycopg3_driver(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @field_validator("OTP_PEPPER")
    @classmethod
    def validate_otp_pepper(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if len(secret) < 32 or secret.startswith("replace-with"):
            raise ValueError("OTP_PEPPER must be a random value of at least 32 characters")
        return value

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.OTP_MODE == "fixed":
            if self.ENVIRONMENT.lower() == "production":
                raise ValueError("Fixed OTP mode is forbidden in production")
            if (
                self.FIXED_OTP_CODE is None
                or len(self.FIXED_OTP_CODE) != 6
                or not self.FIXED_OTP_CODE.isdigit()
            ):
                raise ValueError("FIXED_OTP_CODE must contain exactly six digits")
        if self.ENVIRONMENT.lower() == "production":
            if not self.COOKIE_SECURE:
                raise ValueError("COOKIE_SECURE must be true in production")
            if self.EMAIL_BACKEND == "console":
                raise ValueError("Console email delivery is forbidden in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
