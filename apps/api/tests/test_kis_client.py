from __future__ import annotations

import json
import time
import unittest
from pathlib import Path
import sys
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import types

_INSTALLED_STUBS: list[str] = []

if "config.settings" not in sys.modules:
    settings_stub = types.ModuleType("config.settings")
    settings_stub.KIS_ACCOUNT_ACNT_PRDT_CD = ""
    settings_stub.KIS_ACCOUNT_CANO = ""
    settings_stub.KIS_APP_KEY = "app-key"
    settings_stub.KIS_APP_SECRET = "app-secret"
    settings_stub.KIS_BASE_URL = "https://example.com"
    settings_stub.LOGS_DIR = Path("/tmp")
    sys.modules["config.settings"] = settings_stub
    _INSTALLED_STUBS.append("config.settings")

from broker.kis_client import KISClient, KISCredentials

for _module_name in _INSTALLED_STUBS:
    sys.modules.pop(_module_name, None)


def _response(payload: dict) -> Mock:
    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = payload
    response.text = json.dumps(payload, ensure_ascii=False)
    return response


class KISClientRetryTests(unittest.TestCase):
    def test_expired_cached_token_triggers_single_refresh_and_retry(self):
        client = KISClient(
            KISCredentials(
                app_key="app-key",
                app_secret="app-secret",
                base_url="https://example.com",
            )
        )
        client._access_token = "stale-token"
        client._token_expires_at = time.time() + 3600

        responses = [
            _response({"rt_cd": "1", "msg_cd": "EGW00123", "msg1": "기간이 만료된 token 입니다."}),
            _response({"access_token": "fresh-token", "expires_in": 3600}),
            _response(
                {
                    "rt_cd": "0",
                    "output2": [
                        {
                            "stck_bsop_date": "20260330",
                            "stck_clpr": "176300",
                            "stck_hgpr": "176650",
                            "stck_lwpr": "170600",
                            "acml_vol": "22269147",
                        }
                    ],
                }
            ),
            _response(
                {
                    "rt_cd": "0",
                    "output2": []
                }
            ),
        ]

        with (
            patch("broker.kis_client.requests.request", side_effect=responses) as mock_request,
            patch("broker.kis_client._write_json_file"),
        ):
            rows = client.get_domestic_daily_history(
                "005930",
                start_date="20250101",
                end_date="20260330",
            )

        self.assertEqual(1, len(rows))
        self.assertEqual("20260330", rows[0]["date"])
        self.assertEqual("fresh-token", client._access_token)
        self.assertEqual(4, mock_request.call_count)

    def test_domestic_daily_history_paginates_backward_to_cover_long_ranges(self):
        client = KISClient(
            KISCredentials(
                app_key="app-key",
                app_secret="app-secret",
                base_url="https://example.com",
            )
        )
        client._access_token = "fresh-token"
        client._token_expires_at = time.time() + 3600

        responses = [
            _response(
                {
                    "rt_cd": "0",
                    "output2": [
                        {
                            "stck_bsop_date": "20260330",
                            "stck_clpr": "176300",
                            "stck_hgpr": "176650",
                            "stck_lwpr": "170600",
                            "acml_vol": "22269147",
                        },
                        {
                            "stck_bsop_date": "20260329",
                            "stck_clpr": "175000",
                            "stck_hgpr": "176000",
                            "stck_lwpr": "174000",
                            "acml_vol": "11111111",
                        },
                    ],
                }
            ),
            _response(
                {
                    "rt_cd": "0",
                    "output2": [
                        {
                            "stck_bsop_date": "20260328",
                            "stck_clpr": "174500",
                            "stck_hgpr": "175500",
                            "stck_lwpr": "173000",
                            "acml_vol": "9999999",
                        },
                        {
                            "stck_bsop_date": "20260327",
                            "stck_clpr": "173000",
                            "stck_hgpr": "174000",
                            "stck_lwpr": "172000",
                            "acml_vol": "8888888",
                        },
                    ],
                }
            ),
        ]

        with (
            patch("broker.kis_client.requests.request", side_effect=responses) as mock_request,
            patch("broker.kis_client._write_json_file"),
        ):
            rows = client.get_domestic_daily_history(
                "005930",
                start_date="20260328",
                end_date="20260330",
            )

        self.assertEqual(["20260328", "20260329", "20260330"], [row["date"] for row in rows])
        self.assertEqual(2, mock_request.call_count)


if __name__ == "__main__":
    unittest.main()
