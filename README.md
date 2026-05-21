# WealthPulse

WealthPulse는 Hermes 리서치, Risk Gate, Runtime Executor를 묶은 자동거래 운영 콘솔이다.

Hermes는 판단 JSON을 만들고, WealthPulse는 그 판단을 리스크 정책으로 검증한 뒤 주문 의도를 만든다. Hermes가 직접 주문하지 않는다. 실패한 판단은 대체하지 않고 차단하거나 운영 화면에 노출한다.

## 지금 기준

- 운영 기준: 코드와 이 README
- API: `apps/api`
- Web: `apps/web`
- 런타임 데이터: `storage/logs`
- 리포트 데이터: `storage/reports`
- 실행 기준: `docker-compose.yml`
- 과거 설계 메모: `AGENT_TRADING_REDESIGN.md`

## 디렉터리 구조

```text
.
├── apps
│   ├── api                  # FastAPI, Agent Run, Risk Gate, execution, research ingest
│   └── web                  # Vite + React 운영 콘솔
├── scripts
│   └── run_kospi_research.sh
├── storage
│   ├── logs
│   │   ├── runtime          # engine/account/event/research run state
│   │   ├── audit            # agent/order/risk audit DB
│   │   ├── config           # risk config, watchlist, guardrail, validation config
│   │   └── cache            # universe/research/broker token cache
│   └── reports              # generated report DB/files
├── docker-compose.yml
└── README.md
```

## 설치

Docker 기준:

```bash
docker compose build
```

로컬 API 기준:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

로컬 Web 기준:

```bash
cd apps/web
npm ci
```

## 실행

전체 실행:

```bash
docker compose up -d --build
curl http://localhost:8001/health
```

API만 실행:

```bash
. .venv/bin/activate
cd apps/api
API_PORT=8001 python api_server.py
```

Web만 실행:

```bash
cd apps/web
npm run dev
```

기본 포트:

- Web: `http://localhost:8081`
- API: `http://localhost:8001`
- Health: `http://localhost:8001/health`

## 운영 흐름

1. Candidate Monitor가 후보를 만들고 우량주 여부를 붙인다.
2. Hermes 리서치가 후보별 판단 JSON을 생성해 ingest한다.
3. Agent Run이 최신 research snapshot을 읽는다.
4. Risk Gate가 시장/섹터/종목/추가매수/quote/risk 계산을 검증한다.
5. Runtime Executor가 승인된 주문 의도만 실행 상태에 반영한다.
6. Web 운영 화면에서 성공, 차단, partial failure를 확인한다.

## 주요 화면

- `/agent-dashboard`: Agent Run, Risk Gate, 주문 감사, 리스크 설정
- `/research-ai`: 후보 리서치, Hermes 판단, partial failure 배지
- `/signal-review`: 신호와 리스크 검토
- `/orders-execution`: 주문, 체결, 포트폴리오 관제
- `/performance`: 성과와 회고
- `/lab/validation`: 검증 랩
- `/watchlist`: 관심 종목과 후보 관리

## 주요 API

- `GET /health`
- `GET /api/system/mode`
- `GET /api/agent/runs`
- `POST /api/agent/run`
- `GET /api/risk/config`
- `POST /api/risk/config`
- `GET /api/research/status`
- `POST /api/research/run-status`
- `GET /api/broker/kis/status`
- `GET /api/runtime/engine/status`
- `GET /api/runtime/account`

## 리스크 설정

`GET/POST /api/risk/config`가 Risk Gate 설정의 기준이다.

핵심 옵션:

- `allocation_mode`: `diversified` 또는 `concentrated`
- `bluechip_top_n_kospi`: KOSPI 우량주 판정 개수, 기본 `20`
- `bluechip_top_n_us`: US 우량주 판정 개수, 기본 `20`
- `bluechip_max_symbol_position_ratio`: 집중 모드 우량주 단일 종목 cap, 기본 `0.40`
- `bluechip_risk_per_trade_pct`: 집중 모드 우량주 거래 리스크, 기본 `1.5`
- `bluechip_allow_additional_buy`: 집중 모드 우량주 추가매수 허용, 기본 `true`

집중투자 모드 예시:

```bash
curl -X POST http://localhost:8001/api/risk/config \
  -H 'Content-Type: application/json' \
  -d '{
    "allocation_mode": "concentrated",
    "bluechip_top_n_kospi": 20,
    "bluechip_top_n_us": 20,
    "bluechip_max_symbol_position_ratio": 0.40,
    "bluechip_risk_per_trade_pct": 1.5,
    "bluechip_allow_additional_buy": true
  }'
```

모드별 동작:

- `diversified`: 기존 분산 정책. 일반 종목 cap과 섹터 cap을 강하게 적용한다.
- `concentrated`: 우량주에만 단일 종목 40% cap, 추가매수 허용, 높은 risk budget, 완화된 섹터 cap을 적용한다.
- 우량주 기준: KOSPI는 `kospi100` 상위 20개, US/NASDAQ은 `sp100` 상위 20개다.

후보, 신호, 주문 감사 payload에는 아래 필드가 붙는다.

- `bluechip`
- `bluechip_reason`
- `allocation_mode`
- `cap_source`

## No-Fallback 원칙

운영 판단 경로에서 실패를 숨기지 않는다.

- 리스크 계산 실패: 진입 차단
- quote 실패: 매수 판단 차단
- research snapshot 없음/stale: 추천 리포트로 대체하지 않음
- Hermes partial failure: 성공처럼 처리하지 않음
- 운영 판단 경로의 무음 `except`: 금지

실패 응답은 가능하면 아래 형태를 유지한다.

```json
{
  "ok": false,
  "error_code": "RESEARCH_SNAPSHOT_MISSING",
  "reason": "usable research snapshot is required"
}
```

## Hermes 리서치

KOSPI cron 실행:

```bash
WEALTHPULSE_KOSPI_RESEARCH_LIMIT=9 \
WEALTHPULSE_KOSPI_RESEARCH_CONCURRENCY=3 \
/home/user/wealth-pulse/scripts/run_kospi_research.sh
```

crontab 예시:

```cron
# WEALTHPULSE_RESEARCH_BEGIN
*/10 8-14 * * 1-5 /home/user/wealth-pulse/scripts/run_kospi_research.sh
0,10,20,30 15 * * 1-5 /home/user/wealth-pulse/scripts/run_kospi_research.sh
# WEALTHPULSE_RESEARCH_END
```

환경변수:

- `WEALTHPULSE_API_BASE_URL`: 기본 `http://127.0.0.1:8001`
- `WEALTHPULSE_HERMES_RESEARCH_COMMAND`: Hermes CLI 명령
- `WEALTHPULSE_KOSPI_RESEARCH_LIMIT`: 기본 `9`
- `WEALTHPULSE_KOSPI_RESEARCH_CONCURRENCY`: 기본 `3`
- `WEALTHPULSE_KOSPI_RESEARCH_TIMEOUT`: 종목별 timeout, 기본 `300`
- `WEALTHPULSE_KOSPI_RESEARCH_DRY_RUN=1`: Hermes 호출 없이 대상과 프롬프트만 확인

exit code:

- `0`: 전체 성공
- `1`: 전체 실패
- `2`: 일부 실패

상태 확인:

```bash
curl http://localhost:8001/api/research/status
tail -n 100 storage/logs/runtime/hermes_research_runner.log
```

`/api/research/status`에는 최근 실행 상태가 포함된다.

- `last_run_status`
- `partial_failure`
- `selected_count`
- `success_count`
- `failure_count`
- `recent_errors`

## 검증

Python 테스트 코드는 만들지 않는다. 변경 후 실행 검증만 한다.

```bash
python -m compileall -q apps/api
cd apps/web && npm run build
```

Hermes 수동 확인:

```bash
WEALTHPULSE_KOSPI_RESEARCH_DRY_RUN=1 ./scripts/run_kospi_research.sh
```

운영 확인:

- `/research-ai`에서 partial failure 배지 확인
- `/agent-dashboard`에서 `allocation_mode`, 우량주 cap, 주문 차단 reason 확인
- 집중투자 모드에서 우량주 sizing이 일반 모드보다 커지는지 확인

## 운영 주의

- API 키, 토큰, 계좌 정보는 커밋하지 않는다.
- `storage/logs/config`, `storage/logs/audit`, `storage/logs/runtime`은 운영 상태라 함부로 지우지 않는다.
- SQLite `*.db-wal`, `*.db-shm`은 API 실행 중 삭제하지 않는다.
- 실거래 주문은 broker 상태, runtime mode, risk config를 확인한 뒤 연다.
