from __future__ import annotations

from time import perf_counter

from loguru import logger

from llm.factory import get_model_for_task, get_provider, get_provider_name, validate_provider_models
from llm.types import LLMResponse


async def complete_text(
    *,
    system_prompt: str,
    user_prompt: str,
    task: str,
    temperature: float,
    max_tokens: int,
) -> LLMResponse:
    model = get_model_for_task(task)
    provider_name = get_provider_name()
    validate_provider_models([model])
    provider = get_provider()

    started_at = perf_counter()
    logger.info("LLM request start provider={} model={}", provider_name, model)
    try:
        content = await provider.complete_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        elapsed_ms = int((perf_counter() - started_at) * 1000)
        logger.error(
            "LLM request failed provider={} model={} elapsed_ms={} error={}",
            provider_name,
            model,
            elapsed_ms,
            exc,
        )
        raise

    elapsed_ms = int((perf_counter() - started_at) * 1000)
    logger.info(
        "LLM request done provider={} model={} elapsed_ms={}",
        provider_name,
        model,
        elapsed_ms,
    )
    return LLMResponse(content=content, provider=provider_name, model=model, elapsed_ms=elapsed_ms)


async def complete_json(
    *,
    system_prompt: str,
    user_prompt: str,
    task: str,
    temperature: float,
    max_tokens: int,
) -> LLMResponse:
    model = get_model_for_task(task)
    provider_name = get_provider_name()
    validate_provider_models([model])
    provider = get_provider()

    started_at = perf_counter()
    logger.info("LLM request start provider={} model={}", provider_name, model)
    try:
        content = await provider.complete_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        elapsed_ms = int((perf_counter() - started_at) * 1000)
        logger.error(
            "LLM request failed provider={} model={} elapsed_ms={} error={}",
            provider_name,
            model,
            elapsed_ms,
            exc,
        )
        raise

    elapsed_ms = int((perf_counter() - started_at) * 1000)
    logger.info(
        "LLM request done provider={} model={} elapsed_ms={}",
        provider_name,
        model,
        elapsed_ms,
    )
    return LLMResponse(content=content, provider=provider_name, model=model, elapsed_ms=elapsed_ms)


def validate_runtime_tasks(tasks: list[str]) -> None:
    models = list(dict.fromkeys(get_model_for_task(task) for task in tasks))
    validate_provider_models(models)
