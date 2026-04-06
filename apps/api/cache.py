from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from broker.kis_client import KISClient


class CacheState:
    def __init__(self) -> None:
        self.market = {"data": None, "ts": 0.0}
        self.analysis = {"data": None, "ts": 0.0}
        self.recommendation = {"data": None, "ts": 0.0}
        self.macro = {"data": None, "ts": 0.0}
        self.market_context = {"data": None, "ts": 0.0}
        self.today_picks = {"data": None, "ts": 0.0}
        self.backtest = {"data": None, "mtime": 0.0}
        self.backtest_runs: dict = {}
        self.technical: dict = {}
        self.investor_flow: dict = {}
        self.kis_client: KISClient | None = None
        self.kis_client_disabled = False


cache_state = CacheState()

CACHE_TTL = 300
REPORT_CACHE_TTL = 60
TECHNICAL_CACHE_TTL = 900
INVESTOR_FLOW_CACHE_TTL = 900

_market_cache = cache_state.market
_analysis_cache = cache_state.analysis
_recommendation_cache = cache_state.recommendation
_macro_cache = cache_state.macro
_market_context_cache = cache_state.market_context
_today_picks_cache = cache_state.today_picks
_backtest_cache = cache_state.backtest
_backtest_run_cache = cache_state.backtest_runs
_technical_cache = cache_state.technical
_investor_flow_cache = cache_state.investor_flow
_kis_client = cache_state.kis_client
_kis_client_disabled = cache_state.kis_client_disabled
