# WealthPulse

WealthPulse는 Docker로 실행되는 자동매매 운영 콘솔이야.
한 컨테이너는 FastAPI API를 돌리고, 다른 컨테이너는 React 콘솔을 Nginx로 서빙해. API는 전략 스캔, 후보 모니터, OpenAI 리서치, 리스크 게이트, 가상계좌/실계좌 런타임, 주문 이벤트를 전부 한 프로세스 안에서 다뤄.

이 문서는 후임자가 코드 열기 전에 전체 흐름을 잡기 위한 인수인계 문서야. 그래도 최종 근거는 항상 코드야.

## 한눈에 보는 구조

```text
browser
  -> web container nginx
  -> api container FastAPI
  -> apps/api/server.py route table
  -> routes/*
  -> services/*
  -> storage/logs, storage/reports
```

큰 축은 5개야.

1. 콘솔 UI: `apps/web/src/App.tsx`, `apps/web/src/api/domain.ts`
2. API 라우팅: `apps/api/api_server.py`, `apps/api/server.py`
3. 후보/신호 생성: `services/strategy_engine.py`, `services/live_signal_engine.py`, `services/candidate_monitor_service.py`
4. 리서치 판단: `scripts/run_market_research.sh`, `apps/api/scripts/openai_research_runner.py`, `services/research_*`
5. 런타임/주문: `services/execution_service.py`, `services/trade_workflow.py`, `services/runtime_store.py`

## Docker 실행

기본 실행은 Docker야.

```bash
cp apps/api/.env.example apps/api/.env
docker compose up -d --build api web
curl http://127.0.0.1:8001/health
open http://127.0.0.1:8081
```

서비스는 이렇게 떠.

- `api`: Python 3.11, FastAPI, `uvicorn api_server:app --host 0.0.0.0 --port 8001`
- `web`: React 빌드 산출물을 Nginx가 서빙
- API 포트: `8001`
- Web 포트: `8081`
- API 컨테이너 볼륨: `./storage/reports:/reports`, `./storage/logs:/logs`
- Web 컨테이너는 `/api/` 요청을 `http://api:8001/api/`로 프록시해

재기동은 이거면 돼.

```bash
docker compose up -d --force-recreate api web
docker compose ps
curl http://127.0.0.1:8001/health
```

## 설정

API는 `apps/api/.env`와 루트 `.env`를 읽어. Docker에선 `docker-compose.yml`이 `apps/api/.env`를 env file로 넣고, 로그/리포트 경로를 `/logs`, `/reports`로 고정해.

최소 설정은 이거야.

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

TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

중요한 설정 의미는 이래.

- `EXECUTION_MODE=paper`: 내부 가상계좌 엔진을 써. 기본값이야.
- `EXECUTION_MODE=live`: KIS 실계좌 주문 경로를 써.
- `/api/system/mode`: `EXECUTION_MODE`만 기준으로 모드를 보여줘. 별도 모드 변수로 우회하지 않아.
- `WEALTHPULSE_AGENT_EXECUTION_MODE=agent_primary_quant_assisted`: OpenAI 리서치 buy 판단이 품질/리스크를 통과하면 퀀트 entry 없이도 주문 검토로 올라갈 수 있어.
- `OPENAI_RESEARCH_MAX_OUTPUT_TOKENS=6000`: 리서치 JSON 잘림을 피하려고 현재 기준값으로 둬.
- `DART_API_KEY`: 있으면 OpenDART 공시 evidence를 붙여.
- `KIS_*`: 현재가 조회, 실계좌 모드, 브로커 상태 확인에 필요해.

현재 운용 시장:

- 리서치 대상: `KOSPI`
- 자동매매/수동 주문 대상: `KOSPI`
- 시장 캘린더, 리서치 wrapper, 자동매매 엔진, 수동 주문, 시세 조회는 KOSPI 기준으로만 동작해.
- 운용 대시보드의 시장 흐름 지표는 판단 보조용으로 `NASDAQ`, `S&P100`, `USD/KRW`를 같이 보여줘. 이 값들은 주문/리서치 대상 시장을 늘리지 않아.

