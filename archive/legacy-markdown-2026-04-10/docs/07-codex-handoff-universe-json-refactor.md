# Codex Handoff — 하드코딩 유니버스 제거 및 JSON Snapshot 기반 구조로 전환

작성일: 2026-04-03

## 한 줄 요약

현재 WealthPulse의 유니버스 구성은 `company_catalog.py`, `backtest_universe.py`, `HOLDINGS` 등
프로젝트 내부의 정적/하드코딩 소스를 조합해 만들고 있다.

이 구조를 제거하고,
외부 데이터 소스(FinanceDataReader)를 이용해 매일 생성되는 JSON snapshot을 기준으로
유니버스를 읽는 구조로 바꿔야 한다.

목표는 아래다.

- 기존 하드코딩/정적 목록 소스 제거
- 유니버스는 코드가 아니라 **daily snapshot data** 로 관리
- 앱/백엔드 서비스는 snapshot JSON만 읽음
- 국장: `KOSPI`
- 미장: `S&P500`

---

## 현재 문제

### 1. 유니버스 소스가 하드코딩/정적 소스에 묶여 있음
현재 유니버스는 주로 아래 소스에서 만들어진다.

- `apps/api/config/company_catalog.py` 의 `_BASE_ENTRIES`
- `config/portfolio.py` 의 `HOLDINGS`
- `config/backtest_universe.py` 의 `get_kospi100_universe()`, `get_sp100_nasdaq_universe()`

즉 이름은 동적 규칙처럼 보여도,
실제로는 프로젝트 내부 정적 목록을 잘라 쓰는 구조다.

### 2. 유니버스 규칙 이름과 실제 동작이 어긋남
예:
- `top_liquidity_200`
- `us_mega_cap`

하지만 실제 구현은:
- `top_liquidity_200` = live catalog 중 `market == KOSPI` 만 선택 후 최대 200개
- `us_mega_cap` = live catalog 중 `market == NASDAQ` 만 선택 후 최대 100개

즉 실제로는:
- 거래대금 상위 200 계산 아님
- 미국 메가캡 선별 아님
- 정적 목록 기반 잘라쓰기임

이건 설계 신뢰도를 떨어뜨린다.

### 3. 유니버스는 코드가 아니라 데이터로 다뤄야 함
현재 구조는 코드/설정 안에 목록이 박혀 있어,
업데이트/검증/추적/복구가 불편하다.

유니버스는 아래처럼 다뤄야 한다.
- 외부 데이터 소스로부터 생성
- JSON snapshot 저장
- 앱은 그 snapshot을 읽기만 함

---

## 최종 목표

### 국장 유니버스
- `KOSPI`
- FinanceDataReader 기반 daily snapshot

### 미장 유니버스
- `S&P500`
- FinanceDataReader 기반 daily snapshot

### 앱 구조
- cron 또는 수동 배치가 snapshot 생성
- backend 서비스는 snapshot JSON을 읽어 유니버스 생성
- 기존 하드코딩 목록 및 관련 경로 제거

---

## 외부 소스 선택

### 사용할 패키지
- `FinanceDataReader`

### 확인된 사용 예시
- `fdr.StockListing('KOSPI')`
- `fdr.StockListing('S&P500')`

즉 `KOSPI`, `S&P500` 구성 종목 목록을 가져와 snapshot으로 저장하는 방향이 가능하다.

---

## 원하는 최종 데이터 구조

### 저장 경로 예시

```text
storage/logs/universe_snapshots/kospi/latest.json
storage/logs/universe_snapshots/kospi/YYYY-MM-DD.json
storage/logs/universe_snapshots/sp500/latest.json
storage/logs/universe_snapshots/sp500/YYYY-MM-DD.json
```

### JSON 스키마

```json
{
  "schema_version": 1,
  "as_of_date": "2026-04-03",
  "generated_at": "2026-04-03T18:10:00+09:00",
  "source": "FinanceDataReader",
  "universe": "kospi",
  "market": "KOSPI",
  "count": 940,
  "symbols": [
    {
      "code": "005930",
      "name": "삼성전자",
      "market": "KOSPI"
    },
    {
      "code": "000660",
      "name": "SK하이닉스",
      "market": "KOSPI"
    }
  ],
  "meta": {
    "listing_key": "KOSPI"
  }
}
```

S&P500도 같은 형태로 유지.

예:

```json
{
  "schema_version": 1,
  "as_of_date": "2026-04-03",
  "generated_at": "2026-04-03T07:10:00+09:00",
  "source": "FinanceDataReader",
  "universe": "sp500",
  "market": "US",
  "count": 503,
  "symbols": [
    {
      "code": "AAPL",
      "name": "Apple Inc.",
      "market": "US"
    }
  ],
  "meta": {
    "listing_key": "S&P500"
  }
}
```

---

## 해야 할 작업

## 1) snapshot 생성 스크립트 추가
대상 예시:
- `apps/api/scripts/build_universe_snapshots.py`
- 또는 유사 위치

### 요구사항
- FinanceDataReader로 `KOSPI`, `S&P500` 목록 조회
- 위 JSON 스키마로 저장
- `latest.json` 갱신
- 날짜별 archive 저장
- 실패 시 기존 latest 유지
- count / diff / 경고 로그 남기기 가능하면 좋음

