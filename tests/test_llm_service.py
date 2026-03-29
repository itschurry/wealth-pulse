from __future__ import annotations

import asyncio
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


class _DummyLogger:
    def info(self, *args, **kwargs) -> None:
        pass

    def error(self, *args, **kwargs) -> None:
        pass


sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *args, **kwargs: None))
sys.modules.setdefault("loguru", types.SimpleNamespace(logger=_DummyLogger()))

import llm.service as service


class LLMServiceTests(unittest.TestCase):
    def test_complete_text_returns_metadata_and_logs_provider(self):
        provider = SimpleNamespace(complete_text=AsyncMock(return_value="hello world"))

        with patch("llm.service.get_model_for_task", return_value="nemotron-3-super"), \
             patch("llm.service.get_provider_name", return_value="nemotron"), \
             patch("llm.service.validate_provider_models"), \
             patch("llm.service.get_provider", return_value=provider), \
             patch.object(service.logger, "info") as mock_info:
            result = asyncio.run(
                service.complete_text(
                    system_prompt="system",
                    user_prompt="user",
                    task="report",
                    temperature=0.2,
                    max_tokens=256,
                )
            )

        self.assertEqual("hello world", result.content)
        self.assertEqual("nemotron", result.provider)
        self.assertEqual("nemotron-3-super", result.model)
        self.assertGreaterEqual(result.elapsed_ms, 0)
        provider.complete_text.assert_awaited_once()
        self.assertTrue(
            any(
                call.args[:2] == ("LLM request start provider={} model={}", "nemotron")
                and call.args[2] == "nemotron-3-super"
                for call in mock_info.call_args_list
            )
        )

    def test_complete_json_uses_provider_json_method(self):
        provider = SimpleNamespace(complete_json=AsyncMock(return_value='{"ok":true}'))

        with patch("llm.service.get_model_for_task", return_value="gpt-4o-mini"), \
             patch("llm.service.get_provider_name", return_value="openai"), \
             patch("llm.service.validate_provider_models"), \
             patch("llm.service.get_provider", return_value=provider):
            result = asyncio.run(
                service.complete_json(
                    system_prompt="system",
                    user_prompt="user",
                    task="signal",
                    temperature=0.1,
                    max_tokens=128,
                )
            )

        self.assertEqual('{"ok":true}', result.content)
        provider.complete_json.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
