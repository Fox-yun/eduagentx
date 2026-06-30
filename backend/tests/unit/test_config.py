"""Unit tests for application configuration."""

import pytest

from app.config import Settings, clear_settings_cache


class TestSettings:
    def teardown_method(self):
        clear_settings_cache()

    def test_default_values(self):
        s = Settings(_env_file=None)
        # APP_ENV is set to "test" by conftest.py
        assert s.app_env == "test"
        assert s.cookie_secure is False
        assert s.cookie_samesite == "lax"
        assert s.log_level == "INFO"
        assert s.access_token_ttl_seconds == 900

    def test_llm_defaults(self):
        s = Settings(_env_file=None)
        assert "openai" in s.llm_api_base or "siliconflow" in s.llm_api_base
        assert s.llm_model  # has a default

    def test_is_production_false(self):
        s = Settings(app_env="development", _env_file=None)
        assert s.is_production is False

    def test_is_testing_true(self):
        s = Settings(app_env="test", _env_file=None)
        assert s.is_testing is True

    def test_is_testing_false(self):
        s = Settings(app_env="development", _env_file=None)
        assert s.is_testing is False

    def test_production_requires_secure_cookies(self):
        with pytest.raises(ValueError, match="Production cookies must be Secure"):
            Settings(
                app_env="production",
                app_secret_key="a-very-long-secret-key-for-production-use-64chars!!",
                cookie_secure=False,
                _env_file=None,
            )

    def test_samesite_none_requires_secure(self):
        with pytest.raises(ValueError, match="SameSite=None requires Secure"):
            Settings(cookie_samesite="none", cookie_secure=False, _env_file=None)

    def test_csrf_defaults(self):
        s = Settings(_env_file=None)
        assert s.csrf_cookie_name == "csrftoken"
        assert s.csrf_header_name == "X-CSRF-Token"

    def test_refresh_token_ttl(self):
        s = Settings(_env_file=None)
        assert s.refresh_token_ttl_seconds == 2_592_000  # 30 days

    def test_database_url_default(self):
        s = Settings(_env_file=None)
        assert "postgresql" in s.database_url

    def test_redis_url_default(self):
        s = Settings(_env_file=None)
        assert "redis://" in s.redis_url
