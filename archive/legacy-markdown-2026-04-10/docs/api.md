# daily-market-brief API 문서

이 문서는 `daily-market-brief` 백엔드 API를 **실제 웹 클라이언트가 어떻게 쓰는지 기준으로** 정리한 레퍼런스입니다.

제품 관점에서는 이 API를 **리서치 → 검증 → 실행 → observability** 흐름을 연결하는 investing backend로 보면 이해가 쉽습니다.

목표:

- 엔드포인트 목록만 나열하지 않기
- 쿼리 파라미터 / 요청 payload / 응답 핵심 필드까지 같이 적기
- 운영자가 `curl` 로 바로 점검 가능하게 만들기

---

## 1. 기본 정보

### 1-1. Base URL

- 로컬 API 직접 호출: `http://127.0.0.1:8001`
- Docker Web 프록시 경유: `http://127.0.0.1:8081/api/...`

예:

```bash
curl http://127.0.0.1:8001/api/system/mode
curl http://127.0.0.1:8081/api/system/mode
```

### 1-2. 응답 특성

이 프로젝트 API는 전형적인 REST 스펙처럼 완전히 통일되어 있진 않아.
대신 아래 패턴을 알고 있으면 덜 헷갈려.

- 대부분 `application/json`
- 성공/실패 모두 JSON 반환
- 일부는 HTTP 200 이어도 payload 안에 `error` 가 들어갈 수 있음
- 일부는 `ok: true/false` 패턴 사용
- 일부는 단순 데이터 객체만 반환하고 `ok` 필드가 없음

즉, 실무에서는 아래 3개를 같이 보는 게 안전해.

추가로 이 시스템은 **리서치 후보 경로**와 **퀀트 실행 경로**를 분리해서 다룬다. `runtime_candidate_source_mode` 는 그 둘을 runtime 후보 풀에 어떻게 노출할지 정하는 운영 스위치다.

- `quant_only`: 퀀트 검증/저장/runtime overlay 후보만 사용. 기본값이자 안전 모드
- `research_only`: today picks / recommendations 같은 리서치 후보만 사용
- `hybrid`: 두 경로를 분리 수집한 뒤 runtime 후보 풀에서 합집합으로 병합

1. HTTP status code
2. `ok` 필드 존재 여부
3. `error` 필드 존재 여부

### 1-3. 자주 쓰는 점검 패턴

```bash
curl -s http://127.0.0.1:8001/api/system/mode | jq
curl -s http://127.0.0.1:8001/api/paper/engine/status | jq
curl -s http://127.0.0.1:8001/api/recommendations | jq
```

---

## 2. 헬스체크 / 시스템

## 2-1. `GET /health`

서버 생존 확인용.

```bash
curl http://127.0.0.1:8001/health
```

예시 응답:

```json
{"status":"ok"}
```

## 2-2. `GET /api/system/mode`

현재 운영 모드 조회.

예상 필드:

- `ok`
- `current_mode`
- `supported_modes`

```bash
curl http://127.0.0.1:8001/api/system/mode
```

예시 응답:

```json
{
  "ok": true,
  "current_mode": "live_disabled",
  "supported_modes": ["report", "paper", "live_disabled", "live_ready"]
}
```

## 2-3. `GET /api/system/notifications/status`

알림 채널 상태 확인.

용도:

- 텔레그램 활성 여부 확인
- 알림 설정이 실제로 반영됐는지 확인

```bash
curl http://127.0.0.1:8001/api/system/notifications/status
```

---

## 3. 리서치 / 브리프 계열

이 섹션은 **AI·테마·뉴스 리서치 모드**에 더 가깝습니다.
반대로 백테스트 / walk-forward / 최적화는 아래 `검증 / 백테스트 / 최적화` 섹션이 담당합니다.
두 모드는 운영상 함께 읽지만, API 의미상으로는 교집합 강제가 아니라 역할 분리 + downstream 합집합 흐름으로 보는 편이 맞습니다.

## 3-1. `GET /api/reports`

사용 가능한 리포트 날짜 또는 리포트 목록 조회.

```bash
curl http://127.0.0.1:8001/api/reports
```

## 3-2. `GET /api/reports/index`

리포트 인덱스 정보 조회.

용도:

- 어떤 날짜 리포트가 저장되어 있는지 확인
- 웹 콘솔 인덱싱 기준 확인

