from __future__ import annotations

import asyncio


class NemotronOllamaProvider:
    name = "nemotron"

    def __init__(self) -> None:
        try:
            from ollama import Client
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError(
                "Nemotron provider requires the 'ollama' Python package to be installed."
            ) from exc

        self._client = Client()

    def validate(self, models: list[str]) -> None:
        if not models:
            raise ValueError("Nemotron provider validation requires at least one model.")

        try:
            listing = self._client.list()
        except Exception as exc:
            raise RuntimeError(
                "Ollama daemon is not reachable. Start Ollama before using LLM_PROVIDER=nemotron."
            ) from exc

        available_models = self._extract_model_names(listing)
        missing_models = [model for model in models if not self._has_model(available_models, model)]
        if missing_models:
            raise RuntimeError(
                "Ollama model is not installed: "
                + ", ".join(sorted(missing_models))
                + ". Pull the model on the host before running the app."
            )

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
            self._client.chat,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            options={"temperature": temperature, "num_predict": max_tokens},
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
            self._client.chat,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            format="json",
            options={"temperature": temperature, "num_predict": max_tokens},
        )
        return self._extract_content(response)

    @staticmethod
    def _extract_model_names(listing: object) -> set[str]:
        if isinstance(listing, dict):
            models = listing.get("models", [])
        else:
            models = getattr(listing, "models", [])

        names: set[str] = set()
        for item in models or []:
            if isinstance(item, dict):
                name = item.get("model") or item.get("name")
            else:
                name = getattr(item, "model", None) or getattr(item, "name", None)
            if name:
                names.add(str(name))
        return names

    @staticmethod
    def _has_model(available_models: set[str], requested_model: str) -> bool:
        requested_base = requested_model.split(":", 1)[0]
        for available_model in available_models:
            available_base = available_model.split(":", 1)[0]
            if requested_model == available_model or requested_model == available_base:
                return True
            if requested_base == available_model or requested_base == available_base:
                return True
        return False

    @staticmethod
    def _extract_content(response: object) -> str:
        if isinstance(response, dict):
            message = response.get("message", {})
            return str(message.get("content", "") or "")

        message = getattr(response, "message", None)
        if isinstance(message, dict):
            return str(message.get("content", "") or "")
        return str(getattr(message, "content", "") or "")
