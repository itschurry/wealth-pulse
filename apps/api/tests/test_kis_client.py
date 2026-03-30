from __future__ import annotations

import json
import time
import unittest
from unittest.mock import Mock, patch

from broker.kis_client import KISClient, KISCredentials


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
        self.assertEqual(3, mock_request.call_count)


if __name__ == "__main__":
    unittest.main()