```bash
curl http://127.0.0.1:8001/api/reports/index
```

## 3-3. `GET /api/reports/explain?date=YYYY-MM-DD`

설명용 payload 조회.

쿼리 파라미터:

- `date` 선택. 비우면 최신 기준

```bash
curl "http://127.0.0.1:8001/api/reports/explain?date=2026-03-31"
```

자주 보는 필드:

- `generated_at`
- `summary_lines`
- `judgment_lines`
- `action_items`
- `watch_points`
- explain용 구조화 데이터

## 3-4. `GET /api/analysis?date=YYYY-MM-DD`

분석 리포트 조회.

쿼리 파라미터:

- `date` 선택. 비우면 최신

```bash
curl "http://127.0.0.1:8001/api/analysis?date=2026-03-31"
```

관측된 주요 응답 필드:

- `generated_at`
- `summary_lines`
- `analysis_html`
- `analysis_playbook`
- `date`
- `error`

`analysis_playbook` 내부 예시 필드:

- `market_regime`
- `short_term_bias`
- `mid_term_bias`
- `favored_sectors`
- `avoided_sectors`
- `tactical_setups`
- `invalid_setups`
- `key_risks`
- `event_watchlist`
- `stock_candidates_short_term`
- `stock_candidates_mid_term`
- `gating_rules`

## 3-5. `GET /api/recommendations?date=YYYY-MM-DD`

추천 종목 목록 조회.

이 API는 AI·테마·뉴스 추천 모드의 기본 입력 중 하나입니다.
퀀트 백테스트를 통과한 종목만 반환하는 API로 보면 안 되고, downstream에서는 `today_picks` 와 함께 합집합 후보 흐름으로 해석합니다.

쿼리 파라미터:

- `date` 선택. 비우면 최신/전략 엔진 기준

```bash
curl http://127.0.0.1:8001/api/recommendations
```

관측된 주요 응답 필드:

- `generated_at`
- `date`
- `strategy`
- `universe`
- `signal_counts`
- `recommendations[]`
- `rejected_candidates[]`
- `backtest`
- `error`

`recommendations[]` 주요 필드:

- `rank`
- `name`
- `ticker`
- `sector`
- `signal` (`추천` / `중립` / `회피`)
- `score`
- `confidence`
- `risk_level`
- `reasons[]`
- `risks[]`
- `horizon`
- `gate_status`
- `gate_reasons[]`
- `playbook_alignment`
- `ai_thesis`
- `technical_snapshot`

## 3-6. `GET /api/today-picks?date=YYYY-MM-DD`

오늘의 픽 조회.

운영상으로는 downstream 후보 선택에서 `recommendations` 보다 우선되는 브리핑 소스로 보는 편이 맞습니다.
단, 둘 다 동시에 있어야 한다는 뜻은 아니고 없으면 `recommendations` 가 fallback 역할을 합니다.

쿼리 파라미터:

- `date` 선택. 비우면 최신

```bash
curl http://127.0.0.1:8001/api/today-picks
```

주요 필드:

- `generated_at`
- `date`
- `picks[]`

`picks[]` 관측 필드:

- `name`
- `code`
- `market`
- `sector`
- `signal`
- `score`
- `confidence`
- `reasons[]`
- `risks[]`
- `catalysts[]`
- `related_news[]`
- `theme_score`
- `matched_themes[]`
- `keyword_gate_passed`
- `horizon`
- `gate_status`
- `gate_reasons[]`
- `playbook_alignment`
- `ai_thesis`
- `technical_snapshot`

## 3-7. `GET /api/compare?base=YYYY-MM-DD&prev=YYYY-MM-DD`

두 날짜 리포트 비교.

쿼리 파라미터:

- `base`: 기준 날짜
- `prev`: 비교 날짜

```bash
curl "http://127.0.0.1:8001/api/compare?base=2026-03-31&prev=2026-03-30"
```

주의:

- 현재 서버 구현은 `base`, `prev` 쿼리명을 읽음
- 예전 문서나 예시에서 `base_date`, `prev_date` 라고 쓰면 안 맞을 수 있음

---

## 4. 매크로 / 시장 컨텍스트

## 4-1. `GET /api/macro/latest`

최신 매크로 데이터 조회.

```bash
curl http://127.0.0.1:8001/api/macro/latest
```

