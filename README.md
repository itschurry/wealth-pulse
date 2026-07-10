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
3. 후보/신호 생성: `services/trading_pipeline/*`, `services/candidate_monitor_service.py`, `services/strategy_engine.py`
4. 리서치 판단: `scripts/run_market_research.sh`, `apps/api/scripts/openai_research_runner.py`, `services/research_*`
5. 런타임/주문: `services/execution_service.py`, `services/trade_workflow.py`, `services/runtime_store.py`

## Docker 실행

기본 실행은 Docker야.

```bash
cp apps/api/.env.example apps/api/.env
docker compose up -d --build api web research-loop
curl http://127.0.0.1:8001/health
open http://127.0.0.1:8081
```

자동매매 운영 배포에선 `research-loop`를 같이 빌드해야 해. `api web`만 빌드하면 리서치 루프 이미지가 예전 코드로 남을 수 있어.

```bash
docker compose logs -f research-loop
```

서비스는 이렇게 떠.

- `api`: Python 3.11, FastAPI, `uvicorn api_server:app --host 0.0.0.0 --port 8001`
- `web`: React 빌드 산출물을 Nginx가 서빙
- `research-loop`: `scripts/run_market_research_loop.sh`가 장중에 후보 갱신과 OpenAI 리서치를 반복 실행
- API 포트: `8001`
- Web 포트: `8081`
- API 컨테이너 볼륨: `./storage/reports:/reports`, `./storage/logs:/logs`
- Web 컨테이너는 `/api/` 요청을 `http://api:8001/api/`로 프록시해

재기동은 이거면 돼.

```bash
docker compose up -d --force-recreate api web research-loop
docker compose ps
curl http://127.0.0.1:8001/health
```

## 설정

API는 `apps/api/.env`와 루트 `.env`를 읽어. Docker에선 `docker-compose.yml`이 `apps/api/.env`를 env file로 넣고, 로그/리포트 경로를 `/logs`, `/reports`로 고정해.

최소 설정은 이거야.

