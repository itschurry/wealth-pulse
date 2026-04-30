# WealthPulse

WealthPulse는 Agent-primary 자동거래 운영 콘솔이다.

## 핵심 원칙

- **Hermes**: 뉴스·차트·후보 근거를 분석하고 `BUY / SELL / HOLD` 판단 JSON만 만든다.
- **Risk Gate**: Hermes 판단을 deterministic 규칙으로 최종 심사한다.
- **Executor**: 승인된 주문 의도를 현재 런타임 실행 모드에 맞게 집행한다.
- **운영자**: Agent Run, Risk Gate, 주문/거절 기록을 감시한다.

Hermes는 직접 주문하지 않는다. 실제 주문 여부와 수량은 항상 WealthPulse runtime과 Risk Gate가 결정한다.

## 현재 source of truth

- 코드: `apps/api`, `apps/web`
- 자동거래 재설계 기준: `AGENT_TRADING_REDESIGN.md`
- 운영 실행 기준: `docker-compose.yml`
- 런타임 상태/감사 로그: `storage/logs/runtime`, `storage/logs/audit`
- 리포트/산출물: `storage/reports`

## 서비스 구성

- `apps/api` — API, Agent Run, Risk Gate, broker/execution, research ingest
- `apps/web` — Vite + React 운영 콘솔
- `apps/api/scripts/hermes_research_runner.py` — host-side Hermes 리서치 실행기
- `docker-compose.yml` — API/Web 실행 진입점
- `storage/logs/runtime` — engine/account/event 상태 저장
- `storage/logs/audit` — Agent run/order/risk 감사 DB 저장
- `storage/logs/config` — watchlist, strategy registry, guardrail policy 저장
- `storage/logs/cache` — universe/research/broker token cache 저장
- `storage/reports` — 산출 리포트 저장

## 기본 포트

- Web: `http://localhost:8081`
- API: `http://localhost:8001`
- Health: `http://localhost:8001/health`

## 빠른 시작

```bash
docker compose up -d --build
curl http://localhost:8001/health
```

## 주요 화면

- `/agent-dashboard` — Agent Run · Risk Gate · Runtime 주문 감사
- `/research-ai` — 후보 리서치와 Hermes 판단 상태
- `/signal-review` — 신호/리스크 검토
- `/orders-execution` — 주문·체결·포트폴리오 관제
- `/performance` — 성과/회고
- `/lab/validation` — 검증 랩
- `/watchlist` — 관심 종목/후보 관리

## 주요 API 시작점

- `GET /health`
- `GET /api/system/mode`
- `GET /api/agent/runs`
- `POST /api/agent/run`
- `GET /api/risk/config`
- `GET /api/broker/kis/status`
- `GET /api/runtime/engine/status`
- `GET /api/runtime/account`

## 주의

- API 키, 토큰, 계좌정보는 문서나 커밋에 남기지 않는다.
- 기본 운영은 Agent, Risk Gate, Runtime Executor의 경계를 분리해서 확인한다.
- 실거래 주문은 명시적 안전 점검 전에는 열지 않는다.
- API unittest는 제거된 상태라 변경 검증은 `compileall`, Docker build/recreate, `/health` smoke, 브라우저 QA를 기준으로 한다.