예상 필드:

- `date`
- `items[]`
- `summary[]`
- `error`

`items[]` 예시 필드:

- `key`
- `label`
- `as_of`
- `source`
- `display_value`
- `summary`

## 4-2. `GET /api/market-context/latest?date=YYYY-MM-DD`

시장 컨텍스트 조회.

쿼리 파라미터:

- `date` 선택. 비우면 최신

```bash
curl http://127.0.0.1:8001/api/market-context/latest
```

예상 필드:

- `date`
- `context`
- `error`

`context` 내부 예시:

- `regime`
- `risk_level`
- `inflation_signal`
- `labor_signal`
- `policy_signal`
- `yield_curve_signal`
- `dollar_signal`
- `summary`
- `risks[]`
- `supports[]`

## 4-3. `GET /api/market-dashboard`

시장 대시보드용 종합 payload.

```bash
curl http://127.0.0.1:8001/api/market-dashboard
```

주요 구성:

- `market`
- `macro`
- `context`
- `error`

## 4-4. `GET /api/live-market`

실시간 시세/시장 데이터 조회.

```bash
curl http://127.0.0.1:8001/api/live-market
```

관측 필드 예시:

- `kospi`, `kospi_pct`
- `kosdaq`, `kosdaq_pct`
- `sp100`, `sp100_pct`
- `nasdaq`, `nasdaq_pct`
- `usd_krw`
- `wti`, `wti_pct`
- `gold`, `gold_pct`
- `btc`, `btc_pct`
- `updated_at`

---

## 5. 시그널 / 종목 / 포트폴리오

## 5-1. `GET /api/signals/rank`

시그널 랭킹 조회.

의미:

- quant 백테스트 화면 자체를 반환하는 API는 아님
- `today_picks` 우선 / `recommendations` fallback 후보 흐름 위에 validation gate, EV, liquidity, sizing을 얹은 downstream 신호 뷰에 가까움
- 즉 두 전략 모드의 교집합만 보여주는 API가 아니라, 합집합 후보 흐름을 runtime 관점에서 정리한 API로 보면 됨

```bash
curl http://127.0.0.1:8001/api/signals/rank
```

주요 필드 후보:

- `signals[]`
- `regime`
- `risk_level`
- `error`

웹 UI가 실제로 읽는 시그널 필드:

- `code`
- `name`
- `market`
- `strategy_type`
- `entry_allowed`
- `reason_codes[]`
- `score`
- `ev_metrics.expected_value`
- `ev_metrics.win_probability`
- `ev_metrics.reliability`
- `size_recommendation.quantity`
- `size_recommendation.reason`
- `execution_realism.liquidity_gate_status`
- `execution_realism.slippage_bps`
- `strategy_scorecard`
- `validation_snapshot`

## 5-2. `GET /api/signals/snapshots?limit=N`

시그널 스냅샷 이력 조회.

쿼리 파라미터:

- `limit` 기본 120 수준으로 웹에서 사용

```bash
curl "http://127.0.0.1:8001/api/signals/snapshots?limit=120"
```

## 5-3. `GET /api/signals/{symbol}`

개별 시그널 상세 조회.

```bash
curl http://127.0.0.1:8001/api/signals/005930
```

## 5-4. `GET /api/stock-search?q=keyword`

종목 검색.

쿼리 파라미터:

- `q`: 검색어

```bash
curl "http://127.0.0.1:8001/api/stock-search?q=삼성전자"
```

예상 응답:

```json
[
  {"code":"005930","name":"삼성전자","market":"KOSPI"}
]
```

## 5-5. `GET /api/stock/{symbol}?market=KOSPI|NASDAQ`

개별 종목 가격/기본 정보 조회.

쿼리 파라미터:

- `market`: `KOSPI`, `NASDAQ` 등

```bash
curl "http://127.0.0.1:8001/api/stock/005930?market=KOSPI"
```

웹에서 실제로 기대하는 필드:

- `name`
- `price`
- `change_pct`
- `error`

## 5-6. `GET /api/portfolio/state?refresh=1`

포트폴리오 상태 조회.

쿼리 파라미터:

- `refresh=1` 기본
- `refresh=0` 이면 기존 상태 재사용 의도

```bash
curl "http://127.0.0.1:8001/api/portfolio/state?refresh=1"
```

---

