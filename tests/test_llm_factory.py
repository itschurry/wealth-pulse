from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock, patch

sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *args, **kwargs: None))

import llm.factory as factory


class LLMFactoryTests(unittest.TestCase):
    def tearDown(self) -> None:
        factory.reset_provider_cache()

    def test_invalid_provider_raises_clear_error(self):
        with patch.object(factory, "LLM_PROVIDER", "bogus"):
            with self.assertRaisesRegex(ValueError, "Unsupported LLM_PROVIDER"):
                factory.get_provider_name()

    def test_openai_provider_requires_api_key(self):
        with patch.object(factory, "LLM_PROVIDER", "openai"), \
             patch.object(factory, "OPENAI_API_KEY", ""):
            factory.reset_provider_cache()
            with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY"):
                factory.get_provider()

    def test_nemotron_uses_same_model_for_all_tasks(self):
        with patch.object(factory, "LLM_PROVIDER", "nemotron"), \
             patch.object(factory, "NEMOTRON_MODEL", "nemotron-3-super"):
            self.assertEqual("nemotron-3-super", factory.get_model_for_task("report"))
            self.assertEqual("nemotron-3-super", factory.get_model_for_task("playbook"))
            self.assertEqual("nemotron-3-super", factory.get_model_for_task("signal"))
            self.assertEqual("nemotron-3-super", factory.get_model_for_task("quote"))

    def test_validate_provider_models_only_validates_new_models_once(self):
        provider = MagicMock()

        with patch.object(factory, "LLM_PROVIDER", "openai"), \
             patch.object(factory, "OPENAI_API_KEY", "test-key"), \
             patch.object(factory, "OpenAIProvider", return_value=provider):
            factory.reset_provider_cache()
            factory.validate_provider_models(["gpt-4o-mini"])
            factory.validate_provider_models(["gpt-4o-mini"])

        provider.validate.assert_called_once_with(["gpt-4o-mini"])


if __name__ == "__main__":
    unittest.main()
