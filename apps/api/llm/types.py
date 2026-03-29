from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LLMResponse:
    content: str
    provider: str
    model: str
    elapsed_ms: int


class LLMProvider(Protocol):
    name: str

    def validate(self, models: list[str]) -> None:
        ...

    async def complete_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        ...

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        ...

