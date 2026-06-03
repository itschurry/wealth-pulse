# WealthPulse

WealthPulse의 목적은 투자 전문가에게 맡긴 것처럼 시장에서 좋은 종목을 골라 공격적으로 굴리는 자동 운용 앱이다.

OpenAI API 리서치 판단기는 종목 리서치 JSON을 만들고, WealthPulse는 후보 선정, 리스크 검증, 포지션 sizing, 주문 실행을 담당한다. 리서치 판단기는 직접 주문하지 않는다. 기본 모드는 OpenAI 리서치 `buy` 판단이 품질/리스크를 통과하면 퀀트 entry 없이도 주문 검토로 올리는 공격 운용이다. 실패한 판단은 대체하지 않고 차단하거나 운영 화면에 노출한다.

## 지금 기준

- 운영 기준: 코드와 이 README
- API: `apps/api`
- Web: `apps/web`
- 런타임 데이터: `storage/logs`
- 리포트 데이터: `storage/reports`
- 실행 기준: `docker-compose.yml`

## 디렉터리 구조

```text
.
├── apps
│   ├── api                  # FastAPI, Agent Run, Risk Gate, execution, research ingest
│   └── web                  # Vite + React 운영 콘솔
├── scripts
│   └── run_market_research.sh
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

## 코드 수정 후 운영 반영

코드 수정 후에는 로컬 실행 상태를 믿지 말고 Docker 이미지와 컨테이너를 새로 만든다.

1. 변경 확인

```bash
cd ~/wealth-pulse
git status --short
git diff --check
```

2. 빠른 빌드 검증

```bash
python -m compileall -q apps/api
cd apps/web && npm run build && cd ../..
```

3. Docker 재빌드

```bash
docker compose build api web
```

4. 컨테이너 재배포

```bash
docker compose up -d --force-recreate api web
```

5. 반영 확인

```bash
docker compose ps
curl -fsS http://127.0.0.1:8001/health
curl -fsS http://127.0.0.1:8081 >/dev/null

docker inspect -f '{{.Image}} {{.Config.Image}}' wealth-pulse-api-1
docker inspect -f '{{.Image}} {{.Config.Image}}' wealth-pulse-web-1
```

6. 자동매매 엔진 시작

현재 설정을 그대로 사용해서 엔진을 시작한다. `current_config`가 없으면 시작하지 말고 설정부터 고친다.

```bash
python3 - <<'PY'
import json
import urllib.request

base = 'http://127.0.0.1:8001'

def get(path):
    return json.load(urllib.request.urlopen(base + path))

def post(path, payload):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        base + path,
        data=body,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    return json.load(urllib.request.urlopen(req))

status = get('/api/runtime/engine/status')
state = status.get('data', status).get('state') or {}
config = state.get('current_config')
if not config:
    raise SystemExit('current_config 없음. 엔진 설정 먼저 확인해.')