## API 진입 방식

FastAPI 라우터를 여러 파일에 직접 등록하는 구조가 아니야. `api_server.py`가 `/api/{full_path:path}`를 받고, `server.py`의 `GET_ROUTES`, `POST_ROUTES` 테이블로 넘겨.
지원 메서드는 `GET`, `POST`만이야. 예전처럼 `PUT`을 `POST`로 우회하지 않아.
폐기된 실험 API와 UI는 더 이상 제공하지 않아. 주문 런타임도 저장된 실험 산출물을 읽지 않아.

```text
apps/api/api_server.py
  health()
  api_get()
  api_post()
  api_put()
    -> server.dispatch_get()
    -> server.dispatch_post()
    -> routes/*.py handler
    -> services/*.py
```

새 API를 추가할 때는 보통 이 순서야.

1. `apps/api/routes/<domain>.py`에 handler 추가
2. `apps/api/server.py`의 `GET_ROUTES` 또는 `POST_ROUTES`에 route 추가
3. 프런트에서 쓰면 `apps/web/src/api/domain.ts`에 client 함수 추가

## 프런트 구조

React 앱은 라우터 라이브러리 없이 `App.tsx`에서 URL path를 해석해 화면을 바꿔.

주요 화면:

- `/agent-dashboard`: 운용 요약, 엔진 상태, 리서치 신선도, 포트폴리오 요약
- `/research-ai`: 후보 모니터, 리서치 상태, 스냅샷 상세. 모바일/데스크톱 레이아웃 보정은 `apps/web/src/index.css`의 research responsive 규칙을 봐.
- `/orders-execution`: 런타임 엔진 제어, 포지션, 주문 이벤트, 워크플로우. 보유 포지션은 평가금액, 투자원금, 자산비중을 같이 보여줘.
- `/watchlist`: 사용자 관심 종목
- `/lab/strategies`: 전략 프리셋
- `/lab/universe`: 유니버스

콘솔 데이터는 `apps/web/src/hooks/useConsoleData.ts`가 페이지별 polling profile로 가져와.

- 빠른 polling: 엔진, 실시간 시장
- 중간 polling: 신호, 포트폴리오
- 느린 polling: 리서치, 리포트, 유니버스, 성과

API client는 `apps/web/src/api/domain.ts`에 모여 있어. 화면에서 직접 `/api/*` 문자열을 만들기보다 여기 함수를 우선 봐.

## 저장소와 상태 파일

이 앱은 별도 DB 서버 없이 파일/SQLite 중심으로 상태를 보관해. Docker 기준 실제 경로는 `storage/logs`, `storage/reports`야.

```text
storage/
  reports/
    market_brief.db
  logs/
    runtime/
      engine_state.json
      accounts/simulated_account_state.json
      candidate_monitor.db
      engine_cycles/*.jsonl
      events/
        order_events.jsonl
        execution_events.jsonl
        signal_snapshots.jsonl
        account_snapshots.jsonl
        runtime_events.jsonl
    cache/
      research_snapshots/
        latest/default__MARKET__SYMBOL.json
        history/default__MARKET__SYMBOL.jsonl
        ingest_history.jsonl
        provider_state.json
      strategy_scans/
      universe_snapshots/
      opendart/
    audit/
    config/
      watchlist.json
      agent_risk_config.json
```

상태 저장 역할은 대략 이래.

- `runtime_store.py`: 엔진 상태, cycle, 주문 이벤트, 신호 스냅샷, 계좌 히스토리
- `candidate_monitor_store.py`: 후보 pool, active slots, promotion events SQLite
- `research_store.py`: OpenAI 리서치 latest/history snapshot과 ingest 상태
- `agent_config.py`: 리스크 설정 JSON

## 후보 생성 흐름

후보 생성은 한 번에 끝나는 단순 ranking이 아니야. 전략 스캔, 기존 보유, 관심 종목, 리서치 freshness, 거래대금/등락률/뉴스 점수가 섞여.

