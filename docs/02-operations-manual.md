# 02. 운영 매뉴얼

이 프로젝트는 그냥 대시보드가 아니다. **scanner → runtime → UI** 순서로 굴러가는 운영 시스템이다. 그래서 점검도 그 순서로 해야 덜 헤맨다.

## 0. 운영 원칙

### 원칙 1) Hanna는 주문 엔진이 아니다
- 점수 붙임
- 요약문 생성
- 경고 코드 제공
- 브리프 제공

여기까지만 한다. 주문 허용/차단은 runtime과 risk gate가 맡는다.

### 원칙 2) 파일 로그가 현재 truth source다
지금 코드는 DB보다 아래 파일들이 먼저다.

- `storage/logs/paper_account_state.json`
- `storage/logs/backtest_validation_settings.json`
- `storage/logs/quant_guardrail_policy.json`
- `storage/logs/quant_ops_state.json`
- 기타 order/signal/account/cycle 스냅샷 계열 로그

### 원칙 3) 화면보다 API가 먼저다
화면이 비정상이면 Web부터 의심하지 말고 API payload부터 확인한다.

## 1. 아침/세션 시작 체크

```bash
curl http://localhost:8001/health
curl http://localhost:8001/api/system/mode
curl http://localhost:8001/api/engine/status
curl http://localhost:8001/api/paper/engine/status
curl http://localhost:8001/api/scanner/status
curl http://localhost:8001/api/research/status
```

### 확인 포인트
- `/health` 응답 정상 여부
- engine state: running / paused / stopped / error
- scanner 캐시가 비어 있는지
- research provider 상태가 healthy인지 degraded인지
- 오늘 실패 주문이 있는지

## 2. 장중 스캐너 운영

Web 기준 화면: `ScannerPage.tsx`

이 화면에서 보는 핵심:
- 전략별 스캔 개수
- top candidate
- Layer B quant score
- Layer C Hanna 상태
- Layer D risk reason
- Layer E final action

### 정상 해석법
- `review_for_entry` → 검토 가능한 후보
- `watch_only` → 관심 대상이지만 실행 아님
- `blocked` → risk gate 또는 조건 미충족
- `do_not_touch` → 더 보지 않는 쪽

### 오해하면 안 되는 것
Hanna가 healthy라고 해서 주문 가능이 아니다.
반대로 Hanna가 degraded여도 runtime은 계속 움직일 수 있다.

## 3. 전략 검증 운영

Web 기준 화면: `BacktestValidationPage.tsx`

주요 기능:
- 전략 종류 선택
- market/regime/risk profile 선택
- 전략 파라미터 조정
- validation settings 저장
- backtest 실행
- walk-forward 실행
- optimization 실행
- 전략 preset 저장

### 운영 루틴
1. draft 설정 조정
2. `설정 저장`
3. `백테스트 실행`
4. `Walk-forward 검증`
5. 필요 시 `강건성 검증`
6. 결과가 괜찮으면 프리셋 저장
7. quant-ops나 runtime 적용 후보로 넘김

### 디버깅 포인트
- saved/displayed/draft가 다르면 설정 혼선 가능
- optimizer 결과가 stale이면 runtime 반영 전에 재실행 검토
- walk-forward OOS 신뢰도 낮으면 runtime 반영 막는 게 맞다

## 4. paper runtime 운영

실제 핵심은 `apps/api/services/execution_service.py`에 있다.

여기서 하는 일:
- paper/live 엔진 선택
- 자동 실행 루프
- 주문 이벤트 기록
- engine cycle 기록
- signal snapshot 기록
- account snapshot 기록
- validation gate 적용
- optimized params 반영

### 시작
API:
- `POST /api/paper/engine/start`

Web:
- 주문/리스크 화면의 `엔진 시작`

### 일시정지
- `POST /api/paper/engine/pause`

### 재개
- `POST /api/paper/engine/resume`

### 중지
- `POST /api/paper/engine/stop`

### 상태 확인
- `GET /api/paper/engine/status`
- `GET /api/paper/engine/cycles`
- `GET /api/paper/orders`
- `GET /api/paper/workflow`
- `GET /api/paper/account/history`

