from __future__ import annotations

from routes.reports import handle_reports
from services.operations_report_service import build_operations_report


def handle_reports_explain(date: str | None = None) -> tuple[int, dict]:
    try:
        operations = build_operations_report(limit=500)
        alerts = operations.get('alerts') if isinstance(operations.get('alerts'), list) else []
        summary_lines = [str(item.get('message') or '').strip() for item in alerts if isinstance(item, dict) and str(item.get('message') or '').strip()]
        report = operations.get('report') if isinstance(operations.get('report'), dict) else {}
        analysis = {
            'summary_lines': summary_lines,
            'operations': report,
            'alerts': alerts,
        }
        return 200, {
            'ok': True,
            'owner': 'wealthpulse-agent-runtime',
            'brief_type': 'operations_report_v1',
            'generated_at': operations.get('generated_at'),
            'summary_lines': summary_lines,
            'analysis': analysis,
            'report_reasoning': report,
        }
    except Exception as exc:
        return 500, {'ok': False, 'error': str(exc)}


def handle_reports_index() -> tuple[int, dict]:
    return handle_reports()


def handle_reports_operations(limit: int = 500) -> tuple[int, dict]:
    try:
        return 200, {
            'ok': True,
            **build_operations_report(limit=limit),
        }
    except Exception as exc:
        return 500, {'ok': False, 'error': str(exc)}
