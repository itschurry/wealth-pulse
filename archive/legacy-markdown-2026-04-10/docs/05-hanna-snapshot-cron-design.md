# 스캐너 후보 → Hanna Snapshot 크론 설계

작성일: 2026-04-03

## 한 줄 요약

이 크론의 목적은 `운영 콘솔 -> 장중 스캐너` 에 떠 있는 후보 종목을 주기적으로 읽어,
해당 종목의 Hanna/OpenClaw research snapshot을 생성·저장하고,
다음 스캐너 조회 시 Layer C가 자연스럽게 붙도록 만드는 것이다.

이 작업은 **실행 엔진(runtime)** 이 아니라 **후보 enrich 배치**로 취급해야 한다.

---

## 1. 목표

현재 스캐너 후보가 존재해도, 해당 종목 research snapshot이 없으면 아래처럼 보일 수 있다.

- `research_status = missing`
- `research_unavailable = true`
- `layer_c_status = missing`

즉 크론의 목표는 아래다.

1. 장중 스캐너 후보에 대한 Hanna coverage 확보
2. `research_unavailable` 중 실제 snapshot 누락 케이스 감소
3. 리서치 스냅샷 페이지에서 latest/history 확인 가능하게 만들기
4. 스캐너 UI에서 Layer C attach 확률 높이기

---

## 2. 역할 정의

이 크론은 **매매 판단**을 하지 않는다.

하는 일:
1. 현재 scanner 후보 읽기
2. 종목 리스트 dedupe
3. 최신 snapshot 있는 종목 skip
4. 부족한 종목만 Hanna research 생성
5. snapshot ingest/store
6. 실행 결과 요약 로그 기록

즉 성격은 **candidate enrichment worker** 다.

---

## 3. 입력 / 출력

## 입력
- scanner 후보 목록
  - symbol
  - market
  - strategy / score 등 보조 정보
- 기존 research snapshot latest
- provider 상태

## 출력
- 종목별 latest snapshot 저장
- 저장/skip/fail 집계
- 마지막 실행 로그

---

## 4. 권장 실행 흐름

```text
cron trigger
→ scanner/status 조회
→ 현재 후보 추출
→ (market, symbol) dedupe
→ 최신 snapshot 존재 여부 확인
→ 없는 종목/오래된 종목만 Hanna 요청
→ snapshot ingest/store
→ 요약 로그 남김
```

---

## 5. 필수 규칙

### A. 후보가 없으면 즉시 종료
후보가 없으면 아무것도 하지 않는다.

예시 결과:
- scanned: 0
- generated: 0
- skipped: 0
- reason: no scanner candidates

### B. `(market, symbol)` 단위 dedupe
같은 종목이 여러 전략에 걸려도 snapshot 생성은 한 번이면 충분하다.

### C. freshness 기준 적용
이미 최신 snapshot이 있으면 다시 생성하지 않는다.

권장 기준:
- 장중 크론: 최근 45분 내 snapshot 있으면 skip
- 장마감 크론: 당일 snapshot 있으면 skip, 없으면 1회 생성

### D. canonical market key 유지
lookup/storage key는 반드시 canonical market key 기준으로 맞춘다.

예:
- `KR` → `KOSPI`
- `US` 계열도 내부 표준 key로 normalize

### E. provider 장애 시 graceful degrade
Hanna/OpenClaw가 잠시 불가해도 scanner/runtime 전체를 멈추지 않는다.
실패 집계만 남기고 종료하는 쪽이 맞다.

### F. 휴장/비거래일 skip
시간만 맞는다고 무조건 실행하지 말고, 가능한 범위에서 시장 거래 가능 여부를 먼저 확인한다.

권장 순서:
1. 시장 상태/거래일 확인
2. 휴장·주말·비거래일이면 즉시 skip
3. 거래일이어도 scanner 후보가 없으면 skip
4. 후보가 있어도 freshness 충족이면 skip

즉 최종 실행 조건은 아래처럼 잡는 것이 좋다.
- 거래일
- 현재 크론 목적에 맞는 시간대
- scanner 후보 존재
- snapshot 보강 필요

---

## 6. 크론 구성

## 1) 장중 incremental cron
목적:
- 현재 떠 있는 후보에 대해 snapshot coverage 유지

권장 주기:
- 평일 장중 10분 간격

권장 시간대:
- 09:10 ~ 15:20 (Asia/Seoul)

권장 freshness:
- 최근 45분 내 snapshot 있으면 skip