## 6. 검증 / 백테스트 / 최적화

이 섹션은 **퀀트 트레이딩 모드 전용**입니다.
여기서 다루는 결과는 전략 채택, OOS 신뢰도, 최적화 파라미터를 위한 것이고, AI·테마·뉴스 추천 자체를 검증하는 API는 아닙니다.

## 6-1. `GET /api/backtest/run`

백테스트 실행/조회용 GET 엔드포인트.
웹 클라이언트가 실제로 쿼리스트링을 붙여 호출함.

### 주요 쿼리 파라미터

- `market_scope` : `kospi` | `nasdaq`
- `lookback_days`
- `initial_cash`
- `max_positions`
- `max_holding_days`
- `rsi_min`
- `rsi_max`
- `volume_ratio_min`
- `stop_loss_pct`
- `take_profit_pct`
- `adx_min`
- `mfi_min`
- `mfi_max`
- `bb_pct_min`
- `bb_pct_max`
- `stoch_k_min`
- `stoch_k_max`

### 실제 호출 예시

```bash
curl "http://127.0.0.1:8001/api/backtest/run?market_scope=kospi&lookback_days=1095&initial_cash=10000000&max_positions=5&max_holding_days=15&rsi_min=45&rsi_max=62&volume_ratio_min=1.0&stop_loss_pct=5&adx_min=10&mfi_min=20&mfi_max=80&bb_pct_min=0.05&bb_pct_max=0.95&stoch_k_min=10&stoch_k_max=90"
```

### 주요 응답 필드

- `metrics`
- `equity_curve[]`
- `trades[]`
- `scorecard`
- `error`

`metrics` 는 서비스 레이어에서 확장되어 아래 정보까지 붙을 수 있음.

- `total_return_pct`
- `max_drawdown_pct`
- `profit_factor`
- `win_rate_pct`
- `trade_count`
- `exit_reason_stats`
- `regime_stats`

## 6-2. `GET /api/validation/backtest`

확장 메트릭이 붙은 검증용 백테스트 엔드포인트.

```bash
curl "http://127.0.0.1:8001/api/validation/backtest?market_scope=kospi&lookback_days=1095"
```

차이점:

- `metrics` 가 더 풍부함
- `scorecard` 포함
- 내부적으로 `run_backtest_with_extended_metrics()` 사용

## 6-3. `GET /api/validation/walk-forward`

walk-forward 검증 수행.

```bash
curl "http://127.0.0.1:8001/api/validation/walk-forward?market_scope=kospi&lookback_days=1095"
```

주요 응답 필드:

- `ok`
- `config`
- `segments.train`
- `segments.validation`
- `segments.oos`
- `rolling_windows[]`
- `summary`
- `scorecard`

`summary` 핵심 필드:

- `windows`
- `positive_windows`
- `positive_window_ratio`
- `oos_reliability`
- `composite_score`
- `exit_reason_stats`
- `regime_stats`

주의:

- equity curve 포인트가 60 미만이면 `insufficient_equity_curve_for_walk_forward` 에러가 날 수 있음

## 6-4. `GET /api/validation/settings`

퀀트 검증 baseline 저장값 조회.

용도:

- 백테스트/진단/재검증에서 공통으로 쓸 저장 기준 확인
- 다른 브라우저/기기에서 같은 저장값 재사용
- `runtime_optimized_params.json` 과 별개로 관리되는 baseline 확인

```bash
curl http://127.0.0.1:8001/api/validation/settings | jq
```

주요 필드:

- `ok`
- `query`
- `settings`
- `saved_at`
- `source`

## 6-5. `POST /api/validation/settings/save`

현재 draft를 서버 저장값으로 반영.

```bash
curl -X POST http://127.0.0.1:8001/api/validation/settings/save \
  -H "Content-Type: application/json" \
  -d '{
    "query": {"market_scope":"kospi","lookback_days":1095,"max_holding_days":15},
    "settings": {"strategy":"공유 baseline","trainingDays":180,"validationDays":60,"walkForward":true,"minTrades":8}
  }' | jq
```

동작:

- 서버 JSON 저장소 갱신
- `saved_at` 갱신
- 이후 UI의 baseline 실행 기준으로 사용

## 6-6. `POST /api/validation/settings/reset`

서버 저장값을 기본 quant 설정으로 초기화.

