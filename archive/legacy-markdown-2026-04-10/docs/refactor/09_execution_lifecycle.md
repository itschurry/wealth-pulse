# 단계 9. 실행/체결 lifecycle 정리

## 목표
- 주문 intent 부터 terminal state 까지 추적 가능한 공통 실행 이벤트 모델을 둔다.
- paper / live 가 같은 lifecycle 상태명을 공유한다.

## 표준 lifecycle
- `intent`
- `submitted`
- `accepted`
- `partial_fill`
- `filled`
- `failed`
- `canceled`

## 1차 구현
- 저장소:
  - `order_events.jsonl`: 기존 주문 로그 호환 레코드
  - `execution_events.jsonl`: lifecycle 표준 이벤트 로그
- 공통 식별자:
  - `order_id`
  - `trace_id`
  - `originating_signal_key`
  - `originating_cycle_id`
- 공통 필드:
  - `event_type`
  - `timestamp`
  - `reason_code`
  - `message`
  - `code`
  - `market`
  - `side`
  - `quantity`

## reason_code 표준
- `risk_blocked`
- `insufficient_funds`
- `network_error`
- `broker_rejected`
- `canceled`

기존 `buy_failed`, `sell_failed`, `order_failed` 는 1차에서 `broker_rejected` 로 정규화한다.

## API 반영
- `/api/paper/orders`
  - 기존 `orders` 유지
  - `execution_events`
  - `execution_summary`
- `/api/paper/workflow`
  - 기존 `workflow` 유지
  - `execution_lifecycle`
- `/api/paper/engine/status`
  - `state.execution_lifecycle_summary`

## 후속 작업
- live broker 이벤트를 같은 `execution_events.jsonl` 로 적재
- broker 응답 기반 `accepted` / `partial_fill` 시점 분리
- UI 에서 workflow badge 와 lifecycle badge 를 분리
