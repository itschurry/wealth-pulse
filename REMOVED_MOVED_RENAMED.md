# REMOVED_MOVED_RENAMED

## Added
- `api/routes/engine.py`
- `api/routes/signals.py`
- `api/routes/portfolio.py`
- `api/routes/validation.py`
- `api/routes/reports_domain.py`
- `services/strategy_engine.py`
- `services/ev_calibration_service.py`
- `services/strategy_allocator_service.py`
- `services/risk_guard_service.py`
- `services/sizing_service.py`
- `services/validation_service.py`
- `frontend/src/api/domain.ts`
- `frontend/src/types/domain.ts`
- `MIGRATION_NOTES.md`
- `PROFIT_MAX_IMPACT_RATIONALE.md`
- `LIVE_TRANSITION_BLOCKERS.md`

## Updated (Major behavior change)
- `api/server.py`
  - 도메인형 API 라우팅 추가
- `api/routes/reports.py`
  - recommendations/today picks 내부 산출 경로를 StrategyEngine 기반으로 전환
- `services/execution_service.py`
  - 자동매수/자동매매 매수 경로를 EV+size_recommendation 기반으로 전환
- `broker/execution_engine.py`
  - 슬리피지/유동성/갭 리스크 보정 반영
- `frontend/src/pages/OverviewPage.tsx`
- `frontend/src/pages/SignalsPage.tsx`
- `frontend/src/pages/PaperPortfolioPage.tsx`
- `frontend/src/pages/BacktestValidationPage.tsx`
- `frontend/src/pages/ReportsPage.tsx`
- `README.md`
- `tests/test_api_server.py`

## Removed
- 이번 변경에서 파일 단위 삭제 없음.

## Renamed / Moved
- 이번 변경에서 파일 rename/move 없음(신규 추가 + 기존 파일 수정 중심).
