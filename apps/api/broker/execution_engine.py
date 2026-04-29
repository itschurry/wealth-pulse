"""실시세 기반 모의/실주문 엔진 인터페이스와 Paper/Live 구현.

변경 사항:
  - [수정] PaperExecutionEngine.sell_fee_rate 계산에 증권거래세(0.18%) 반영
  - [수정] LiveBrokerExecutionEngine: KISClient를 실제로 연결하는 구현체로 교체
           (기존 stub → 국내/해외주식 주문 + 잔고 조회 실제 호출)
  - [추가] EngineConfig.sell_tax_rate_domestic: 증권거래세 상수 분리
"""
from __future__ import annotations

import datetime
import json
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from config.market_calendar import is_market_open
from market_utils import lookup_company_listing


# ── 인터페이스 ────────────────────────────────────────────────────────────────

class ExecutionEngine(Protocol):
    """주문 실행 엔진 공통 인터페이스."""

    def get_account(
        self, *, refresh_quotes: bool = True) -> dict[str, Any]: ...

    def place_order(
        self,
        *,
        side: str,
        code: str,
        market: str,
        quantity: int,
        order_type: str = "market",
        limit_price: float | None = None,
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
    ) -> dict[str, Any]: ...

    def reset(
        self,
        *,
        initial_cash_krw: float | None = None,
        initial_cash_usd: float | None = None,
        seed_positions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]: ...


# ── 설정 ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class EngineConfig:
    state_path: Path
    default_initial_cash_krw: float = 10_000_000.0
    default_initial_cash_usd: float = 10_000.0

    # 증권사 수수료 (매수/매도 공통, 온라인 기준 약 0.015%)
    buy_fee_rate: float = 0.00015
    sell_fee_rate: float = 0.00015

    # 국내주식 매도 시 증권거래세 (2025년 기준 0.18%, 코스피/코스닥 공통)
    # 해외주식에는 적용 안 함 (양도세는 연간 정산 개념이라 실시간 차감 제외)
    sell_tax_rate_domestic: float = 0.0018

    slippage_bps_base: float = 8.0
    slippage_bps_open_boost: float = 6.0
    slippage_bps_event_boost: float = 4.0
    liquidity_min_volume: int = 30_000
    liquidity_adv_ratio_limit: float = 0.03
    stop_gap_risk_bps: float = 25.0
    order_notifier: Callable[[dict[str, Any],
                              dict[str, Any]], None] | None = None

    def effective_sell_cost_rate(self, market: str) -> float:
        """실제 매도 총비용률 = 수수료 + (국내주식이면 증권거래세).

        국내: 0.00015 + 0.0018 = 0.19515%
        해외: 0.00015 (증권거래세 없음)
        """
        if market == "KOSPI":
            return self.sell_fee_rate + self.sell_tax_rate_domestic
        return self.sell_fee_rate


# ── Paper 엔진 ────────────────────────────────────────────────────────────────