추가 skip 조건:
- 휴장/비거래일이면 실행하지 않음
- 시장 상태 확인이 가능하면 그 값을 우선 사용

## 2) 장마감 finalization cron
목적:
- 당일 마지막 후보 상태 정리
- 장중 누락된 snapshot 보강

권장 시간:
- 평일 15:40 1회 (Asia/Seoul)

권장 freshness:
- 당일 snapshot 있으면 skip

추가 skip 조건:
- 휴장/비거래일이면 실행하지 않음
- 당일 거래 자체가 없었다면 조용히 종료

---

## 7. 과호출 방지 정책

### 제한 1. 한 번 실행당 최대 처리 종목 수 제한
예:
- 최대 20~30종목

후보가 많으면 아래 우선순위를 사용한다.
1. snapshot 없는 종목 우선
2. 상위 점수 종목 우선

### 제한 2. 직전 성공 종목 재요청 억제
같은 종목을 너무 자주 다시 생성하지 않는다.

### 제한 3. 가능하면 배치 ingest 선호
한 종목씩 과도하게 쪼개 호출하지 않고, 가능한 범위에서 묶어서 저장한다.

---

## 8. 실패 분류

실패는 아래 정도로 나누는 편이 좋다.

- `provider_unavailable`
- `ingest_failed`
- `invalid_symbol_or_market`
- `scanner_source_unavailable`

이렇게 나누면 나중에 운영/디버깅이 쉬워진다.

---

## 9. UI/운영에서 보여주면 좋은 최소 상태

- 마지막 snapshot cron 실행 시각
- 이번 실행 후보 수
- 생성 수
- skip 수
- fail 수

이 정도면 운영자가 충분히 판단할 수 있다.

---

## 10. runtime과 분리해야 하는 이유

이 크론은 runtime apply와 묶으면 안 된다.

이유:
- runtime = 실행 규칙 반영
- Hanna snapshot cron = 설명/보조 점수 보강

둘을 묶으면 research 상태 때문에 실행 경로가 꼬일 수 있다.
따라서 반드시 **분리된 보조 배치**로 유지하는 것이 맞다.

---

## 11. 권장 초기안

최소 버전:
- 장중 10분 간격 1개
- 장마감 15:40 1개
- `(market, symbol)` dedupe
- freshness skip
- 실패 집계 로그

이 구성이 가장 단순하고, 실제 운영에도 충분하다.

---

## 12. 휴장 판단 정책

권장 판단 순서:
1. 오늘이 해당 시장 거래일인지 확인
2. 거래일이 아니면 바로 종료
3. 거래일이면 scanner 후보 존재 여부 확인
4. 후보가 있으면 freshness 부족 종목만 처리

시장 상태 API가 있으면 그것을 우선 사용하고,
없다면 주말/공휴일/비거래일 규칙과 scanner 후보 유무를 함께 사용한다.

즉 이 크론은 "시간이 됐으니 그냥 실행" 이 아니라,
"오늘 이 시장에서 snapshot 보강이 실제 필요한가"를 먼저 판단해야 한다.

---

## 13. 기대 효과

1. 장중 스캐너에서 Hanna coverage 증가
2. `research_unavailable` 중 실제 누락 케이스 감소
3. `리서치 스냅샷` 페이지 활용도 증가
4. `관심 종목` 페이지에서도 종목별 research 재사용 가능성 증가

---

## 14. OpenClaw cron 구현 방향

권장 구현 방식:
- OpenClaw cron job은 **isolated agentTurn** 으로 실행
- 기본 delivery는 `none` 으로 둬서 장중 반복 알림을 피함
- 작업 프롬프트는 아래 순서로 작성
  1. scanner 후보 조회
  2. 후보 dedupe
  3. snapshot latest 조회
  4. freshness 기준으로 skip/generate 결정
  5. 필요한 종목만 Hanna ingest 수행
  6. 결과 로그/요약 남기기

추가로 backend에 아래 진단/타깃 API를 두면 운영이 쉬워진다.
- `/api/research/scanner-targets` : 현재 scanner 후보별 snapshot 존재/fresh/stale 상태 확인
- `/api/research/scanner-enrich-targets` : 실제 보강이 필요한 `(market, symbol)` 대상만 dedupe해서 반환

즉 크론은 사용자에게 시끄럽게 떠들기보다,
조용히 snapshot coverage를 보강하는 background worker처럼 동작하는 것이 맞다.
