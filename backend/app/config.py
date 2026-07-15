"""Application configuration using Pydantic Settings."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import unquote, urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: Literal["development", "test", "staging", "production"] = Field(
        default="development",
        description="Application environment",
    )
    app_secret_key: str = Field(
        default="dev-secret-key-change-in-production",
        min_length=32,
        description="Secret key for signing JWT tokens",
    )

    # Database (PostgreSQL only)
    database_url: str = Field(
        default="postgresql+asyncpg://eduagentx:eduagentx@localhost:5432/eduagentx",
        description="PostgreSQL async connection URL",
    )

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )

    # Cookie configuration
    cookie_secure: bool = Field(default=False, description="Set Secure flag on cookies")
    cookie_samesite: Literal["lax", "strict", "none"] = Field(default="lax", description="SameSite cookie attribute")
    cookie_domain: str | None = Field(default=None, description="Cookie domain")

    # CSRF
    csrf_cookie_name: str = Field(default="csrftoken", description="CSRF cookie name")
    csrf_header_name: str = Field(default="X-CSRF-Token", description="CSRF header name")

    # Token TTL
    access_token_ttl_seconds: int = Field(default=900, description="Access token TTL in seconds")
    refresh_token_ttl_seconds: int = Field(default=2_592_000, description="Refresh token TTL in seconds (30 days)")

    # CORS
    cors_allowed_origins: list[str] = Field(
        default=["http://localhost:5173"],
        description="Allowed CORS origins",
    )

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Log level",
    )

    # E2E testing
    enable_e2e_routes: bool = Field(
        default=False,
        description="Enable E2E test-only routes. Requires APP_ENV=test.",
    )
    e2e_token: str | None = Field(
        default=None,
        description="Token required for E2E test routes. Only used when APP_ENV=test and ENABLE_E2E_ROUTES=true.",
    )

    # LLM / AI Agent
    llm_api_base: str = Field(
        default="https://api.siliconflow.cn/v1",
        description="OpenAI-compatible API base URL",
    )
    llm_api_key: str = Field(
        default="",
        description="API key for LLM provider",
    )
    llm_model: str = Field(
        default="deepseek-ai/DeepSeek-V4-Pro",
        description="Model name for LLM calls",
    )
    tts_model: str = Field(
        default="FunAudioLLM/CosyVoice2-0.5B",
        description="SiliconFlow text-to-speech model",
    )
    tts_voice: str = Field(
        default="FunAudioLLM/CosyVoice2-0.5B:anna",
        description="SiliconFlow text-to-speech voice",
    )
    tts_speed: float = Field(default=1.0, ge=0.25, le=4.0)
    tts_timeout_seconds: float = Field(default=180.0, gt=0)

    # Object Storage (MinIO)
    minio_endpoint: str | None = Field(
        default=None,
        description="MinIO endpoint (e.g. 'localhost:9000'). If empty, uses in-memory storage.",
    )
    minio_access_key: str = Field(default="minioadmin", description="MinIO access key")
    minio_secret_key: str = Field(default="minioadmin", description="MinIO secret key")
    minio_bucket: str = Field(default="eduagentx", description="MinIO bucket name")
    minio_secure: bool = Field(default=False, description="Use HTTPS for MinIO connection")
    local_storage_path: str = Field(
        default=".local-storage",
        description="Persistent filesystem object storage used outside tests when MinIO is not configured",
    )

    # Email & SMTP Settings
    smtp_host: str | None = Field(default=None, description="SMTP server host")
    smtp_port: int = Field(default=1025, description="SMTP server port")
    smtp_username: str | None = Field(default=None, description="SMTP username")
    smtp_password: str | None = Field(default=None, description="SMTP password")
    smtp_use_tls: bool = Field(default=False, description="Use SSL/TLS for SMTP connection")
    smtp_start_tls: bool = Field(default=False, description="Use STARTTLS for SMTP connection")
    smtp_timeout_seconds: float = Field(default=10.0, description="SMTP timeout in seconds")
    smtp_from_email: str = Field(default="noreply@eduagentx.local", description="Sender email address")
    smtp_from_name: str = Field(default="EduAgentX", description="Sender display name")
    public_frontend_url: str = Field(default="http://127.0.0.1:8081", description="Public frontend URL for links")
    email_verification_ttl_seconds: int = Field(default=86400, description="Verification token TTL")
    password_reset_ttl_seconds: int = Field(default=1800, description="Password reset token TTL")
    email_auto_verify: bool = Field(default=False, description="Auto verify email in development")
    email_outbox_encryption_key: str = Field(
        default="dev-email-outbox-encryption-key-32b=",
        description="AEAD key for outbox payload encryption",
    )

    # Known insecure placeholder values that must not be used in production
    _INSECURE_PLACEHOLDERS: set[str] = {
        "dev-secret-key-change-in-production",
        "dev-secret-key-replace-with-at-least-64-random-characters-in-production",
        "replace-with-at-least-64-random-characters",
        "CHANGE_ME_TO_64_PLUS_RANDOM_CHARACTERS",
        "dev-email-outbox-encryption-key-32b=",
        "replace-with-a-separate-random-key-32b=",
        "CHANGE_ME_TO_32_PLUS_RANDOM_CHARACTERS",
    }
    _INSECURE_PASSWORDS: set[str] = {
        "eduagentx",
        "minioadmin",
        "password",
        "CHANGE_ME_TO_STRONG_PASSWORD",
        "CHANGE_ME_TO_STRONG_ACCESS_KEY",
        "CHANGE_ME_TO_STRONG_SECRET_KEY",
        "CHANGE_ME_TO_REDIS_PASSWORD",
    }

    @model_validator(mode="after")
    def validate_production(self) -> Settings:
        """Validate production-specific settings."""
        if self.app_env == "production":
            # Reject placeholder / short secret keys
            if self.app_secret_key in self._INSECURE_PLACEHOLDERS:
                raise ValueError(
                    "APP_SECRET_KEY must be replaced with a real random value in production. "
                    "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
                )
            if len(self.app_secret_key) < 64:
                raise ValueError(
                    "APP_SECRET_KEY must be at least 64 characters in production "
                    f"(current: {len(self.app_secret_key)} characters)"
                )

            # Cookies must be secure
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production")

            # Reject default / placeholder database passwords
            db_password = self._extract_password_from_url(self.database_url)
            if db_password in self._INSECURE_PASSWORDS:
                raise ValueError(
                    "DATABASE_URL contains a default or placeholder password. "
                    "Set a strong POSTGRES_PASSWORD in production."
                )

            # Reject default MinIO credentials
            if self.minio_access_key in self._INSECURE_PASSWORDS:
                raise ValueError(
                    "MINIO_ACCESS_KEY must not use default value in production."
                )
            if self.minio_secret_key in self._INSECURE_PASSWORDS:
                raise ValueError(
                    "MINIO_SECRET_KEY must not use default value in production."
                )

            # Reject default / placeholder Redis passwords
            redis_password = self._extract_password_from_url(self.redis_url)
            if redis_password is None:
                raise ValueError(
                    "REDIS_URL must include a password in production. "
                    "Set a strong REDIS_PASSWORD."
                )
            if redis_password in self._INSECURE_PASSWORDS:
                raise ValueError(
                    "REDIS_URL contains a default or placeholder password. "
                    "Set a strong REDIS_PASSWORD in production."
                )

            # Reject placeholder outbox encryption key
            if self.email_outbox_encryption_key in self._INSECURE_PLACEHOLDERS:
                raise ValueError(
                    "EMAIL_OUTBOX_ENCRYPTION_KEY must be replaced with a real random value in production. "
                    "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
                )
            if len(self.email_outbox_encryption_key) < 32:
                raise ValueError(
                    "EMAIL_OUTBOX_ENCRYPTION_KEY must be at least 32 characters in production."
                )

            # Reject HTTP public URLs
            if self.public_frontend_url.startswith("http://") and not self._is_localhost_url(
                self.public_frontend_url
            ):
                raise ValueError(
                    "PUBLIC_FRONTEND_URL must use HTTPS in production "
                    f"(current: {self.public_frontend_url})"
                )

            # CORS must not be wildcard
            if "*" in self.cors_allowed_origins:
                raise ValueError(
                    "CORS_ALLOWED_ORIGINS must not contain '*' in production. "
                    "Specify explicit origins."
                )

        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError("SameSite=None requires Secure cookies")

        return self

    @staticmethod
    def _extract_password_from_url(url: str) -> str | None:
        """Extract password from a database/redis URL."""
        parsed = urlparse(url)
        if parsed.password:
            return unquote(parsed.password)
        return None

    @staticmethod
    def _is_localhost_url(url: str) -> bool:
        """Check if a URL points to localhost."""
        parsed = urlparse(url)
        return parsed.hostname in ("localhost", "127.0.0.1", "::1")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_testing(self) -> bool:
        return self.app_env == "test"


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings.

    Call get_settings.cache_clear() in tests to reset.
    """
    return Settings()


def clear_settings_cache() -> None:
    """Clear the settings cache. Useful in tests."""
    get_settings.cache_clear()