```bash
curl -X POST http://127.0.0.1:8001/api/validation/settings/reset | jq
```

주의:

- baseline 저장값만 기본값으로 되돌림
- runtime optimized params / saved candidate는 그대로 둠

## 6-7. `GET /api/backtest/kospi`

KOSPI 전용 백테스트 결과 조회/실행용 보조 엔드포인트.

```bash
curl http://127.0.0.1:8001/api/backtest/kospi
```

## 6-8. `POST /api/run-optimization`

최적화 작업 시작.

웹에서는 body 없이 호출함.

```bash
curl -X POST http://127.0.0.1:8001/api/run-optimization
```

주요 응답 패턴:

- `{"status":"started"}`
- `{"status":"already_running"}`
- `{"status":"error", "error":"..."}`

## 6-9. `GET /api/optimization-status`

최적화 작업 진행 상태 확인.

```bash
curl http://127.0.0.1:8001/api/optimization-status
```

주요 필드:

- `running`
- `error`
- 상태 설명용 필드들

## 6-10. `GET /api/optimized-params`

최적화된 파라미터 조회. 이 엔드포인트는 **탐색 결과(search)** 만 보여준다. runtime에 실제 반영된 후보와는 분리된다.

```bash
curl http://127.0.0.1:8001/api/optimized-params
```

관측 필드:

- `status`
- `global_params`
- `version`
- `optimized_at`
- 기타 최적화 메타데이터

## 6-11. `GET /api/quant-ops/workflow`

퀀트 운영 워크플로우 상태 조회.

```bash
curl http://127.0.0.1:8001/api/quant-ops/workflow | jq
```

주요 필드:

- `guardrail_policy` — 현재 채택/보류/거절 정책 스냅샷
- `search_result` — optimizer 탐색 결과 요약
- `latest_candidate` — 가장 최근 재검증 후보 (`guardrail_policy`, `decision.policy_version` 포함)
- `saved_candidate` — 저장된 후보
- `runtime_apply` — 실제 runtime 반영 상태
- `stage_status` — `candidate_search` / `revalidation` / `save` / `runtime_apply`

## 6-12. `GET /api/quant-ops/policy`

현재 quant guardrail policy 조회.

```bash
curl http://127.0.0.1:8001/api/quant-ops/policy | jq
```

주요 필드:

- `policy.thresholds.reject` — 즉시 reject/차단 기준
- `policy.thresholds.adopt` — full adopt 기준
- `policy.thresholds.limited_adopt` — limited adopt 기준
- `policy.thresholds.limited_adopt_runtime` — 제한 채택 시 runtime clamp 기준

## 6-13. `POST /api/quant-ops/policy/save`

현재 guardrail policy 저장.

```bash
curl -X POST http://127.0.0.1:8001/api/quant-ops/policy/save   -H "Content-Type: application/json"   -d '{
    "policy": {
      "version": 1,
      "thresholds": {
        "adopt": {"min_profit_factor": 1.12},
        "limited_adopt": {"max_near_miss_count": 2}
      }
    }
  }' | jq
```

## 6-14. `POST /api/quant-ops/policy/reset`

기본 guardrail policy로 복구.

```bash
curl -X POST http://127.0.0.1:8001/api/quant-ops/policy/reset -H "Content-Type: application/json" -d '{}' | jq
```

## 6-15. `POST /api/quant-ops/revalidate`

optimizer 탐색 결과를 현재 baseline 기준으로 다시 검증한다.

```bash
curl -X POST http://127.0.0.1:8001/api/quant-ops/revalidate   -H "Content-Type: application/json"   -d '{
    "query": {"market_scope":"kospi","lookback_days":1095,"stop_loss_pct":5},
    "settings": {"strategy":"운영 전략","trainingDays":180,"validationDays":60,"walkForward":true,"minTrades":8}
  }' | jq
```

주의:

- optimizer 결과가 없으면 실패
- 결과는 `latest_candidate` 로 저장되지만 아직 runtime 반영은 아님

## 6-16. `POST /api/quant-ops/save-candidate`

재검증 통과 후보 저장.

```bash
curl -X POST http://127.0.0.1:8001/api/quant-ops/save-candidate   -H "Content-Type: application/json"   -d '{"candidate_id":"cand-...","note":"operator 승인"}' | jq
```

가드레일:

