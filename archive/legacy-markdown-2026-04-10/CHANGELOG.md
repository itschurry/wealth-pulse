# Changelog

## 2026-03-30

### Added
- paper 엔진 운영 로그 저장 구조 추가
  - `storage/logs/engine_state.json`
  - `storage/logs/engine_cycles/*.jsonl`
  - `storage/logs/order_events.jsonl`
  - `storage/logs/signal_snapshots.jsonl`
  - `storage/logs/account_snapshots.jsonl`
- paper 엔진 API 확장
  - `POST /api/paper/engine/pause`
  - `POST /api/paper/engine/resume`
  - `GET /api/paper/engine/cycles`
  - `GET /api/paper/orders`
  - `GET /api/paper/account/history`
  - `GET /api/signals/snapshots`
  - `GET /api/system/notifications/status`
- 텔레그램 전용 운영 알림 서비스 추가
  - 엔진 시작/중지/일시정지/재개/오류
  - 주문 실패
  - 일일 손실 한도 초과

### Changed
- `execution_service`를 운영형 상태 모델로 확장
  - `engine_state`(`running/paused/stopped/error`) 중심으로 상태 관리
  - 재시작 시 안전하게 `stopped` 복구
  - `current_config`, `validation_policy`, `optimized_params` 상태 노출
- 자동매매 cycle 실행에 validation gate 정책 반영
  - 최소 거래수/샤프/신뢰도 기준으로 진입 차단
  - 차단 사유를 `reason_code`로 누적 집계
- quote payload 및 주문 이벤트에 `source/fetched_at/is_stale` 메타데이터 반영
- 콘솔 UI 운영성 강화
  - Overview: 엔진 상태/다음 실행/오늘 주문·손익/정책·최적화 상태 표시
  - Signals: 점수/신뢰/EV/진입/수량/검증/유동성·슬리피지/상세 사유 표시
  - Paper: 시작/일시정지/재개/중지/강제 새로고침, cycle·주문·계좌·snapshot 로그 연계
  - Validation: 실행 중인 validation gate 정책 표시
  - polling을 fast/mid/slow로 분리

### Fixed
- 엔진 루프 예외 발생 시 오류 상태와 원인/시각을 영속 상태로 남기도록 수정
- 알림 실패가 엔진 핵심 흐름을 중단시키지 않도록 격리

### Docs
- `README.md`에 paper 운영 방법, 텔레그램 설정, 운영 로그 파일 위치, 신규 API 반영
- `apps/api/.env.example`에 `TELEGRAM_ENABLED` 추가
