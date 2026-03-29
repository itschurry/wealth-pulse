from __future__ import annotations

from broker.kis_client import KISClient


class CacheState:
    def __init__(self) -> None:
        self.market = {"data": None, "ts": 0.0}
        self.analysis = {"data": None, "ts": 0.0}
        self.recommendation = {"data": None, "ts": 0.0}
        self.macro = {"data": None, "ts": 0.0}
        self.market_context = {"data": None, "ts": 0.0}
        self.today_picks = {"data": None, "ts": 0.0}
        self.ai_signals = {"data": None, "ts": 0.0}
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