```bash
OPENAI_API_KEY=
OPENAI_ADMIN_KEY=
OPENAI_RESEARCH_MODEL=gpt-4.1
OPENAI_RESEARCH_MAX_OUTPUT_TOKENS=6000
WEALTHPULSE_RESEARCH_LIMIT=30
WEALTHPULSE_RESEARCH_MARKET=KOSPI
WEALTHPULSE_RESEARCH_MODE=missing_or_stale
WEALTHPULSE_RESEARCH_TIMEOUT=600
WEALTHPULSE_RESEARCH_CONCURRENCY=3
WEALTHPULSE_RESEARCH_LOOP_INTERVAL_SECONDS=60
WEALTHPULSE_RESEARCH_CLOSED_INTERVAL_SECONDS=600
WEALTHPULSE_RESEARCH_DRY_RUN=0

FRED_API_KEY=
ECOS_API_KEY=
DART_API_KEY=

KIS_APP_KEY=
KIS_APP_SECRET=
KIS_ACCOUNT_CANO=
KIS_ACCOUNT_ACNT_PRDT_CD=01
KIS_BASE_URL=https://openapi.koreainvestment.com:9443

EXECUTION_MODE=paper
LIVE_PERFORMANCE_STARTING_EQUITY_KRW=5000000
WEALTHPULSE_AGENT_EXECUTION_MODE=agent_primary_quant_assisted

TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

중요한 설정 의미는 이래.

- `EXECUTION_MODE=paper`: 내부 가상계좌 엔진을 써. 기본값이야.
- `EXECUTION_MODE=live`: KIS 실계좌 주문 경로를 써.
- `LIVE_PERFORMANCE_STARTING_EQUITY_KRW=5000000`: 실계좌 통합 수익률 기준 평가금액이야. `/api/performance/summary`는 이 값을 시작 자산으로 보고 현재 총 평가금액 대비 수익률을 계산해.
- `/api/system/mode`: `EXECUTION_MODE`만 기준으로 모드를 보여줘. 별도 모드 변수로 우회하지 않아.
- `WEALTHPULSE_AGENT_EXECUTION_MODE=agent_primary_quant_assisted`: OpenAI 리서치 buy 판단이 품질/리스크를 통과하면 퀀트 entry 없이도 주문 검토로 올라갈 수 있어.
- `OPENAI_RESEARCH_MAX_OUTPUT_TOKENS=6000`: 리서치 JSON 잘림을 피하려고 현재 기준값으로 둬.
- `OPENAI_ADMIN_KEY`: `/api/openai/billing`이 OpenAI Usage/Costs API를 조회할 때 써. OpenAI Admin key가 아니면 사용량/비용 조회가 실패해.
- `WEALTHPULSE_RESEARCH_LIMIT=30`: loop 1회에서 분석할 pending 후보 수야.
- `WEALTHPULSE_RESEARCH_MARKET=KOSPI`: loop가 장 시간 체크에 쓰는 시장이야.
- `WEALTHPULSE_RESEARCH_MODE=missing_or_stale`: 비어 있거나 낡은 리서치만 다시 채워.
- `WEALTHPULSE_RESEARCH_TIMEOUT=600`: 종목 1개 OpenAI 리서치 timeout 초야.
- `WEALTHPULSE_RESEARCH_CONCURRENCY=3`: 동시에 돌릴 종목 리서치 수야. 처음엔 3으로 둬.
- `WEALTHPULSE_RESEARCH_LOOP_INTERVAL_SECONDS=60`: 장중 `research-loop` 반복 간격 초야.
- `WEALTHPULSE_RESEARCH_CLOSED_INTERVAL_SECONDS=600`: 장 마감/휴장 때 다시 확인하기까지 대기할 초야.
- `WEALTHPULSE_RESEARCH_DRY_RUN=0`: `1`이면 후보만 모으고 OpenAI 호출은 안 해.
- `DART_API_KEY`: 있으면 OpenDART 공시 evidence를 붙여.
- `KIS_*`: 현재가 조회, 실계좌 모드, 브로커 상태 확인에 필요해.
- 리서치 소스팩은 후보 모니터의 Naver 실시간 가격/거래대금에 FinanceDataReader 기반 `close_vs_sma20`, `close_vs_sma60`, `volume_ratio`, `rsi14`를 병합해. 이 추세 지표가 있어야 `review_for_entry`로 올라갈 수 있어.

현재 운용 시장:

- 리서치 대상: `KOSPI`
- 자동매매/수동 주문 대상: `KOSPI`
- 시장 캘린더, 리서치 wrapper, 자동매매 엔진, 수동 주문, 시세 조회는 KOSPI 기준으로만 동작해.
- 운용 대시보드의 시장 흐름 지표는 판단 보조용으로 일별 등락률이 붙은 `KOSPI` 미니 그래프, `NASDAQ`, `S&P100`, `USD/KRW`를 같이 보여줘. 이 값들은 주문/리서치 대상 시장을 늘리지 않아.
- 운용 대시보드 상단 우측은 `/api/openai/billing`에서 KST 기준 이번 달 누적 OpenAI 비용, 토큰, 요청 수를 보여줘. 이 값은 `OPENAI_ADMIN_KEY`가 있어야 조회돼.

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

OpenAI 비용/사용량 확인:

```bash
curl http://127.0.0.1:8001/api/openai/billing
```

## 프런트 구조

React 앱은 라우터 라이브러리 없이 `App.tsx`에서 URL path를 해석해 화면을 바꿔.

주요 화면:

- `/agent-dashboard`: 운용 요약, 엔진 상태, 리서치 신선도, 포트폴리오/성과 요약. 홈 포트폴리오 카드는 총자산, 현금, 보유 평가금액을 함께 보여주고, 성과 카드는 통합 수익률/보유 수익률을 `% (금액)` 형식으로 보여줘.
- `/research-ai`: 후보 모니터, 리서치 상태, 스냅샷 상세. 모바일/데스크톱 레이아웃 보정은 `apps/web/src/index.css`의 research responsive 규칙을 봐.
- `/orders-execution`: 런타임 엔진 제어, 포지션, 주문 이벤트, 워크플로우. 보유 포지션은 평가금액, 투자원금, 자산비중을 같이 보여줘.
- `/watchlist`: 사용자 관심 종목
- `/lab/strategies`: 전략 프리셋
- `/lab/universe`: 유니버스

`buy_watch` / `watch_only`는 기본적으로 관찰 신호야. 다만 `overweight + buy_watch`가 fresh/healthy 리서치, A/B 검증, 최소 추세/거래량, 리스크 게이트를 통과하면 소액 주문 검토인 `review_for_entry`까지 승격될 수 있어.

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
      engine_cycles/*.jsonl
      events/
        order_events.jsonl
        execution_events.jsonl
        signal_snapshots.jsonl
        account_snapshots.jsonl
        runtime_events.jsonl
    cache/
      trading_pipeline/
        universe/kospi__latest.json
        scan/kospi__latest.json
        ranked/kospi__latest.json
        watchlist/kospi__latest.json
        research_queue/kospi__latest.json
      research_snapshots/
        latest/default__MARKET__SYMBOL.json
        history/default__MARKET__SYMBOL.jsonl
        ingest_history.jsonl
        provider_state.json
      opendart/
    audit/
    config/
      watchlist.json
      agent_risk_config.json
```

