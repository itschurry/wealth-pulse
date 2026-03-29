from __future__ import annotations

from config.settings import (
    LLM_PROVIDER,
    NEMOTRON_MODEL,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_PLAYBOOK_MODEL,
    OPENAI_SIGNAL_MODEL,
)
from llm.providers.nemotron_ollama_provider import NemotronOllamaProvider
from llm.providers.openai_provider import OpenAIProvider
from llm.types import LLMProvider

_ALLOWED_PROVIDERS = {"openai", "nemotron"}
_MODEL_BY_PURPOSE = {
    "report": OPENAI_MODEL,
    "playbook": OPENAI_PLAYBOOK_MODEL,
    "signal": OPENAI_SIGNAL_MODEL,
    "quote": OPENAI_MODEL,
}

_provider_cache: LLMProvider | None = None
_validated_models: set[str] = set()


def get_provider_name() -> str:
    provider = (LLM_PROVIDER or "openai").strip().lower()
    if provider not in _ALLOWED_PROVIDERS:
        raise ValueError(
            f"Unsupported LLM_PROVIDER '{LLM_PROVIDER}'. Expected one of: openai, nemotron."
        )
    return provider


def get_model_for_task(task: str) -> str:
    provider = get_provider_name()
    if provider == "nemotron":
        if not NEMOTRON_MODEL:
            raise ValueError("LLM_PROVIDER=nemotron requires NEMOTRON_MODEL to be set.")
        return NEMOTRON_MODEL

    model = _MODEL_BY_PURPOSE.get(task)
    if not model:
        raise ValueError(f"Unknown LLM task '{task}'.")
    return model


def get_provider() -> LLMProvider:
    global _provider_cache

    if _provider_cache is not None:
        return _provider_cache

    provider = get_provider_name()
    if provider == "openai":
        if not OPENAI_API_KEY:
            raise ValueError("LLM_PROVIDER=openai requires OPENAI_API_KEY to be set.")
        _provider_cache = OpenAIProvider(api_key=OPENAI_API_KEY)
        return _provider_cache

    if not NEMOTRON_MODEL:
        raise ValueError("LLM_PROVIDER=nemotron requires NEMOTRON_MODEL to be set.")
    _provider_cache = NemotronOllamaProvider()
    return _provider_cache


def validate_provider_models(models: list[str]) -> None:
    pending_models = [model for model in models if model not in _validated_models]
    if not pending_models:
        return

    provider = get_provider()
    provider.validate(pending_models)
    _validated_models.update(pending_models)


def reset_provider_cache() -> None:
    global _provider_cache
    _provider_cache = None
    _validated_models.clear()

