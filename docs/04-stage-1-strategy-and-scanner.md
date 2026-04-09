# 04. Stage 1 — 전략과 스캐너

이 단계는 "무엇을 볼지"를 정하는 계층이다. 아직 주문 얘기보다 후보 수집과 점수화가 먼저다.

## 구성 요소

- 전략 레지스트리
- 유니버스 빌더
- 스캐너 상태 집계
- Layer A/B/D/E 표시용 candidate payload

## 전략 레지스트리

관련 파일:
- `apps/api/routes/strategies.py`
- `apps/web/src/pages/SettingsPage.tsx`
- `apps/web/src/pages/BacktestValidationPage.tsx`

주요 엔드포인트:
- `GET /api/strategies`
- `GET /api/strategies/metadata`
- `GET /api/strategies/{strategy_id}`
- `POST /api/strategies/save`
- `POST /api/strategies/toggle`
- `POST /api/strategies/delete`
- `POST /api/strategies/seed-defaults`

### 역할
- 전략 목록 조회
- market/live_only 필터링
- editable field metadata 제공
- 프리셋 저장/활성/비활성

## 유니버스

관련 파일:
- `apps/api/routes/universe.py`

주요 엔드포인트:
- `GET /api/universe`

동작:
- 현재 유니버스 목록 조회
- `refresh=1`일 때 전략별 유니버스 재생성
- `rule_name`, `market`별 개별 조회 가능

### 운영 포인트
전략이 있는데 후보가 아예 없다면 무조건 스캐너 탓부터 할 게 아니라
1. 전략 enabled 여부
2. universe rule
3. market 매칭
부터 봐야 한다.

## 스캐너 상태

관련 파일:
- `apps/api/routes/scanner.py`
- `apps/api/routes/engine.py`
- `apps/web/src/pages/ScannerPage.tsx`

주요 엔드포인트:
- `GET /api/scanner/status`
- `GET /api/engine/status`

### `engine/status`의 의미
이 엔드포인트는 단순 엔진 상태만 주는 게 아니다.

포함 내용:
- mode
- execution payload
- registry 요약
- allocator 요약
- risk guard state
- scanner 결과

중요한 점:
- 장중 폴링 엔드포인트라서 **fresh scan을 매번 트리거하지 않음**
- 캐시된 scan 결과만 사용

이 설계가 맞다. 여기서 매번 라이브 스캔 돌리면 운영 UI가 버벅이는 정도가 아니라 그냥 망가진다.

## ScannerPage가 보여주는 것

Web 파일:
- `apps/web/src/pages/ScannerPage.tsx`

이 화면은 단순 테이블이 아니라 각 candidate를 레이어별로 쪼개 보여준다.

### 요약 바에서 보는 것
- 스캔 전략 수
- 활성 전략 수
- 스캔 종목 수
- 후보 수
- 스캔 소스(cache/live)
- Hanna 상태

### 전략별 카드에서 보는 것
- strategy_name
- market
- universe_rule
- scan_cycle
- last_scan_at / next_scan_at
- scanned_symbol_count / universe_symbol_count

### 후보별 표에서 보는 것
- rank
- symbol
- Layer B 점수
- Layer C 상태
- Layer D/E 상태
- reason codes

## Layer A~E 해석

### Layer A
- universe_rule
- scan_time
- inclusion_reason

### Layer B
- quant_score
- strategy_id
- quant_tags

### Layer C
- research_score
- warnings
- tags
- summary
- provider health 반영

### Layer D
- blocked 여부
- reason codes
- liquidity/spread/position cap 상태

### Layer E
- final_action
- decision_reason
- source_context

## scanner / runtime / Hanna 분리 관점

### scanner
- 종목을 긁고 정량 후보를 만든다.
- 후보 순위와 레이어별 메타를 유지한다.

### runtime
- 스캐너 결과를 실제 orderable 후보로 연결할지 판단한다.

### Hanna
- candidate에 설명을 붙인다.
- health/degraded/research_unavailable 상태를 만든다.
- 하지만 주문 판단권은 없다.

## Stage 1 디버깅 체크포인트

### 전략은 있는데 후보가 없음
- `/api/strategies`
- `/api/universe?refresh=1`
- `/api/scanner/status?refresh=1`

### scanner count는 있는데 화면에 비어 보임
- `/api/engine/status`
- `apps/web/src/pages/ScannerPage.tsx`의 `top_candidates` 사용부
- candidate payload 안의 `signal_id`, `strategy_id`, `final_action`

### Hanna만 이상함
- `/api/research/status`
- `/api/research/snapshots/latest`

## 운영에서 바로 봐야 할 항목

- `scanner.source`: cache인지 live_scan인지
- `scanner.refreshing`: 갱신 중인지
- `strategy_counts`
- `entry_allowed_count`
- `blocked_count`
- candidate별 `final_action`
- candidate별 `reason_codes`

## 자주 생기는 문제

### 1) candidate는 있는데 다 blocked
이건 스캐너가 고장난 게 아니라 리스크/검증 계층이 보수적으로 막는 상황일 수 있다.

### 2) Hanna unavailable이라서 시스템 전체가 죽었다고 착각
아니다. Layer C 품질 저하일 뿐이다.

### 3) engine/status를 실시간 스캔 API로 오해
아니다. 캐시 요약 성격이 강하다.
