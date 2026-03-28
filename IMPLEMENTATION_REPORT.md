# IMPLEMENTATION_REPORT

## Scope
- Profit-Max refactor Stage 1 중심 구현:
  - 공통 전략 엔진(StrategyEngine)
  - EV 캘리브레이션/리스크 가드/사이징
  - 도메인 API 재설계
  - 실행 현실화(슬리피지/유동성/갭)
  - 운영 콘솔형 프런트 페이지 전환

## Key Outcomes
- 매수 경로가 점수 기반 분기에서 EV + guard + sizing 기반으로 전환됨.
- `/api/engine|signals|portfolio|validation|reports` 도메인 API 사용 가능.
- 백테스트/검증에 OOS 중심 지표 제공(Profit Factor, OOS reliability 등).

## Verification
- Python compile: pass
- Frontend build: pass
- Selected tests:
  - `tests/test_api_server.py`: pass
  - `tests/test_reports_cache.py`: pass
  - `tests/test_scheduler.py`: pass
- Full tests:
  - 기존 baseline 전략 디폴트 상수 불일치 3건으로 fail (`test_shared_strategy`, `test_strategy_config`)