상태 저장 역할은 대략 이래.

- `runtime_store.py`: 엔진 상태, cycle, 주문 이벤트, 신호 스냅샷, 계좌 히스토리
- `services/trading_pipeline/store.py`: 유니버스, 스캔, 랭킹, watchlist, research queue JSON snapshot
- `research_store.py`: OpenAI 리서치 latest/history snapshot과 ingest 상태
- `agent_config.py`: 리스크 설정 JSON

## 후보 생성 흐름

후보 생성은 `services/trading_pipeline` 하나로 고정했어. 예전처럼 정적 유니버스, 전략별 스캔, 별도 후보 DB를 섞지 않아.

```text
Naver mobile stock list: marketValue + up
  -> trading_pipeline.universe.build_dynamic_universe()
  -> trading_pipeline.scanner.scan_universe()
  -> trading_pipeline.ranker.rank_candidates()
  -> trading_pipeline.research_queue.build_research_queue()
  -> cache/trading_pipeline/*.json
  -> /api/monitor/watchlist
```

핵심 파일:

- `services/trading_pipeline/universe.py`: 네이버 장중 종목 리스트에서 보통주만 읽고 가격/거래대금 기준 동적 유니버스 생성
- `services/trading_pipeline/scanner.py`: 거래대금, 등락률, 거래량으로 후보 발굴
- `services/trading_pipeline/ranker.py`: scanner 점수를 active slot 우선순위로 변환
- `services/trading_pipeline/research_queue.py`: 리서치 snapshot이 없거나 낡은 후보만 pending으로 분리
- `services/trading_pipeline/decision.py`: 저장된 active slot과 리서치 snapshot으로 Layer A-E 신호 생성
- `services/candidate_monitor_service.py`: 기존 API 호환 wrapper
- `services/strategy_engine.py`: 기존 import 호환 wrapper. 실제 신호는 `trading_pipeline.decision`만 쓴다

유니버스 기본값:

- 시장: `KOSPI`
- 최소 가격: `1,000원`
- 최소 거래대금: `50억`. 상승률이 보여도 거래대금이 이 기준보다 낮으면 보유 종목이 아닌 이상 후보에서 빠진다.
- 기본 pool: `100`
- active slot: `core 24 + promotion 8 + held`

후보 source는 단순해.

- `market_scanner`: 동적 유니버스에서 발굴된 기본 후보
- `realtime_mover`: `change_pct >= 2.0` 또는 `trading_value >= 500억`
- `trading_value_top`, `change_rate_top`, `volume_top`: rank 기반 보조 근거
- `forced_symbol`: 이미 보유 중이라 유니버스에 강제로 포함된 종목

상태 변경은 POST만 쓴다.

```bash
curl -X POST http://127.0.0.1:8001/api/monitor/refresh \
  -H 'Content-Type: application/json' \
  -d '{"markets":["KOSPI"],"limit":30,"mode":"missing_or_stale"}'
```

조회는 GET만 쓴다. `GET /api/monitor/watchlist?persist=1`은 실패한다.

```bash
curl 'http://127.0.0.1:8001/api/monitor/watchlist?market=KOSPI&limit=30&mode=missing_or_stale'
curl 'http://127.0.0.1:8001/api/universe?market=KOSPI'
curl 'http://127.0.0.1:8001/api/signals/rank?limit=100'
```

## OpenAI 리서치 흐름

리서치 판단은 주문을 내지 않아. Python이 데이터를 모으고, OpenAI는 JSON 판단만 반환해. 주문 실행은 항상 런타임과 리스크 게이트가 맡아.

운영 흐름:

```text
POST /api/monitor/refresh
  -> cache/trading_pipeline/watchlist
GET /api/monitor/watchlist
  -> pending_items
  -> research_source_enricher.build_research_source_pack()
  -> openai_research_client.call_openai_research()
  -> research_agent_payload.build_agent_research_ingest_payload()
  -> /api/research/ingest/bulk
  -> research_store latest/history snapshot
```

한 번만 실행:

