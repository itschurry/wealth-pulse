from __future__ import annotations

from api.routes.reports import handle_analysis, handle_reports
from services.strategy_engine import build_signal_book


def handle_reports_explain(date: str | None = None) -> tuple[int, dict]:
    try:
        status, analysis = handle_analysis(date)
        if status != 200:
            return status, analysis

        signal_book = build_signal_book(markets=["KOSPI", "NASDAQ"], cfg={})
        return 200, {
            "ok": True,
            "analysis": analysis,
            "signal_reasoning": [
                {
                    "code": item.get("code"),
                    "strategy_type": item.get("strategy_type"),
                    "entry_allowed": item.get("entry_allowed"),
                    "reason_codes": item.get("reason_codes"),
                    "signal_reasoning": item.get("signal_reasoning"),
                }
                for item in signal_book.get("signals", [])[:30]
            ],
            "report_reasoning": analysis.get("analysis_playbook") if isinstance(analysis, dict) else {},
            "generated_at": signal_book.get("generated_at"),
        }
    except Exception as exc:
        return 500, {"ok": False, "error": str(exc)}


def handle_reports_index() -> tuple[int, dict]:
    return handle_reports()
