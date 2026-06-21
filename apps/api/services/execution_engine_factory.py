from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from broker.execution_engine import EngineConfig, LiveBrokerExecutionEngine, SimulatedExecutionEngine
from broker.kis_client import KISClient
from services.market_data_service import get_usd_krw_rate, resolve_stock_quote
from services.runtime_account_cache import ACCOUNT_STATE_DIR

_simulated_engine: SimulatedExecutionEngine | None = None
_live_engine: LiveBrokerExecutionEngine | None = None


def _get_simulated_engine(order_notifier: Callable[[dict[str, Any], dict[str, Any]], None]) -> SimulatedExecutionEngine:
    global _simulated_engine
    if _simulated_engine is None:
        state_path = Path(os.getenv("RUNTIME_ACCOUNT_STATE_PATH") or str(ACCOUNT_STATE_DIR / "simulated_account_state.json"))
        _simulated_engine = SimulatedExecutionEngine(
            config=EngineConfig(
                state_path=state_path,
                default_initial_cash_krw=10_000_000.0,
                default_initial_cash_usd=0.0,
                order_notifier=order_notifier,
            ),
            quote_provider=resolve_stock_quote,
            fx_provider=get_usd_krw_rate,
        )
    return _simulated_engine


def _get_live_engine() -> LiveBrokerExecutionEngine:
    global _live_engine
    if _live_engine is None:
        kis = KISClient.from_env()
        _live_engine = LiveBrokerExecutionEngine(
            kis_client=kis,
            quote_provider=resolve_stock_quote,
            fx_provider=get_usd_krw_rate,
            config=EngineConfig(
                state_path=ACCOUNT_STATE_DIR / "live_account_state.json",
            ),
        )
    return _live_engine


def get_execution_engine(
    mode: str = "paper",
    *,
    order_notifier: Callable[[dict[str, Any], dict[str, Any]], None],
) -> SimulatedExecutionEngine | LiveBrokerExecutionEngine:
    normalized_mode = str(mode or "paper").strip().lower()
    if normalized_mode == "live":
        return _get_live_engine()
    return _get_simulated_engine(order_notifier)
