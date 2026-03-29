from __future__ import annotations

import asyncio


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError(
                "OpenAI provider requires the 'openai' package to be installed."
            ) from exc

        self._client = OpenAI(api_key=api_key)

    def validate(self, models: list[str]) -> None:
        if not models:
            raise ValueError("OpenAI provider validation requires at least one model.")

    async def complete_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        response = await asyncio.to_thread(
            self._client.chat.completions.create,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_completion_tokens=max_tokens,
        )
        return self._extract_content(response)

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        response = await asyncio.to_thread(
            self._client.chat.completions.create,
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_completion_tokens=max_tokens,
        )
        return self._extract_content(response)

    @staticmethod
    def _extract_content(response: object) -> str:
        choices = getattr(response, "choices", None)
        if not choices:
            return ""
        message = getattr(choices[0], "message", None)
        return getattr(message, "content", "") or ""

