# WealthPulse

자동매매 후보 발굴, OpenAI 리서치 판단, 리스크 게이트, 가상계좌 런타임, 운영 콘솔을 한 저장소에서 돌리는 앱이야.
문서보다 코드를 먼저 봐. 이 README도 현재 코드 기준 인수인계용으로만 유지해.

## 설치와 실행

```bash
cp apps/api/.env.example apps/api/.env
docker compose up -d --build api web
curl http://127.0.0.1:8001/health
open http://127.0.0.1:8081
```

기본 실행은 Docker야. API는 `http://127.0.0.1:8001`, Web은 `http://127.0.0.1:8081`에서 확인해.

## 운영 엔트리포인트

### API 서버

```bash
docker compose up -d api
curl http://127.0.0.1:8001/health
```

- 앱 정의: `apps/api/api_server.py`
- 라우팅 테이블: `apps/api/server.py`
- 헬스체크: `GET /health`
- API prefix: `/api/*`

### 프런트

```bash
docker compose up -d web
open http://127.0.0.1:8081
```

- 앱 셸: `apps/web/src/App.tsx`
- 운용 화면: `apps/web/src/pages/WealthPulseHomePage.tsx`
- 리서치 화면: `apps/web/src/pages/CandidateResearchPage.tsx`
- 주문/계좌 화면: `apps/web/src/pages/RuntimePortfolioPage.tsx`
- 실험 화면: `apps/web/src/pages/BacktestValidationPage.tsx`

### OpenAI 리서치

운영 래퍼는 이거야.

```bash
scripts/run_market_research.sh
```

직접 돌릴 땐 이렇게 해.

```bash
docker compose exec api python scripts/openai_research_runner.py \
  --market KOSPI \
  --limit 12 \
  --mode missing_or_stale \
  --api-base-url http://127.0.0.1:8001 \
  --timeout 600 \
  --concurrency 3
```

드라이런은 후보와 프롬프트만 확인해.

```bash
docker compose exec api python scripts/openai_research_runner.py \
  --market KOSPI \
  --limit 3 \
  --dry-run
```

흐름은 이 순서야.

1. `scripts/run_market_research.sh`
2. `apps/api/scripts/openai_research_runner.py`
3. `services/research_source_enricher.py`
4. `services/openai_research_client.py`
5. `services/research_agent_payload.py`
6. `POST /api/research/ingest/bulk`
7. `services/research_store.py`

## 주요 설정

`apps/api/config/settings.py`가 `.env`를 읽어. Docker 실행 전에 `apps/api/.env`를 만들고 필요한 값만 채워.

```bash
OPENAI_API_KEY=
OPENAI_RESEARCH_MODEL=gpt-4.1
OPENAI_RESEARCH_MAX_OUTPUT_TOKENS=6000

FRED_API_KEY=
ECOS_API_KEY=
DART_API_KEY=

KIS_APP_KEY=
KIS_APP_SECRET=
KIS_ACCOUNT_CANO=
KIS_ACCOUNT_ACNT_PRDT_CD=01
KIS_BASE_URL=https://openapi.koreainvestment.com:9443

EXECUTION_MODE=paper
WEALTHPULSE_AGENT_EXECUTION_MODE=agent_primary_quant_assisted

# Docker는 docker-compose.yml에서 /reports, /logs로 잡아.
# REPORT_OUTPUT_DIR=/absolute/path/to/reports
# LOGS_DIR=/absolute/path/to/logs
TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

리서치 래퍼 전용 설정은 셸 환경변수로 준다.

```bash
WEALTHPULSE_API_BASE_URL=http://127.0.0.1:8001
WEALTHPULSE_RESEARCH_LIMIT=12
WEALTHPULSE_RESEARCH_MODE=missing_or_stale
WEALTHPULSE_RESEARCH_TIMEOUT=600
WEALTHPULSE_RESEARCH_CONCURRENCY=3
WEALTHPULSE_RESEARCH_DRY_RUN=0
```

## 런타임 확인

```bash
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8001/api/runtime/engine/status
curl http://127.0.0.1:8001/api/research/status
curl http://127.0.0.1:8001/api/broker/kis/status
```

주문 판단이 이상하면 이 순서로 봐.

1. `apps/api/services/agent_risk_gate.py`
2. `apps/api/services/trade_workflow.py`
3. `apps/api/services/research_source_policy.py`
4. `apps/api/services/quant_ops_service.py`
5. `apps/api/services/execution_service.py`

## 디렉터리 구조

```text
.
├── apps/
│   ├── api/
│   │   ├── api_server.py              # FastAPI 앱
│   │   ├── server.py                  # /api 라우팅 테이블
│   │   ├── routes/                    # HTTP 핸들러
│   │   ├── services/                  # 리서치, 런타임, 리스크, 저장소 로직
│   │   ├── scripts/                   # 운영/검증 CLI
│   │   ├── analyzer/                  # 백테스트와 분석 엔진
│   │   └── config/                    # 설정, 유니버스, 마켓 캘린더
│   └── web/
│       ├── src/                       # React 콘솔
│       ├── public/
│       └── nginx.conf                 # Docker web API 프록시
├── scripts/
│   └── run_market_research.sh         # 운영 리서치 래퍼
├── storage/
│   ├── reports/                       # 리포트/SQLite
│   └── logs/
│       ├── runtime/                   # 런타임 상태와 리서치 로그
│       ├── audit/
│       ├── config/
│       └── cache/
├── archive/                           # 예전 마크다운 문서 보관
├── docker-compose.yml
└── requirements.txt
```

## 자주 쓰는 API

```bash
curl 'http://127.0.0.1:8001/api/monitor/watchlist?market=KOSPI&limit=12&refresh=1'
curl 'http://127.0.0.1:8001/api/research/snapshots/latest?market=KOSPI&symbol=005930'
curl http://127.0.0.1:8001/api/runtime/account
curl -X POST http://127.0.0.1:8001/api/runtime/engine/start -H 'Content-Type: application/json' -d '{}'
curl -X POST http://127.0.0.1:8001/api/runtime/engine/stop -H 'Content-Type: application/json' -d '{}'
```

## 검증

```bash
docker compose build api web
docker compose up -d --force-recreate api web
curl http://127.0.0.1:8001/health
git diff --check
```

## 문서 보관

기존 마크다운 문서는 전부 `archive/`로 옮겼어.

```text
archive/README.md
archive/storage/README.md
```
