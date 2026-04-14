# SQLite 기반 핵심 감시 + 승격 슬롯 전환 계획

목표
- JSON 중심 운영 상태를 SQLite 기반 감시 상태로 전환
- 시장별 `핵심 감시 + 승격 슬롯 + 보유 종목 상시 추적` 구조로 후보/리서치/장중 판단 흐름 재구성
- 애매한 이중 구조를 남기지 않고 단계 종료 시점마다 구구조를 명확히 삭제

원칙
- 유니버스 원본은 기존 소스 유지
- 운영 중 자주 읽는 상태만 SQLite로 이동
- 단계별로 "새 구조 연결 -> 구 구조 참조 제거 -> 검증"까지 한 배치로 닫기
- 호환용 임시 어댑터는 최종 단계 전에 반드시 제거

## 1단계 — SQLite 저장소 도입
범위
- `apps/api/services/candidate_monitor_store.py` 신설
- SQLite DB: 시장별 후보 풀, 핵심 감시 슬롯, 승격 슬롯, 보유 추적, 이벤트 로그 저장
- 최소 CRUD + replace/upsert API 제공

완료 기준
- SQLite DB 파일 생성
- 후보 풀/활성 슬롯/이벤트를 저장·조회하는 단위 테스트 통과
- 아직 기존 JSON 운영 경로는 유지

## 2단계 — 후보 풀/핵심 감시/승격 슬롯 선정 서비스 연결
범위
- `apps/api/services/candidate_monitor_service.py` 신설
- 입력 truth source는 우선 `strategy_scans/*.json`의 `top_candidates`
- 시장별 규칙
  - 핵심 감시 슬롯 10~12
  - 승격 슬롯 2~3
  - 보유 종목 별도 고정 추적
- 리서치 대상은 `핵심 감시 + 승격 슬롯` 중심으로 계산

완료 기준
- 시장별 watchlist materialize 가능
- 승격/탈락 이벤트가 SQLite에 남음
- research 대상 선정이 전체 캐시 목록이 아니라 watchlist 기준으로 바뀜

## 3단계 — API 전환
범위
- 후보 리서치/감시 화면에서 쓰는 API를 SQLite 기반 상태로 교체
- 새 API 예시
  - `/api/monitor/status`
  - `/api/monitor/watchlist`
  - `/api/monitor/promotions`
- 기존 research/scanner 경로 중 역할이 겹치는 것은 정리 대상 표시

완료 기준
- 프론트가 watchlist truth source를 읽음
- "현재 후보 / 리서치 대상 / 저장소 상태"가 SQLite 기준으로 일관됨
- 구 API 중 불필요한 중복 경로는 제거 또는 호출처 삭제

## 4단계 — 장중 판단 연결
범위
- signals/rank 또는 entry selection 경로가 watchlist를 우선 사용하도록 연결
- 장중 전체 유니버스는 경량 스캔만 유지하고, 강한 신규 후보만 승격 슬롯으로 편입

완료 기준
- 실제 후보 판단이 시장별 watchlist 중심으로 수렴
- 전 종목 깊은 평가를 매번 하지 않음
- 보유 종목은 예외 추적으로 유지

## 5단계 — 흔적 삭제/용어 통일/검증
범위
- 더 이상 안 쓰는 JSON 기반 운영 상태 삭제
- 임시 어댑터/호환용 타입/옛 컴포넌트/옛 함수명 제거
- 용어 통일
  - 종목 풀
  - 1차 후보 풀
  - 핵심 감시
  - 승격 슬롯
  - 후보 리서치

완료 기준
- 구구조와 신구조가 섞여 있지 않음
- Docker build + API smoke test + 브라우저 QA 통과
- 남은 JSON은 유니버스/설정/정말 필요한 로그만 남음

삭제 원칙
- 단계 완료 후 더 이상 읽지 않는 경로는 바로 삭제
- "혹시 몰라 남겨두기" 금지
- 최종 완료 시점엔 old naming / old types / old adapters / dead JSON 접근 제거
