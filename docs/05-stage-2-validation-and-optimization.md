# 05. Stage 2 — 검증과 최적화

여기는 "이 전략을 그냥 믿고 돌릴 거냐"를 걸러내는 계층이다. Stage 1이 후보 수집이면, Stage 2는 파라미터와 신뢰도 검증이다.

## 구성 요소

- validation settings 저장
- backtest
- walk-forward validation
- optimization
- quant-ops workflow / policy

## 핵심 파일

백엔드:
- `apps/api/routes/validation.py`
- `apps/api/routes/optimization.py`
- `apps/api/routes/quant_ops.py`
- `apps/api/services/backtest_params_store.py`
- `apps/api/services/quant_guardrail_policy_store.py`
- `apps/api/services/execution_service.py`

프론트:
- `apps/web/src/pages/BacktestValidationPage.tsx`
- `apps/web/src/pages/SettingsPage.tsx`
- `apps/web/src/api/domain.ts`

## Validation 설정 저장 구조

저장 파일:
- `storage/logs/backtest_validation_settings.json`

코드 기준 상태:
- `saved`
- `approved` (quant ops runtime apply 메타에 연결)
- `applied`
- `displayed`

관련 API:
- `GET /api/validation/settings`
- `POST /api/validation/settings/save`
- `POST /api/validation/settings/reset`

### 왜 중요하냐
이 프로젝트는 브라우저 draft랑 서버 saved가 분리돼 있다. 이거 구분 안 하면 검증 결과 해석이 틀어진다.

## Backtest

관련 API:
- `GET /api/validation/backtest`
- 호환용: `GET /api/backtest/run`

프론트는 현재 `BacktestValidationPage.tsx`에서 **`/api/validation/backtest`**를 쓰도록 맞춰져 있다.

### 주요 입력
- `market_scope`
- `lookback_days`
- `strategy_kind`
- `regime_mode`
- `risk_profile`
- `portfolio_constraints`
- `strategy_params`
- validation settings

### 주요 출력
- metrics
- performance_summary
- execution_summary
- regime_breakdown
- failure_modes
- parameter_band

## Walk-forward

관련 API:
- `GET /api/validation/walk-forward`

화면상 핵심 지표:
- windows 수
- positive_window_ratio
- oos_reliability
- composite_score
- train / validation / oos 세그먼트 scorecard

운영 의미:
- 단순 총수익보다 OOS 신뢰도 확인용
- runtime 반영 전에 최소 관문 역할

## Optimization

관련 API:
- `POST /api/run-optimization`
- `GET /api/optimized-params`
- `GET /api/optimization-status`

Web 해석 기준:
- optimizer는 "최적값 발굴기"보다 **강건성 검증기**로 취급
- aggregate robust zone을 보여줌
- global parameter patch / symbol별 reliable 여부 확인 가능

### stale 관리
`execution_service.py`에는 optimized params 최대 연령 경고 로직이 있다.
오래된 결과는 stale로 보고 재실행을 권고한다.

## Quant-Ops

관련 API:
- `GET /api/quant-ops/workflow`
- `GET /api/quant-ops/policy`
- `POST /api/quant-ops/policy/save`
- `POST /api/quant-ops/policy/reset`
- `POST /api/quant-ops/revalidate`
- `POST /api/quant-ops/save-candidate`
- `POST /api/quant-ops/apply-runtime`
- `POST /api/quant-ops/reset-workflow`

저장 파일:
- `storage/logs/quant_guardrail_policy.json`
- `storage/logs/quant_ops_state.json`

### 정책 기본값 의미
`quant_guardrail_policy_store.py` 기준으로
- reject
- adopt
- limited_adopt
- limited_adopt_runtime

이렇게 나뉜다.

즉, 결과가 애매하면 아예 버리는 게 아니라 **제한 채택** 후 runtime 위험도를 낮춰 적용하는 경로가 있다.

## runtime과의 연결

가장 중요한 연결점은 여기다.

`apps/api/services/execution_service.py`:
- validation gate 적용
- optimized params 적용
- quant candidate runtime patch 적용

### validation gate 기본 축
- 최소 trade 수
- 최소 sharpe
- low/insufficient reliability 차단
- optimized reliability 요구 여부

### quant candidate patch 적용 시 달라지는 것
- market별 strategy params patch
- validation_min_trades 변경 가능
- limited_adopt면 risk_per_trade 감소
- max_positions_per_market 감소
- max_symbol_weight_pct 감소
- max_market_exposure_pct 감소

이게 runtime에 직접 반영된다.

## 운영 절차 추천

### 전략 검증 루틴
1. draft 설정 조정
2. saved로 저장
3. backtest 실행
4. walk-forward 실행
5. optimization 실행
6. 결과 보고 preset 저장 또는 quant-ops 후보화
7. quant-ops revalidate
8. 승인 시 runtime apply

## 문제 생겼을 때 보는 순서

### validation 결과가 이상함
- `GET /api/validation/settings`
- `storage/logs/backtest_validation_settings.json`
- draft/saved/displayed 상태 비교

### optimizer 결과가 반영 안 됨
- `GET /api/optimized-params`
- `GET /api/optimization-status`
- `GET /api/quant-ops/workflow`
- `storage/logs/quant_ops_state.json`

### runtime에서 너무 보수적으로 막음
- `GET /api/paper/engine/status`
- validation policy 필드 확인
- quant-ops policy 확인
- limited_adopt runtime cap 적용 여부 확인

## Stage 2에서 꼭 기억할 것

### 1) draft와 saved는 다르다
브라우저에서 만진 값이 서버 기준값이 아니다.

### 2) optimizer는 자동 정답 생성기가 아니다
robust zone 확인용으로 읽는 게 맞다.

### 3) quant-ops는 검증 결과를 runtime에 번역하는 계층이다
validation 결과를 그대로 실전 적용하지 않고,
정책과 한도를 거쳐 runtime 설정 patch로 옮긴다.