```bash
docker compose exec api python scripts/openai_research_runner.py \
  --market KOSPI \
  --limit 30 \
  --mode missing_or_stale \
  --api-base-url http://127.0.0.1:8001 \
  --timeout 600 \
  --concurrency 3
```

컨테이너 안에서 wrapper를 직접 돌릴 수도 있어.

```bash
docker compose exec api /app/scripts/run_market_research.sh
```

장중 상시 실행은 crontab이 아니라 Compose 서비스로 돌려. 서비스는 계속 떠 있고, KRX 정규장인 평일 09:00~15:30에만 runner를 실행해. 장 마감/휴장에는 OpenAI 호출 없이 `WEALTHPULSE_RESEARCH_CLOSED_INTERVAL_SECONDS`만큼 잔다.

```bash
docker compose up -d --build research-loop
docker compose logs -f research-loop
tail -f storage/logs/runtime/openai_research_runner.log
```

리서치 crontab이 남아 있으면 지워. `research-loop`와 cron을 같이 켜면 같은 종목을 중복 분석하고 OpenAI 비용이 늘어.

드라이런:

```bash
docker compose exec api python scripts/openai_research_runner.py \
  --market KOSPI \
  --limit 3 \
  --dry-run
```

루트의 `scripts/run_market_research.sh`는 1회 실행 wrapper야. `scripts/run_market_research_loop.sh`는 KRX 정규장에만 이 wrapper를 반복 호출하는 장중 loop runner야.
컨테이너에서는 `/app/scripts/run_market_research.sh`, `/app/scripts/run_market_research_loop.sh`로 실행해.
현재 wrapper와 `openai_research_runner.py`는 운용 리서치 시장을 `KOSPI`로 제한해. wrapper의 기본 리서치 처리량은 `WEALTHPULSE_RESEARCH_LIMIT=30`이고, loop runner는 활성 후보 슬롯을 장중에 계속 신선하게 유지하는 용도야.

리서치 source pack 구성:

- 뉴스: Google News RSS, 최근 3일 쿼리
- 기술 지표: 후보의 `technical_snapshot` 우선, 없으면 KOSPI/KOSDAQ은 FinanceDataReader
- 공시 evidence: OpenDART API, KRX KIND, KRX 데이터 링크

OpenAI 출력 계약:

- schema 이름: `wealthpulse_research_snapshot_v2`
- 필수 필드: `symbol`, `market`, `confidence`, `rating`, `action`, `summary`, `bull_case`, `bear_case`, `catalysts`, `risks`, `invalidation_trigger`, `trade_plan`, `technical_features`, `news_inputs`, `evidence`, `data_quality`
- 허용 rating: `strong_buy`, `overweight`, `hold`, `underweight`, `sell`
- 허용 action: `buy`, `buy_watch`, `hold`, `reduce`, `sell`, `block`
- 기본 snapshot TTL: 15분. agent payload와 research store 기본값이 같아.

`buy` 또는 `buy_watch`가 ingest 되려면 조건이 빡세. live 신규 매수 승격은 `buy`가 기본이고, `buy_watch`는 아래 품질 조건과 최소 추세 조건을 추가로 통과할 때만 주문 검토 후보가 된다.

- 최근 72시간 안의 신뢰 가능한 뉴스가 있어야 해
- 뉴스는 URL과 `published_at`이 있어야 해
- 공식 evidence나 허용 domain evidence가 있어야 해
- `data_quality.has_news`, `has_recent_price`, `has_technical_features`가 true여야 해
- `bear_case`, `catalysts`, `invalidation_trigger.condition`이 있어야 해
- `technical_features`나 `trade_plan`에서 현재가를 읽을 수 있어야 해
- `invalidation_trigger.stop_loss`, `trade_plan.stop_loss`, `trade_plan.take_profit`이 0이거나 비어 있으면 현재가 기준 손절 -5%, 익절 +12% 가격으로 정규화해

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
- `services/trading_pipeline/decision.py`
- `services/strategy_engine.py`

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
- Layer C action이 `buy`거나, `overweight + buy_watch`가 최소 추세 조건을 통과해야 해
- Layer C research가 fresh/healthy/derived 상태여야 해
- research validation grade가 A 또는 B여야 해
- source quality가 충분해야 해
- RSI/이평/거래량 같은 technical sanity가 깨지면 안 돼
- `buy_watch` 승격은 `close_vs_sma20 >= 1.0` 또는 `close_vs_sma60 >= 1.0`이고, `volume_ratio >= 0.35`여야 해
- Layer D risk가 막지 않아야 해

