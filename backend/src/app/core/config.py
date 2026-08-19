# src/app/core/config.py
# Purpose: centralized pydantic-settings configuration; single source of truth for env vars.
# Exports: Settings, get_settings

import logging
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("app")
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )

    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # Providers
    ZEN_API_KEY: str = ""
    ZEN_BASE_URL: str = ""
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # Defaults
    DEFAULT_PROVIDER: str = "zen"
    DEFAULT_MODEL: str = "deepseek-v4-flash-free"
    TEMPERATURE: float = 0.7
    FALLBACK_PROVIDER: str = ""
    FALLBACK_MODEL: str = ""
    GROQ_MODEL: str = "qwen/qwen3.6-27b"
    OPENROUTER_MODEL: str = "z-ai/glm-5.2:free"

    # Embeddings
    EMBEDDING_PROVIDER: str = "gemini"
    EMBEDDING_MODEL: str = "gemini-embedding-2"

    # Runtime
    DATA_DIR: str = "./data"
    CORS_ORIGINS: str = "http://localhost:3001"
    MAX_UPLOAD_BYTES: int = 20 * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def data_dir_path(self) -> Path:
        return Path(self.DATA_DIR).resolve()

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir_path / "uploads"

    @property
    def vectorstore_dir(self) -> Path:
        return self.data_dir_path / "vectorstore"

    def provider_configured(self, provider: str) -> bool:
        if provider == "zen":
            return bool(self.ZEN_API_KEY and self.ZEN_BASE_URL)
        if provider == "openai":
            return bool(self.OPENAI_API_KEY)
        if provider == "anthropic":
            return bool(self.ANTHROPIC_API_KEY)
        if provider == "gemini":
            return bool(self.GEMINI_API_KEY)
        if provider == "groq":
            return bool(self.GROQ_API_KEY)
        if provider == "openrouter":
            return bool(self.OPENROUTER_API_KEY)
        return provider == "ollama"


@lru_cache
def get_settings() -> Settings:
    return Settings()
