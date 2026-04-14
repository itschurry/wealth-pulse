# 08. API와 Truth Source

이 문서는 현재 코드에서 자주 쓰는 API와, 실제 운영 기준이 되는 저장 파일을 한 번에 보게 정리한 표다.

## 1. 최상위 truth source

현재 compose 기준으로는 외부 DB가 없다. 그래서 내부 기준은 아래다.

### 1차
- API 응답
- `storage/logs/*` 상태 파일
- `storage/reports/*` 산출물

### 2차
- Web 화면

즉, 화면과 파일이 다르면 **파일/API를 먼저 믿는 게 맞다**.

## 2. 경로 기준

`apps/api/config/settings.py` 기준:

- `REPO_ROOT = /home/user/wealth-pulse`
- `STORAGE_DIR = REPO_ROOT / storage`
- `REPORTS_DIR = storage/reports`
- `LOGS_DIR = storage/logs`

도커 기준:
- `/reports`
- `/logs`

## 3. 헬스/시스템

| API | 용도 | 체크 포인트 |
|---|---|---|
| `GET /health` | API 헬스 | `{"status":"ok"}` |
| `GET /api/system/mode` | 시스템 모드 상태 | 운영 mode 확인 |
| `GET /api/engine/status` | 엔진+allocator+scanner 종합 상태 | scanner 캐시, risk guard, allocator |

## 4. 스캐너/전략/유니버스

| API | 용도 | 주의 |
|---|---|---|
| `GET /api/scanner/status` | 스캐너 상태 | `refresh`, `cache_only` 파라미터 확인 |
| `GET /api/strategies` | 전략 목록 | `market`, `live_only` 지원 |
| `GET /api/strategies/metadata` | 전략 메타 | editable fields / defaults 확인 |
| `GET /api/strategies/{id}` | 전략 상세 | 저장된 프리셋 점검 |
| `POST /api/strategies/save` | 전략 저장 | preset 생성 |
| `POST /api/strategies/toggle` | 전략 on/off | enabled 전환 |
| `POST /api/strategies/delete` | 전략 삭제 | 되돌리기 없음 |
| `POST /api/strategies/seed-defaults` | 기본 전략 시드 | 초기 세팅용 |
| `GET /api/universe` | 유니버스 조회/재생성 | `refresh=1` 가능 |

## 5. validation / optimization / quant-ops

| API | 용도 | Truth source |
|---|---|---|
| `GET /api/validation/settings` | 저장된 validation 상태 | `backtest_validation_settings.json` |
| `POST /api/validation/settings/save` | validation 저장 | `backtest_validation_settings.json` |
| `POST /api/validation/settings/reset` | validation 초기화 | `backtest_validation_settings.json` |
| `GET /api/validation/backtest` | 백테스트 실행 | 실행 시점 계산 결과 |
| `GET /api/validation/walk-forward` | walk-forward | 실행 시점 계산 결과 |
| `GET /api/validation/diagnostics` | 진단 | validation 디버깅 |
| `POST /api/run-optimization` | optimizer 실행 | 백그라운드 계산 |
| `GET /api/optimized-params` | 최적화 결과 조회 | optimized params payload |
| `GET /api/optimization-status` | optimizer 상태 | running 여부 |
| `GET /api/quant-ops/workflow` | quant-ops 상태 | `quant_ops_state.json` 연동 |
| `GET /api/quant-ops/policy` | 가드레일 정책 | `quant_guardrail_policy.json` |
| `POST /api/quant-ops/policy/save` | 정책 저장 | `quant_guardrail_policy.json` |
| `POST /api/quant-ops/policy/reset` | 정책 초기화 | `quant_guardrail_policy.json` |
| `POST /api/quant-ops/revalidate` | 후보 재검증 | workflow/state 갱신 |
| `POST /api/quant-ops/save-candidate` | 후보 저장 | workflow/state 갱신 |
| `POST /api/quant-ops/apply-runtime` | runtime 적용 | `quant_ops_state.json`, engine config 반영 |
| `POST /api/quant-ops/reset-workflow` | 워크플로우 초기화 | 상태 초기화 |

## 6. research / Hanna / reports

| API | 용도 | 주의 |
|---|---|---|
| `GET /api/research/status` | provider 상태 | healthy/degraded/missing 확인 |
| `GET /api/monitor/status` | 시장별 후보풀/감시 슬롯 요약 | core/promotion/held 집계 |
| `GET /api/monitor/watchlist` | 감시 슬롯 + pending research 조회 | 후보 리서치 truth source |
| `GET /api/monitor/promotions` | 감시 편입/제외 로그 | 슬롯 이동 추적 |
| `GET /api/research/snapshots/latest` | 최신 snapshot | freshness 확인 |
| `GET /api/research/snapshots` | snapshot 목록 | symbol/market/provider 필터 |
| `POST /api/research/ingest/bulk` | 일괄 ingest | 외부 ingest 경로 |
| `GET /api/hanna/brief` | Hanna 브리프 | operator brief |
| `GET /api/reports/explain` | 브리프+분석 | ReportsPage 기반 |
| `GET /api/reports/index` | 리포트 인덱스 | 도메인 진입점 |
| `GET /api/reports/operations` | 운영 리포트 | operations report |
| `GET /api/reports` | 기존 리포트 응답 | legacy/domain 혼용 구간 |
| `GET /api/analysis` | 분석 리포트 | 날짜 인자 가능 |
| `GET /api/recommendations` | 추천 | 날짜 인자 가능 |
| `GET /api/today-picks` | 오늘 추천 종목 | 날짜 인자 가능 |
| `GET /api/macro/latest` | 거시 데이터 | macro 블록 |
| `GET /api/market-context/latest` | 시장 컨텍스트 | 브리프 보조 |
| `GET /api/market-dashboard` | 시장 대시보드 | UI용 |

