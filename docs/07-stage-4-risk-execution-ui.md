# 07. Stage 4 — 리스크, 실행, UI

이 단계가 실제 운영의 본체다. 후보가 아무리 좋아 보여도 여기서 막히면 주문 안 나간다. 그게 정상이다.

## 핵심 파일

- `apps/api/services/execution_service.py`
- `apps/api/routes/trading.py`
- `apps/api/routes/engine.py`
- `apps/web/src/pages/PaperPortfolioPage.tsx`
- `apps/web/src/pages/ReportsPage.tsx`

## 실행 엔진 구조

`execution_service.py` 기준으로 엔진은 두 종류다.

### paper
- 내부 가상계좌 사용
- 기본 모드
- 상태 파일: `paper_account_state.json`

### live
- KISClient 기반 실거래 경로
- 코드 경로는 존재
- mode 인자로만 제어하게 돼 있음

## 자동 실행 루프

핵심 함수 흐름:
- `_start_auto_trader`
- `_auto_trader_loop`
- `_run_auto_trader_cycle`
- `_stop_auto_trader`
- `_pause_auto_trader`
- `_resume_auto_trader`

### loop가 하는 일
1. 엔진 상태 로드
2. 시장별 포지션/주문 상황 확인
3. 청산 조건 검사
4. signal book 기반 진입 후보 선택
5. risk/validation/sizing 반영
6. 주문 실행
7. order / signal / execution / cycle / account snapshot 기록

## validation gate

runtime 쪽에서 실제로 보는 필드:
- `validation_gate_enabled`
- `validation_min_trades`
- `validation_min_sharpe`
- `validation_block_on_low_reliability`
- `validation_require_optimized_reliability`

### blocked 되는 대표 이유
- trade 수 부족
- sharpe 부족
- reliability low/insufficient
- optimized validation 실패

## risk/action 흐름

실행 경로는 대충 이런 식이다.

```text
signal book
  -> risk check
  -> entry_allowed 결정
  -> size recommendation
  -> final action / execution decision
  -> order
```

로그에 남는 것:
- order events
- execution events
- signal snapshots
- engine cycles
- account snapshots

## 주요 저장 파일/경로

루트:
- `storage/logs`

대표 상태 파일:
- `paper_account_state.json`
- `quant_ops_state.json`
- `backtest_validation_settings.json`
- `quant_guardrail_policy.json`

추가로 runtime history는 order/signal/account/cycle 계열 파일들로 저장된다. 실제 파일명은 store 구현 기준으로 `storage/logs` 아래에 생긴다.

## Paper API

### 조회
- `GET /api/paper/account`
- `GET /api/paper/engine/status`
- `GET /api/paper/engine/cycles`
- `GET /api/paper/orders`
- `GET /api/paper/workflow`
- `GET /api/paper/account/history`

### 실행/제어
- `POST /api/paper/order`
- `POST /api/paper/reset`
- `POST /api/paper/history/clear`
- `POST /api/paper/auto-invest`
- `POST /api/paper/engine/start`
- `POST /api/paper/engine/pause`
- `POST /api/paper/engine/resume`
- `POST /api/paper/engine/stop`

## 주문/리스크 UI 해석

`PaperPortfolioPage.tsx`는 그냥 포트폴리오 목록이 아니다.

핵심 블록:
- Risk First hero
- 위험 포지션 요약
- 엔진 상태 패널
- 최근 체결 내역
- 최근 엔진 이벤트 로그
- 실행 워크플로우
- Risk / Action 로그

### 운영자 관점에서 먼저 보는 순서
1. 엔진이 running인가
2. 신규 진입이 허용인가 차단인가
3. 오늘 실패 주문 수가 급증했나
4. blocked reason 상위 항목이 뭔가
5. review_for_entry가 order 단계로 갔나

## 워크플로우 단계

화면 기준 분류:
- `discover`
- `signal`
- `decision`
- `order`

세부 상태 예시:
- watch
- blocked
- signal_generated
- execution_decided
- order_ready
- order_sent
- filled
- rejected

### 해석법
- discover에서 막힘 → 스캐닝/리스크 초기단 차단
- signal까지만 감 → 신호는 났지만 실행 판단 전
- decision에서 멈춤 → risk/sizing/validation 쪽
- order에서 실패 → 브로커/현금/주문 한도/시장 조건 문제

## 차단/실패 원인 예시

코드상 자주 나오는 것들:
- `validation_trades_low`
- `validation_sharpe_low`
- `validation_reliability_low`
- `optimized_validation_failed`
- `size_zero`
- `daily_buy_limit_reached`
- `symbol_daily_limit_reached`
- `market_closed`
- 현금 부족 계열 실패

## 리스크 운영 포인트

### 포지션 위험 판정
화면에서 주로 보는 기준:
- 손절가 근접
- 손실 심화
- 장기 보유 + 약세

### 주문 실패 요약
- 오늘 실패 주문 수
- insufficient cash 반복 종목
- top reason
- latest failure reason
- cooldown 필요 여부

이게 다 `execution_service.py` 안에서 요약된다.

## scanner / runtime / Hanna가 여기서 만나는 방식

### scanner
후보를 올린다.

### Hanna
후보에 설명과 research quality를 붙인다.

### runtime
마지막에
- 허용/차단
- 수량
- 주문
- 히스토리 저장
을 한다.

실행 계층 우선순위는 항상 runtime 쪽이다.

## 장애 대응 체크리스트

### 주문이 안 나감
- `/api/paper/workflow`
- `/api/paper/orders`
- Risk / Action 로그
- blocked reason summary

### 계속 실패 주문 발생
- `/api/paper/orders`
- insufficient cash 반복 여부
- 일일 주문 한도
- market open 여부

### 엔진 상태가 paused/stopped로 남음
- 수동 start/resume 필요
- 재시작 후 자동 재개 기대하면 안 됨

### Web엔선 괜찮아 보이는데 실제로는 안 굴러감
- `/api/paper/engine/status`
- `storage/logs/paper_account_state.json`
- 최근 cycle/error 확인

## 운영 결론

리스크/실행 단계는 친절하게 굴지 않는다. 조건 안 맞으면 막는다.
그걸 억지로 푸는 게 아니라, 왜 막았는지 로그와 워크플로우로 읽는 게 이 시스템의 맞는 사용법이다.
