# Quant Ops Flow

## 목적
이 문서는 `daily-market-brief`에서 퀀트 전략을 다룰 때의 올바른 운영 흐름을 정리한다.

핵심 원칙:
- 몬테카를로 최적화는 **후보 탐색**이다.
- 최종 판단은 **재검증(validation / walk-forward / OOS)** 으로 한다.
- 저장은 **재검증 통과 후**에만 한다.
- AI 추천 전략과 퀀트 전략은 **교집합이 아니라 합집합**이다.

---

## 전략 모드

### 1) 퀀트 전략
- 백테스트
- 파라미터 탐색
- validation
- walk-forward
- OOS
- execution gate

### 2) AI 추천 전략
- today picks
- recommendations
- 뉴스/테마/브리핑
- EV / confidence / narrative

두 흐름은 병렬로 운용할 수 있지만, 한쪽이 다른 쪽의 후보 포함 여부를 강제하면 안 된다.

---

## 운영 흐름

### Step 1. Baseline 백테스트
현재 전략 기본 파라미터로 백테스트를 수행한다.

확인 항목:
- 총 수익률
- CAGR
- 최대 낙폭
- trade count
- win rate
- Sharpe
- exit reason
- 후보 편중 여부

목적:
- 현재 전략의 성격과 문제점을 파악한다.

### Step 2. 진단
Baseline 결과를 해부한다.

확인 항목:
- reliability 이유
- validation gate 차단 포인트
- tail risk
- exit reason analysis
- 종목/섹터 집중도
- 후보 편중 여부

목적:
- 성과 저하 원인을 구조적으로 파악한다.

### Step 3. 파라미터 탐색
몬테카를로 최적화 또는 bounded search로 파라미터 후보를 찾는다.

중요:
- 이 단계는 채택 단계가 아니다.
- 더 좋아 보이는 후보를 찾는 단계다.

### Step 4. 재검증
탐색한 파라미터를 실제 백테스트 / validation / walk-forward / OOS에 다시 넣는다.

확인 항목:
- train / validation / OOS 성과
- rolling windows
- positive window ratio
- reliability
- composite score
- tail risk
- exit weakness

목적:
- 과적합인지, 실제로도 쓸 만한지 판별한다.

#### Step 4-1. 종목별 재검증/승인
- `per_symbol` 후보도 종목 단위로 별도 재검증한다.
- 운영자는 종목마다 `승인(approved) / 보류(hold) / 거절(rejected)` 상태를 명시해야 한다.
- 승인 상태가 아니거나, 탐색 버전이 바뀌었거나, 탐색 결과가 stale이면 저장/반영을 차단한다.

### Step 5. 채택 / 보류 / 거절
재검증 결과를 바탕으로 의사결정한다.

- 채택: OOS / 신뢰도 / tail risk / 낙폭이 허용 범위
- 보류: 일부 구간 약점, 편중, exit weakness 존재
- 거절: 음수 OOS, 과도한 낙폭, 부족한 표본, 심한 tail risk

### Step 6. 저장
재검증을 통과한 파라미터만 저장한다.

저장 대상:
- global optimized params
- 승인된 per-symbol overlay params
- reliability metadata
- composite score / tail risk snapshot

### Step 7. Paper / Runtime 반영
퀀트 라인과 AI 추천 라인을 병렬로 참고하되, 교집합 조건으로 묶지 않는다.

중요 가드레일:
- runtime 반영 시 `saved + approved` 종목 후보만 `runtime_optimized_params.json`의 `per_symbol`에 포함한다.
- 저장되지 않았거나 승인되지 않은 종목 후보는 runtime에서 자동 제외한다.

### Step 8. 사후 모니터링
실제 운용 후 계속 확인한다.

확인 항목:
- 실제 체결 결과
- exit weakness
- 종목/섹터 편중
- expected vs realized
- regime 변화

---

## 금지할 실수
- optimizer 결과를 바로 저장
- 백테스트 수익률만 보고 채택
- OOS만 보고 validation/rolling 약점 무시
- AI 추천과 퀀트 전략을 교집합으로 설계
- 편중/청산 약점 분석 없이 파라미터만 반복 조정

---

## 현재 구현 상태

이번 리팩터링으로 아래가 반영됐어.

### 코드
- `quant_ops_state.json` 으로 latest candidate / saved candidate / runtime apply 상태를 분리 저장
- `quant_ops_state.json`에 종목별 latest/saved/approval/runtime 상태도 분리 저장
- `optimized_params.json`(탐색 결과)와 `runtime_optimized_params.json`(운영 반영본)을 분리
- 저장 API와 runtime apply API가 재검증 guardrail 통과 전에는 실행되지 않도록 차단
- paper engine current config가 저장 후보 반영 시 같이 갱신되도록 연결
- 종목별 API(`revalidate-symbol`, `set-symbol-approval`, `save-symbol-candidate`)로 운영자 승인 흐름을 명시

### UI/UX
- 퀀트 검증 화면 상단에 6단계 workflow 레일 추가
- Search / Validated Candidate / Saved / Runtime Apply 상태를 각각 카드로 분리
- Per-Symbol Candidate Approval 패널에서 종목별 재검증/승인/저장/가드레일 상태를 분리
- baseline 진단과 optimizer 후보 재검증을 별도 버튼/영역으로 분리
- 저장/반영 차단 사유를 guardrail 리스트로 표시

---

## 한 줄 요약
최적화는 후보 탐색이고, 재검증이 최종 판단이며, 저장은 재검증 통과 후에만 한다.
