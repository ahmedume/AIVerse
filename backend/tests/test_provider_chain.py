# tests/test_provider_chain.py
# Purpose: ordered auto-switch chain — default first, then fallback, groq, openrouter.

import pytest

from app.core import llm
from app.core.exceptions import AppError, ProviderNotConfiguredError


class _FakeSettings:
    FALLBACK_PROVIDER = "zen"
    FALLBACK_MODEL = "deepseek-v4-flash-free"
    GROQ_MODEL = "llama-3.3-70b-versatile"
    OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
    ZEN_API_KEY = "k"
    ZEN_BASE_URL = "http://zen.test"
    GEMINI_API_KEY = "k"
    GROQ_API_KEY = ""
    OPENROUTER_API_KEY = ""

    def provider_configured(self, provider: str) -> bool:  # noqa: PLR0911
        if provider == "zen":
            return bool(self.ZEN_API_KEY and self.ZEN_BASE_URL)
        if provider == "gemini":
            return bool(self.GEMINI_API_KEY)
        if provider == "groq":
            return bool(self.GROQ_API_KEY)
        if provider == "openrouter":
            return bool(self.OPENROUTER_API_KEY)
        return False


def _name(m) -> str:
    return getattr(m, "model", "") or getattr(m, "model_name", "")


def _chain(monkeypatch, default="gemini", model="m1"):
    fake = _FakeSettings()
    monkeypatch.setattr(llm, "settings", fake)
    return [_name(m) for m in llm.get_model_chain(default, model)], fake


def test_chain_order_primary_fallback_then_extra(monkeypatch):
    models, fake = _chain(monkeypatch)
    assert models == ["m1", "deepseek-v4-flash-free"]


def test_chain_skips_unconfigured_groq_and_openrouter(monkeypatch):
    models, fake = _chain(monkeypatch)
    assert "llama-3.3-70b-versatile" not in models
    assert "meta-llama/llama-3.3-70b-instruct:free" not in models
    fake.GROQ_API_KEY = "k"
    models = [_name(m) for m in llm.get_model_chain("gemini", "m1")]
    assert models == ["m1", "deepseek-v4-flash-free", "llama-3.3-70b-versatile"]
    fake.OPENROUTER_API_KEY = "k"
    models = [_name(m) for m in llm.get_model_chain("gemini", "m1")]
    assert models == [
        "m1",
        "deepseek-v4-flash-free",
        "llama-3.3-70b-versatile",
        "meta-llama/llama-3.3-70b-instruct:free",
    ]


def test_chain_dedupes_when_fallback_matches_primary(monkeypatch):
    fake = _FakeSettings()
    monkeypatch.setattr(llm, "settings", fake)
    models = [_name(m) for m in llm.get_model_chain("zen", "deepseek-v4-flash-free")]
    assert models == ["deepseek-v4-flash-free"]


def test_chain_skips_unconfigured_primary(monkeypatch):
    fake = _FakeSettings()
    fake.GEMINI_API_KEY = ""
    fake.GROQ_API_KEY = "k"
    monkeypatch.setattr(llm, "settings", fake)
    models = [_name(m) for m in llm.get_model_chain("gemini", "m1")]
    assert models == ["deepseek-v4-flash-free", "llama-3.3-70b-versatile"]


def test_unknown_provider_raises(monkeypatch):
    fake = _FakeSettings()
    monkeypatch.setattr(llm, "settings", fake)
    with pytest.raises(AppError):
        llm.get_model_chain("nope", "m1")


def test_get_chat_model_groq_requires_key(monkeypatch):
    fake = _FakeSettings()
    monkeypatch.setattr(llm, "settings", fake)
    with pytest.raises(ProviderNotConfiguredError):
        llm.get_chat_model("groq", "llama-3.3-70b-versatile")