## 런타임 엔진 흐름

자동매매 엔진은 `services/execution_service.py` 안에서 thread로 돌아. 제어 API는 `/api/runtime/engine/start`, `/stop`, `/pause`, `/resume`, `/status`야.

시작:

```bash
curl -X POST http://127.0.0.1:8001/api/runtime/engine/start \
  -H 'Content-Type: application/json' \
  -d '{"markets":["KOSPI"],"interval_seconds":60}'
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
  -> 보유 포지션 수익률 exit 조건 확인(-5% 손절, +12% 익절, +3% 이후 고점 대비 -3%p 트레일링익절)
  -> 기술지표 보조 exit 조건 확인
  -> build_signal_book()
  -> allowed entry 후보 선택
  -> active slot entry 후보 검토
  -> sizing/risk/order limit 확인
  -> engine.place_order()
  -> order_events, signal_snapshots, account_snapshots, engine_cycles 저장
```

런타임 청산 기준은 고정값이야. 보유 수익률이 `-5%` 이하이면 손절, `+12%` 이상이면 익절로 시장가 매도한다. 추가로 한 번이라도 `+3%` 이상 수익을 본 포지션은 최고 수익률 대비 `3%p` 이상 밀리면 `트레일링익절`로 시장가 매도한다. 이 판단은 기술지표 조회 성공 여부와 분리돼.
장중 자동매매 기본 주기는 `60`초야. 신규 매수는 동적 watchlist active slot만 본다. 리서치 action이 `buy`이거나 품질 좋은 `buy_watch`이고, Layer E가 `review_for_entry`를 내고, `size_recommendation.quantity > 0`일 때만 주문 후보가 된다. `hold`는 점수가 높아도 신규 매수로 승격하지 않는다.
교체 매도는 교체 매수 수량이 현재 계좌 기준으로 이미 1주 이상 나올 때만 실행하고, 매도해서 생길 현금을 가정하지 않는다. rotation 매도는 기본 `min_holding_minutes=30`을 지나야 가능하다. 손절/익절은 이 제한보다 먼저 처리된다.

`paper` 모드는 내부 가상계좌를 쓴다. 가상계좌 상태는 `storage/logs/runtime/accounts/simulated_account_state.json`에 저장돼.

`live` 모드는 KIS를 통해 실계좌 경로를 쓴다. `EXECUTION_MODE=live`를 켜기 전에 `/api/broker/kis/status`, 계좌 상태, 주문 제한을 직접 봐야 해. KOSPI 실계좌 매수는 주문 직전에 KIS 주문가능수량을 조회하고, 시장가 요청이면 현재가 지정가로 바꿔 주문 금액 초과를 줄인다. 요청 수량이 주문가능수량보다 크면 주문가능수량으로 낮춰 한 번만 낸다. KIS `EGW00133` 접근토큰 발급 제한은 rate-limit 계열로 처리해 연속 주문 중 토큰 제한 실패를 줄인다.

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
curl -X POST http://127.0.0.1:8001/api/monitor/refresh -H 'Content-Type: application/json' -d '{"markets":["KOSPI"],"limit":30,"mode":"missing_or_stale"}'
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
curl -X POST http://127.0.0.1:8001/api/monitor/refresh -H 'Content-Type: application/json' -d '{"markets":["KOSPI"],"limit":30,"mode":"missing_or_stale"}'
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
│   ├── run_market_research.sh
│   └── run_market_research_loop.sh
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

1. `apps/api/services/trading_pipeline/orchestrator.py`
2. `apps/api/services/trading_pipeline/universe.py`
3. `apps/api/services/trading_pipeline/scanner.py`
4. `apps/api/services/trading_pipeline/ranker.py`
5. `apps/api/services/trading_pipeline/research_queue.py`
6. `apps/api/services/trading_pipeline/decision.py`
7. `apps/api/services/live_layers.py`
8. `apps/api/services/research_scoring.py`
9. `apps/api/services/sizing_service.py`
10. `apps/api/services/trade_workflow.py`

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
docker compose build api web research-loop
docker compose up -d --force-recreate api web research-loop
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

loop runner 구문과 Compose 서비스는 이렇게 확인해.

```bash
docker compose config
docker compose run --rm --no-deps research-loop sh -lc 'bash -n /app/scripts/run_market_research_loop.sh && bash -n /app/scripts/run_market_research.sh'
```

## 문서 보관

예전 마크다운 문서는 여기로 옮겼어.

```text
archive/README.md
archive/storage/README.md
```
