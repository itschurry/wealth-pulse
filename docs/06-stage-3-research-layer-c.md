# 06. Stage 3 — Research / Layer C / Hanna

여긴 설명 계층이다. 이름 때문에 제일 많이 오해받는 파트인데, 정리하면 별거 없다.

> **Hanna는 리서치 스코어러이자 브리프 생성기지, 주문 엔진이 아니다.**

## 역할 정의

Layer C에서 하는 일:
- research score 부여
- structured summary/warnings/tags 제공
- operator brief 생성
- scanner 후보를 설명 가능한 형태로 보강

Layer C에서 하지 않는 일:
- buy/sell/order 직접 결정
- 포지션 sizing
- risk veto override
- 주문 전송

## 관련 파일

백엔드:
- `apps/api/routes/hanna.py`
- `apps/api/routes/research.py`
- `apps/api/services/hanna_brief_service.py`
- `apps/api/routes/reports_domain.py`

프론트:
- `apps/web/src/pages/ScannerPage.tsx`
- `apps/web/src/pages/ReportsPage.tsx`
- `apps/web/src/pages/PaperPortfolioPage.tsx`

## Hanna 브리프 서비스

`apps/api/services/hanna_brief_service.py`가 하는 일:
- runtime signal book과 market context를 받아
- summary_lines를 만들고
- stance / regime / risk_level / guard_reasons / context_risks 메타를 붙인다.

응답 특징:
- `brief_type: hanna_operator_brief_v2`
- `owner: hanna`
- `source: hanna_runtime_brief`
- `migration.backend_owner: hanna`

즉, 이미 코드 차원에서 "브리프 소유자"를 Hanna로 분리해놨다.

## Research 관련 API

### 상태/타겟/스냅샷
- `GET /api/research/status`
- `GET /api/monitor/status`
- `GET /api/monitor/watchlist`
- `GET /api/monitor/promotions`
- `GET /api/research/snapshots/latest`
- `GET /api/research/snapshots`
- `POST /api/research/ingest/bulk`

### 브리프/설명
- `GET /api/hanna/brief`
- `GET /api/reports/explain`
- `GET /api/reports/index`
- `GET /api/reports/operations`

## Scanner에서의 Hanna 상태

`ScannerPage.tsx`는 Hanna 상태를 꽤 명확히 구분한다.

상태 값:
- `healthy`
- `degraded`
- `timeout`
- `research_unavailable`

판단 기준 예시:
- candidate-level `research_status`
- provider status / freshness
- `research_unavailable`
- Layer C warning에 `research_unavailable` 포함 여부

### 해석법
- `healthy`: Layer C 리서치가 정상
- `degraded`: stale/partial/품질 저하
- `timeout`: 응답 지연
- `research_unavailable`: 리서치 데이터 자체 없음

중요:
이건 Layer C 상태다. 시스템 전체 실행 가능 여부랑 1:1로 같지 않다.

## Reports에서의 Hanna

`ReportsPage.tsx`는 Hanna를 아래 용도로 쓴다.

- 오늘 브리프
- 리스크 알림의 참고 설명
- watch decision/research queue 보강
- summary lines와 rationale 제공

문구도 꽤 직접적이다.

- 리서치 요약은 참고용
- live path 최종 판단은 Layer E final action과 Risk Gate가 끝냄

이게 지금 코드의 공식 입장이라고 보면 된다.

## 주문/리스크 화면에서의 Hanna

`PaperPortfolioPage.tsx`도 같은 원칙을 다시 박아둔다.

- Layer B quant 후보
- Layer C research scorer(Hanna, 선택)
- Layer D risk veto
- Layer E final action

즉, 화면마다 같은 경계선을 반복해서 넣고 있다. 이유는 간단하다. 그만큼 이 경계를 자주 헷갈렸다는 뜻이다.

## scanner / runtime / Hanna 분리 요약

### scanner
- 후보 수집
- quant 레이어 정보 생성

### runtime
- validation / risk / sizing / execution 적용
- 최종 주문 여부 결정

### Hanna
- 설명, research score, 브리프 생성
- quality signal 제공

## 운영에서 Hanna를 어떻게 써야 하나

### 맞는 사용법
- 후보 우선순위 설명 읽기
- 왜 이 종목이 관찰/차단인지 보조 근거 확인
- 브리프에서 장세 문장/가드 사유 확인
- degraded/timeout 여부를 모니터링

### 틀린 사용법
- Hanna 점수만 보고 주문
- research unavailable이면 엔진 전체 중지 판단
- Hanna 문장을 final action보다 우선함

## 디버깅 체크포인트

### Hanna가 timeout/degraded로 계속 보임
1. `GET /api/research/status`
2. `GET /api/research/snapshots/latest`
3. `GET /api/hanna/brief`
4. ScannerPage와 ReportsPage의 상태 비교

### 브리프는 나오는데 candidate research_score가 비어 있음
- 감시 슬롯 기준 pending target 계산 문제일 수 있음
- `monitor/status`, `monitor/watchlist`, snapshots latest 확인

### research unavailable가 많음
- ingest가 안 돌았거나
- snapshot freshness가 부족하거나
- provider 상태가 missing/stale일 수 있음

## 운영 문구로 정리하면

Hanna는 잘 말해주는 사람이지, 버튼 누르는 사람은 아니다.
그 버튼은 아직 runtime이 쥐고 있다.
