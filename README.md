# WealthPulse

현재 코드 기준으로 다시 정리한 운영 문서 세트야. 예전 마크다운은 `archive/legacy-markdown-2026-04-10/`로 이미 분리돼 있고, 이 README와 `docs/`가 이제 기준 문서다.

## 한 줄 요약

WealthPulse는
- **scanner/runtime**가 정량 후보를 만들고 실행 상태를 관리하고
- **Hanna**가 외부 리서치 스코어러/브리프 역할만 맡고
- **web 콘솔**이 그 결과를 운영자가 읽고 제어하는
운영형 투자 콘솔이다.

핵심은 이거 하나만 기억하면 된다.

> **주문 권한은 scanner/runtime 쪽에 있고, Hanna는 설명과 점수만 붙인다.**

## 서비스 구성

- `apps/api` — FastAPI 기반 백엔드, 라우팅 허브, paper runtime, validation, quant-ops, research ingest
- `apps/web` — Vite + React 운영 콘솔
- `docker-compose.yml` — 운영 기본 실행 진입점
- `storage/logs` — 런타임 상태/로그/히스토리 저장
- `storage/reports` — 리포트 산출물 저장

## 기본 포트

- Web: `http://localhost:8081`
- API: `http://localhost:8001`
- Health: `http://localhost:8001/health`

## 빠른 시작

```bash
docker compose up -d --build
```

확인:

```bash
curl http://localhost:8001/health
```

## 문서 인덱스

- `docs/00-index.md` — 전체 문서 안내
- `docs/01-installation.md` — 설치/실행/환경변수/볼륨
- `docs/02-operations-manual.md` — 일상 운영 절차, 장애 대응, 점검 포인트
- `docs/03-architecture-overview.md` — 전체 아키텍처와 책임 분리
- `docs/04-stage-1-strategy-and-scanner.md` — 전략/유니버스/스캐너 레이어
- `docs/05-stage-2-validation-and-optimization.md` — 백테스트/Walk-forward/최적화/quant-ops
- `docs/06-stage-3-research-layer-c.md` — Hanna / research ingest / Layer C 역할
- `docs/07-stage-4-risk-execution-ui.md` — 리스크 가드, 실행 엔진, 주문/포트폴리오 UI
- `docs/08-api-and-truth-sources.md` — 주요 API와 저장 파일 기준표

## 지금 코드에서 봐야 할 핵심 파일

### 백엔드
- `apps/api/api_server.py` — FastAPI 앱, `/health`, `/api/*` 진입점
- `apps/api/server.py` — 실제 GET/POST 라우트 등록표
- `apps/api/config/settings.py` — `REPO_ROOT`, `STORAGE_DIR`, `REPORTS_DIR`, `LOGS_DIR`
- `apps/api/services/execution_service.py` — paper/live 엔진 선택, 자동 실행 루프, 주문/워크플로우 로깅
- `apps/api/services/backtest_params_store.py` — validation 설정 저장
- `apps/api/services/quant_guardrail_policy_store.py` — quant-ops 가드레일 정책 저장

### 프론트엔드
- `apps/web/src/pages/ScannerPage.tsx` — Layer A~E 스캐너 운영 화면
- `apps/web/src/pages/BacktestValidationPage.tsx` — 검증 랩
- `apps/web/src/pages/ReportsPage.tsx` — 브리프/알림/관심 시나리오
- `apps/web/src/pages/PaperPortfolioPage.tsx` — 주문/리스크 관제판
- `apps/web/src/pages/SettingsPage.tsx` — draft/saved/displayed 상태 관리
- `apps/web/src/api/domain.ts` — 프론트가 호출하는 주요 API 집합

## 저장 경로 한눈에 보기

코드 기준 기본 경로:

- 로그 루트: `storage/logs`
- 리포트 루트: `storage/reports`
- 도커 내부 로그: `/logs`
- 도커 내부 리포트: `/reports`

대표 파일:
- `storage/logs/paper_account_state.json`
- `storage/logs/backtest_validation_settings.json`
- `storage/logs/quant_guardrail_policy.json`
- `storage/logs/quant_ops_state.json`
- 기타 engine/order/signal/account snapshot 계열 로그

## 운영 디버깅 시작점

문제 생기면 괜히 한 바퀴 돌지 말고 이 순서로 보면 된다.

1. `GET /health`
2. `GET /api/system/mode`
3. `GET /api/engine/status`
4. `GET /api/paper/engine/status`
5. `GET /api/scanner/status`
6. `GET /api/research/status`
7. `storage/logs/*` 상태 파일 확인
8. Web에서 Scanner / 주문·리스크 / 설정 상태 화면 확인

## 주의

- `apps/api/.env` 안의 실제 키 값은 문서에 적지 않는다.
- Hanna는 **리서치/브리프 전용**이다. 주문 명령 계층으로 오해하면 운영 판단이 꼬인다.
- `docker-compose.yml` 기준으로는 별도 DB 컨테이너가 없다. 현재 truth source는 주로 **파일 기반 로그/상태 저장소**다.