- `latest_candidate.guardrails.can_save` 가 `true` 인 경우에만 성공
- 보류/거절 후보거나 optimizer 버전이 바뀌면 차단

## 6-17. `POST /api/quant-ops/apply-runtime`

저장된 후보를 paper/runtime 설정으로 반영.

```bash
curl -X POST http://127.0.0.1:8001/api/quant-ops/apply-runtime   -H "Content-Type: application/json"   -d '{"candidate_id":"cand-..."}' | jq
```

동작:

- `runtime_optimized_params.json` 생성/갱신
- paper engine current config 갱신
- 다음 cycle부터 runtime 적용본 우선 사용

---

## 7. 워치리스트 API

## 7-1. `GET /api/watchlist`

현재 워치리스트 조회.

```bash
curl http://127.0.0.1:8001/api/watchlist
```

예시 응답:

```json
{
  "items": [
    {
      "code": "005930",
      "name": "삼성전자",
      "market": "KOSPI",
      "price": 81200,
      "change_pct": 1.23
    }
  ]
}
```

## 7-2. `POST /api/watchlist/save`

워치리스트 전체 저장.

### 요청 body

```json
{
  "items": [
    {
      "code": "005930",
      "name": "삼성전자",
      "market": "KOSPI",
      "price": 81200,
      "change_pct": 1.23
    }
  ]
}
```

### curl 예시

```bash
curl -X POST http://127.0.0.1:8001/api/watchlist/save \
  -H "Content-Type: application/json" \
  -d '{"items":[{"code":"005930","name":"삼성전자","market":"KOSPI","price":81200,"change_pct":1.23}]}'
```

### 제약

- `code`, `name`, `market` 필수
- 중복 `(market, code)` 는 서버에서 정리됨
- `price`, `change_pct` 는 선택

## 7-3. `POST /api/watchlist-actions`

워치리스트 기반 액션 계산.

이 API는 생각보다 유용해.
단순 저장이 아니라 관심종목에 대해 `buy / hold / watch / sell` 판단 결과를 만들어줌.

### 요청 body

```json
{
  "items": [
    {
      "code": "005930",
      "name": "삼성전자",
      "market": "KOSPI",
      "price": 81200,
      "change_pct": 1.23
    }
  ],
  "date": "2026-03-31"
}
```

- `items` 필수
- `date` 선택. 비우면 최신 리포트 기준

### curl 예시

```bash
curl -X POST http://127.0.0.1:8001/api/watchlist-actions \
  -H "Content-Type: application/json" \
  -d '{"items":[{"code":"005930","name":"삼성전자","market":"KOSPI"}]}'
```

### 주요 응답 필드

- `generated_at`
- `date`
- `actions[]`

`actions[]` 관측 필드:

- `code`
- `name`
- `market`
- `price`
- `change_pct`
- `action` (`buy` / `hold` / `watch` / `sell`)
- `signal`
- `score`
- `confidence`
- `reasons[]`
- `risks[]`
- `related_news[]`
- `technicals`
- `investor_flow`
- `ai_signal`
- `changed_from_yesterday`
- `gate_status`
- `gate_reasons[]`
- `horizon`
- `playbook_alignment`
- `ai_thesis`

---

## 8. 모의투자 엔진 API

## 8-1. `GET /api/paper/account?refresh=1`

모의 계좌 상태 조회.

쿼리 파라미터:

- `refresh=1` 기본
- `refresh=0` 은 캐시/기존 상태 재사용 의도

```bash
curl "http://127.0.0.1:8001/api/paper/account?refresh=1"
```

주요 응답 필드:

- `mode`
- `base_currency`
- `initial_cash_krw`
- `initial_cash_usd`
- `cash_krw`
- `cash_usd`
- `market_value_krw`
- `equity_krw`
- `realized_pnl_krw`
- `positions[]`
- `orders[]`
- `error`

## 8-2. `POST /api/paper/order`

수동 모의 주문 실행.

### 요청 body

웹 클라이언트 기준 payload:

```json
{
  "side": "buy",
  "code": "005930",
  "market": "KOSPI",
  "quantity": 1,
  "order_type": "market",
  "limit_price": null
}
```

필드:

- `side`: `buy` | `sell`
- `code`: 종목 코드
- `market`: `KOSPI` | `NASDAQ`
- `quantity`: 수량
- `order_type`: `market` | `limit`
- `limit_price`: 지정가 주문 시 선택

