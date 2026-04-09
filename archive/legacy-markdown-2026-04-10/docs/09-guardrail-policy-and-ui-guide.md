# Guardrail Policy & UI Guide

작성일: 2026-04-04

## 왜 이 문서가 필요한가

현재 가드레일 정책 설정은 다음 문제가 있다.

1. **허용값(enum) 목록이 UI에서 명확히 보이지 않음**
2. **라벨은 한글인데 실제 저장값은 영어**라서 의미 연결이 끊김
3. 백테스트 화면에 비해 **설명과 추천값이 부족**함
4. 리스크 가드/가드레일/채택 판정이 서로 어떻게 연결되는지 직관적으로 보이지 않음

이 문서는 아래를 목표로 한다.

- 가드레일 정책의 개념 정리
- 입력 가능한 값 목록(enum / 상태값) 명시
- UI에서 어떻게 친절하게 보여줘야 하는지 설계안 제시
- 리스크 가드가 언제 활성/비활성되는지 설명

---

## 1. 개념 정리

### 1.1 Guardrail Policy란
가드레일 정책은 전략 후보를 아래 단계로 분류하는 정책이다.

- `adopt` → 풀채택
- `limited_adopt` → 제한 채택
- `hold` → 보류
- `reject` → 거절

즉 백테스트/검증 결과를 바탕으로
**"이 후보를 운영에 반영할지"** 판단하는 규칙 집합이다.

---

### 1.2 Risk Guard와의 차이
가드레일 정책은 **후보 채택 정책**이고,
리스크 가드는 **실시간 진입 허용 정책**이다.

정리하면:

- **Guardrail Policy**
  - 후보를 save/apply 할 수 있는가?
  - 전략 자체를 운영 후보로 승격할 수 있는가?

- **Risk Guard**
  - 지금 이 시점에 실제 진입을 허용할 것인가?
  - 손실 한도, 노출 한도, 쿨다운 등에 걸리지 않는가?

즉:
- Guardrail은 **전략/후보 수준**
- Risk Guard는 **실거래/실행 수준**

---

## 2. 채택 판정 단계

### 2.1 `adopt`
의미:
- 운영에 바로 채택 가능한 후보
- save/apply 가능
- 가장 엄격한 기준 통과

일반 조건 예시:
- `reliability = high`
- trade count 충분
- profit factor 양호
- drawdown 양호
- expected shortfall 양호
- positive window ratio 양호

---

### 2.2 `limited_adopt`
의미:
- 제한 운영으로는 채택 가능
- probationary 수준
- 완벽하진 않지만 운영 시도 가능

일반 조건 예시:
- `reliability = medium` 허용
- 일부 지표는 adopt 기준 미달 가능
- 대신 치명적 리스크는 없어야 함
- save/apply 가능

이번 NASDAQ 케이스처럼,
**medium 신뢰도지만 수익/낙폭/ES/표본이 충분히 양호한 경우**는
limited_adopt로 보는 게 합리적이다.

---

### 2.3 `hold`
의미:
- 치명적이지는 않지만 채택하기엔 아직 애매함
- save/apply 불가
- 추가 개선 또는 조건 변경 필요

일반 조건 예시:
- hard reject는 아님
- 하지만 adopt / limited_adopt 조건도 못 넘음

---

### 2.4 `reject`
의미:
- 치명적 리스크가 있어 채택 불가
- save/apply 불가

일반 조건 예시:
- trade count 너무 적음
- expected shortfall 과도
- drawdown 과도
- profit factor 너무 낮음
- validation quality 자체가 부족

---

## 3. 신뢰도(reliability) 값 목록

현재 UI에서 가장 불친절한 부분 중 하나가 이거다.

### 허용값
- `high`
- `medium`
- `low`

### UI 표시는 이렇게 해야 함
- **높음 (`high`)**
- **중간 (`medium`)**
- **낮음 (`low`)**

### 의미
- `high`
  - 풀채택(adopt) 후보로 갈 가능성이 높음
- `medium`
  - 제한 채택(limited_adopt) 후보 가능
- `low`
  - 보류/거절 가능성이 높음

