"""실시세 기반 모의/실주문 엔진 인터페이스와 Paper 구현."""

from __future__ import annotations

import datetime
import json
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from market_utils import lookup_company_listing


class ExecutionEngine(Protocol):
    """주문 실행 엔진 공통 인터페이스."""

    def get_account(self, *, refresh_quotes: bool = True) -> dict[str, Any]:
        ...

    def place_order(
        self,
        *,
        side: str,
        code: str,
        market: str,
        quantity: int,
        order_type: str = "market",
        limit_price: float | None = None,
    ) -> dict[str, Any]:
        ...

    def reset(
        self,
        *,
        initial_cash_krw: float | None = None,
        initial_cash_usd: float | None = None,
        paper_days: int | None = None,
        seed_positions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class EngineConfig:
    state_path: Path
    default_initial_cash_krw: float = 10_000_000.0
    default_initial_cash_usd: float = 10_000.0
    default_paper_days: int = 7
    buy_fee_rate: float = 0.00015
    sell_fee_rate: float = 0.00015
    order_notifier: Callable[[dict[str, Any], dict[str, Any]], None] | None = None


class PaperExecutionEngine:
    """실시세를 참고해 내부 가상 계좌만 업데이트하는 모의 체결 엔진."""

    def __init__(
        self,
        *,
        config: EngineConfig,
        quote_provider: Callable[[str, str], dict[str, Any]],
        fx_provider: Callable[[], float | None],
    ) -> None:
        self.config = config
        self.quote_provider = quote_provider
        self.fx_provider = fx_provider
        self._lock = threading.Lock()
        self._state = self._load_state()

    def get_account(self, *, refresh_quotes: bool = True) -> dict[str, Any]:
        with self._lock:
            state = self._state
            if refresh_quotes:
                self._refresh_positions(state)
                self._persist(state)
            return self._build_snapshot(state)

    def reset(
        self,
        *,
        initial_cash_krw: float | None = None,
        initial_cash_usd: float | None = None,
        paper_days: int | None = None,
        seed_positions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            seed_krw = float(initial_cash_krw if initial_cash_krw is not None else self.config.default_initial_cash_krw)
            seed_usd = float(initial_cash_usd if initial_cash_usd is not None else self.config.default_initial_cash_usd)
            days = int(paper_days if paper_days is not None else self.config.default_paper_days)
            seed_krw = max(0.0, seed_krw)
            seed_usd = max(0.0, seed_usd)
            days = max(1, min(365, days))
            self._state = self._new_state(seed_krw, seed_usd, days)
            if seed_positions:
                self._state["positions"] = self._build_seed_positions(seed_positions)
                self._refresh_positions(self._state)
            self._state["starting_equity_krw"] = self._baseline_equity_krw(self._state)
            self._state["updated_at"] = _now_iso()
            self._persist(self._state)
            return self._build_snapshot(self._state)

    def place_order(
        self,
        *,
        side: str,
        code: str,
        market: str,
        quantity: int,
        order_type: str = "market",
        limit_price: float | None = None,
    ) -> dict[str, Any]:
        normalized_side = side.strip().lower()
        normalized_market = market.strip().upper()
        normalized_order_type = order_type.strip().lower()
        normalized_code = code.strip().upper()
        if normalized_side not in {"buy", "sell"}:
            return {"ok": False, "error": "side는 buy/sell만 허용합니다."}
        if normalized_order_type not in {"market", "limit"}:
            return {"ok": False, "error": "order_type은 market/limit만 허용합니다."}
        if normalized_market not in {"KOSPI", "NASDAQ"}:
            return {"ok": False, "error": "market은 KOSPI/NASDAQ만 허용합니다."}
        if quantity <= 0:
            return {"ok": False, "error": "quantity는 1 이상이어야 합니다."}
        if not normalized_code:
            return {"ok": False, "error": "code가 필요합니다."}
        with self._lock:
            elapsed = _days_elapsed(str(self._state.get("created_at") or ""))
            paper_days = int(self._state.get("paper_days") or self.config.default_paper_days)
            if elapsed >= paper_days:
                return {"ok": False, "error": "설정한 모의투자 기간이 종료되어 신규 주문이 차단되었습니다."}

        try:
            quote = self.quote_provider(normalized_code, normalized_market)
        except Exception as exc:
            return {"ok": False, "error": f"시세 조회 실패: {exc}"}

        quote_price = _to_float(quote.get("price"))
        if quote_price is None or quote_price <= 0:
            return {"ok": False, "error": "유효한 현재가를 가져오지 못했습니다."}

        fx_rate = 1.0 if normalized_market == "KOSPI" else (_to_float(self.fx_provider()) or 1300.0)
        can_fill, reject_reason = self._can_fill(
            side=normalized_side,
            order_type=normalized_order_type,
            quote_price=quote_price,
            limit_price=limit_price,
        )
        if not can_fill:
            return {"ok": False, "error": reject_reason or "체결 조건이 맞지 않습니다."}

        executed_local = quote_price if normalized_order_type == "market" else float(limit_price)
        executed_krw = executed_local * fx_rate
        fee_rate = self.config.buy_fee_rate if normalized_side == "buy" else self.config.sell_fee_rate
        notional_local = executed_local * quantity
        notional_krw = executed_krw * quantity
        fee_local = max(0.0, notional_local * fee_rate)
        fee_krw = max(0.0, notional_krw * fee_rate)
        now = _now_iso()

        with self._lock:
            state = self._state
            self._refresh_positions(state)
            order_id = f"paper-{uuid.uuid4().hex[:12]}"
            position_key = f"{normalized_market}:{normalized_code}"
            position = state["positions"].get(position_key)

            if normalized_side == "buy":
                if normalized_market == "KOSPI":
                    required_cash_krw = notional_krw + fee_krw
                    if float(state["cash_krw"]) < required_cash_krw:
                        return {"ok": False, "error": "원화 주문 가능 현금이 부족합니다."}
                    state["cash_krw"] = float(state["cash_krw"]) - required_cash_krw
                    state["total_fees_krw"] = float(state["total_fees_krw"]) + fee_krw
                else:
                    required_cash_usd = notional_local + fee_local
                    if float(state["cash_usd"]) < required_cash_usd:
                        return {"ok": False, "error": "달러 주문 가능 현금이 부족합니다."}
                    state["cash_usd"] = float(state["cash_usd"]) - required_cash_usd
                    state["total_fees_usd"] = float(state["total_fees_usd"]) + fee_local

                prev_qty = int(position["quantity"]) if position else 0
                prev_cost_local = float(position["avg_price_local"]) * prev_qty if position else 0.0
                next_qty = prev_qty + quantity
                avg_price_local = (prev_cost_local + notional_local) / max(next_qty, 1)
                avg_price_krw = avg_price_local * fx_rate
                state["positions"][position_key] = {
                    "code": normalized_code,
                    "name": str(quote.get("name") or normalized_code),
                    "market": normalized_market,
                    "currency": "KRW" if normalized_market == "KOSPI" else "USD",
                    "quantity": next_qty,
                    "entry_ts": str(position.get("entry_ts") or now) if position else now,
                    "avg_price_local": avg_price_local,
                    "avg_price_krw": avg_price_krw,
                    "last_price_local": executed_local,
                    "last_price_krw": executed_krw,
                    "fx_rate": fx_rate,
                    "updated_at": now,
                }
                realized_local = 0.0
                realized_krw = 0.0
            else:
                held_qty = int(position["quantity"]) if position else 0
                if held_qty < quantity:
                    return {"ok": False, "error": "매도 가능 수량이 부족합니다."}
                avg_price_local = float(position["avg_price_local"])
                avg_price_krw = float(position["avg_price_krw"])
                proceeds_local = notional_local - fee_local
                proceeds_krw = notional_krw - fee_krw
                realized_local = (executed_local - avg_price_local) * quantity - fee_local
                realized_krw = (executed_krw - avg_price_krw) * quantity - fee_krw
                if normalized_market == "KOSPI":
                    state["cash_krw"] = float(state["cash_krw"]) + proceeds_krw
                    state["realized_pnl_krw"] = float(state["realized_pnl_krw"]) + realized_krw
                    state["total_fees_krw"] = float(state["total_fees_krw"]) + fee_krw
                else:
                    state["cash_usd"] = float(state["cash_usd"]) + proceeds_local
                    state["realized_pnl_usd"] = float(state["realized_pnl_usd"]) + realized_local
                    state["total_fees_usd"] = float(state["total_fees_usd"]) + fee_local
                remain_qty = held_qty - quantity
                if remain_qty <= 0:
                    state["positions"].pop(position_key, None)
                else:
                    position["quantity"] = remain_qty
                    position["last_price_local"] = executed_local
                    position["last_price_krw"] = executed_krw
                    position["fx_rate"] = fx_rate
                    position["updated_at"] = now

            event = {
                "order_id": order_id,
                "ts": now,
                "side": normalized_side,
                "order_type": normalized_order_type,
                "code": normalized_code,
                "name": str(quote.get("name") or normalized_code),
                "market": normalized_market,
                "quantity": quantity,
                "filled_price_local": round(executed_local, 4),
                "filled_price_krw": round(executed_krw, 4),
                "fx_rate": round(fx_rate, 4),
                "notional_local": round(notional_local, 4),
                "notional_krw": round(notional_krw, 2),
                "fee_local": round(fee_local, 4),
                "fee_krw": round(fee_krw, 2),
                "realized_pnl_local": round(realized_local, 4),
                "realized_pnl_krw": round(realized_krw, 2),
                "status": "filled",
            }
            state["orders"].insert(0, event)
            state["orders"] = state["orders"][:300]
            state["updated_at"] = now
            self._persist(state)
            snapshot = self._build_snapshot(state)

        notifier = self.config.order_notifier
        if notifier is not None:
            try:
                notifier(event, snapshot)
            except Exception:
                # 체결 자체는 성공 처리하고, 알림 장애만 격리한다.
                pass

        return {"ok": True, "event": event, "account": snapshot}

    def _can_fill(
        self,
        *,
        side: str,
        order_type: str,
        quote_price: float,
        limit_price: float | None,
    ) -> tuple[bool, str | None]:
        if order_type == "market":
            return True, None
        if limit_price is None or limit_price <= 0:
            return False, "limit 주문에는 유효한 limit_price가 필요합니다."
        if side == "buy" and quote_price <= limit_price:
            return True, None
        if side == "sell" and quote_price >= limit_price:
            return True, None
        return False, f"현재가 {quote_price:,.2f}가 지정가 조건을 충족하지 않습니다."

    def _build_snapshot(self, state: dict[str, Any]) -> dict[str, Any]:
        positions = list(state["positions"].values())
        total_market_value_krw = sum(float(item.get("market_value_krw") or 0.0) for item in positions)
        total_market_value_usd = sum(float(item.get("market_value_usd") or 0.0) for item in positions)
        fx_rate = _to_float(self.fx_provider()) or 1300.0
        cash_krw = float(state["cash_krw"])
        cash_usd = float(state["cash_usd"])
        equity_krw = cash_krw + (cash_usd * fx_rate) + total_market_value_krw
        starting_equity_krw = float(state.get("starting_equity_krw") or self._baseline_equity_krw(state))
        created_at = state["created_at"]
        paper_days = int(state.get("paper_days") or self.config.default_paper_days)
        days_elapsed = _days_elapsed(created_at)
        days_left = max(0, paper_days - days_elapsed)
        return {
            "mode": "paper",
            "base_currency": "MULTI",
            "created_at": created_at,
            "updated_at": state["updated_at"],
            "paper_days": paper_days,
            "days_elapsed": days_elapsed,
            "days_left": days_left,
            "initial_cash_krw": round(float(state["initial_cash_krw"]), 2),
            "initial_cash_usd": round(float(state["initial_cash_usd"]), 2),
            "cash_krw": round(cash_krw, 2),
            "cash_usd": round(cash_usd, 4),
            "market_value_krw": round(total_market_value_krw, 2),
            "market_value_usd": round(total_market_value_usd, 4),
            "equity_krw": round(equity_krw, 2),
            "starting_equity_krw": round(starting_equity_krw, 2),
            "fx_rate": round(fx_rate, 4),
            "realized_pnl_krw": round(float(state["realized_pnl_krw"]), 2),
            "realized_pnl_usd": round(float(state["realized_pnl_usd"]), 4),
            "total_fees_krw": round(float(state["total_fees_krw"]), 2),
            "total_fees_usd": round(float(state["total_fees_usd"]), 4),
            "positions": positions,
            "orders": state["orders"][:80],
        }

    def _refresh_positions(self, state: dict[str, Any]) -> None:
        for key, position in list(state["positions"].items()):
            code = str(position.get("code") or "")
            market = str(position.get("market") or "")
            quantity = int(position.get("quantity") or 0)
            if not code or not market or quantity <= 0:
                state["positions"].pop(key, None)
                continue
            # 이름이 코드와 동일하면 카탈로그에서 먼저 보완 (시세 조회 실패 시에도 적용)
            current_name = str(position.get("name") or "")
            if not current_name or current_name == code:
                catalog = (
                    lookup_company_listing(code=code, scope="core")
                    or lookup_company_listing(code=code, scope="live")
                )
                if catalog and catalog.get("name"):
                    position["name"] = catalog["name"]
            try:
                quote = self.quote_provider(code, market)
            except Exception:
                continue
            quote_price = _to_float(quote.get("price"))
            if quote_price is None or quote_price <= 0:
                continue
            fx_rate = 1.0 if market == "KOSPI" else (_to_float(self.fx_provider()) or float(position.get("fx_rate") or 1300.0))
            last_price_local = quote_price
            last_price_krw = quote_price * fx_rate
            avg_price_local = float(position.get("avg_price_local") or 0.0)
            avg_price_krw = float(position.get("avg_price_krw") or 0.0)
            market_value_local = last_price_local * quantity
            market_value_krw = last_price_krw * quantity
            unrealized_local = (last_price_local - avg_price_local) * quantity
            unrealized_krw = (last_price_krw - avg_price_krw) * quantity
            base_cost_krw = avg_price_krw * quantity
            unrealized_pct = (unrealized_krw / base_cost_krw * 100) if base_cost_krw > 0 else 0.0
            resolved_name = quote.get("name") or position.get("name") or ""
            if not resolved_name or resolved_name == code:
                catalog = lookup_company_listing(code=code, scope="core") or lookup_company_listing(code=code, scope="live")
                if catalog and catalog.get("name"):
                    resolved_name = catalog["name"]
            position["name"] = str(resolved_name or code)
            position["last_price_local"] = last_price_local
            position["last_price_krw"] = last_price_krw
            position["fx_rate"] = fx_rate
            position["market_value_usd"] = market_value_local if market == "NASDAQ" else 0.0
            position["market_value_krw"] = market_value_krw
            position["unrealized_pnl_local"] = unrealized_local
            position["unrealized_pnl_krw"] = unrealized_krw
            position["unrealized_pnl_pct"] = unrealized_pct
            position["updated_at"] = _now_iso()

    def _new_state(self, initial_cash_krw: float, initial_cash_usd: float, paper_days: int) -> dict[str, Any]:
        now = _now_iso()
        fx_rate = _to_float(self.fx_provider()) or 1300.0
        return {
            "created_at": now,
            "updated_at": now,
            "paper_days": paper_days,
            "initial_cash_krw": initial_cash_krw,
            "initial_cash_usd": initial_cash_usd,
            "cash_krw": initial_cash_krw,
            "cash_usd": initial_cash_usd,
            "starting_equity_krw": initial_cash_krw + (initial_cash_usd * fx_rate),
            "realized_pnl_krw": 0.0,
            "realized_pnl_usd": 0.0,
            "total_fees_krw": 0.0,
            "total_fees_usd": 0.0,
            "positions": {},
            "orders": [],
        }

    def _build_seed_positions(self, seed_positions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        now = _now_iso()
        positions: dict[str, dict[str, Any]] = {}
        for raw in seed_positions:
            market = str(raw.get("market") or "").strip().upper()
            code = str(raw.get("code") or "").strip().upper()
            quantity = int(raw.get("quantity") or 0)
            avg_price_local = _to_float(raw.get("avg_price_local"))
            if market not in {"KOSPI", "NASDAQ"} or not code or quantity <= 0 or avg_price_local is None or avg_price_local <= 0:
                continue
            fx_rate = 1.0 if market == "KOSPI" else (_to_float(self.fx_provider()) or 1300.0)
            key = f"{market}:{code}"
            positions[key] = {
                "code": code,
                "name": str(raw.get("name") or code),
                "market": market,
                "currency": "KRW" if market == "KOSPI" else "USD",
                "quantity": quantity,
                "entry_ts": str(raw.get("entry_ts") or now),
                "avg_price_local": avg_price_local,
                "avg_price_krw": avg_price_local * fx_rate,
                "last_price_local": avg_price_local,
                "last_price_krw": avg_price_local * fx_rate,
                "fx_rate": fx_rate,
                "updated_at": now,
            }
        return positions

    def _load_state(self) -> dict[str, Any]:
        payload = _read_json(self.config.state_path)
        if not payload:
            state = self._new_state(
                self.config.default_initial_cash_krw,
                self.config.default_initial_cash_usd,
                self.config.default_paper_days,
            )
            self._persist(state)
            return state

        if not isinstance(payload.get("positions"), dict):
            payload["positions"] = {}
        if not isinstance(payload.get("orders"), list):
            payload["orders"] = []
        payload.setdefault("created_at", _now_iso())
        payload.setdefault("updated_at", _now_iso())
        payload.setdefault("paper_days", self.config.default_paper_days)
        payload.setdefault("initial_cash_krw", self.config.default_initial_cash_krw)
        payload.setdefault("initial_cash_usd", self.config.default_initial_cash_usd)
        payload.setdefault("cash_krw", payload["initial_cash_krw"])
        payload.setdefault("cash_usd", payload["initial_cash_usd"])
        payload.setdefault("starting_equity_krw", self._baseline_equity_krw(payload))
        payload.setdefault("realized_pnl_krw", 0.0)
        payload.setdefault("realized_pnl_usd", 0.0)
        payload.setdefault("total_fees_krw", 0.0)
        payload.setdefault("total_fees_usd", 0.0)
        return payload

    def _baseline_equity_krw(self, state: dict[str, Any]) -> float:
        fx_rate = _to_float(self.fx_provider()) or 1300.0
        seed_cash_krw = float(state.get("initial_cash_krw") or 0.0)
        seed_cash_usd = float(state.get("initial_cash_usd") or 0.0)
        seed_positions_krw = sum(
            float(item.get("avg_price_krw") or 0.0) * float(item.get("quantity") or 0.0)
            for item in (state.get("positions") or {}).values()
            if isinstance(item, dict)
        )
        return seed_cash_krw + (seed_cash_usd * fx_rate) + seed_positions_krw

    def _persist(self, state: dict[str, Any]) -> None:
        self.config.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _to_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


def _days_elapsed(created_at_iso: str) -> int:
    try:
        created_at = datetime.datetime.fromisoformat(created_at_iso)
    except (TypeError, ValueError):
        return 0
    now = datetime.datetime.now(created_at.tzinfo or datetime.timezone.utc)
    return max(0, (now.date() - created_at.date()).days)