### curl 예시

```bash
curl -X POST http://127.0.0.1:8001/api/paper/order \
  -H "Content-Type: application/json" \
  -d '{"side":"buy","code":"005930","market":"KOSPI","quantity":1,"order_type":"market","limit_price":null}'
```

### 응답 패턴

```json
{
  "ok": true,
  "account": { ... }
}
```

또는

```json
{
  "ok": false,
  "error": "..."
}
```

## 8-3. `POST /api/paper/reset`

모의 계좌 초기화.

### 요청 body

관측된 payload:

```json
{
  "initial_cash_krw": 10000000,
  "initial_cash_usd": 10000,
  "paper_days": 7,
  "seed_positions": []
}
```

- `initial_cash_krw` 선택
- `initial_cash_usd` 선택
- `paper_days` 선택
- `seed_positions` 선택

### curl 예시

```bash
curl -X POST http://127.0.0.1:8001/api/paper/reset \
  -H "Content-Type: application/json" \
  -d '{"initial_cash_krw":10000000,"initial_cash_usd":10000,"paper_days":7}'
```

## 8-4. `POST /api/paper/auto-invest`

추천 기반 자동 투자 액션 1회 실행.

중요 의미:

- 후보 입력은 `today_picks` 우선 / `recommendations` fallback 흐름을 사용함
- quant 검증 결과는 validation gate, sizing, optimized params 쪽에서 별도로 반영됨
- 즉 quant와 AI 추천이 둘 다 동시에 일치해야만 주문 후보가 되는 교집합 모델은 아님

### 요청 body

웹 클라이언트 기준 허용 필드:

```json
{
  "market": "KOSPI",
  "max_positions": 5,
  "min_score": 60,
  "include_neutral": false,
  "theme_gate_enabled": true,
  "theme_min_score": 0.5,
  "theme_min_news": 2,
  "theme_priority_bonus": 0.1,
  "theme_focus": ["robotics", "physical_ai"]
}
```

모든 필드가 항상 필수는 아님.
`{}` 로 호출해도 기본 동작을 쓰는 쪽에 가깝다.

### 응답 패턴

- `ok`
- `account`
- `executed[]`
- `skipped[]`
- `message`
- `error`

## 8-5. `POST /api/paper/engine/start`

모의투자 엔진 시작.

운영 해석:

- 엔진은 quant validation gate와 AI 추천 candidate flow를 함께 사용함
- 하지만 두 모드를 교집합으로 묶는 게 아니라, combined candidate flow 위에 gate를 얹는 방식으로 읽는 편이 정확함

### 요청 body

웹 UI가 실제로 보내는 필드:

```json
{
  "interval_seconds": 300,
  "markets": ["KOSPI", "NASDAQ"],
  "max_positions_per_market": 5,
  "daily_buy_limit": 20,
  "daily_sell_limit": 20,
  "max_orders_per_symbol_per_day": 3
}
```

### curl 예시

```bash
curl -X POST http://127.0.0.1:8001/api/paper/engine/start \
  -H "Content-Type: application/json" \
  -d '{"interval_seconds":300,"markets":["KOSPI","NASDAQ"],"max_positions_per_market":5,"daily_buy_limit":20,"daily_sell_limit":20,"max_orders_per_symbol_per_day":3}'
```

### 응답 패턴

- `ok`
- `state`
- `account`
- `message`
- `error`

## 8-6. `POST /api/paper/engine/pause`

엔진 일시정지.

```bash
curl -X POST http://127.0.0.1:8001/api/paper/engine/pause
```

## 8-7. `POST /api/paper/engine/resume`

엔진 재개.

```bash
curl -X POST http://127.0.0.1:8001/api/paper/engine/resume
```

## 8-8. `POST /api/paper/engine/stop`

엔진 중지.

```bash
curl -X POST http://127.0.0.1:8001/api/paper/engine/stop
```

## 8-9. `GET /api/paper/engine/status`

엔진 상태 조회.

```bash
curl http://127.0.0.1:8001/api/paper/engine/status
```

웹이 실제로 읽는 핵심 필드:

- `ok`
- `state.running`
- `state.engine_state`
- `state.last_run_at`
- `state.next_run_at`
- `state.last_error`
- `state.last_summary`
- `state.today_order_counts`
- `state.today_realized_pnl`
- `state.validation_policy`
- `state.optimized_params`
- `state.config`
- `account`
- `message`
- `error`