started = post('/api/runtime/engine/start', config)
started_state = started.get('data', started).get('state') or {}
print(json.dumps({
    'engine_state': started_state.get('engine_state'),
    'running': started_state.get('running'),
    'execution_mode': started_state.get('execution_mode'),
    'started_at': started_state.get('started_at'),
    'next_run_at': started_state.get('next_run_at'),
    'last_error': started_state.get('last_error'),
}, ensure_ascii=False, indent=2))
PY
```

7. 엔진 상태 최종 확인

```bash
curl -fsS http://127.0.0.1:8001/api/runtime/engine/status
```

## 실제 매매 흐름

운용 경로는 `OpenAI 리서치가 buy를 내면 바로 매수`가 아니다. 후보 풀, 리서치, 현재가, 리스크, sizing, 최종 액션이 모두 통과해야 주문된다.

1. 후보 풀 생성

   `strategy_engine.py`가 `collect_pick_candidates()` 결과와 Candidate Monitor active slot을 합친다. active slot은 OpenAI 리서치 스냅샷이 fresh이고 점수가 `min_score` 이상이어야 `entry` 후보가 된다.

   기준 코드: `apps/api/services/strategy_engine.py`

2. 현재가 확인

   `resolve_stock_quote()`로 현재가를 확인한다. quote 조회가 실패하면 `quote_unavailable`로 막고 `watch/blocked` 상태로 내린다.

   기준 코드: `apps/api/services/strategy_engine.py`

3. 리서치, 퀀트, 리스크 결합

   후보 점수, OpenAI 리서치 `research_score`, validation snapshot, Risk Guard, sizing 결과를 합쳐 signal을 만든다. 최종 주문 가능 조건은 `entry_allowed == true`와 `final_action == review_for_entry`다.

   기준 코드: `apps/api/services/strategy_engine.py`

4. 최종 액션 결정

   Layer E가 OpenAI 리서치 판단과 퀀트 신호를 다시 검증한다. OpenAI 리서치가 `buy`를 내도 confidence, validation, technical, evidence가 약하면 `watch_only`로 빠진다.

   기준 코드: `apps/api/services/live_layers.py`

5. 주문 판단

   `summarize_order_decision()`은 `final_action == review_for_entry`이고 sizing 수량이 1주 이상일 때만 `buy`로 바꾼다. 그 외는 hold/block이다.

   기준 코드: `apps/api/services/order_decision_service.py`

6. 실행 루프

   Runtime Executor는 장 열림 확인, 보유 종목 매도 조건 확인, signal book 생성, 후보 필터링, 포지션 한도, 일일 주문 한도, 종목별 주문 한도를 확인한 뒤 시장가 주문을 낸다.

   기준 코드: `apps/api/services/execution_service.py`

7. 집중투자

   기본 모드는 `concentrated`다. 후보가 우량주일 때 단일 종목 cap, risk budget, 추가매수 정책이 완화된다. 우량주 기준은 유니버스 상위 N개다.

   기준 코드: `apps/api/services/bluechip_universe.py`, `apps/api/services/sizing_service.py`

## 주요 화면

- `/agent-dashboard`: 운용 현황판
- `/research-ai`: 리서치
- `/orders-execution`: 주문
- `/watchlist`: 관심
- `/lab/validation`: 실험

`/operations-dashboard`는 별도 메뉴로 쓰지 않는다. 기존 주소로 들어오면 `/agent-dashboard` 운용 현황판으로 합쳐진다.
`/performance`는 별도 메뉴로 쓰지 않는다. 기존 주소로 들어오면 `/agent-dashboard` 운용 현황판으로 합쳐진다.
`/signal-review`는 별도 메뉴로 쓰지 않는다. 기존 주소로 들어오면 `/orders-execution` 주문 페이지로 합쳐진다.

UI는 관제 설명보다 숫자, 표, 상태 배지를 우선한다. 긴 안내문, 보조 설명, 반복 메타는 숨기고 각 화면은 핵심 지표만 먼저 보이게 둔다.

탐색 메뉴는 상단 가로 네비게이션이다. 핸드폰과 세로 모니터에서는 화면 맨 위에 고정된 가로 스크롤 탭으로 항상 접근 가능해야 한다.

리서치 화면의 감시/승격 테이블은 최대 10개 행 높이로 고정하고, 나머지는 표 안에서 스크롤한다. 상태/조회 영역은 압축 카드로 둔다.

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

## 공격 운용 정책

기본 운용은 공격형이다. 단, 리서치나 quote가 없으면 매수하지 않는다.

- 기본 `allocation_mode`: `concentrated`
- 후보 풀 기본: 시장별 `100`
- active core slot 기본: 시장별 `20`
- promotion slot 기본: 시장별 `4`
- 런타임 research refresh limit: `60`
- OpenAI 리서치 기본 limit/concurrency: `12 / 3`
- Agent 주문 판단 기본: `agent_primary_quant_assisted`
- 자동 운영 시장: `KOSPI`만 사용
- 회전매매 기본: score gap `2.0`, 일 `6회`, 최소 보유일 `0`
- 우량주 추가매수: 집중 모드에서 허용
- 우량주 단일 종목 cap: `40%`
- 우량주 risk per trade: `1.5%`

후보 풀은 좋은 종목을 먼저 올리는 방식이다.

- KOSPI: `kospi100` 기반
- NASDAQ/US: 현재 자동 운영에서 제외. KOSPI 검증 이후 다시 연다.
- KOSPI와 NASDAQ 후보/백테스트 코드는 남겨두지만, 자동 리서치와 자동매매 기본 루프는 KOSPI만 돈다.
- 우선순위: 보유 종목, 우량주, 높은 OpenAI 리서치 점수, 뉴스 급증, 거래대금 상위, 상승률 상위, 관심종목
- 근거 없는 일반 유니버스 종목은 active slot 뒤로 밀린다.
- 집중 모드에서는 우량주가 후보 풀과 active slot에서 더 강하게 올라온다.

차단 기준:

- research snapshot 없음/stale
- quote 조회 실패
- Risk Guard 실패
- sizing 수량 0
- 주문 API 실패

## 리스크 설정

`GET/POST /api/risk/config`가 Risk Gate 설정의 기준이다.

핵심 옵션:

- `allocation_mode`: `concentrated` 또는 `diversified`, 기본 `concentrated`
- `bluechip_top_n_kospi`: KOSPI 우량주 판정 개수, 기본 `20`
- `bluechip_top_n_us`: US 우량주 판정 개수, 기본 `20`
- `bluechip_max_symbol_position_ratio`: 집중 모드 우량주 단일 종목 cap, 기본 `0.40`
- `bluechip_risk_per_trade_pct`: 집중 모드 우량주 거래 리스크, 기본 `1.5`
- `bluechip_allow_additional_buy`: 집중 모드 우량주 추가매수 허용, 기본 `true`
- `WEALTHPULSE_AGENT_EXECUTION_MODE`: Agent 주문 판단 모드. 기본 `agent_primary_quant_assisted`

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
- `concentrated`: 기본 운용 정책. 우량주에 단일 종목 40% cap, 추가매수 허용, 높은 risk budget, 완화된 섹터 cap을 적용한다.
- 우량주 기준: KOSPI는 `kospi100` 상위 20개, US/NASDAQ은 `sp100` 상위 20개다.

Agent 주문 판단 모드:

- `agent_primary_quant_assisted`: 기본. OpenAI 리서치 `buy`가 리서치 품질, technical sanity, Risk Guard, sizing을 통과하면 퀀트 entry 없이도 `review_for_entry`로 승격한다.
- `quant_gated_agent`: OpenAI 리서치 `buy`여도 퀀트 entry가 같이 떠야 `review_for_entry`로 승격한다.
- `agent_only`: OpenAI 리서치 `buy` 판단 중심으로 `review_for_entry`를 만든다.

```bash
WEALTHPULSE_AGENT_EXECUTION_MODE=agent_primary_quant_assisted \
python apps/api/api_server.py
```

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
- OpenAI 리서치 partial failure: 성공처럼 처리하지 않음
- 운영 판단 경로의 무음 `except`: 금지

실패 응답은 가능하면 아래 형태를 유지한다.

```json
{
  "ok": false,
  "error_code": "RESEARCH_SNAPSHOT_MISSING",
  "reason": "usable research snapshot is required"
}
```

## OpenAI 리서치

Python collector가 뉴스, DART 공시, 공식 링크, 후보 점수, FinanceDataReader 기반 기술 지표를 먼저 모은다. OpenAI 리서치 판단기는 이 입력만 보고 `Research Snapshot v2` JSON을 만든다. WealthPulse는 그 결과를 그대로 믿지 않고 ingest 단계에서 검증한다.

뉴스/근거 입력 구조:

- `source_inputs.news_inputs`: 후보별 Google News RSS 최신 기사. 기본 최근 3일 쿼리
- `source_inputs.evidence`: OpenDART 최근 공시, KRX/KIND 또는 Nasdaq/SEC 공식 링크
- `source_inputs.technical_features`: `current_price`, `close_vs_sma20`, `close_vs_sma60`, `volume_ratio`, `rsi14`
- `news_inputs`: `title`, `source`, `url`, `published_at`, `summary`
- `evidence`: URL이 있거나 `dart`, `opendart`, `krx`, `kind`, `sec`, `nasdaq`, `nyse`, `company_ir` 같은 공식 출처
- `data_quality`: `has_news`, `has_recent_price`, `has_technical_features`

리서치 runner는 `source_inputs`를 프롬프트에 넣고, ingest 직전에도 `news_inputs`와 `evidence`를 보존한다. 모델이 근거를 빼먹어도 수집된 원천 근거는 snapshot에 남긴다.

리서치 runner는 기본으로 브로커 quote를 추가 조회하지 않는다. KIS 토큰 제한 때문에 리서치가 막히면 시장 추적이 죽는다. quote 추가 조회가 꼭 필요하면 아래처럼 명시해서 켠다.

```bash
WEALTHPULSE_RESEARCH_FETCH_QUOTES=1 \
python apps/api/scripts/openai_research_runner.py --market KOSPI --limit 3
```

`buy` / `buy_watch` 차단 규칙:

- `news_inputs` 없음
- URL 없음
- `published_at` 없음 또는 파싱 실패
- 72시간 초과 뉴스
- 허용목록 밖 출처
- URL/공식 출처 없는 evidence
- `data_quality`가 뉴스/현재가/기술지표를 모두 확인하지 못함

차단 시 ingest 결과는 `accepted=0`, `rejected=1`로 남고 아래 error code 중 하나를 반환한다.

- `news_inputs_required_for_buy`
- `news_url_required`
- `news_published_at_required`
- `news_stale`
- `source_not_allowed`
- `evidence_url_required`
- `research_quality_gate_failed`

허용 source label:

```text
naver-openapi, google-news-rss, dart, opendart, krx, kind,
company_ir, company_newsroom, sec, nasdaq, nyse
```

블로그, 커뮤니티, 광고성 랜딩, URL 없는 주장성 근거는 매수 근거로 쓰지 않는다.

시장 자동 선택 실행:

```bash
OPENAI_API_KEY=sk-... \
OPENAI_RESEARCH_MODEL=gpt-4.1 \
WEALTHPULSE_RESEARCH_LIMIT=12 \
WEALTHPULSE_RESEARCH_CONCURRENCY=3 \
/home/user/wealth-pulse/scripts/run_market_research.sh
```

동작 기준:

- KOSPI 정규장: KOSPI만 리서치
- US 정규장: NASDAQ 리서치 안 함
- KOSPI 휴장/장외: 리서치 실행 안 함
- 캘린더 판정 실패: 실패로 종료

crontab 예시:

```cron
# WEALTHPULSE_RESEARCH_BEGIN
*/10 * * * 1-5 /home/user/wealth-pulse/scripts/run_market_research.sh
# WEALTHPULSE_RESEARCH_END
```

환경변수:

- `WEALTHPULSE_API_BASE_URL`: 기본 `http://127.0.0.1:8001`
- `OPENAI_API_KEY`: OpenAI API key. 없으면 OpenAI 리서치는 `OPENAI_API_KEY_required`로 실패한다.
- `OPENAI_RESEARCH_MODEL`: OpenAI 리서치 판단 모델, 기본 `gpt-4.1`
- `OPENAI_RESEARCH_MAX_OUTPUT_TOKENS`: OpenAI 응답 토큰 상한, 기본 `6000`. 더 낮게 잡아도 내부 최소값은 `6000`
- `WEALTHPULSE_RESEARCH_LIMIT`: 시장 공통 limit, 기본 `12`
- `WEALTHPULSE_RESEARCH_CONCURRENCY`: 시장 공통 concurrency, 기본 `3`
- `WEALTHPULSE_RESEARCH_TIMEOUT`: 시장 공통 timeout, 기본 `600`
- `WEALTHPULSE_RESEARCH_FETCH_QUOTES=1`: 리서치 입력 생성 중 KIS quote 추가 조회
- `WEALTHPULSE_RESEARCH_DRY_RUN=1`: OpenAI API 호출 없이 대상과 프롬프트만 확인