class PaperExecutionEngine:
    """실시세를 참고해 내부 가상 계좌만 업데이트하는 모의 체결 엔진.

    KIS 실거래 API로 시세를 조회하지만, 실제 주문은 내부 state에만 기록한다.
    증권거래세(KOSPI 매도 0.18%)를 수수료에 포함하여 현실적인 P&L을 산출한다.
    """

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
        seed_positions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            seed_krw = float(
                initial_cash_krw
                if initial_cash_krw is not None
                else self.config.default_initial_cash_krw
            )
            seed_usd = float(
                initial_cash_usd
                if initial_cash_usd is not None
                else self.config.default_initial_cash_usd
            )
            seed_krw = max(0.0, seed_krw)
            seed_usd = max(0.0, seed_usd)

            self._state = self._new_state(seed_krw, seed_usd)
            if seed_positions:
                self._state["positions"] = self._build_seed_positions(
                    seed_positions)
            self._refresh_positions(self._state)
            self._state["starting_equity_krw"] = self._baseline_equity_krw(
                self._state)
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
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
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
            try:
                quote = self.quote_provider(normalized_code, normalized_market)
            except Exception as exc:
                return {"ok": False, "error": f"시세 조회 실패: {exc}"}

            quote_price = _to_float(quote.get("price"))
            if quote_price is None or quote_price <= 0:
                return {"ok": False, "error": "유효한 현재가를 가져오지 못했습니다."}
            if bool(quote.get("is_stale")):
                return {"ok": False, "error": "quote_stale"}

            can_trade, liquidity_reason = self._liquidity_gate(
                market=normalized_market, quote=quote, quantity=quantity
            )
            if not can_trade:
                return {"ok": False, "error": liquidity_reason or "liquidity_guard_blocked"}

            fx_rate = (
                1.0
                if normalized_market == "KOSPI"
                else (_to_float(self.fx_provider()) or 1300.0)
            )

            can_fill, reject_reason = self._can_fill(
                side=normalized_side,
                order_type=normalized_order_type,
                quote_price=quote_price,
                limit_price=limit_price,
            )
            if not can_fill:
                return {"ok": False, "error": reject_reason or "체결 조건이 맞지 않습니다."}

            slippage_bps = self._estimate_slippage_bps(
                market=normalized_market,
                quote=quote,
                quantity=quantity,
                side=normalized_side,
            )

            if normalized_order_type == "market":
                if normalized_side == "buy":
                    executed_local = quote_price * \
                        (1.0 + slippage_bps / 10_000.0)
                else:
                    executed_local = quote_price * \
                        (1.0 - slippage_bps / 10_000.0)
            else:
                executed_local = float(limit_price)

            executed_krw = executed_local * fx_rate

            # 매수: 증권사 수수료만 / 매도: 수수료 + 증권거래세 (국내만)
            buy_fee_rate = self.config.buy_fee_rate
            sell_cost_rate = self.config.effective_sell_cost_rate(
                normalized_market)
            fee_rate = buy_fee_rate if normalized_side == "buy" else sell_cost_rate

            now = _now_iso()

            state = self._state
            # Explicit sells must not trigger unrelated auto-liquidations before
            # the requested position is checked. A previous refresh can remove a
            # take-profit/stop-loss position from state; using the stale cycle
            # snapshot would otherwise create a second sell attempt with
            # "매도 가능 수량이 부족합니다.". Buys may still refresh first so
            # pending liquidations free paper cash/slots before new exposure.
            if normalized_side == "buy":
                self._refresh_positions(state)

            order_id = f"paper-{uuid.uuid4().hex[:12]}"
            position_key = f"{normalized_market}:{normalized_code}"
            position = state["positions"].get(position_key)

            if normalized_side == "buy":
                if normalized_market == "KOSPI":
                    per_share_cash = executed_krw * (1.0 + buy_fee_rate)
                    affordable_qty = (
                        int(float(state["cash_krw"]) // per_share_cash)
                        if per_share_cash > 0
                        else 0
                    )
                else:
                    per_share_cash = executed_local * (1.0 + buy_fee_rate)
                    affordable_qty = (
                        int(float(state["cash_usd"]) // per_share_cash)
                        if per_share_cash > 0
                        else 0
                    )
                quantity = min(quantity, affordable_qty)
                if quantity <= 0:
                    if normalized_market == "KOSPI":
                        return {"ok": False, "error": "원화 주문 가능 현금이 부족합니다."}
                    return {"ok": False, "error": "달러 주문 가능 현금이 부족합니다."}

            notional_local = executed_local * quantity
            notional_krw = executed_krw * quantity
            fee_local = max(0.0, notional_local * fee_rate)
            fee_krw = max(0.0, notional_krw * fee_rate)

            if normalized_side == "buy":
                if normalized_market == "KOSPI":
                    required_cash_krw = notional_krw + fee_krw
                    if float(state["cash_krw"]) < required_cash_krw:
                        return {"ok": False, "error": "원화 주문 가능 현금이 부족합니다."}
                    state["cash_krw"] = float(
                        state["cash_krw"]) - required_cash_krw
                    state["total_fees_krw"] = float(
                        state["total_fees_krw"]) + fee_krw
                else:
                    required_cash_usd = notional_local + fee_local
                    if float(state["cash_usd"]) < required_cash_usd:
                        return {"ok": False, "error": "달러 주문 가능 현금이 부족합니다."}
                    state["cash_usd"] = float(
                        state["cash_usd"]) - required_cash_usd
                    state["total_fees_usd"] = float(
                        state["total_fees_usd"]) + fee_local

                prev_qty = int(position["quantity"]) if position else 0
                prev_cost_local = (
                    float(position["avg_price_local"]) *
                    prev_qty if position else 0.0
                )
                next_qty = prev_qty + quantity
                avg_price_local = (prev_cost_local +
                                   notional_local) / max(next_qty, 1)
                avg_price_krw = avg_price_local * fx_rate

                final_sl = _to_float(stop_loss_pct)
                if final_sl is None and position:
                    final_sl = _to_float(position.get("stop_loss_pct"))
                final_tp = _to_float(take_profit_pct)
                if final_tp is None and position:
                    final_tp = _to_float(position.get("take_profit_pct"))

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
                    "stop_loss_pct": final_sl,
                    "take_profit_pct": final_tp,
                    "fx_rate": fx_rate,
                    "updated_at": now,
                }
                realized_local = 0.0
                realized_krw = 0.0

            else:  # sell
                held_qty = int(position["quantity"]) if position else 0
                if held_qty < quantity:
                    return {"ok": False, "error": "매도 가능 수량이 부족합니다."}

                avg_price_local = float(position["avg_price_local"])
                avg_price_krw = float(position["avg_price_krw"])
                proceeds_local = notional_local - fee_local
                proceeds_krw = notional_krw - fee_krw
                realized_local = (
                    executed_local - avg_price_local) * quantity - fee_local
                realized_krw = (executed_krw - avg_price_krw) * \
                    quantity - fee_krw

                if normalized_market == "KOSPI":
                    state["cash_krw"] = float(state["cash_krw"]) + proceeds_krw
                    state["realized_pnl_krw"] = (
                        float(state["realized_pnl_krw"]) + realized_krw
                    )
                    state["total_fees_krw"] = float(
                        state["total_fees_krw"]) + fee_krw
                else:
                    state["cash_usd"] = float(
                        state["cash_usd"]) + proceeds_local
                    state["realized_pnl_usd"] = (
                        float(state["realized_pnl_usd"]) + realized_local
                    )
                    state["total_fees_usd"] = float(
                        state["total_fees_usd"]) + fee_local

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
                "fee_breakdown": {
                    "brokerage_rate": (
                        buy_fee_rate if normalized_side == "buy" else self.config.sell_fee_rate
                    ),
                    "tax_rate": (
                        0.0
                        if normalized_side == "buy" or normalized_market != "KOSPI"
                        else self.config.sell_tax_rate_domestic
                    ),
                    "total_rate": fee_rate,
                },
                "realized_pnl_local": round(realized_local, 4),
                "realized_pnl_krw": round(realized_krw, 2),
                "status": "filled",
                "quote_source": quote.get("source") or "unknown",
                "quote_fetched_at": quote.get("fetched_at") or "",
                "quote_is_stale": bool(quote.get("is_stale")),
                "execution_realism": {
                    "slippage_bps": round(slippage_bps, 2),
                    "slippage_model_version": "intraday_v2",
                    "liquidity_gate_status": "passed",
                },
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
                    pass

            return {"ok": True, "event": event, "account": snapshot}

    def _market_is_opening_window(self, market: str) -> bool:
        now = datetime.datetime.now(datetime.timezone.utc)
        if market == "KOSPI":
            current = now.astimezone(
                datetime.timezone(datetime.timedelta(hours=9))
            )
            return current.hour == 9 and current.minute < 30
        if market == "NASDAQ":
            et = now.astimezone(
                datetime.timezone(datetime.timedelta(hours=-4))
            )
            return (et.hour == 9 and et.minute >= 30) or (
                et.hour == 10 and et.minute < 30
            )
        return False

    def _estimate_slippage_bps(
        self,
        *,
        market: str,
        quote: dict[str, Any],
        quantity: int,
        side: str,
    ) -> float:
        bps = float(self.config.slippage_bps_base)
        if self._market_is_opening_window(market):
            bps += float(self.config.slippage_bps_open_boost)
        change_pct = abs(_to_float(quote.get("change_pct")) or 0.0)
        bps += min(12.0, change_pct * 1.2)
        if bool(quote.get("event_risk")):
            bps += float(self.config.slippage_bps_event_boost)
        volume_ratio = _to_float(quote.get("volume_ratio"))
        if volume_ratio is not None and 0 < volume_ratio < 1.0:
            bps += (1.0 - volume_ratio) * 10.0
        if quantity >= 1000:
            bps += 2.0
        if side == "sell":
            bps += 0.5
        return max(1.0, min(80.0, bps))

    def _liquidity_gate(
        self, *, market: str, quote: dict[str, Any], quantity: int
    ) -> tuple[bool, str | None]:
        volume = _to_float(quote.get("volume"))
        avg_volume = _to_float(quote.get("volume_avg20")) or volume
        if volume is not None and volume < self.config.liquidity_min_volume:
            return False, "liquidity_guard:volume_too_low"
        if avg_volume is not None and avg_volume > 0:
            adv_ratio = quantity / avg_volume
            if adv_ratio > float(self.config.liquidity_adv_ratio_limit):
                return False, "liquidity_guard:adv_ratio_exceeded"
        return True, None

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
        total_market_value_krw = sum(
            float(item.get("market_value_krw") or 0.0) for item in positions
        )
        total_market_value_usd = sum(
            float(item.get("market_value_usd") or 0.0) for item in positions
        )
        fx_rate = _to_float(self.fx_provider()) or 1300.0
        cash_krw = float(state["cash_krw"])
        cash_usd = float(state["cash_usd"])
        equity_krw = cash_krw + (cash_usd * fx_rate) + total_market_value_krw
        starting_equity_krw = float(
            state.get("starting_equity_krw") or self._baseline_equity_krw(state)
        )
        created_at = state["created_at"]
        days_elapsed = _days_elapsed(created_at)

        return {
            "mode": "paper",
            "base_currency": "MULTI",
            "created_at": created_at,
            "updated_at": state["updated_at"],
            "days_elapsed": days_elapsed,
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

            current_name = str(position.get("name") or "")
            if not current_name or current_name == code:
                catalog = lookup_company_listing(
                    code=code, scope="core"
                ) or lookup_company_listing(code=code, scope="live")
                if catalog and catalog.get("name"):
                    position["name"] = catalog["name"]

            try:
                quote = self.quote_provider(code, market)
            except Exception:
                continue

            quote_price = _to_float(quote.get("price"))
            if quote_price is None or quote_price <= 0:
                continue

            fx_rate = (
                1.0
                if market == "KOSPI"
                else (_to_float(self.fx_provider()) or float(position.get("fx_rate") or 1300.0))
            )
            last_price_local = quote_price
            last_price_krw = quote_price * fx_rate
            avg_price_local = float(position.get("avg_price_local") or 0.0)
            avg_price_krw = float(position.get("avg_price_krw") or 0.0)
            market_value_local = last_price_local * quantity
            market_value_krw = last_price_krw * quantity
            unrealized_local = (last_price_local - avg_price_local) * quantity
            unrealized_krw = (last_price_krw - avg_price_krw) * quantity
            base_cost_krw = avg_price_krw * quantity
            unrealized_pct = (
                (unrealized_krw / base_cost_krw *
                 100) if base_cost_krw > 0 else 0.0
            )

            resolved_name = quote.get("name") or position.get("name") or ""
            if not resolved_name or resolved_name == code:
                catalog = lookup_company_listing(
                    code=code, scope="core"
                ) or lookup_company_listing(code=code, scope="live")
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

            sl = _to_float(position.get("stop_loss_pct"))
            tp = _to_float(position.get("take_profit_pct"))
            liquidation_reason = None
            if sl is not None and unrealized_pct <= -sl:
                liquidation_reason = "stop_loss"
            elif tp is not None and unrealized_pct >= tp:
                liquidation_reason = "take_profit"

            if liquidation_reason:
                if not is_market_open(market):
                    position["pending_liquidation_reason"] = liquidation_reason
                    continue
                position.pop("pending_liquidation_reason", None)
                self._auto_liquidate(
                    state=state,
                    key=key,
                    position=position,
                    market=market,
                    quantity=quantity,
                    last_price_local=last_price_local,
                    last_price_krw=last_price_krw,
                    avg_price_local=avg_price_local,
                    avg_price_krw=avg_price_krw,
                    fx_rate=fx_rate,
                    reason=liquidation_reason,
                )

    def _auto_liquidate(
        self,
        *,
        state: dict[str, Any],
        key: str,
        position: dict[str, Any],
        market: str,
        quantity: int,
        last_price_local: float,
        last_price_krw: float,
        avg_price_local: float,
        avg_price_krw: float,
        fx_rate: float,
        reason: str,
    ) -> None:
        now = _now_iso()
        sell_cost_rate = self.config.effective_sell_cost_rate(market)
        slippage_bps = float(self.config.slippage_bps_base)
        if reason == "stop_loss":
            slippage_bps += float(self.config.stop_gap_risk_bps)

        gap_price_local = max(0.0, last_price_local *
                              (1.0 - slippage_bps / 10_000.0))
        gap_price_krw = gap_price_local * fx_rate
        notional_local = gap_price_local * quantity
        notional_krw = gap_price_krw * quantity
        fee_local = max(0.0, notional_local * sell_cost_rate)
        fee_krw = max(0.0, notional_krw * sell_cost_rate)
        proceeds_local = notional_local - fee_local
        proceeds_krw = notional_krw - fee_krw
        realized_local = (gap_price_local - avg_price_local) * \
            quantity - fee_local
        realized_krw = (gap_price_krw - avg_price_krw) * quantity - fee_krw

        if market == "KOSPI":
            state["cash_krw"] = float(state["cash_krw"]) + proceeds_krw
            state["realized_pnl_krw"] = float(
                state["realized_pnl_krw"]) + realized_krw
            state["total_fees_krw"] = float(state["total_fees_krw"]) + fee_krw
        else:
            state["cash_usd"] = float(state["cash_usd"]) + proceeds_local
            state["realized_pnl_usd"] = float(
                state["realized_pnl_usd"]) + realized_local
            state["total_fees_usd"] = float(
                state["total_fees_usd"]) + fee_local

        event = {
            "order_id": f"paper-liq-{uuid.uuid4().hex[:8]}",
            "ts": now,
            "side": "sell",
            "order_type": "market",
            "code": position["code"],
            "name": position["name"],
            "market": market,
            "quantity": quantity,
            "filled_price_local": round(gap_price_local, 4),
            "filled_price_krw": round(gap_price_krw, 4),
            "fx_rate": round(fx_rate, 4),
            "notional_local": round(notional_local, 4),
            "notional_krw": round(notional_krw, 2),
            "fee_local": round(fee_local, 4),
            "fee_krw": round(fee_krw, 2),
            "realized_pnl_local": round(realized_local, 4),
            "realized_pnl_krw": round(realized_krw, 2),
            "status": "filled",
            "note": f"Auto-liquidation ({reason})",
            "execution_realism": {
                "slippage_bps": round(slippage_bps, 2),
                "slippage_model_version": "gap-risk-v1",
            },
        }
        state["orders"].insert(0, event)
        state["positions"].pop(key, None)

        notifier = self.config.order_notifier
        if notifier is not None:
            try:
                notifier(event, self._build_snapshot(state))
            except Exception:
                pass

    def _new_state(
        self, initial_cash_krw: float, initial_cash_usd: float
    ) -> dict[str, Any]:
        now = _now_iso()
        fx_rate = _to_float(self.fx_provider()) or 1300.0
        return {
            "created_at": now,
            "updated_at": now,
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

    def _build_seed_positions(
        self, seed_positions: list[dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        now = _now_iso()
        positions: dict[str, dict[str, Any]] = {}
        for raw in seed_positions:
            market = str(raw.get("market") or "").strip().upper()
            code = str(raw.get("code") or "").strip().upper()
            quantity = int(raw.get("quantity") or 0)
            avg_price_local = _to_float(raw.get("avg_price_local"))
            if (
                market not in {"KOSPI", "NASDAQ"}
                or not code
                or quantity <= 0
                or avg_price_local is None
                or avg_price_local <= 0
            ):
                continue
            fx_rate = (
                1.0
                if market == "KOSPI"
                else (_to_float(self.fx_provider()) or 1300.0)
            )
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
            )
            self._persist(state)
            return state
        if not isinstance(payload.get("positions"), dict):
            payload["positions"] = {}
        if not isinstance(payload.get("orders"), list):
            payload["orders"] = []
        payload.setdefault("created_at", _now_iso())
        payload.setdefault("updated_at", _now_iso())
        payload.pop("paper_days", None)
        payload.setdefault("initial_cash_krw",
                           self.config.default_initial_cash_krw)
        payload.setdefault("initial_cash_usd",
                           self.config.default_initial_cash_usd)
        payload.setdefault("cash_krw", payload["initial_cash_krw"])
        payload.setdefault("cash_usd", payload["initial_cash_usd"])
        payload.setdefault("starting_equity_krw",
                           self._baseline_equity_krw(payload))
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
            float(item.get("avg_price_krw") or 0.0)
            * float(item.get("quantity") or 0.0)
            for item in (state.get("positions") or {}).values()
            if isinstance(item, dict)
        )
        return seed_cash_krw + (seed_cash_usd * fx_rate) + seed_positions_krw

    def _persist(self, state: dict[str, Any]) -> None:
        self.config.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.state_path.write_text(
            json.dumps(state, ensure_ascii=False), encoding="utf-8"
        )


# ── Live 엔진 ────────────────────────────────────────────────────────────────

class LiveBrokerExecutionEngine:
    """KISClient를 통해 실제 계좌에 주문을 집행하는 실거래 엔진.

    사용 전 체크리스트:
      □ .env의 KIS_BASE_URL이 실거래 서버인지 확인
      □ KIS_ACCOUNT_CANO, KIS_ACCOUNT_ACNT_PRDT_CD 설정 확인
      □ kis_client.place_cash_order / place_overseas_order에 hashkey 포함 확인 (✅ 완료)
      □ 시장 개장 시간 체크 로직 추가 권장
      □ 일일 최대 주문 횟수 제한 추가 권장
    """

    def __init__(
        self,
        *,
        kis_client: Any,  # KISClient — 순환 import 방지를 위해 Any 타입
        quote_provider: Callable[[str, str], dict[str, Any]],
        fx_provider: Callable[[], float | None],
        config: EngineConfig,
    ) -> None:
        self._client = kis_client
        self.quote_provider = quote_provider
        self.fx_provider = fx_provider
        self.config = config

    def get_account(self, *, refresh_quotes: bool = True) -> dict[str, Any]:
        """실계좌 잔고를 KIS API에서 직접 조회한다."""
        try:
            return self._client.get_balance()
        except Exception as exc:
            return {
                "ok": False,
                "mode": "live",
                "error": str(exc),
            }

    def place_order(
        self,
        *,
        side: str,
        code: str,
        market: str,
        quantity: int,
        order_type: str = "market",
        limit_price: float | None = None,
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
    ) -> dict[str, Any]:
        """실계좌에 주문을 집행한다. hashkey는 KISClient 내부에서 자동 처리된다.

        현재 지원: KOSPI 국내주식 현금주문, NASDAQ 해외주식 현금주문
        지정가(limit) 주문: limit_price 필수
        """
        normalized_market = market.strip().upper()
        normalized_side = side.strip().lower()

        if normalized_side not in {"buy", "sell"}:
            return {"ok": False, "error": "side는 buy/sell만 허용합니다."}
        if normalized_market not in {"KOSPI", "NASDAQ"}:
            return {"ok": False, "error": "market은 KOSPI/NASDAQ만 허용합니다."}
        if quantity <= 0:
            return {"ok": False, "error": "quantity는 1 이상이어야 합니다."}

        # 주문 가격 결정
        if order_type == "limit":
            if limit_price is None or limit_price <= 0:
                return {"ok": False, "error": "limit 주문에는 유효한 limit_price가 필요합니다."}
            price = limit_price
            order_division = "00"  # 지정가
        else:
            # 시장가: 현재가를 quote에서 가져와 ORD_UNPR=0으로 보내거나
            # KIS 시장가 주문 코드(01)로 처리
            order_division = "01"  # 시장가
            price = 0  # 시장가 주문 시 0 입력

        try:
            if normalized_market == "KOSPI":
                result = self._client.place_cash_order(
                    side=normalized_side,
                    code=code.strip().upper(),
                    quantity=quantity,
                    price=price,
                    order_division=order_division,
                )
            else:  # NASDAQ
                result = self._client.place_overseas_order(
                    side=normalized_side,
                    symbol=code.strip().upper(),
                    quantity=quantity,
                    price=price,
                    exchange="NASDAQ",
                    order_division=order_division,
                )
            return {"ok": True, "mode": "live", **result}
        except Exception as exc:
            return {
                "ok": False,
                "mode": "live",
                "error": str(exc),
                "requested": {
                    "side": side,
                    "code": code,
                    "market": market,
                    "quantity": quantity,
                    "order_type": order_type,
                    "limit_price": limit_price,
                },
            }

    def reset(
        self,
        *,
        initial_cash_krw: float | None = None,
        initial_cash_usd: float | None = None,
        seed_positions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """실거래 엔진에서는 reset이 허용되지 않는다."""
        return {
            "ok": False,
            "mode": "live",
            "error": "실거래 엔진은 reset을 지원하지 않습니다.",
        }


# ── 유틸 ─────────────────────────────────────────────────────────────────────

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
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(
        timespec="seconds"
    )


def _days_elapsed(created_at_iso: str) -> int:
    try:
        created_at = datetime.datetime.fromisoformat(created_at_iso)
    except (TypeError, ValueError):
        return 0
    now = datetime.datetime.now(created_at.tzinfo or datetime.timezone.utc)
    return max(0, (now.date() - created_at.date()).days)
