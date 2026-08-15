# src/app/core/config.py
# Purpose: centralized pydantic-settings configuration; single source of truth for env vars.
# Exports: Settings, get_settings

import logging
from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("app")
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"
DEV_SECRET_KEY = "dev-only-insecure-key-change-me"
_SAMPLE_SECRET_KEY = "change-me-to-a-random-32+char-string"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )

    # App
    APP_ENV: str = "development"
    SECRET_KEY: str = DEV_SECRET_KEY
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/app.db"

    # Auth
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ISSUER: str = "nexus"
    JWT_ALGORITHM: str = "HS256"
    AUTH_RATE_LIMIT: str = "5/minute"
    REFRESH_RATE_LIMIT: str = "10/minute"
    COOKIE_NAME_ACCESS: str = "nexus_access"
    COOKIE_NAME_REFRESH: str = "nexus_refresh"

    # Providers
    ZEN_API_KEY: str = ""
    ZEN_BASE_URL: str = ""
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # Defaults
    DEFAULT_PROVIDER: str = "zen"
    DEFAULT_MODEL: str = "deepseek-v4-flash-free"

    # Embeddings
    EMBEDDING_PROVIDER: str = "zen"
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # Runtime
    DATA_DIR: str = "./data"
    CORS_ORIGINS: str = "http://localhost:3000"

    @model_validator(mode="after")
    def _validate_secret_key(self) -> "Settings":
        if self.APP_ENV == "production" and self.SECRET_KEY in (DEV_SECRET_KEY, _SAMPLE_SECRET_KEY):
            raise ValueError(
                "SECRET_KEY must be a random string of 32+ characters in production"
            )
        if self.APP_ENV != "production" and self.SECRET_KEY in (
            DEV_SECRET_KEY,
            _SAMPLE_SECRET_KEY,
        ):
            logger.warning("Using insecure default SECRET_KEY — set a random one in .env")
        return self

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def cookie_secure(self) -> bool:
        # Secure cookies require HTTPS; dev runs on plain http://localhost
        return self.is_production

    # Provider presence helpers (exposed to clients via /auth/me as booleans)
    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def data_dir_path(self) -> Path:
        return Path(self.DATA_DIR).resolve()

    def provider_configured(self, provider: str) -> bool:
        if provider == "zen":
            return bool(self.ZEN_API_KEY and self.ZEN_BASE_URL)
        if provider == "openai":
            return bool(self.OPENAI_API_KEY)
        if provider == "anthropic":
            return bool(self.ANTHROPIC_API_KEY)
        if provider == "gemini":
            return bool(self.GEMINI_API_KEY)
        return provider == "ollama"

    def configured_providers(self) -> dict[str, bool]:
        return {
            "zen": self.provider_configured("zen"),
            "openai": self.provider_configured("openai"),
            "anthropic": self.provider_configured("anthropic"),
            "gemini": self.provider_configured("gemini"),
            "ollama": self.provider_configured("ollama"),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()