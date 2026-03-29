from app.core.cache import (
    CACHE_TTL,
    INVESTOR_FLOW_CACHE_TTL,
    REPORT_CACHE_TTL,
    TECHNICAL_CACHE_TTL,
    cache_state,
)

_market_cache = cache_state.market
_analysis_cache = cache_state.analysis
_recommendation_cache = cache_state.recommendation
_macro_cache = cache_state.macro
_market_context_cache = cache_state.market_context
_today_picks_cache = cache_state.today_picks
_ai_signals_cache = cache_state.ai_signals
_backtest_cache = cache_state.backtest
_backtest_run_cache = cache_state.backtest_runs
_technical_cache = cache_state.technical
_investor_flow_cache = cache_state.investor_flow
_kis_client = cache_state.kis_client
_kis_client_disabled = cache_state.kis_client_disabled
