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


def _response(payload: dict, headers: dict | None = None) -> Mock:
    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = payload
    response.text = json.dumps(payload, ensure_ascii=False)
    response.headers = headers or {}
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

    def test_rate_limit_error_retries_same_request_before_failing_history(self):
        client = KISClient(
            KISCredentials(
                app_key="app-key",
                app_secret="app-secret",
                base_url="https://example.com",
            )
        )
        client._access_token = "fresh-token"
        client._token_expires_at = time.time() + 3600
        client._rate_limit_wait = Mock()

        responses = [
            _response({"rt_cd": "1", "msg_cd": "EGW00201", "msg1": "초당 거래건수를 초과하였습니다."}),
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
            _response({"rt_cd": "0", "output2": []}),
        ]

        with (
            patch("broker.kis_client.requests.request", side_effect=responses) as mock_request,
            patch("broker.kis_client.time.sleep") as mock_sleep,
        ):
            rows = client.get_domestic_daily_history(
                "005930",
                start_date="20260330",
                end_date="20260330",
            )

        self.assertEqual(1, len(rows))
        self.assertEqual("20260330", rows[0]["date"])
        self.assertEqual(2, mock_request.call_count)
        mock_sleep.assert_called_once_with(1.1)

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

    def test_get_balance_combines_domestic_and_overseas_holdings(self):
        client = KISClient(
            KISCredentials(
                app_key="app-key",
                app_secret="app-secret",
                base_url="https://example.com",
                account_cano="12345678",
                account_product_code="01",
            )
        )
        client._access_token = "fresh-token"
        client._token_expires_at = time.time() + 3600

        responses = [
            _response(
                {
                    "rt_cd": "0",
                    "output1": [
                        {
                            "pdno": "005930",
                            "prdt_name": "삼성전자",
                            "hldg_qty": "3",
                            "ord_psbl_qty": "3",
                            "pchs_avg_pric": "70000",
                            "prpr": "71000",
                            "evlu_amt": "213000",
                            "evlu_pfls_amt": "3000",
                            "evlu_pfls_rt": "1.43",
                        }
                    ],
                    "output2": [
                        {
                            "dnca_tot_amt": "2000000",
                            "pchs_amt_smtl_amt": "210000",
                            "scts_evlu_amt": "213000",
                            "evlu_pfls_smtl_amt": "3000",
                            "tot_evlu_amt": "2213000",
                        }
                    ],
                }
            ),
            _response(
                {
                    "rt_cd": "0",
                    "output1": [
                        {
                            "ovrs_pdno": "AAPL",
                            "ovrs_item_name": "Apple Inc.",
                            "ovrs_excg_cd": "NASD",
                            "tr_crcy_cd": "USD",
                            "cblc_qty13": "2",
                            "ord_psbl_qty1": "2",
                            "pchs_avg_pric": "150.5",
                            "now_pric2": "160.0",
                            "ovrs_stck_evlu_amt": "320.0",
                            "frcr_evlu_pfls_amt": "19.0",
                            "evlu_pfls_rt": "6.31",
                            "bass_exrt": "1450.0",
                        }
                    ],
                    "output2": [
                        {
                            "frcr_dncl_amt_2": "1000.0",
                            "frcr_buy_amt_smtl1": "301.0",
                            "frcr_evlu_amt2": "320.0",
                            "frcr_evlu_pfls_amt": "19.0",
                            "tot_evlu_pfls_amt": "19.0",
                            "bass_exrt": "1450.0",
                        }
                    ],
                }
            ),
            _response({"rt_cd": "0", "output1": [], "output2": [{}]}),
            _response({"rt_cd": "0", "output1": [], "output2": [{}]}),
        ]

        with patch("broker.kis_client.requests.request", side_effect=responses) as mock_request:
            payload = client.get_balance()

        self.assertEqual(4, mock_request.call_count)
        self.assertEqual("real", payload["mode"])
        self.assertEqual(2, len(payload["positions"]))
        self.assertEqual(2000000.0, payload["summary"]["cash_krw"])
        self.assertEqual(1000.0, payload["summary"]["cash_usd"])
        self.assertEqual(213000.0, payload["summary"]["eval_amount_krw"])
        self.assertEqual(320.0, payload["summary"]["eval_amount_usd"])
        nasdaq = next(item for item in payload["positions"] if item["code"] == "AAPL")
        self.assertEqual("NASDAQ", nasdaq["market"])
        self.assertEqual("USD", nasdaq["currency"])
        self.assertEqual(2, nasdaq["quantity"])
        self.assertEqual(1450.0, nasdaq["fx_rate"])
        self.assertEqual(320.0, nasdaq["eval_amount"])

    def test_get_balance_prefers_settled_cash_and_raw_total_for_domestic_summary(self):
        client = KISClient(
            KISCredentials(
                app_key="app-key",
                app_secret="app-secret",
                base_url="https://example.com",
                account_cano="12345678",
                account_product_code="01",
            )
        )
        client._access_token = "fresh-token"
        client._token_expires_at = time.time() + 3600

        responses = [
            _response(
                {
                    "rt_cd": "0",
                    "output1": [
                        {
                            "pdno": "003850",
                            "prdt_name": "보령",
                            "hldg_qty": "18",
                            "ord_psbl_qty": "18",
                            "pchs_avg_pric": "9890",
                            "prpr": "9870",
                            "evlu_amt": "177660",
                            "evlu_pfls_amt": "-360",
                            "evlu_pfls_rt": "-0.20",
                        },
                        {
                            "pdno": "085310",
                            "prdt_name": "엔케이",
                            "hldg_qty": "160",
                            "ord_psbl_qty": "160",
                            "pchs_avg_pric": "1152",
                            "prpr": "1144",
                            "evlu_amt": "183040",
                            "evlu_pfls_amt": "-1280",
                            "evlu_pfls_rt": "-0.69",
                        },
                    ],
                    "output2": [
                        {
                            "dnca_tot_amt": "2507620",
                            "nxdy_excc_amt": "2145268",
                            "pchs_amt_smtl_amt": "362340",
                            "bfdy_tlex_amt": "12",
                            "scts_evlu_amt": "360700",
                            "evlu_pfls_smtl_amt": "-1640",
                            "tot_evlu_amt": "2505968",
                            "nass_amt": "2505968",
                        }
                    ],
                }
            ),
            _response({"rt_cd": "0", "output1": [], "output2": [{}]}),
            _response({"rt_cd": "0", "output1": [], "output2": [{}]}),
            _response({"rt_cd": "0", "output1": [], "output2": [{}]}),
        ]

        with patch("broker.kis_client.requests.request", side_effect=responses) as mock_request:
            payload = client.get_balance()

        self.assertEqual(4, mock_request.call_count)
        self.assertEqual(2145268.0, payload["summary"]["deposit"])
        self.assertEqual(2145268.0, payload["summary"]["cash_krw"])
        self.assertEqual(360700.0, payload["summary"]["eval_amount_krw"])
        self.assertEqual(2505968.0, payload["summary"]["total_amount"])
        self.assertEqual(2505968.0, payload["summary"]["total_amount_krw"])

    def test_get_balance_prefers_current_settlement_cash_when_same_day_buys_exist(self):
        client = KISClient(
            KISCredentials(
                app_key="app-key",
                app_secret="app-secret",
                base_url="https://example.com",
                account_cano="12345678",
                account_product_code="01",
            )
        )
        client._access_token = "fresh-token"
        client._token_expires_at = time.time() + 3600

        responses = [
            _response(
                {
                    "rt_cd": "0",
                    "output1": [
                        {
                            "pdno": "003850",
                            "prdt_name": "보령",
                            "hldg_qty": "18",
                            "ord_psbl_qty": "18",
                            "pchs_avg_pric": "9890",
                            "prpr": "9860",
                            "evlu_amt": "177480",
                            "evlu_pfls_amt": "-540",
                            "evlu_pfls_rt": "-0.30",
                        },
                        {
                            "pdno": "085310",
                            "prdt_name": "엔케이",
                            "hldg_qty": "160",
                            "ord_psbl_qty": "160",
                            "pchs_avg_pric": "1152",
                            "prpr": "1153",
                            "evlu_amt": "184480",
                            "evlu_pfls_amt": "160",
                            "evlu_pfls_rt": "0.08",
                        },
                        {
                            "pdno": "241560",
                            "prdt_name": "두산밥캣",
                            "hldg_qty": "3",
                            "ord_psbl_qty": "3",
                            "pchs_avg_pric": "72500",
                            "prpr": "72400",
                            "evlu_amt": "217200",
                            "evlu_pfls_amt": "-300",
                            "evlu_pfls_rt": "-0.13",
                        },
                        {
                            "pdno": "294870",
                            "prdt_name": "IPARK현대산업개발",
                            "hldg_qty": "8",
                            "ord_psbl_qty": "8",
                            "pchs_avg_pric": "24000",
                            "prpr": "24050",
                            "evlu_amt": "192400",
                            "evlu_pfls_amt": "400",
                            "evlu_pfls_rt": "0.20",
                        },
                    ],
                    "output2": [
                        {
                            "dnca_tot_amt": "2507620",
                            "nxdy_excc_amt": "2145268",
                            "prvs_rcdl_excc_amt": "1735755",
                            "pchs_amt_smtl_amt": "771840",
                            "bfdy_tlex_amt": "12",
                            "thdt_tlex_amt": "13",
                            "scts_evlu_amt": "771560",
                            "evlu_pfls_smtl_amt": "-280",
                            "tot_evlu_amt": "2507315",
                            "nass_amt": "2507315",
                        }
                    ],
                }
            ),
            _response({"rt_cd": "0", "output1": [], "output2": [{}]}),
            _response({"rt_cd": "0", "output1": [], "output2": [{}]}),
            _response({"rt_cd": "0", "output1": [], "output2": [{}]}),
        ]

        with patch("broker.kis_client.requests.request", side_effect=responses):
            payload = client.get_balance()

        self.assertEqual(1735755.0, payload["summary"]["deposit"])
        self.assertEqual(1735755.0, payload["summary"]["cash_krw"])
        self.assertEqual(771560.0, payload["summary"]["eval_amount_krw"])
        self.assertEqual(2507315.0, payload["summary"]["total_amount"])
        self.assertEqual(payload["summary"]["cash_krw"] + payload["summary"]["eval_amount_krw"], payload["summary"]["total_amount"])

    def test_get_balance_falls_back_to_cash_plus_eval_when_domestic_total_is_missing(self):
        client = KISClient(
            KISCredentials(
                app_key="app-key",
                app_secret="app-secret",
                base_url="https://example.com",
                account_cano="12345678",
                account_product_code="01",
            )
        )
        client._access_token = "fresh-token"
        client._token_expires_at = time.time() + 3600

        responses = [
            _response(
                {
                    "rt_cd": "0",
                    "output1": [
                        {
                            "pdno": "005930",
                            "prdt_name": "삼성전자",
                            "hldg_qty": "3",
                            "ord_psbl_qty": "3",
                            "pchs_avg_pric": "70000",
                            "prpr": "71000",
                            "evlu_amt": "213000",
                            "evlu_pfls_amt": "3000",
                            "evlu_pfls_rt": "1.43",
                        }
                    ],
                    "output2": [
                        {
                            "prvs_rcdl_excc_amt": "2000000",
                            "pchs_amt_smtl_amt": "210000",
                            "scts_evlu_amt": "213000",
                            "evlu_pfls_smtl_amt": "3000",
                        }
                    ],
                }
            ),
            _response({"rt_cd": "0", "output1": [], "output2": [{}]}),
            _response({"rt_cd": "0", "output1": [], "output2": [{}]}),
            _response({"rt_cd": "0", "output1": [], "output2": [{}]}),
        ]

        with patch("broker.kis_client.requests.request", side_effect=responses):
            payload = client.get_balance()

        self.assertEqual(2000000.0, payload["summary"]["cash_krw"])
        self.assertEqual(213000.0, payload["summary"]["eval_amount_krw"])
        self.assertEqual(2213000.0, payload["summary"]["total_amount"])
        self.assertEqual(2213000.0, payload["summary"]["total_amount_krw"])


if __name__ == "__main__":
    unittest.main()