exit code:

- `0`: 전체 성공
- `1`: 전체 실패
- `2`: 일부 실패

상태 확인:

```bash
curl http://localhost:8001/api/research/status
tail -n 100 storage/logs/runtime/openai_research_runner.log
```

`/api/research/status`에는 최근 실행 상태가 포함된다.

- `last_run_status`
- `partial_failure`
- `selected_count`
- `success_count`
- `failure_count`
- `quality_gate_rejected_count`
- `trusted_news_count`
- `untrusted_source_count`
- `stale_news_count`
- `avg_source_quality_score`
- `outcome_1d_hit_rate`
- `outcome_5d_hit_rate`
- `outcome_20d_hit_rate`
- `duration_seconds`
- `avg_seconds_per_success`
- `concurrency`
- `recent_errors`

사후 성과 추적:

```bash
python apps/api/scripts/research_outcome_evaluator.py --limit 20 --dry-run
python apps/api/scripts/research_outcome_evaluator.py --limit 200
```

기준:

- `buy` / `buy_watch`: 평가 수익률이 0보다 크면 hit
- `sell` / `reduce`: 평가 수익률이 0보다 작으면 hit
- `hold`: hit 계산 제외
- 저장 필드: `return_1d`, `return_3d`, `return_5d`, `return_20d`, `max_drawdown_20d`, `hit`

리서치 부하 정책:

- 후보 풀은 넓게 유지한다.
- OpenAI 리서치 대상은 active slot으로 압축한다.
- 프롬프트에는 종목/점수/선정근거/핵심 기술지표만 넣는다.
- 리서치가 없거나 오래되면 매수하지 않는다.

## 검증

Python 테스트 코드는 만들지 않는다. 변경 후 실행 검증만 한다.

```bash
python -m compileall -q apps/api
cd apps/web && npm run build
```

OpenAI 리서치 수동 확인:

```bash
WEALTHPULSE_RESEARCH_DRY_RUN=1 ./scripts/run_market_research.sh
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