## 5. 주문/리스크 화면 해석

Web 기준 화면: `PaperPortfolioPage.tsx`

이 화면에서 먼저 봐야 할 칸:

### 1) 엔진 상태
- running인지
- paused인지
- last_error가 있는지
- next_run_at이 잡혀 있는지

### 2) 리스크 가드
- 신규 진입 허용 여부
- today 실패 주문 수
- blocked reason 상위 항목

### 3) Risk / Action 로그
- Layer D risk decision
- Layer E final action
- reason code
- 최근 signal snapshot

### 4) 워크플로우
- discover
- signal
- decision
- order

여기서 어디서 끊겼는지 보면 된다.

## 6. 실패 시 진단 순서

### 케이스 A. 후보는 보이는데 주문이 없다
1. `GET /api/scanner/status`
2. `GET /api/paper/workflow`
3. `GET /api/paper/orders`
4. 주문/리스크 화면의 Risk / Action 로그 확인

보통 원인:
- Layer D 차단
- validation gate 차단
- size recommendation 0
- daily/symbol order limit 도달
- 현금 부족

### 케이스 B. 엔진이 멈춘다
1. `GET /api/paper/engine/status`
2. `engine_state == error` 확인
3. `last_error` 확인
4. `storage/logs` 상태 파일 확인

코드상 서버 재시작 후 running/paused 상태를 자동 재개하지 않고 `stopped`로 복구한다. 이건 안전장치다. 버그로 오해하면 안 된다.

### 케이스 C. Hanna 상태가 이상하다
1. `GET /api/research/status`
2. `GET /api/research/snapshots/latest`
3. `GET /api/hanna/brief`
4. Web Scanner / Reports 화면 비교

중요:
- Hanna degraded = research 품질 저하 가능성
- Hanna unavailable = Layer C 정보 부족
- 하지만 scanner/runtime의 기본 흐름이 바로 죽는 구조는 아님

### 케이스 D. validation 결과가 이상하다
1. `GET /api/validation/settings`
2. `GET /api/validation/backtest?...`
3. `GET /api/validation/walk-forward?...`
4. `GET /api/optimized-params`
5. `GET /api/optimization-status`

## 7. 운영 중 자주 보는 파일

- `storage/logs/paper_account_state.json`
- `storage/logs/backtest_validation_settings.json`
- `storage/logs/quant_guardrail_policy.json`
- `storage/logs/quant_ops_state.json`

그리고 코드 쪽에선:
- `apps/api/services/execution_service.py`
- `apps/api/services/backtest_params_store.py`
- `apps/api/services/quant_guardrail_policy_store.py`

## 8. 리셋 절차

### 로그만 정리
- `POST /api/paper/history/clear` with `{"clear_all": true}`

### 계좌 리셋
- `POST /api/paper/reset`

### 로그 + 계좌 상태 완전 정리
- `POST /api/paper/history/clear` with `reset_account` 포함

Web에서도 같은 기능 버튼이 있다.

## 9. 데일리 운영 체크리스트

### 시작 전
- API health 정상
- scanner status 존재
- research status 확인
- validation 설정 saved/displayed 확인

### 장중
- 엔진 running 확인
- 실패 주문 급증 여부 확인
- risk blocked 사유 상위 항목 확인
- readiness 후보가 order 단계로 가는지 확인

### 종료 전
- 오늘 cycle 요약 확인
- 실패 주문과 blocked 사유 저장/파악
- 필요 시 validation/optimizer 재실행 계획 정리

## 10. 제일 흔한 착각

### 착각 1
"Hanna가 좋아 보이니까 주문돼야 하는데요?"

아니. Hanna는 설명 계층이다.

### 착각 2
"UI에 안 보이니 데이터가 없는 게 아니라 프론트 버그겠지"

그럴 수도 있지만, 지금 구조에선 먼저 API payload와 `storage/logs`를 봐야 맞다.

### 착각 3
"DB가 있겠지"

지금 compose 기준으론 없다. 파일 저장 기반이다.