```text
strategy scans + configured universe + held positions + user watchlist + latest research
  -> candidate_monitor_service._dedupe_market_candidates()
  -> candidate_monitor_service.build_market_watchlist()
  -> candidate_monitor_store.candidate_pool
  -> candidate_monitor_store.active_slots
  -> /api/monitor/watchlist
```

핵심 파일:

- `services/live_signal_engine.py`: 전략별 유니버스를 훑고 기술지표로 `top_candidates` 생성
- `services/candidate_monitor_service.py`: 여러 후보 소스를 합치고 우선순위를 계산
- `services/candidate_monitor_store.py`: 후보 pool과 active slot 저장
- `routes/candidate_monitor.py`: `/api/monitor/status`, `/api/monitor/watchlist`, `/api/monitor/promotions`

후보 slot 타입은 3개야.

- `held`: 이미 보유 중인 종목
- `core`: 상시 감시할 핵심 후보
- `promotion`: 뉴스/거래대금/등락률/리서치 점수로 승격된 후보

`/api/monitor/watchlist`는 리서치 runner가 읽는 핵심 API야. 응답 안의 `pending_items`가 OpenAI 리서치 대상이 돼.

## OpenAI 리서치 흐름

리서치 판단은 주문을 내지 않아. Python이 데이터를 모으고, OpenAI는 JSON 판단만 반환해. 주문 실행은 항상 런타임과 리스크 게이트가 맡아.

운영 흐름:

```text
/api/monitor/watchlist
  -> pending_items
  -> research_source_enricher.build_research_source_pack()
  -> openai_research_client.call_openai_research()
  -> research_agent_payload.build_agent_research_ingest_payload()
  -> /api/research/ingest/bulk
  -> research_store latest/history snapshot
```

실행:

```bash
docker compose exec api python scripts/openai_research_runner.py \
  --market KOSPI \
  --limit 12 \
  --mode missing_or_stale \
  --api-base-url http://127.0.0.1:8001 \
  --timeout 600 \
  --concurrency 3
```

컨테이너 안에서 wrapper를 직접 돌릴 수도 있어.

```bash
docker compose exec api /app/scripts/run_market_research.sh
```

호스트 cron에서 계정명을 박지 말고 repo 위치만 변수로 둬.

```cron
*/5 * * * 1-5 REPO_DIR=/path/to/wealth-pulse; cd "$REPO_DIR" && docker compose exec -T api /app/scripts/run_market_research.sh
```

드라이런:

```bash
docker compose exec api python scripts/openai_research_runner.py \
  --market KOSPI \
  --limit 3 \
  --dry-run
```

루트의 `scripts/run_market_research.sh`는 호스트 cron과 API 컨테이너 양쪽에서 쓸 수 있는 wrapper야. 컨테이너에서는 `/app/scripts/run_market_research.sh`로 실행해.
현재 wrapper와 `openai_research_runner.py`는 운용 리서치 시장을 `KOSPI`로 제한해.

리서치 source pack 구성:

- 뉴스: Google News RSS, 최근 3일 쿼리
- 기술 지표: 후보의 `technical_snapshot` 우선, 없으면 KOSPI/KOSDAQ은 FinanceDataReader
- 공시 evidence: OpenDART API, KRX KIND, KRX 데이터 링크

OpenAI 출력 계약:

- schema 이름: `wealthpulse_research_snapshot_v2`
- 필수 필드: `symbol`, `market`, `confidence`, `rating`, `action`, `summary`, `bull_case`, `bear_case`, `catalysts`, `risks`, `invalidation_trigger`, `trade_plan`, `technical_features`, `news_inputs`, `evidence`, `data_quality`
- 허용 rating: `strong_buy`, `overweight`, `hold`, `underweight`, `sell`
- 허용 action: `buy`, `buy_watch`, `hold`, `reduce`, `sell`, `block`

`buy` 또는 `buy_watch`가 ingest 되려면 조건이 빡세.

