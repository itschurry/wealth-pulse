"""한국투자증권 Open API 최소 클라이언트."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from requests import HTTPError

from config.settings import (
    KIS_ACCOUNT_ACNT_PRDT_CD,
    KIS_ACCOUNT_CANO,
    KIS_APP_KEY,
    KIS_APP_SECRET,
    KIS_BASE_URL,
    LOGS_DIR,
)


class KISConfigError(RuntimeError):
    """필수 환경 변수가 없을 때 발생한다."""


class KISAPIError(RuntimeError):
    """한국투자증권 API 호출 실패."""


@dataclass(frozen=True)
class KISCredentials:
    app_key: str
    app_secret: str
    base_url: str
    account_cano: str = ""
    account_product_code: str = ""

    @classmethod
    def from_env(cls) -> "KISCredentials":
        if not KIS_APP_KEY or not KIS_APP_SECRET:
            raise KISConfigError(
                "KIS 앱키와 시크릿이 필요합니다. .env를 확인하세요."
            )

        return cls(
            app_key=KIS_APP_KEY,
            app_secret=KIS_APP_SECRET,
            base_url=KIS_BASE_URL,
            account_cano=KIS_ACCOUNT_CANO,
            account_product_code=KIS_ACCOUNT_ACNT_PRDT_CD,
        )


class KISClient:
    """토큰 발급과 시세 조회를 위한 최소 REST 클라이언트."""

    _TOKEN_CACHE_PATH = LOGS_DIR / "kis_token_cache.json"
    _OVERSEAS_PRICE_PATH = "/uapi/overseas-price/v1/quotations/price-detail"
    _OVERSEAS_DAILY_PATH = "/uapi/overseas-price/v1/quotations/dailyprice"
    _OVERSEAS_PRICE_TR_IDS = ("HHDFS76200200",)
    _OVERSEAS_DAILY_TR_IDS = ("HHDFS76240000",)
    _OVERSEAS_EXCHANGE_MAP = {
        "NASDAQ": ("NAS", "NASD", "NASQ"),
        "NYSE": ("NYS", "NYSE"),
        "AMEX": ("AMS", "AMEX"),
    }

    def __init__(
        self,
        credentials: KISCredentials,
        timeout: float = 10.0,
    ) -> None:
        self.credentials = credentials
        self.timeout = timeout
        self._access_token = ""
        self._token_expires_at = 0.0

    @classmethod
    def from_env(cls, timeout: float = 10.0) -> "KISClient":
        return cls(KISCredentials.from_env(), timeout=timeout)

    @staticmethod
    def is_configured() -> bool:
        return bool(KIS_APP_KEY and KIS_APP_SECRET)

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload, _ = self._request_full(
            method,
            path,
            headers=headers,
            params=params,
            json_body=json_body,
        )
        return payload

    def _request_full(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], requests.Response]:
        response = requests.request(
            method=method,
            url=f"{self.credentials.base_url}{path}",
            headers=headers,
            params=params,
            json=json_body,
            timeout=self.timeout,
        )
        try:
            response.raise_for_status()
        except HTTPError as exc:
            message = response.text.strip() or str(exc)
            raise KISAPIError(message) from exc
        payload = response.json()

        rt_cd = str(payload.get("rt_cd") or "")
        if rt_cd and rt_cd != "0":
            raise KISAPIError(payload.get("msg1") or f"KIS API 오류: {rt_cd}")
        return payload, response

    def issue_access_token(self, force_refresh: bool = False) -> str:
        self._load_cached_token()
        if (
            self._access_token
            and not force_refresh
            and time.time() < self._token_expires_at
        ):
            return self._access_token

        payload = self._request(
            "POST",
            "/oauth2/tokenP",
            headers={"content-type": "application/json"},
            json_body={
                "grant_type": "client_credentials",
                "appkey": self.credentials.app_key,
                "appsecret": self.credentials.app_secret,
            },
        )

        access_token = payload.get("access_token")
        if not access_token:
            raise KISAPIError("토큰 발급 응답에 access_token이 없습니다.")

        expires_in = int(payload.get("expires_in", 3600))
        self._access_token = access_token
        self._token_expires_at = time.time() + max(expires_in - 60, 60)
        self._save_cached_token()
        return access_token

    def _auth_headers(self, tr_id: str) -> dict[str, str]:
        return {
            "authorization": f"Bearer {self.issue_access_token()}",
            "appkey": self.credentials.app_key,
            "appsecret": self.credentials.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }

    def _load_cached_token(self) -> None:
        if self._access_token and time.time() < self._token_expires_at:
            return
        token_data = _read_json_file(self._TOKEN_CACHE_PATH)
        if not token_data:
            return
        if token_data.get("base_url") != self.credentials.base_url:
            return
        expires_at = float(token_data.get("expires_at") or 0)
        if time.time() >= expires_at:
            return
        access_token = str(token_data.get("access_token") or "")
        if not access_token:
            return
        self._access_token = access_token
        self._token_expires_at = expires_at

    def _save_cached_token(self) -> None:
        _write_json_file(
            self._TOKEN_CACHE_PATH,
            {
                "base_url": self.credentials.base_url,
                "access_token": self._access_token,
                "expires_at": self._token_expires_at,
            },
        )

    def _account_parts(self) -> tuple[str, str]:
        if not self.credentials.account_cano:
            raise KISConfigError(
                "KIS_ACCOUNT_CANO가 필요합니다. 계좌번호 앞 8자리를 .env에 넣어주세요."
            )
        return self.credentials.account_cano, (
            self.credentials.account_product_code or "01"
        )

    def check_connection(self) -> dict[str, Any]:
        token = self.issue_access_token()
        return {
            "ok": True,
            "mode": "real",
            "base_url": self.credentials.base_url,
            "token_prefix": token[:12],
        }

    def get_domestic_price(self, code: str) -> dict[str, Any]:
        payload = self._request(
            "GET",
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            headers=self._auth_headers("FHKST01010100"),
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": code,
            },
        )
        output = payload.get("output") or {}
        return {
            "code": code,
            "name": output.get("hts_kor_isnm", ""),
            "price": _to_int(output.get("stck_prpr")),
            "change": _to_int(output.get("prdy_vrss")),
            "change_pct": _to_float(output.get("prdy_ctrt")),
            "open": _to_int(output.get("stck_oprc")),
            "high": _to_int(output.get("stck_hgpr")),
            "low": _to_int(output.get("stck_lwpr")),
            "volume": _to_int(output.get("acml_vol")),
        }

    def get_domestic_daily_history(
        self,
        code: str,
        *,
        start_date: str,
        end_date: str,
        period_division: str = "D",
        adjusted_price: str = "0",
    ) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
            headers=self._auth_headers("FHKST03010100"),
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": code,
                "FID_INPUT_DATE_1": start_date,
                "FID_INPUT_DATE_2": end_date,
                "FID_PERIOD_DIV_CODE": period_division,
                "FID_ORG_ADJ_PRC": adjusted_price,
            },
        )
        output = payload.get("output2") or payload.get("output") or []
        history = []
        for item in output:
            date = str(item.get("stck_bsop_date") or item.get("xymd") or "")
            close = _to_float(item.get("stck_clpr") or item.get("clos"))
            high = _to_float(item.get("stck_hgpr") or item.get("hgpr"))
            low = _to_float(item.get("stck_lwpr") or item.get("lwpr"))
            volume = _to_float(item.get("acml_vol") or item.get("tvol"))
            if not date or close is None:
                continue
            history.append({
                "date": date,
                "close": close,
                "high": high,
                "low": low,
                "volume": volume,
            })
        return history

    def get_overseas_price(
        self,
        symbol: str,
        *,
        exchange: str = "NASDAQ",
    ) -> dict[str, Any]:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol is required")

        payload: dict[str, Any] | None = None
        for exchange_code in self._normalize_overseas_exchange(exchange):
            for tr_id in self._OVERSEAS_PRICE_TR_IDS:
                try:
                    payload = self._request(
                        "GET",
                        self._OVERSEAS_PRICE_PATH,
                        headers=self._auth_headers(tr_id),
                        params={
                            "AUTH": "",
                            "EXCD": exchange_code,
                            "SYMB": normalized_symbol,
                        },
                    )
                except KISAPIError:
                    continue
                if payload:
                    break
            if payload:
                break

        if not payload:
            raise KISAPIError("해외 현재가 조회에 실패했습니다.")

        output = payload.get("output") or {}
        output2 = payload.get("output2") or {}
        merged = {**output2, **output}
        price = _pick_float(
            merged,
            "last",
            "clos",
            "ovrs_nmix_prpr",
            "stck_prpr",
            "trade_price",
            "last_price",
        )
        previous_close = _pick_float(
            merged,
            "base",
            "prdy_clpr",
            "prev",
            "xprc",
            "prev_close",
        )
        change = _pick_float(
            merged,
            "diff",
            "t_xdif",
            "prdy_vrss",
            "change",
        )
        change_pct = _pick_float(
            merged,
            "rate",
            "t_xrat",
            "prdy_ctrt",
            "change_rate",
            "change_pct",
        )
        if change_pct is None and price not in (None, 0) and previous_close not in (None, 0):
            change_pct = ((price - previous_close) / previous_close) * 100
        if change is None and price is not None and previous_close is not None:
            change = price - previous_close

        return {
            "code": normalized_symbol,
            "name": _pick_str(merged, "name", "hts_kor_isnm", "ovrs_item_name"),
            "price": price,
            "change": change,
            "change_pct": change_pct,
            "open": _pick_float(merged, "open", "oprc"),
            "high": _pick_float(merged, "high", "hgpr"),
            "low": _pick_float(merged, "low", "lwpr"),
            "volume": _pick_float(merged, "tvol", "acml_vol", "volume"),
            "raw": merged,
        }

    def get_overseas_daily_history(
        self,
        symbol: str,
        *,
        exchange: str = "NASDAQ",
        start_date: str = "",
        end_date: str = "",
    ) -> list[dict[str, Any]]:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol is required")
        if not end_date:
            end_date = time.strftime("%Y%m%d")

        payload: dict[str, Any] | None = None
        for exchange_code in self._normalize_overseas_exchange(exchange):
            for tr_id in self._OVERSEAS_DAILY_TR_IDS:
                try:
                    payload = self._request(
                        "GET",
                        self._OVERSEAS_DAILY_PATH,
                        headers=self._auth_headers(tr_id),
                        params={
                            "AUTH": "",
                            "EXCD": exchange_code,
                            "SYMB": normalized_symbol,
                            "GUBN": "0",
                            "BYMD": end_date,
                            "MODP": "1",
                        },
                    )
                except KISAPIError:
                    continue
                if payload:
                    break
            if payload:
                break

        if not payload:
            raise KISAPIError("해외 일봉 조회에 실패했습니다.")

        output = payload.get("output2") or payload.get("output1") or payload.get("output") or []
        history = []
        for item in output:
            date = str(item.get("xymd") or item.get("stck_bsop_date") or "")
            close = _pick_float(item, "clos", "stck_clpr", "last")
            high = _pick_float(item, "high", "hgpr", "stck_hgpr")
            low = _pick_float(item, "low", "lwpr", "stck_lwpr")
            volume = _pick_float(item, "tvol", "acml_vol", "volume")
            if not date or close is None:
                continue
            if start_date and date < start_date:
                continue
            if end_date and date > end_date:
                continue
            history.append({
                "date": date,
                "close": close,
                "high": high,
                "low": low,
                "volume": volume,
            })
        return history

    def _normalize_overseas_exchange(self, exchange: str) -> tuple[str, ...]:
        normalized = (exchange or "").strip().upper()
        if normalized in self._OVERSEAS_EXCHANGE_MAP:
            return self._OVERSEAS_EXCHANGE_MAP[normalized]
        for _, exchange_codes in self._OVERSEAS_EXCHANGE_MAP.items():
            if normalized in exchange_codes:
                return exchange_codes
        return self._OVERSEAS_EXCHANGE_MAP["NASDAQ"]

    def get_balance(
        self,
        *,
        after_hours: str = "N",
        inquiry_division: str = "01",
        unit_price_division: str = "01",
        include_fund_settlement: str = "N",
        auto_repayment: str = "N",
        process_division: str = "00",
    ) -> dict[str, Any]:
        cano, product_code = self._account_parts()
        tr_id = "TTTC8434R"
        api_path = "/uapi/domestic-stock/v1/trading/inquire-balance"

        fk100 = ""
        nk100 = ""
        tr_cont = ""
        raw_positions: list[dict[str, Any]] = []
        raw_summary: list[dict[str, Any]] = []

        while True:
            headers = self._auth_headers(tr_id)
            if tr_cont:
                headers["tr_cont"] = tr_cont

            payload, response = self._request_full(
                "GET",
                api_path,
                headers=headers,
                params={
                    "CANO": cano,
                    "ACNT_PRDT_CD": product_code,
                    "AFHR_FLPR_YN": after_hours,
                    "OFL_YN": "",
                    "INQR_DVSN": inquiry_division,
                    "UNPR_DVSN": unit_price_division,
                    "FUND_STTL_ICLD_YN": include_fund_settlement,
                    "FNCG_AMT_AUTO_RDPT_YN": auto_repayment,
                    "PRCS_DVSN": process_division,
                    "CTX_AREA_FK100": fk100,
                    "CTX_AREA_NK100": nk100,
                },
            )

            raw_positions.extend(payload.get("output1") or [])
            raw_summary = payload.get("output2") or raw_summary

            tr_cont = str(response.headers.get("tr_cont") or "")
            fk100 = str(payload.get("ctx_area_fk100") or "")
            nk100 = str(payload.get("ctx_area_nk100") or "")

            if tr_cont not in {"M", "F"}:
                break

        positions = []
        for item in raw_positions:
            quantity = _to_int(
                item.get("hldg_qty")
                or item.get("cblc_qty")
                or item.get("ord_psbl_qty")
            )
            position = {
                "code": item.get("pdno") or item.get("prdt_no") or "",
                "name": (
                    item.get("prdt_name")
                    or item.get("prdt_abrv_name")
                    or item.get("hts_kor_isnm")
                    or ""
                ),
                "quantity": quantity,
                "orderable_quantity": _to_int(item.get("ord_psbl_qty")),
                "avg_price": _to_float(item.get("pchs_avg_pric")),
                "current_price": _to_float(item.get("prpr")),
                "eval_amount": _to_float(item.get("evlu_amt")),
                "profit_loss": _to_float(item.get("evlu_pfls_amt")),
                "profit_loss_rate": _to_float(item.get("evlu_pfls_rt")),
            }
            if any(
                value not in (None, "", 0)
                for value in (
                    position["quantity"],
                    position["eval_amount"],
                    position["profit_loss"],
                )
            ):
                positions.append(position)

        summary_row = (raw_summary or [{}])[0]
        summary = {
            "deposit": _to_float(summary_row.get("dnca_tot_amt")),
            "buy_amount": _to_float(summary_row.get("pchs_amt_smtl_amt")),
            "eval_amount": _to_float(summary_row.get("scts_evlu_amt")),
            "eval_profit_loss": _to_float(summary_row.get("evlu_pfls_smtl_amt")),
            "total_amount": _to_float(summary_row.get("tot_evlu_amt")),
        }
        return {
            "mode": "real",
            "account_product_code": product_code,
            "positions": positions,
            "summary": summary,
            "raw": {
                "positions": raw_positions,
                "summary": raw_summary,
            },
        }

    def get_orderable_amount(
        self,
        code: str,
        order_price: int | str,
        *,
        order_division: str = "00",
        include_cma: str = "N",
        include_overseas: str = "N",
    ) -> dict[str, Any]:
        cano, product_code = self._account_parts()
        tr_id = "TTTC8908R"
        payload = self._request(
            "GET",
            "/uapi/domestic-stock/v1/trading/inquire-psbl-order",
            headers=self._auth_headers(tr_id),
            params={
                "CANO": cano,
                "ACNT_PRDT_CD": product_code,
                "PDNO": code,
                "ORD_UNPR": str(order_price),
                "ORD_DVSN": order_division,
                "CMA_EVLU_AMT_ICLD_YN": include_cma,
                "OVRS_ICLD_YN": include_overseas,
            },
        )
        output = payload.get("output") or {}
        return {
            "code": code,
            "order_price": _to_float(order_price),
            "max_orderable_quantity": _to_int(
                output.get("max_buy_qty") or output.get("nrcvb_buy_qty")
            ),
            "orderable_cash": _to_float(
                output.get("ord_psbl_cash")
                or output.get("psbl_cash")
                or output.get("max_buy_amt")
            ),
            "raw": output,
        }

    def place_cash_order(
        self,
        side: str,
        code: str,
        quantity: int | str,
        price: int | str,
        *,
        order_division: str = "00",
        exchange_id: str = "KRX",
    ) -> dict[str, Any]:
        cano, product_code = self._account_parts()
        normalized_side = side.lower()
        if normalized_side not in {"buy", "sell"}:
            raise ValueError("side는 'buy' 또는 'sell'만 허용합니다.")

        tr_id = "TTTC0012U" if normalized_side == "buy" else "TTTC0011U"

        payload = self._request(
            "POST",
            "/uapi/domestic-stock/v1/trading/order-cash",
            headers={
                **self._auth_headers(tr_id),
                "content-type": "application/json",
            },
            json_body={
                "CANO": cano,
                "ACNT_PRDT_CD": product_code,
                "PDNO": code,
                "ORD_DVSN": order_division,
                "ORD_QTY": str(quantity),
                "ORD_UNPR": str(price),
                "EXCG_ID_DVSN_CD": exchange_id,
                "SLL_TYPE": "",
                "CNDT_PRIC": "",
            },
        )
        output = payload.get("output") or {}
        return {
            "mode": "real",
            "side": normalized_side,
            "code": code,
            "quantity": _to_int(quantity),
            "price": _to_float(price),
            "branch_no": output.get("KRX_FWDG_ORD_ORGNO") or output.get("ODNO_ORGN"),
            "order_no": output.get("ODNO") or output.get("odno"),
            "order_time": output.get("ORD_TMD") or output.get("ord_tmd"),
            "raw": output,
        }


def _to_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    try:
        path.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        return


def _pick_float(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key not in payload:
            continue
        value = _to_float(payload.get(key))
        if value is not None:
            return value
    return None


def _pick_str(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return ""
