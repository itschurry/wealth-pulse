from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.report_cache import get_cached_payload


class ReportsCacheHelperTests(unittest.TestCase):
    def test_returns_recent_cached_payload_without_reloading(self):
        cache_bucket = {"data": {"cached": True}, "ts": time.time()}

        result = get_cached_payload(cache_bucket, lambda: {"loaded": True}, {"error": True}, ttl=60.0)

        self.assertEqual({"cached": True}, result)
        self.assertEqual({"data": {"cached": True}, "ts": cache_bucket["ts"]}, cache_bucket)

    def test_populates_cache_when_loader_returns_data(self):
        cache_bucket = {"data": None, "ts": 0.0}

        result = get_cached_payload(cache_bucket, lambda: {"loaded": True}, {"error": True}, ttl=60.0)

        self.assertEqual({"loaded": True}, result)
        self.assertEqual({"loaded": True}, cache_bucket["data"])
        self.assertGreater(cache_bucket["ts"], 0.0)

    def test_missing_payload_is_not_written_back_to_cache(self):
        cache_bucket = {"data": None, "ts": 0.0}

        result = get_cached_payload(cache_bucket, lambda: {}, {"error": True}, ttl=60.0)

        self.assertEqual({"error": True}, result)
        self.assertIsNone(cache_bucket["data"])
        self.assertEqual(0.0, cache_bucket["ts"])


if __name__ == "__main__":
    unittest.main()
