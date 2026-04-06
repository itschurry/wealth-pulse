from __future__ import annotations

def handle_hanna_brief(date: str | None = None) -> tuple[int, dict]:
    try:
        try:
            from domains.report.market_context_service import get_market_context
        except ModuleNotFoundError:  # pragma: no cover - package import fallback
            from apps.api.domains.report.market_context_service import get_market_context
        from services.hanna_brief_service import build_hanna_brief_from_runtime
        from services.strategy_engine import build_signal_book
        from services.execution_service import get_execution_service

        _, execution_payload = get_execution_service().paper_engine_status()
        account = execution_payload.get("account") if isinstance(execution_payload, dict) else {}
        signal_book = build_signal_book(
            markets=["KOSPI", "NASDAQ"],
            cfg={},
            account=account if isinstance(account, dict) else {},
        )
        market_context = get_market_context()
        return 200, build_hanna_brief_from_runtime(
            signal_book=signal_book,
            market_context=market_context,
            date=date,
        )
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}
