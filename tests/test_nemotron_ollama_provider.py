from __future__ import annotations

import asyncio
import sys
import types
import unittest
from unittest.mock import MagicMock

from llm.providers.nemotron_ollama_provider import NemotronOllamaProvider


class NemotronOllamaProviderTests(unittest.TestCase):
    def test_validate_checks_model_presence(self):
        fake_client = MagicMock()
        fake_client.list.return_value = {"models": [{"name": "nemotron-3-super:latest"}]}
        fake_module = types.SimpleNamespace(Client=lambda: fake_client)

        with patch_modules(ollama=fake_module):
            provider = NemotronOllamaProvider()
            provider.validate(["nemotron-3-super"])

        fake_client.list.assert_called_once_with()

    def test_complete_json_reads_content_from_ollama_response(self):
        fake_client = MagicMock()
        fake_client.chat.return_value = {"message": {"content": '{"signals": []}'}}
        fake_module = types.SimpleNamespace(Client=lambda: fake_client)

        with patch_modules(ollama=fake_module):
            provider = NemotronOllamaProvider()
            content = asyncio.run(
                provider.complete_json(
                    system_prompt="system",
                    user_prompt="user",
                    model="nemotron-3-super",
                    temperature=0.1,
                    max_tokens=64,
                )
            )

        self.assertEqual('{"signals": []}', content)
        fake_client.chat.assert_called_once()


class patch_modules:
    def __init__(self, **modules: object) -> None:
        self._modules = modules
        self._originals: dict[str, object | None] = {}

    def __enter__(self) -> None:
        for name, module in self._modules.items():
            self._originals[name] = sys.modules.get(name)
            sys.modules[name] = module

    def __exit__(self, exc_type, exc, tb) -> None:
        for name, module in self._originals.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


if __name__ == "__main__":
    unittest.main()