## 7. paper runtime / execution

| API | 용도 | Truth source |
|---|---|---|
| `GET /api/paper/account` | 계좌 조회 | `paper_account_state.json` + 최신 계산 |
| `POST /api/paper/order` | 수동 주문 | order/event 로그 |
| `POST /api/paper/reset` | 계좌 리셋 | `paper_account_state.json` |
| `POST /api/paper/history/clear` | 로그 초기화 | logs 파일 정리 |
| `POST /api/paper/auto-invest` | 자동 매수 | 실행 엔진 경유 |
| `POST /api/paper/engine/start` | 엔진 시작 | engine state 저장 |
| `POST /api/paper/engine/pause` | 엔진 일시정지 | engine state 저장 |
| `POST /api/paper/engine/resume` | 엔진 재개 | engine state 저장 |
| `POST /api/paper/engine/stop` | 엔진 중지 | engine state 저장 |
| `GET /api/paper/engine/status` | 엔진 상태 | engine state + workflow summary |
| `GET /api/paper/engine/cycles` | cycle 이력 | cycle 로그 |
| `GET /api/paper/orders` | 주문/실행 이벤트 | order + execution event 로그 |
| `GET /api/paper/workflow` | workflow 요약 | signal/order 연계 |
| `GET /api/paper/account/history` | 계좌 스냅샷 이력 | account snapshot 로그 |

## 8. market / signals / 기타

| API | 용도 |
|---|---|
| `GET /api/signals/rank` | signal 랭킹 |
| `GET /api/signals/snapshots` | signal snapshots |
| `GET /api/signals/{id}` | signal 상세 |
| `GET /api/portfolio/state` | 포트폴리오 상태 |
| `GET /api/performance/summary` | 성능 요약 |
| `GET /api/live-market` | 실시간 시장 요약 |
| `GET /api/stock-search?q=` | 종목 검색 |
| `GET /api/stock/{symbol}` | 종목 가격 |
| `GET /api/watchlist` | watchlist 조회 |
| `POST /api/watchlist-actions` | watchlist 액션 |
| `POST /api/watchlist/save` | watchlist 저장 |

## 9. 주요 저장 파일 표

| 파일 | 용도 | 코드 근거 |
|---|---|---|
| `storage/logs/backtest_validation_settings.json` | validation saved/displayed 기준 | `backtest_params_store.py` |
| `storage/logs/quant_guardrail_policy.json` | quant-ops 가드레일 정책 | `quant_guardrail_policy_store.py` |
| `storage/logs/quant_ops_state.json` | runtime apply 메타/상태 | `backtest_params_store.py`, quant-ops routes |
| `storage/logs/paper_account_state.json` | paper 계좌 상태 | `execution_service.py` |
| `storage/logs/*order*` | 주문 이벤트 | `paper_runtime_store` 계열 |
| `storage/logs/*signal*` | signal snapshot | `paper_runtime_store` 계열 |
| `storage/logs/*cycle*` | 엔진 사이클 | `paper_runtime_store` 계열 |
| `storage/logs/*account*` | 계좌 snapshot | `paper_runtime_store` 계열 |
| `storage/reports/*` | 리포트 산출물 | `config/settings.py` |

## 10. 디버깅 체크포인트 요약

### 증상: 화면 비어 있음
- `GET /api/engine/status`
- `GET /api/scanner/status`
- `GET /api/research/status`

### 증상: 주문 안 나감
- `GET /api/paper/engine/status`
- `GET /api/paper/workflow`
- `GET /api/paper/orders`
- `storage/logs`의 runtime 상태 파일

### 증상: 검증값이 이상함
- `GET /api/validation/settings`
- `storage/logs/backtest_validation_settings.json`

### 증상: quant-ops 반영 안 됨
- `GET /api/quant-ops/workflow`
- `GET /api/quant-ops/policy`
- `storage/logs/quant_ops_state.json`

## 11. 마지막 정리

지금 코드베이스는 화려한 척해도 결국 이런 시스템이다.

- scanner가 후보를 만들고
- runtime이 막거나 실행하고
- Hanna가 설명을 붙이고
- 파일 로그가 최종 기록을 남긴다

이 순서를 안 잊으면 디버깅도 훨씬 빨라진다.
