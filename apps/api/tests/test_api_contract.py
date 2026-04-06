from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api_contract import normalize_legacy_response


class ApiContractTests(unittest.TestCase):
    def test_non_priority_route_keeps_legacy_payload(self):
        payload = {"ok": True}

        result = normalize_legacy_response("/api/system/mode", 200, payload)

        self.assertEqual(payload, result)

    def test_priority_route_wraps_success_payload(self):
        result = normalize_legacy_response(
            "/api/signals/rank",
            200,
            {"ok": True, "count": 3, "trace_id": "trace-123"},
        )

        self.assertEqual({"ok": True, "count": 3}, result["data"])
        self.assertEqual("trace-123", result["meta"]["trace_id"])
        self.assertEqual("signals_rank", result["meta"]["source"])
        self.assertTrue(result["meta"]["updated_at"])
        self.assertTrue(result["meta"]["version"])

    def test_priority_route_wraps_error_payload(self):
        result = normalize_legacy_response(
            "/api/validation/settings/save",
            500,
            {"ok": False, "error": "save failed", "reason": "disk_full"},
        )

        self.assertEqual("http_500", result["error"]["error_code"])
        self.assertEqual("save failed", result["error"]["message"])
        self.assertEqual({"ok": False, "reason": "disk_full"}, result["error"]["details"])
        self.assertEqual("validation_settings_save", result["meta"]["source"])


if __name__ == "__main__":
    unittest.main()
