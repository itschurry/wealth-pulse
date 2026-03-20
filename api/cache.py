import threading

from broker.execution_engine import PaperExecutionEngine
from broker.kis_client import KISClient

CACHE_TTL = 300
REPORT_CACHE_TTL = 60
TECHNICAL_CACHE_TTL = 900
INVESTOR_FLOW_CACHE_TTL = 900

_market_cache: dict = {"data": None, "ts": 0.0}
_analysis_cache: dict = {"data": None, "ts": 0.0}
_recommendation_cache: dict = {"data": None, "ts": 0.0}
_macro_cache: dict = {"data": None, "ts": 0.0}
_market_context_cache: dict = {"data": None, "ts": 0.0}
_today_picks_cache: dict = {"data": None, "ts": 0.0}
_ai_signals_cache: dict = {"data": None, "ts": 0.0}
_backtest_cache: dict = {"data": None, "mtime": 0.0}
_backtest_run_cache: dict = {}
_technical_cache: dict = {}
_investor_flow_cache: dict = {}
_kis_client: KISClient | None = None
_kis_client_disabled = False
_paper_engine: PaperExecutionEngine | None = None
_auto_trader_lock = threading.Lock()
_auto_trader_stop_event: threading.Event | None = None
_auto_trader_thread: threading.Thread | None = None
_auto_trader_state: dict = {
    "running": False,
    "started_at": "",
    "last_run_at": "",
    "last_error": "",
    "last_summary": {},
    "config": {},
}