## 8-10. `GET /api/paper/engine/cycles?limit=N`

엔진 사이클 로그 조회.

쿼리 파라미터:

- `limit` 기본 50, 최대 300

```bash
curl "http://127.0.0.1:8001/api/paper/engine/cycles?limit=30"
```

응답 패턴:

- `ok`
- `cycles[]`
- `count`
- `error`

## 8-11. `GET /api/paper/orders?limit=N`

주문 이벤트 로그 조회.

쿼리 파라미터:

- `limit` 기본 100, 최대 500

```bash
curl "http://127.0.0.1:8001/api/paper/orders?limit=60"
```

응답 패턴:

- `ok`
- `orders[]`
- `count`
- `error`

`orders[]` 에서 자주 보는 필드:

- `order_id`
- `timestamp` 또는 `ts`
- `code`
- `name`
- `side`
- `quantity`
- `filled_price_local`
- `success`
- `failure_reason`

## 8-12. `GET /api/paper/account/history?limit=N`

계좌 스냅샷 이력 조회.

쿼리 파라미터:

- `limit` 기본 100, 최대 500

```bash
curl "http://127.0.0.1:8001/api/paper/account/history?limit=60"
```

응답 패턴:

- `ok`
- `history[]`
- `count`
- `error`

---

## 9. 보조 엔드포인트

## 9-1. `GET /api/engine/status`

엔진 전반 상태 조회.

```bash
curl http://127.0.0.1:8001/api/engine/status
```

이 API는 `paper/engine/status` 와 일부 겹칠 수 있어서,
실제 운영 점검은 보통 `paper/engine/status` 쪽이 더 직접적이야.

---

## 10. 실무용 curl 묶음

## 10-1. 아침 점검

```bash
curl -s http://127.0.0.1:8001/health | jq
curl -s http://127.0.0.1:8001/api/system/mode | jq
curl -s http://127.0.0.1:8001/api/analysis | jq
curl -s http://127.0.0.1:8001/api/recommendations | jq
curl -s http://127.0.0.1:8001/api/today-picks | jq
```

## 10-2. 모의투자 상태 점검

```bash
curl -s http://127.0.0.1:8001/api/paper/engine/status | jq
curl -s "http://127.0.0.1:8001/api/paper/engine/cycles?limit=10" | jq
curl -s "http://127.0.0.1:8001/api/paper/orders?limit=20" | jq
curl -s "http://127.0.0.1:8001/api/paper/account/history?limit=20" | jq
```

## 10-3. 검증/최적화 점검

```bash
curl -s http://127.0.0.1:8001/api/optimization-status | jq
curl -s http://127.0.0.1:8001/api/optimized-params | jq
curl -s "http://127.0.0.1:8001/api/validation/walk-forward?market_scope=kospi&lookback_days=1095" | jq
```

## 10-4. 워치리스트 액션 계산

```bash
curl -X POST http://127.0.0.1:8001/api/watchlist-actions \
  -H "Content-Type: application/json" \
  -d '{"items":[{"code":"005930","name":"삼성전자","market":"KOSPI"}]}' | jq
```

---

## 11. 주의할 점

- `compare` 는 쿼리명이 `base`, `prev` 기준이라 `base_date`, `prev_date` 로 쓰면 안 맞을 수 있음
- `paper/*` API는 상태 조회와 실행 API가 섞여 있으니, 실행 후에는 `paper/engine/status` 를 한 번 더 확인하는 게 안전함
- `watchlist-actions` 는 단순 CRUD가 아니라 기술지표/수급/리포트 비교까지 섞인 계산 API라 응답이 큼
- `validation/walk-forward` 는 데이터 길이가 부족하면 에러가 정상적으로 날 수 있음
- 일부 API는 `HTTP 200 + error 필드` 조합이 가능하니, 무조건 status code만 보면 안 됨

---

## 12. 관련 문서

- 사용 매뉴얼: [`usage.md`](./usage.md)
- 웹 UI 사용 매뉴얼: [`ui-manual.md`](./ui-manual.md)
- 신뢰도 기준선 문서: [`quant-reliability-baseline-2026-03-31.md`](./quant-reliability-baseline-2026-03-31.md)
