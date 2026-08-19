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

SUPPORTED_PROVIDERS = ("zen", "openai", "anthropic", "gemini", "ollama", "groq", "openrouter")


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
    if provider == "groq":
        if not settings.provider_configured("groq"):
            raise ProviderNotConfiguredError("groq")
        return ChatOpenAI(
            model=model,
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
            temperature=temperature,
        )
    if provider == "openrouter":
        if not settings.provider_configured("openrouter"):
            raise ProviderNotConfiguredError("openrouter")
        return ChatOpenAI(
            model=model,
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
            default_headers={"HTTP-Referer": "http://localhost:3001", "X-Title": "AIverse"},
            temperature=temperature,
        )
    if provider == "ollama":
        return ChatOllama(base_url=settings.OLLAMA_BASE_URL, model=model, temperature=temperature)
    raise AppError(f"Unknown provider '{provider}'", "UNKNOWN_PROVIDER")


def get_model_chain(
    provider: str, model: str, temperature: float = 0.7
) -> list[BaseChatModel]:
    """Ordered candidate models in auto-switch order: requested provider first,
    then the configured fallback, then Groq, then OpenRouter. Providers without
    keys are skipped; empty means none usable. Every consumer iterates the chain
    and tries each model until one responds."""
    if provider not in SUPPORTED_PROVIDERS:
        raise AppError(f"Unknown provider '{provider}'", "UNKNOWN_PROVIDER")
    candidates: list[tuple[str, str]] = [(provider, model)]
    if settings.FALLBACK_PROVIDER and settings.FALLBACK_MODEL:
        candidates.append((settings.FALLBACK_PROVIDER, settings.FALLBACK_MODEL))
    candidates.append(("groq", settings.GROQ_MODEL))
    candidates.append(("openrouter", settings.OPENROUTER_MODEL))
    seen: set[tuple[str, str]] = set()
    chain: list[BaseChatModel] = []
    for candidate_provider, candidate_model in candidates:
        key = (candidate_provider, candidate_model)
        if key in seen or not settings.provider_configured(candidate_provider):
            continue
        seen.add(key)
        chain.append(get_chat_model(candidate_provider, candidate_model, temperature))
    return chain


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
    if provider == "gemini":
        if not settings.provider_configured("gemini"):
            raise ProviderNotConfiguredError("gemini")
        return GeminiEmbeddings(model=settings.EMBEDDING_MODEL)
    if provider == "ollama":
        return OllamaEmbeddings(
            base_url=settings.OLLAMA_BASE_URL, model=settings.EMBEDDING_MODEL
        )
    raise AppError(f"Unknown embedding provider '{provider}'", "UNKNOWN_PROVIDER")


class GeminiEmbeddings(Embeddings):
    """Embeddings via the Google genai SDK (no official langchain wrapper)."""

    def __init__(self, model: str) -> None:
        from google.genai import Client, types

        self._model = model
        self._client = Client(api_key=get_settings().GEMINI_API_KEY)
        self._types = types

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        contents = [
            self._types.Content(parts=[self._types.Part(text=text)]) for text in texts
        ]
        result = self._client.models.embed_content(model=self._model, contents=contents)
        embeddings = result.embeddings or []
        return [list(item.values or []) for item in embeddings]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]