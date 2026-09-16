import binascii
from functools import lru_cache

from cryptography.fernet import Fernet
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

    JWT_SECRET: SecretStr
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "lifelink-api"
    JWT_AUDIENCE: str = "lifelink-clients"
    ACCESS_TOKEN_MINUTES: int = 15
    REFRESH_TOKEN_DAYS: int = 30
    MFA_CHALLENGE_MINUTES: int = 5
    MFA_ENCRYPTION_KEY: SecretStr

    FRONTEND_URL: str = "http://localhost:3000"
    REFRESH_COOKIE_NAME: str = "lifelink_refresh"
    COOKIE_SECURE: bool = False
    COOKIE_DOMAIN: str | None = None

    @field_validator("COOKIE_DOMAIN", mode="before")
    @classmethod
    def empty_cookie_domain_is_none(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("JWT_SECRET")
    @classmethod
    def validate_jwt_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if len(secret) < 32 or secret.startswith("replace-with"):
            raise ValueError("JWT_SECRET must be a random value of at least 32 characters")
        return value

    @field_validator("MFA_ENCRYPTION_KEY")
    @classmethod
    def validate_mfa_key(cls, value: SecretStr) -> SecretStr:
        try:
            Fernet(value.get_secret_value().encode("utf-8"))
        except (binascii.Error, TypeError, ValueError) as exc:
            raise ValueError("MFA_ENCRYPTION_KEY must be a valid Fernet key") from exc
        return value

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.ENVIRONMENT.lower() == "production":
            if not self.COOKIE_SECURE:
                raise ValueError("COOKIE_SECURE must be true in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