- 최근 72시간 안의 신뢰 가능한 뉴스가 있어야 해
- 뉴스는 URL과 `published_at`이 있어야 해
- 공식 evidence나 허용 domain evidence가 있어야 해
- `data_quality.has_news`, `has_recent_price`, `has_technical_features`가 true여야 해
- `bear_case`, `catalysts`, `invalidation_trigger.condition`, `stop_loss`, `trade_plan.stop_loss`, `trade_plan.take_profit`이 있어야 해

품질 게이트 위치:

- source/domain 검증: `services/research_source_policy.py`
- agent payload 정규화: `services/research_agent_payload.py`
- snapshot 저장/신선도/등급: `services/research_store.py`
- 런타임 Layer C 조회: `services/research_scoring.py`

## Layer A-E 판단 구조

런타임 후보는 Layer A-E를 거쳐 최종 action이 정해져.

```text
Layer A: 후보가 어떤 universe/slot/source에서 왔는지
Layer B: quant/technical score와 signal_state
Layer C: 저장된 research snapshot 조회와 freshness/quality 평가
Layer D: risk guard와 sizing 결과
Layer E: quant + agent + risk를 합쳐 final_action 결정
```

구현 위치:

- `services/live_layers.py`
- `services/strategy_engine.py`
- `services/live_signal_engine.py`

중요한 상태값:

- `signal_state=entry`: 진입 후보
- `signal_state=watch`: 감시 후보
- `signal_state=exit`: 청산 후보
- `final_action=review_for_entry`: 주문 검토 가능
- `final_action=watch_only`: 감시만
- `final_action=do_not_touch`: 건드리지 않음
- `final_action=blocked`: 차단

Layer E에서 `review_for_entry`가 나오려면 대체로 이 조건이 맞아야 해.

- `signal_state`가 entry거나 agent buy 판단이 충분해야 해
- Layer C research가 fresh/healthy/derived 상태여야 해
- research validation grade가 A 또는 B여야 해
- source quality가 충분해야 해
- RSI/이평/거래량 같은 technical sanity가 깨지면 안 돼
- Layer D risk가 막지 않아야 해

## 런타임 엔진 흐름

자동매매 엔진은 `services/execution_service.py` 안에서 thread로 돌아. 제어 API는 `/api/runtime/engine/start`, `/stop`, `/pause`, `/resume`, `/status`야.

시작:

```bash
curl -X POST http://127.0.0.1:8001/api/runtime/engine/start \
  -H 'Content-Type: application/json' \
  -d '{"markets":["KOSPI"],"interval_seconds":300}'
```

상태:

```bash
curl http://127.0.0.1:8001/api/runtime/engine/status
curl http://127.0.0.1:8001/api/runtime/engine/cycles?limit=30
curl http://127.0.0.1:8001/api/runtime/orders?limit=60
curl http://127.0.0.1:8001/api/runtime/workflow?limit=120
```

cycle 내부 흐름:

```text
_auto_trader_loop()
  -> _run_auto_trader_cycle()
  -> runtime account 조회
  -> 시장 개장 여부 확인
  -> 보유 포지션 수익률 exit 조건 확인(-5% 손절, +12% 익절)
  -> 기술지표 보조 exit 조건 확인
  -> build_signal_book()
  -> allowed entry 후보 선택
  -> sizing/risk/order limit 확인
  -> engine.place_order()
  -> order_events, signal_snapshots, account_snapshots, engine_cycles 저장
```

런타임 청산 기준은 고정값이야. 보유 수익률이 `-5%` 이하이면 손절, `+12%` 이상이면 익절로 시장가 매도한다. 이 판단은 기술지표 조회 성공 여부와 분리돼.

`paper` 모드는 내부 가상계좌를 쓴다. 가상계좌 상태는 `storage/logs/runtime/accounts/simulated_account_state.json`에 저장돼.

`live` 모드는 KIS를 통해 실계좌 경로를 쓴다. `EXECUTION_MODE=live`를 켜기 전에 `/api/broker/kis/status`, 계좌 상태, 주문 제한을 직접 봐야 해. KOSPI 실계좌 매수는 주문 직전에 KIS 주문가능수량을 조회하고, 시장가 요청이면 현재가 지정가로 바꿔 주문 금액 초과를 줄인다. 요청 수량이 주문가능수량보다 크면 주문가능수량으로 낮춰 한 번만 낸다.

