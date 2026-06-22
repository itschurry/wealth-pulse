from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from broker.kis_client import KISClient, _read_json_file, _write_json_file


class KISClientTests(unittest.TestCase):
    def test_access_token_issue_limit_is_rate_limit_error(self) -> None:
        payload = {
            "error_code": "EGW00133",
            "error_description": "접근토큰 발급 잠시 후 다시 시도하세요(1분당 1회)",
        }

        self.assertTrue(KISClient._is_rate_limit_error(payload))

    def test_write_json_file_creates_parent_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "token.json"

            _write_json_file(path, {"access_token": "abc"})

            self.assertEqual(_read_json_file(path), {"access_token": "abc"})


if __name__ == "__main__":
    unittest.main()
