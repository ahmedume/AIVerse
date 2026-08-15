# src/app/core/llm.py
# Purpose: provider factory — chat models + embeddings, guarded by configured keys.
# Exports: SUPPORTED_PROVIDERS, get_chat_model, get_embeddings

from langchain_anthropic import ChatAnthropic
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.core.config import get_settings
from app.core.exceptions import AppError, ProviderNotConfiguredError

settings = get_settings()

SUPPORTED_PROVIDERS = ("zen", "openai", "anthropic", "gemini", "ollama")


def get_chat_model(provider: str, model: str, temperature: float = 0.7) -> BaseChatModel:
    if provider == "zen":
        if not settings.provider_configured("zen"):
            raise ProviderNotConfiguredError("zen")
        return ChatOpenAI(
            model=model,
            api_key=settings.ZEN_API_KEY,
            base_url=settings.ZEN_BASE_URL,
            temperature=temperature,
        )
    if provider == "openai":
        if not settings.provider_configured("openai"):
            raise ProviderNotConfiguredError("openai")
        return ChatOpenAI(
            model=model, api_key=settings.OPENAI_API_KEY, temperature=temperature
        )
    if provider == "anthropic":
        if not settings.provider_configured("anthropic"):
            raise ProviderNotConfiguredError("anthropic")
        return ChatAnthropic(
            model=model, api_key=settings.ANTHROPIC_API_KEY, temperature=temperature
        )
    if provider == "gemini":
        if not settings.provider_configured("gemini"):
            raise ProviderNotConfiguredError("gemini")
        return ChatGoogleGenerativeAI(
            model=model, api_key=settings.GEMINI_API_KEY, temperature=temperature
        )
    if provider == "ollama":
        return ChatOllama(base_url=settings.OLLAMA_BASE_URL, model=model, temperature=temperature)
    raise AppError(f"Unknown provider '{provider}'", "UNKNOWN_PROVIDER")


def get_embeddings() -> Embeddings:
    provider = settings.EMBEDDING_PROVIDER
    if provider in ("zen", "openai"):
        api_key = settings.ZEN_API_KEY if provider == "zen" else settings.OPENAI_API_KEY
        base_url = settings.ZEN_BASE_URL if provider == "zen" else None
        if not api_key:
            raise ProviderNotConfiguredError(provider)
        return OpenAIEmbeddings(
            model=settings.EMBEDDING_MODEL, openai_api_key=api_key, openai_api_base=base_url
        )
    if provider == "ollama":
        return OllamaEmbeddings(
            base_url=settings.OLLAMA_BASE_URL, model=settings.EMBEDDING_MODEL
        )
    raise AppError(f"Unknown embedding provider '{provider}'", "UNKNOWN_PROVIDER")