## 주문 판단과 리스크

주문은 `final_action=review_for_entry`만으로 바로 나가는 게 아니야. 최종 주문 가능 여부는 order decision, size recommendation, runtime limit을 다시 통과해야 해.

관련 파일:

- `services/trade_workflow.py`: signal/order workflow stage 계산
- `services/order_decision_service.py`: orderable/action/quantity 요약
- `services/risk_guard_service.py`: 계좌 기반 리스크 상태
- `services/agent_risk_gate.py`: agent decision용 deterministic gate
- `services/sizing_service.py`: 포지션 사이징
- `services/execution_service.py`: 실제 cycle과 주문 호출

주문 관련 주요 제한:

- 시장 개장 여부
- 일일 buy/sell limit
- 종목별 일일 주문 횟수
- 보유 수량과 매도 가능 수량
- 현금과 포지션 cap
- daily loss limit
- sector/market exposure
- cooldown
- validation gate
- research freshness와 quality gate

workflow stage는 콘솔에서 주문이 어디서 멈췄는지 볼 때 중요해.

- `watch`
- `signal_generated`
- `execution_decided`
- `order_ready`
- `order_sent`
- `filled`
- `rejected`
- `blocked`

## Research와 Runtime의 관계

이 앱에서 OpenAI 리서치는 독립 실행되고, 런타임은 저장된 리서치 스냅샷을 읽어. 즉 실시간 cycle이 OpenAI를 매번 직접 호출하는 구조가 아니야.

정상적인 운영 순서:

1. 후보 모니터가 active slots를 만든다
2. 리서치 runner가 pending 후보를 분석한다
3. `research_store`가 latest snapshot을 저장한다
4. 런타임 Layer C가 해당 snapshot을 읽는다
5. Layer E가 agent/quant/risk를 합쳐 `final_action`을 정한다
6. runtime order path가 실제 주문 여부를 다시 판단한다

그래서 “감시만 하고 매수가 안 됨” 증상은 보통 이 순서로 봐야 해.

```bash
curl http://127.0.0.1:8001/api/runtime/engine/status
curl http://127.0.0.1:8001/api/research/status
curl 'http://127.0.0.1:8001/api/monitor/watchlist?market=KOSPI&limit=20&refresh=0'
curl 'http://127.0.0.1:8001/api/signals/rank?limit=50'
curl 'http://127.0.0.1:8001/api/runtime/workflow?limit=120'
```

판단 순서:

1. `engine_state`가 `running`인지
2. 시장이 열려 있는지
3. `research.status`와 `research.freshness`가 healthy/fresh인지
4. active slot 수가 충분한지
5. signal의 `final_action`이 `review_for_entry`까지 올라왔는지
6. `entry_allowed`가 true인지
7. `size_recommendation.quantity`가 0보다 큰지
8. `blocked_reason_counts`, `reason_codes`, `workflow_stage`가 뭔지

## 주요 API 지도

엔진/런타임:

```bash
curl http://127.0.0.1:8001/api/engine/summary
curl http://127.0.0.1:8001/api/engine/status
curl http://127.0.0.1:8001/api/runtime/account
curl http://127.0.0.1:8001/api/runtime/engine/status
curl http://127.0.0.1:8001/api/runtime/engine/cycles?limit=30
curl http://127.0.0.1:8001/api/runtime/orders?limit=60
curl http://127.0.0.1:8001/api/runtime/workflow?limit=120
```

후보/신호:

```bash
curl 'http://127.0.0.1:8001/api/monitor/status?market=KOSPI&refresh=0'
curl 'http://127.0.0.1:8001/api/monitor/watchlist?market=KOSPI&limit=30&mode=missing_or_stale'
curl 'http://127.0.0.1:8001/api/monitor/promotions?market=KOSPI&limit=50'
curl 'http://127.0.0.1:8001/api/signals/rank?limit=100'
curl 'http://127.0.0.1:8001/api/signals/snapshots?limit=120'
```

