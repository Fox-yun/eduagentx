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
    """Get cached application settings."""
    return Settings()