### 주의
- ticker/code normalize
- market normalize (`KOSPI`, `US` or `NASDAQ/NYSE` 등 일관성 정의)
- symbols 배열은 안정적인 정렬 유지

---

## 2) 기존 universe builder가 JSON snapshot만 읽도록 변경
대상 파일 예시:
- `apps/api/services/universe_builder.py`

### 현재 문제
지금은 `get_company_catalog(scope="live")` 를 읽고,
거기서 `top_liquidity_200`, `us_mega_cap` 같은 규칙을 잘라 만든다.

### 바꿔야 할 방향
이제는 아래처럼 바꿔야 한다.

- `kospi` snapshot 읽기
- `sp500` snapshot 읽기
- 필요하면 rule name을 JSON source에 매핑

예:
- `kospi` → `storage/logs/universe_snapshots/kospi/latest.json`
- `sp500` → `storage/logs/universe_snapshots/sp500/latest.json`

### 요구사항
- snapshot이 있으면 그걸 읽음
- 없으면 명시적 에러 또는 fallback 전략 정의
- 캐시/refresh 동작도 snapshot 생성 시점 기준으로 단순화

---

## 3) 하드코딩 종목 소스 제거
대상 예시:
- `apps/api/config/company_catalog.py`
- `config/backtest_universe.py`
- `config/portfolio.py` 연동부 중 유니버스 생성에 직접 쓰이는 부분
- `apps/api/services/universe_builder.py`
- 관련 호출부

### 제거 대상
- `_BASE_ENTRIES` 기반 live universe 생성 의존성
- `get_kospi100_universe()` / `get_sp100_nasdaq_universe()` 를 universe source로 쓰는 흐름
- `HOLDINGS` 를 universe 생성 입력으로 쓰는 흐름

### 주의
완전 삭제가 목표지만,
다른 기능(예: 종목명 매핑, watchlist, 뉴스 alias 등)이 여전히 `company_catalog` 를 쓸 수 있다면
**유니버스 생성용 의존성만 제거**하고,
다른 도메인에서 필요한 최소 카탈로그 기능은 분리하는 방향이 더 안전하다.

즉:
- 유니버스 source 로서의 company catalog 제거
- 이름/alias lookup 용 보조 catalog는 필요 시 별도 유지 가능

---

## 4) strategy registry 기본 universe_rule 정리
대상 파일 예시:
- `apps/api/services/strategy_registry.py`

### 현재 문제
기본 strategy들이
- `top_liquidity_200`
- `us_mega_cap`
같은 이름을 사용함

### 바꿔야 할 방향
이제 rule naming도 실제 동작 기준으로 단순화한다.

추천 예시:
- `kospi`
- `sp500`

즉 strategy registry도 새 snapshot 기반 rule명을 사용하도록 바꾼다.

---

## 5) live_signal_engine / live_jobs 등 호출부 정리
대상 파일 예시:
- `apps/api/services/live_signal_engine.py`
- `apps/api/jobs/live_jobs.py`
- 기타 `get_universe_snapshot(...)` 호출부

### 해야 할 일
기존 rule 이름/의미가 바뀌므로,
새 snapshot rule (`kospi`, `sp500`) 기준으로 동작하도록 정리.

---

## 6) docs / UI 문구 정리
하드코딩 기반 rule이 제거되면,
문구도 실제 동작에 맞게 정리해야 한다.

예:
- `top_liquidity_200` 같은 misleading 이름 제거
- `us_mega_cap` 제거
- `KOSPI`, `S&P500` snapshot 기반이라는 설명 반영

---

## cron 설계 방향
이 작업에서 cron 정의 자체를 코드로 생성할 필요는 없지만,
최종 구조는 아래를 전제로 설계한다.

### 추천 실행 시각
- `KOSPI`: 평일 18:00 전후
- `S&P500`: 평일 07:00 전후 (한국시간 기준)

### 역할
- snapshot 생성
- latest.json 갱신
- 날짜별 archive 저장

앱은 snapshot 생성 책임을 지지 않고,
읽기만 한다.

---

## 비목표
이번 작업 범위에서 제외:
- 장중 실시간 유동성 랭킹 구현
- KIS 기반 거래대금 top100 구축
- 위키/야후 등 대체 소스 fallback 다중화
- strategy candidate refactor

이번 작업은 오직:
> **하드코딩 유니버스를 없애고, KOSPI / S&P500 JSON snapshot 기반으로 읽게 바꾸는 것**

에 집중한다.

---

## 완료 조건
아래가 만족되면 완료로 본다.

1. 유니버스 생성이 더 이상 `_BASE_ENTRIES`, `get_kospi100_universe()`, `get_sp100_nasdaq_universe()`, `HOLDINGS` 에 의존하지 않는다
2. `KOSPI`, `S&P500` snapshot JSON 생성 스크립트가 있다
3. universe builder는 snapshot JSON만 읽는다
4. strategy registry와 runtime/live 경로가 새 rule명을 사용한다
5. misleading rule name (`top_liquidity_200`, `us_mega_cap`) 제거 또는 완전한 backward-compat cleanup 수행
6. docs/UI 문구가 새 구조에 맞다

---

## 사용자 기대 문장
최종적으로 사용자는 이렇게 이해하면 된다.

> "유니버스는 코드에 박아놓은 목록이 아니라,
> 매일 생성되는 KOSPI / S&P500 snapshot JSON을 읽어서 쓴다."

이게 이번 작업의 핵심이다.
