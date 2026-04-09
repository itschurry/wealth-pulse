# 00. 문서 인덱스

이 문서 세트는 **지금 저장소 코드**를 기준으로 다시 썼다. 옛날 문서랑 섞어 읽으면 오히려 헷갈린다. 기준은 아래 파일들이다.

- `apps/api`
- `apps/web`
- `docker-compose.yml`

## 먼저 읽을 순서

1. `01-installation.md` — 띄우는 법
2. `03-architecture-overview.md` — 구조 이해
3. `02-operations-manual.md` — 실제 운영 순서
4. 필요할 때 stage 문서별 참조

## 문서 목록

### `01-installation.md`
- Docker Compose 기반 실행
- 포트/볼륨/환경변수
- 초기 점검 명령

### `02-operations-manual.md`
- 데일리 운영 루틴
- 엔진 시작/정지/리셋
- 실패 주문, stale 데이터, 리서치 문제 대응

### `03-architecture-overview.md`
- scanner / runtime / Hanna 분리
- web ↔ api ↔ storage 흐름
- truth source 정의

### `04-stage-1-strategy-and-scanner.md`
- 전략 레지스트리
- 유니버스
- 장중 스캐너
- Layer A/B/D/E 관점

### `05-stage-2-validation-and-optimization.md`
- 백테스트
- Walk-forward
- optimization
- quant-ops workflow

### `06-stage-3-research-layer-c.md`
- Hanna 브리프
- research status / snapshot / ingest
- Layer C가 해도 되는 일 / 하면 안 되는 일

### `07-stage-4-risk-execution-ui.md`
- paper runtime
- auto trader 루프
- 주문/리스크 화면
- 포지션 관리

### `08-api-and-truth-sources.md`
- 주요 API 엔드포인트
- 저장 파일 기준표
- 디버깅할 때 먼저 봐야 할 파일

## 가장 중요한 운영 원칙

### 1) scanner와 runtime은 실행 계층
- 스캐너가 후보를 만든다.
- runtime이 paper/live 엔진을 돌린다.
- 주문 허용/차단은 runtime 쪽 로직이 쥔다.

### 2) Hanna는 Layer C 리서치 계층
- research score
- summary/warnings/tags
- operator brief

여기까지만 한다. **buy/sell/order 직접 결정권 없음**.

### 3) 현재 저장소의 단일 진실원은 DB가 아니라 파일 저장소
- `storage/logs`
- `storage/reports`

즉, 이 프로젝트는 지금 시점에선 "파일 기반 운영 상태 저장"이 핵심이다.

## 빠른 체크 포인트

```bash
curl http://localhost:8001/health
curl http://localhost:8001/api/engine/status
curl http://localhost:8001/api/paper/engine/status
curl http://localhost:8001/api/scanner/status
curl http://localhost:8001/api/research/status
```

## 관련 핵심 파일

- API 앱 진입점: `apps/api/api_server.py`
- API 라우트 표: `apps/api/server.py`
- 설정/경로: `apps/api/config/settings.py`
- 실행 엔진: `apps/api/services/execution_service.py`
- 웹 스캐너 화면: `apps/web/src/pages/ScannerPage.tsx`
- 웹 주문/리스크 화면: `apps/web/src/pages/PaperPortfolioPage.tsx`
