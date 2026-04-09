# WealthPulse 운영 매뉴얼

이 문서는 현재 앱에 실제로 존재하는 화면과 기능 기준으로,
처음부터 끝까지 어떤 순서로 써야 하는지 설명한다.
핵심은 **탐색(scanner)**, **실행(runtime)**, **설명(Hanna/Layer C)** 를 섞지 않는 것이다.

---

## 1. 시스템을 이루는 세 줄기

### A. Quant Runtime
실제 실행 엔진이다.

하는 일:
- 백테스트
- walk-forward
- 최적화
- candidate 재검증
- save candidate
- runtime apply
- engine start

즉 **실제 실행 규칙을 결정**한다.

### B. Scanner
장중 탐색 레이어다.

하는 일:
- 전략별 유니버스 스캔
- 기술 조건 기반 후보 발굴
- Layer A/B/D/E 포함 후보 표시

즉 **무엇을 볼지 찾는 역할**이다.

### C. Hanna / OpenClaw / Layer C
리서치 보조 레이어다.

하는 일:
- scanner 후보 종목 기준 research snapshot 생성
- warnings / tags / summary / research_score 제공
- Layer C enrich

즉 **설명과 보조 점수**를 붙인다.
최종 매수/매도 결정권은 없다.

---

## 2. 현재 UI 구조

### 01 `내 대시보드`
빠르게 전체 상태를 보는 화면이다.

보는 것:
- 포트폴리오 상태
- signals 요약
- live market
- market context

### 02 `운영 콘솔`
실제 운영 화면이다.

현재 탭:
- 전략 관리
- 장중 스캐너
- 주문/리스크
- 유니버스
- 성과
- 전략 검증 랩
- 관심 종목
- 리서치 스냅샷

### 03 `리서치 리포트`
설명/브리프 화면이다.

현재 탭:
- 투자 브리프
- 리스크 알림
- 관심 시나리오

---

## 3. 운영 순서

### Step 0. 상태 확인
먼저 아래가 살아 있어야 한다.
- API health
- market data
- broker / paper engine
- scanner status
- research status

### Step 1. 기본 정책/프리셋 설정
여기서 정하는 것:
- validation settings
- quant policy
- runtime candidate source mode
- 시장(KOSPI / NASDAQ)
- 리스크 한도

이 단계는 **판을 세팅하는 단계**다.

### Step 2. 백테스트
저장할 가치가 있는 baseline인지 확인한다.

### Step 3. Walk-forward
백테스트보다 중요한 재검증 단계다.
과최적화 여부를 가늠한다.

### Step 4. 최적화
optimizer를 돌려 candidate를 만든다.

### Step 5. 재검증
optimizer 결과를 바로 쓰지 말고 revalidate 한다.

### Step 6. 저장
재검증 통과 candidate를 save 한다.

### Step 7. Runtime Apply
저장한 candidate를 실행 엔진 runtime 설정에 반영한다.

### Step 8. Engine Start
paper engine을 시작한다.
현재 운영 기준으로는 이 단계를 우선 기준으로 본다.

### Step 9. 장중 스캐너 후보 확인
`운영 콘솔 -> 장중 스캐너` 에서 현재 전략별 후보를 확인한다.
이 단계는 runtime과 별도로 존재할 수 있다.

### Step 10. Hanna research ingest
현재 장중 스캐너 후보 종목 기준으로 research snapshot을 생성하고 bulk ingest 한다.
필요하면 `운영 콘솔 -> 리서치 스냅샷` 에서 특정 종목 snapshot latest/history도 직접 확인한다.

### Step 11. UI 확인
아래를 확인한다.
- 장중 스캐너 후보 존재 여부
- Layer C 상태
- research_score / warnings / summary
- final_action
- blocked / do_not_touch 이유
- `리서치 리포트 -> 투자 브리프` 쪽 설명 일치 여부

---

## 4. 중요한 원칙

### 원칙 1. scanner 후보는 runtime apply 전에도 생긴다
scanner는 탐색 레이어다.
즉 최적화 저장/runtime 반영이 끝나야만 후보가 생기는 구조가 아니다.

### 원칙 2. Hanna는 scanner 후보에 붙는다
Hanna snapshot은 현재 scanner 후보 종목 기준으로 생성하는 것이 맞다.

### 원칙 3. runtime apply와 Hanna ingest는 다른 문제다
- runtime apply = 실행 규칙 반영
- Hanna ingest = 후보 설명/보조 점수 반영

둘은 관련은 있지만 같은 단계가 아니다.

### 원칙 4. 최종 액션은 Quant/Risk가 잡는다
Layer C가 붙어 있어도 최종 액션은 Layer D/E가 정한다.
예: `do_not_touch`, `blocked`, `review_for_entry`

---

## 4. 화면별 추천 사용 순서

### 가장 기본 루프
1. `내 대시보드` 에서 전체 상태 확인
2. `운영 콘솔 -> 전략 검증 랩` 에서 baseline / 백테스트 / walk-forward / optimizer 상태 확인
3. `운영 콘솔 -> 전략 관리` 에서 승인 전략 확인
4. `운영 콘솔 -> 장중 스캐너` 에서 장중 후보 확인
5. `운영 콘솔 -> 리서치 스냅샷` 에서 특정 종목 snapshot 확인
6. `리서치 리포트 -> 투자 브리프` 에서 사람이 읽는 브리프 확인

---

## 5. 추천 운영 루프

### 장 시작 전
1. validation / quant policy 확인
2. optimizer candidate 상태 확인
3. runtime apply 상태 확인
4. engine 상태 확인

### 장중
1. 장중 스캐너 후보 확인
2. 장중 스캐너 후보 종목 기준 Hanna snapshot ingest
3. 장중 스캐너 화면에서 Layer C / final_action 확인
4. blocked / do_not_touch 이유 확인

### 장 마감 후
1. 결과 점검
2. 후보 저장 여부 재검토
3. 다음 세션용 정책/프리셋 정리

---

## 6. 새로 추가된 화면의 역할

### 관심 종목
관심 종목을 추가/관리하는 화면이다.
실행 엔진보다 사람이 보는 관심 종목 관리에 가깝다.

### 리서치 스냅샷
특정 심볼의 research snapshot latest/history를 직접 확인하는 화면이다.
Layer C 디버깅에 가장 유용하다.

### 리서치 리포트
시장 설명, 투자 브리프, 리스크 알림, 관심 시나리오를 사람이 읽는 화면이다.
실행 레이어와 동일하지 않다.

---

## 7. 가장 흔한 오해

### 오해 1. Hanna가 안 붙으면 엔진이 안 돌아야 한다
아니다.
research가 없어도 quant+risk 기준으로 계속 진행하는 게 맞다.

### 오해 2. scanner 후보는 runtime 저장 후보가 있어야만 생긴다
아니다.
scanner 후보는 탐색 레이어에서 먼저 생긴다.

### 오해 3. UI에서 research_unavailable이면 프론트 버그다
항상 그런 건 아니다.
실제로 research snapshot이 없는 경우가 많다.

---

## 8. 운영자가 기억할 최소 문장

- scanner는 **무엇을 볼지 찾는다**
- runtime은 **무엇을 실행할지 결정한다**
- Hanna는 **왜 봐야 하는지 설명한다**
- final_action은 **Layer D/E가 정한다**