### UX 규칙
이 값은 절대 text input으로 두면 안 됨.
**dropdown / segmented control / radio** 중 하나로 고정해야 함.

---

## 4. 자주 쓰는 상태값 목록

### 4.1 decision status
허용값:
- `adopt`
- `limited_adopt`
- `hold`
- `reject`

UI 표시:
- 풀채택 (`adopt`)
- 제한 채택 (`limited_adopt`)
- 보류 (`hold`)
- 거절 (`reject`)

---

### 4.2 approval level
허용값:
- `full`
- `probationary`
- `blocked`

UI 표시:
- 정식 승인 (`full`)
- 시험 운영 (`probationary`)
- 차단 (`blocked`)

---

### 4.3 objective
실제 값은 프로젝트 구현에 따라 더 늘어날 수 있지만,
현재 주로 쓰는 값은 이런 식이다.

예시:
- `수익 우선`
- `수익+안정 균형`
- `안정 우선`

UI에서는 반드시:
- 현재 선택값
- 설명
- 추천 용도
를 같이 보여줘야 한다.

예:
- **수익 우선**: 공격적, 변동성 허용
- **수익+안정 균형**: 기본 추천
- **안정 우선**: 낙폭/테일리스크 중시

---

## 5. 리스크 가드 활성/비활성 조건

리스크 가드는 "후보가 좋아 보인다"와는 별개로,
**지금 실제 진입을 허용할지** 판단한다.

### 5.1 리스크 가드가 활성되는 경우
다음처럼 실제 포지션/실행 판단이 필요한 순간 활성된다.

- `signal_state = entry`
- 진입 수량을 계산하려고 할 때
- 실제 주문/포지션 추천 크기를 확정할 때
- 일일 손실 한도 / 노출 한도 / 쿨다운 체크를 해야 할 때

즉:
- 진짜 들어갈 가능성이 있는 후보
- 실제 사이징이 필요한 후보
에서 활성된다.

---

### 5.2 리스크 가드가 사실상 비활성/완화되는 경우
다음처럼 아직 scan-only 상태면 강한 차단보다 **통과 상태만 표시**할 수 있다.

- `signal_state = watch`
- `signal_state = exit`
- 수량이 0인 signal-only 상태
- 포지션 추천이 아직 계산되지 않은 상태
- 단순 scanner 표시용 후보

실제 코드상으로는 이런 경우 아래처럼 보일 수 있다.
- `entry_allowed = false`
- `risk_check.message = scan_only`
- `size_recommendation.quantity = 0`
- `final_allowed_size = 0`

즉 리스크 가드가 완전히 없는 게 아니라,
**실행 차단이 아니라 표시/유지 상태로만 존재**하는 셈이다.

---

### 5.3 리스크 가드가 차단되는 대표 조건
예시:
- 일일 손실 한도 초과
- 손실 연속 횟수 초과
- cooldown active
- symbol exposure cap 초과
- sector exposure cap 초과
- market exposure cap 초과
- 최소 유동성 미달
- 스프레드 과도

UI에서는 이걸 코드값만 보여주면 안 되고,
아래처럼 이유를 같이 번역해줘야 한다.

예:
- `daily_loss_limit_exceeded` → **일일 손실 한도 초과**
- `cooldown_active` → **연속 손실로 인한 일시 중단 중**
- `sector_exposure_limit` → **섹터 노출 한도 초과**

---

## 6. 권장 가드레일 정책 구조

### 6.1 Hard reject
무조건 reject해야 하는 조건 예시:
- `trade_count < min_trade_floor`
- `profit_factor < hard_min_profit_factor`
- `max_drawdown_pct < hard_max_drawdown_pct`
- `expected_shortfall_5_pct < hard_min_expected_shortfall_5_pct`

이건 사용자가 세부값을 넣을 수 있어도,
설명은 반드시 아래처럼 보여야 한다.

예:
- 최소 거래 수
- 최소 손익비
- 최대 허용 낙폭
- 최대 허용 테일리스크

---

### 6.2 Full adopt
예시 기준:
- `reliability = high`
- positive window ratio 기준 통과
- trade_count 기준 통과
- drawdown / ES / PF 기준 통과

