# 단계 7. 주문 결정 도메인 독립

## 목표
- buy/sell/hold/block 판단을 한 군데서만 계산한다.
- “왜 샀는지 / 왜 안 샀는지”를 `reason_code`로 추적 가능하게 만든다.

## 표준 출력
- `buy`
- `sell`
- `hold`
- `block`

## OrderDecisionDto
- `action`
- `reason_code`
- `confidence`
- `sizing_summary`
- `trace_id`

## 현재 반영 상태
- 실행 판단에 연결된 서버 경로:
  - `apps/api/services/trade_workflow.py`
  - `apps/api/services/execution_service.py`
  - `apps/api/services/live_layers.py`
  - `apps/api/services/live_signal_engine.py`
- 관련 테스트:
  - `apps/api/tests/test_trade_workflow.py`
  - `apps/api/tests/test_execution_lifecycle.py`
  - `apps/api/tests/test_runtime_signal_path.py`

## 현재 문제
- 전용 `OrderDecisionService` 이름의 단일 서비스는 아직 없다.
- 주문 판단 책임이 `trade_workflow`, `execution_service`, `signal_engine`에 분산되어 있다.
- 일부 경로는 `reason_code`, 일부는 `reason_codes`, 일부는 `risk_reason_code`를 같이 사용한다.

## 정리 원칙
- router에서 독자 판단 금지
- broker/service는 실행만 담당하고 최종 결정은 주문 결정 도메인에서 계산
- order preview, workflow summary, blocked summary 모두 같은 판단 결과를 재사용

## 다음 단계
1. `OrderDecisionService` 또는 동등한 도메인 서비스 도입
2. 입력 contract 통일
   - signal
   - validation result
   - guardrail result
   - account snapshot
   - market snapshot
   - runtime config
3. 출력 contract를 `OrderDecisionDto`로 고정
4. 기존 서비스의 분산 판단식을 호출 위임 형태로 축소
