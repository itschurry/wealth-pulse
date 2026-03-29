# daily-market-brief

고수익/고생존 자동투자 엔진(Profit-Max Auto-Invest Engine) 플랫폼입니다.

이 저장소의 제품 목표는 리포트 생성 자체가 아니라, 전략 신호 생성과 실행(paper 우선), 백테스트 검증, 그리고 사람이 추적 가능한 설명 리포트를 하나의 운영 흐름으로 통합하는 것입니다.

## Product Direction
- Core: 신호 생성 + 포트폴리오/주문 실행 엔진
- Validation: 백테스트 + paper trading
- Explainability: 리포트/시장 컨텍스트
- Future-ready: 실계좌 실행 인터페이스(Live engine stub)

## Runtime Modes
- `report`: 설명 리포트 생성 중심 실행
- `paper`: 모의투자 실행 모드
- `live_disabled`: 실계좌 인터페이스 비활성(기본)
- `live_ready`: 실계좌 연결 준비 모드

현재 모드는 환경변수 `AUTO_INVEST_MODE`와 `/api/system/mode` 응답으로 확인할 수 있습니다.

## Architecture (Refactor Target)
```text
.
├── app/            # 제품 모드/런타임 공통 정의
├── domain/         # 도메인 모델/규칙(점진 확장)
├── services/       # signal/execution/backtest/report 유스케이스
├── infra/          # 외부 연동 어댑터(점진 확장)
├── jobs/           # scheduler가 호출하는 실행 wrapper
├── api/            # HTTP route (request/response 매핑 중심)
├── broker/         # execution engine 구현체(paper/live stub)
├── analyzer/       # 전략/분석 로직
├── collectors/     # 데이터 수집
├── frontend/       # 운영 콘솔 UI
└── tests/
```

## Core Services
- `services.signal_service`: 추천/테마 게이트 기반 후보 산출
- `services.execution_service`: paper 계좌, 자동매매 루프, 주문 실행
- `services.backtest_service`: 전략 검증/백테스트 orchestration
- `services.report_service`: 리포트 생성 파이프라인

## Domain API (Redesigned)
기존 report-first 스키마 호환 유지가 아닌 도메인형 API를 기준으로 운영합니다.

- `GET /api/engine/status`: 실행 상태, allocator, risk guard, mode
- `GET /api/signals/rank`: EV 랭킹 신호 목록
- `GET /api/signals/{code}`: 개별 신호 상세
- `GET /api/portfolio/state`: 포지션/현금/리스크 가드 상태
- `GET /api/validation/backtest`: 확장 성과지표 포함 백테스트 결과
- `GET /api/validation/walk-forward`: walk-forward 요약(train/validation/OOS)
- `GET /api/reports/explain`: explainability 전용 리포트 뷰
- `GET /api/reports/index`: 리포트 인덱스

## Quick Start
```bash
# python deps
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# frontend deps
cd frontend
npm install
cd ..

# one-shot report generation
python3 run_once.py

# api server (terminal 1)
python3 api_server.py

# frontend dev server (terminal 2)
cd frontend && npm run dev
```

## LLM Provider
- `LLM_PROVIDER=openai` keeps the existing OpenAI flow.
- `LLM_PROVIDER=nemotron` uses a host-installed Ollama instance and the local Nemotron model.
- OpenAI와 Nemotron 모두 동일하게 host Python runtime 에서 실행합니다.
- 운영 기준 명령은 `python3 run_once.py`, `python3 api_server.py`, `scheduler.py`, `scripts/manage_scheduler_systemd.sh` 입니다.

Example `.env` values:

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_SIGNAL_MODEL=gpt-4o-mini
OPENAI_PLAYBOOK_MODEL=gpt-4o-mini
```

```bash
LLM_PROVIDER=nemotron
NEMOTRON_MODEL=nemotron-3-super
```

Before running with `LLM_PROVIDER=nemotron`, ensure Ollama is installed and the model is already pulled on the host server.

## Local Host Runtime
- Backend API: `python3 api_server.py` on `127.0.0.1:8001`
- Frontend dev UI: `cd frontend && npm run dev`
- One-shot report: `python3 run_once.py`
- Scheduler: `python3 scheduler.py`
- Long-running scheduler service: `bash scripts/manage_scheduler_systemd.sh install`

The Vite dev server proxies `/api` requests to `http://localhost:8001`, so the local console works without Docker.

## Production-Like Host Run
```bash
source .venv/bin/activate
python3 api_server.py
python3 scheduler.py
```

If you need the frontend as static assets on a host machine, build it with:

```bash
cd frontend
npm run build
```

This repository no longer uses Docker, docker-compose, nginx, or container entrypoints as an operation path.

## Validation Workflow
1. 백테스트로 전략 파라미터 검증
2. paper trading으로 실행/상태/위험 규칙 검증
3. 리포트로 매매 근거/시장 맥락 점검
4. live 모드 전환 준비(현재는 stub)

## Disclaimer
본 프로젝트의 데이터/리포트/추천은 투자 참고용이며, 최종 투자 판단과 책임은 사용자에게 있습니다.