---

### 6.3 Limited adopt
추천 기준:
- `reliability = medium` 허용
- near-miss 0~2 허용
- 다만 tail risk / drawdown / trade count 최소선 이상
- 수익률이 양수이고 PF가 1 이상이면 제한 채택 가능

### 이번 NASDAQ 케이스에서 중요했던 규칙
다음 경우를 limited_adopt로 허용하는 것이 합리적이었다.

- `reliability = medium`
- `near_miss = 0`
- `oos_return > 0`
- `profit_factor` 양호
- `max_drawdown` 양호
- `expected_shortfall_5_pct` 양호

즉 "완벽하진 않지만 실제로는 괜찮은 후보"를 살릴 수 있어야 한다.

---

## 7. UI 설계안

### 7.1 기본 원칙
가드레일 설정은 백테스트처럼 친절해야 한다.
즉 다음 4가지는 반드시 보여야 한다.

1. **한글 라벨**
2. **실제 저장값(영문 enum)**
3. **허용값 목록**
4. **추천 설명 / preset**

---

### 7.2 추천 UI 컴포넌트
#### enum 계열
예:
- reliability
- decision
- approval level

→ text input 금지
→ dropdown / radio / segmented control 사용

예시:

**신뢰도 기준**
- 높음 (`high`)
- 중간 (`medium`)
- 낮음 (`low`)

---

### 7.3 threshold 계열
예:
- 최소 거래 수
- 최소 손익비
- 최대 허용 낙폭
- 최소 positive window ratio

→ number input 사용
→ 아래에 단위/의미 표시

예시:
- 최소 거래 수 (`trade_count`)
  - 권장: 20 ~ 30
- 최대 허용 낙폭 (`max_drawdown_pct`)
  - 음수 퍼센트
  - 예: `-15` = -15%

---

### 7.4 preset 제공
가드레일도 백테스트처럼 preset이 있어야 한다.

추천 preset:
- **보수적**
- **균형형**
- **공격형**

예시:

#### 보수적
- reliability: high
- trade_count 높게
- drawdown 허용폭 좁게
- ES 허용폭 좁게

#### 균형형
- reliability: high/medium 허용
- limited_adopt 적극 활용
- 기본 추천

#### 공격형
- medium 중심 허용
- drawdown/ES 허용폭 다소 완화
- 후보 수 확보 목적

---

### 7.5 inline help 예시
예:

**리스크 허용 신뢰도**
- 현재 값: 중간 (`medium`)
- 허용값: `high`, `medium`, `low`
- 설명:
  - `high`: 풀채택 후보 위주
  - `medium`: 제한 채택 후보 허용
  - `low`: 실험 후보까지 허용

이 정도만 있어도 체감이 확 달라진다.

---

## 8. 추천 TODO

### 정책 측면
1. `medium + near_miss 0` 승격 규칙 문서화
2. 시장별(NASDAQ / KOSPI) 가드레일 임계값 분리
3. hard reject / hold / limited_adopt 기준 명문화

### UI 측면
1. enum 입력을 모두 선택형으로 전환
2. 한글 라벨 + 영어 저장값 동시 표기
3. 허용값 목록 UI에 노출
4. preset 추가
5. inline help / tooltip 추가
6. 현재 입력값이 어떤 판정에 영향을 주는지 옆에 설명

### 런타임/디버깅 측면
1. hold 이유를 더 구조적으로 보여주기
2. near-miss 항목을 카드 형태로 노출
3. save/apply 불가 시 막는 조건을 사용자 친화적으로 표시

---

## 9. 한 줄 요약

가드레일 설정은 지금보다 훨씬 백테스트처럼 친절해야 한다.

즉:
- **입력 가능한 값 목록을 보여주고**
- **한글 설명과 영어 값을 같이 표시하고**
- **추천 preset과 inline help를 제공하고**
- **리스크 가드가 언제 활성/비활성되는지 명확히 알려줘야** 한다.

이 문서의 목적은 그 UX를 구현 가능한 수준으로 정리하는 것이다.
