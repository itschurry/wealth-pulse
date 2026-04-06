from __future__ import annotations



def handle_hanna_brief(date: str | None = None) -> tuple[int, dict]:
    try:
        from routes.reports import _get_market_context
        from services.hanna_brief_service import build_hanna_brief_from_runtime
        from services.strategy_engine import build_signal_book

        signal_book = build_signal_book(markets=["KOSPI", "NASDAQ"], cfg={})
        market_context = _get_market_context()
        return 200, build_hanna_brief_from_runtime(
            signal_book=signal_book,
            market_context=market_context,
            date=date,
        )
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
