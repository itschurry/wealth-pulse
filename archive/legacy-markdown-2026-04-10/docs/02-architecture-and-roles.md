# WealthPulse 아키텍처와 역할 분리

이 문서는 WealthPulse의 주요 레이어와 역할 분리를 설명한다.

---

## 1. Layer 구조

### Layer A — Universe / Scanner
역할:
- 종목 포함 여부 결정
- 유니버스 규칙 적용
- 스캔 시점 기록

하지 않는 일:
- 주문 판단
- 리서치 점수 계산
- 최종 실행 결정

### Layer B — Quant
역할:
- 기술 조건 기반 점수
- signal_state 계산
- quant tags / reasoning 생성

하지 않는 일:
- 외부 리서치 생성
- 최종 리스크 차단 결정

### Layer C — Hanna / OpenClaw Research
역할:
- research_score
- components
- warnings
- tags
- summary
- freshness / availability

하지 않는 일:
- 최종 종목 선정 단독 결정
- 매수/매도 지시
- 포지션 사이징
- 리스크 게이트 우회

### Layer D — Risk / Gate
역할:
- blocked 여부
- 이유 코드
- size recommendation 반영
- risk guard state 반영

### Layer E — Final Action
역할:
- `review_for_entry`
- `watch_only`
- `blocked`
- `do_not_touch`

최종 사용자/운영자가 가장 신뢰해야 할 액션 레이어다.

---

## 2. 실제 화면과 레이어의 대응

### `내 대시보드`
- 포트폴리오
- signals
- live market
- market context

즉 운영 현황을 빠르게 보는 요약 화면이다.

### `운영 콘솔 -> 전략 관리 / 전략 검증 랩 / 주문/리스크`
Runtime 쪽과 가장 가깝다.
- validation
- optimizer
- saved candidate
- runtime apply
- engine 상태

### `운영 콘솔 -> 장중 스캐너`
Scanner 레이어와 가장 가깝다.
- strategy scan
- top candidates
- Layer A/B/C/D/E 읽기

### `운영 콘솔 -> 리서치 스냅샷`
Layer C 저장소를 직접 보는 화면이다.
- latest snapshot
- history
- components
- warnings / tags / summary

### `리서치 리포트`
사람이 읽는 설명 레이어다.
- 투자 브리프
- 리스크 알림
- 관심 시나리오
- hanna brief

---

## 3. Scanner vs Runtime vs Hanna

### Scanner
- 전략별 후보를 찾는다
- 장중 탐색용이다
- 현재 뭘 보고 있어야 하는지 알려준다

### Runtime
- 실제 엔진 규칙을 실행한다
- 저장/재검증된 quant candidate 기준으로 움직인다
- 주문/포지션과 직접 연결된다

### Hanna
- scanner 후보 또는 운영 관심 종목에 대해 리서치를 붙인다
- 설명, 경고, 보조 점수를 제공한다
- execution owner가 아니다

---

## 4. 데이터 흐름

### Quant Runtime 흐름
validation settings -> backtest -> walk-forward -> optimization -> revalidate -> save -> runtime apply -> engine start

### Scanner 흐름
strategy registry -> universe snapshot -> technical scan -> scanner candidates -> layer A/B/D/E view

### Hanna 흐름
scanner candidates -> research generation -> bulk ingest -> research snapshot store -> Layer C attach

---

## 5. 왜 분리해야 하나

### 이유 1. 실행 경로 안정성
Hanna가 없어도 엔진은 quant+risk 기준으로 돌아야 한다.

### 이유 2. 설명 가능성
Hanna는 종목을 왜 봐야 하는지 설명하는 데 유용하다.

### 이유 3. 운영 명확성
- scanner는 탐색
- runtime은 실행
- Hanna는 설명

이게 흐려지면 UI도 헷갈리고 운영도 꼬인다.

---

## 6. research_unavailable의 의미

`research_unavailable` 는 보통 아래 중 하나다.
- 해당 종목 snapshot 없음
- freshness missing
- provider 상태 missing

이 뜻은:
- Hanna가 현재 종목에 대해 설명을 못 붙임
- 하지만 quant+risk 경로는 계속 감

즉 시스템 고장으로 해석하면 안 된다.

---

## 7. 운영자가 UI를 읽는 법

### `장중 스캐너`에서 봐야 할 것
- Layer B: quant_score
- Layer C: research_score / warnings / summary
- Layer D: blocked 여부
- Layer E: final_action

### `리서치 스냅샷`에서 봐야 할 것
- latest snapshot 존재 여부
- market key
- generated_at / ttl_minutes
- warnings / tags / summary
- history 누적 상태

### 해석 규칙
- Layer C가 healthy여도 final_action이 `do_not_touch`면 안 건드린다
- Layer C가 unavailable이어도 quant+risk가 충분하면 후보 자체는 계속 볼 수 있다
- 최종 결정은 Layer E 기준이다

---

## 8. truth source

### backend truth source
- `signals/rank`
- `signals/{code}`
- `scanner/status`
- `research/status`
- `research/snapshots/latest`
- `research/snapshots`

### 중요
같은 종목이라도 UI 페이지마다 데이터 소스가 다를 수 있다.
그래서 backend truth source와 UI source를 항상 맞춰야 한다.
