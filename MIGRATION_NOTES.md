# MIGRATION_NOTES

## 2026-03-28 Profit-Max Refactor (Stage 1 중심)

### 1) API 리디자인
- 신규 도메인 API를 추가하고 서버 라우팅에 연결:
  - `/api/engine/status`
  - `/api/signals/rank`
  - `/api/signals/{code}`
  - `/api/portfolio/state`
  - `/api/validation/backtest`
  - `/api/validation/walk-forward`
  - `/api/reports/explain`
  - `/api/reports/index`

### 2) 공통 전략 엔진 단일화
- `services/strategy_engine.py`를 도입해 EV 기반 신호 생성을 공통 경로로 통합.
- `services/execution_service.py`의 자동매수/자동매매 매수 경로를 `StrategyEngine` 결과 사용 방식으로 전환:
  - `entry_allowed`
  - `ev_metrics.expected_value`
  - `size_recommendation.quantity`
  - `reason_codes`

### 3) EV/Allocator/Risk/Sizing 계층 추가
- `services/ev_calibration_service.py`: 캘리브레이션 + shrinkage 기반 EV 산출
- `services/strategy_allocator_service.py`: 전략타입 결정 + regime 기반 할당
- `services/risk_guard_service.py`: 일손실/연속손실/쿨다운/노출캡 가드
- `services/sizing_service.py`: stop-distance + 예산 + 노출캡 기반 사이징

### 4) 실행 현실화
- `broker/execution_engine.py`에 아래 로직 추가:
  - 장초 가중 포함 슬리피지 모델
  - 유동성 가드(최소 거래량/ADV 주문비율)
  - 자동청산 시 갭 리스크 보정 체결가

### 5) 검증/지표 확장
- `services/validation_service.py`로 확장 성과지표 및 walk-forward 요약 추가:
  - CAGR, MDD, Sharpe, Sortino, Profit Factor, Win Rate, Avg Win/Loss, Exposure, Turnover
  - Exit reason stats, regime stats, rolling windows

### 6) 프런트 운영 콘솔화
- 라우트별 페이지를 신규 도메인 API 소비 방식으로 전환:
  - `Overview`: 엔진/가드 요약
  - `Signals`: EV 랭크 표
  - `Paper Portfolio`: 포지션 + guard 상태
  - `Backtest/Validation`: 백테스트 + OOS 요약
  - `Reports`: explainability 뷰

### 7) 테스트/빌드 메모
- 통과:
  - `python3 -m py_compile ...` (변경 파일 컴파일)
  - `cd frontend && npm run build`
  - `PYTHONPATH=. .venv/bin/pytest -q tests/test_api_server.py tests/test_reports_cache.py tests/test_scheduler.py`
- 전체 `tests` 실행은 기존 baseline 불일치 3건(`test_shared_strategy`, `test_strategy_config`)로 실패.