리서치:

```bash
curl http://127.0.0.1:8001/api/research/status
curl 'http://127.0.0.1:8001/api/research/snapshots?limit=50'
curl 'http://127.0.0.1:8001/api/research/snapshots/latest?market=KOSPI&symbol=005930'
```

브로커/모드:

```bash
curl http://127.0.0.1:8001/api/system/mode
curl http://127.0.0.1:8001/api/broker/kis/status
curl http://127.0.0.1:8001/api/portfolio/state
```

전략:

```bash
curl http://127.0.0.1:8001/api/strategies
curl http://127.0.0.1:8001/api/strategies/metadata
```

## 디렉터리 구조

```text
.
├── apps/
│   ├── api/
│   │   ├── api_server.py
│   │   ├── server.py
│   │   ├── routes/
│   │   ├── services/
│   │   ├── scripts/
│   │   ├── analyzer/
│   │   ├── config/
│   │   ├── broker/
│   │   └── domains/
│   └── web/
│       ├── src/
│       │   ├── api/
│       │   ├── hooks/
│       │   ├── pages/
│       │   ├── components/
│       │   └── adapters/
│       ├── public/
│       └── nginx.conf
├── scripts/
│   └── run_market_research.sh
├── storage/
│   ├── reports/
│   └── logs/
├── archive/
├── docker-compose.yml
└── requirements.txt
```

`archive/`는 예전 마크다운 문서 보관용이야.

## 후임자가 먼저 봐야 할 코드 순서

앱 실행 흐름을 볼 때:

1. `docker-compose.yml`
2. `apps/api/api_server.py`
3. `apps/api/server.py`
4. `apps/api/routes/engine.py`
5. `apps/api/routes/trading.py`
6. `apps/api/services/execution_service.py`
7. `apps/api/services/execution_engine_factory.py`
8. `apps/api/services/runtime_account_cache.py`
9. `apps/api/services/runtime_validation_gate.py`

`execution_service.py`는 auto trader loop와 주문 흐름의 중심이고, 엔진 생성, 라이브 계좌 캐시, validation gate는 별도 서비스로 분리돼 있어.

후보와 매수 판단을 볼 때:

1. `apps/api/services/candidate_monitor_service.py`
2. `apps/api/services/strategy_engine.py`
3. `apps/api/services/live_layers.py`
4. `apps/api/services/research_scoring.py`
5. `apps/api/services/sizing_service.py`
6. `apps/api/services/trade_workflow.py`

OpenAI 리서치를 볼 때:

1. `apps/api/scripts/openai_research_runner.py`
2. `apps/api/services/research_source_enricher.py`
3. `apps/api/services/openai_research_client.py`
4. `apps/api/services/research_agent_payload.py`
5. `apps/api/services/research_source_policy.py`
6. `apps/api/services/research_store.py`

프런트를 볼 때:

1. `apps/web/src/App.tsx`
2. `apps/web/src/hooks/useConsoleData.ts`
3. `apps/web/src/api/domain.ts`
4. `apps/web/src/pages/WealthPulseHomePage.tsx`
5. `apps/web/src/pages/CandidateResearchPage.tsx`
6. `apps/web/src/pages/RuntimePortfolioPage.tsx`

## 검증

기본 검증은 Docker 기준으로 해.

```bash
docker compose build api web
docker compose up -d --force-recreate api web
curl http://127.0.0.1:8001/health
git diff --check
```

리서치 runner만 확인할 땐 API 컨테이너에서 dry-run을 돌려.

```bash
docker compose exec api python scripts/openai_research_runner.py \
  --market KOSPI \
  --limit 3 \
  --dry-run
```

wrapper까지 확인할 땐 이렇게 돌려.

```bash
docker compose exec -e WEALTHPULSE_RESEARCH_DRY_RUN=1 api /app/scripts/run_market_research.sh
```

## 문서 보관

예전 마크다운 문서는 여기로 옮겼어.

```text
archive/README.md
archive/storage/README.md
```
