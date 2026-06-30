"""Application configuration using Pydantic Settings."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

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

    @model_validator(mode="after")
    def validate_production(self) -> Settings:
        """Validate production-specific settings."""
        if self.app_env == "production":
            if self.app_secret_key == "dev-secret-key-change-in-production":
                raise ValueError("Production secret key is invalid")
            if not self.cookie_secure:
                raise ValueError("Production cookies must be Secure")

        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError("SameSite=None requires Secure cookies")

        return self

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
