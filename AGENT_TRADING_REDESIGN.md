# WealthPulse Agent Trading Redesign

## 1. Goal

WealthPulse의 목표는 리포트 앱이 아니라 안정적으로 수익을 내는 거래 시스템이다.

목표 흐름:

```text
Candidate Sources
  - Quant Strategy Signal
  - Technical Momentum Scan
  - News/Event Trigger
  - Portfolio Recheck
-> Market/News Feature Pack
-> Hermes Analyst Team
  - Technical Analyst
  - News Analyst
  - Bull Case Agent
  - Bear Case Agent
-> Hermes Trade Decision Agent
-> Deterministic Risk Guard
-> Execution
-> Decision Memory
-> Outcome Reflection
```

백테스트 전략은 더 이상 자동거래의 유일한 진입 게이트가 아니다. 백테스트 전략은 후보 출처와 참고 신호 중 하나로 낮추고, Hermes agent가 뉴스와 차트 feature를 종합해 거래 판단을 주도한다. 단, 최종 주문은 항상 WealthPulse runtime의 deterministic risk guard, liquidity check, sizing clamp를 거쳐 실행한다.

## 2. Current Problems

### 2.0 Legacy Docs Are No Longer Source Of Truth

기존 `docs/`와 루트 `archive/` 문서는 새 목표와 맞지 않아 제거했다.

앞으로 기준 문서는 이 파일과 현재 코드다. `README.md`는 source of truth가 아니라 실행 진입점과 핵심 운영 요약만 담는다.

처리 방침:

```text
README.md는 현재 구조 요약과 실행 진입점만 유지
docs/ 제거
archive/ 제거
새 설계 판단은 AGENT_TRADING_REDESIGN.md와 코드 기준으로 수행
```

### 2.1 Research Is Not Real Analysis

현재 `hanna_enrich_runner.py`는 Hermes나 LLM 분석을 하지 않는다.

현재 흐름:

```text
candidate rank
+ freshness
+ final_action
-> research_score
-> summary
-> ingest
```

이건 분석이 아니라 metadata scoring이다.

### 2.2 Layer C/E Connection Is Weak

현재 Layer C는 저장된 snapshot을 읽고 `research_score`, `summary`, `warnings`를 붙인다.

Layer E는 단순 조건문으로 판단한다.

```text
quant_score >= threshold
research_score >= threshold
risk not blocked
-> review_for_entry
```

이 구조는 agent가 분석해서 거래 판단을 하는 구조가 아니다.

### 2.3 Local Cron And Agent Work Are Mixed

라즈베리파이5 서버의 local crontab은 데이터 갱신에는 적합하다.

하지만 LLM 분석 작업은 Hermes cron이 더 적합하다.

### 2.4 Quant Strategy Is Over-Privileged

현재 구조는 백테스트/quant strategy가 후보 생성과 진입 판단의 중심이다.

문제:

```text
quant entry가 없으면 agent가 좋은 뉴스/차트 setup을 봐도 주문 후보가 되기 어렵다.
quant 후보가 약해도 research_score 보정만으로 review_for_entry가 될 수 있다.
백테스트 전략의 과거 edge가 현재 뉴스/수급/시장 regime 변화를 충분히 반영하지 못한다.
```

새 구조에서는 quant strategy를 제거하지 않는다. 대신 quant strategy는 여러 candidate source 중 하나로 낮춘다. 자동거래의 중심은 agent-driven decision이고, quant feature는 technical sanity check, confidence 보정, 성과 비교 기준으로 사용한다.

## 3. Runtime Ownership

### 3.1 Raspberry Pi Local Crontab

local crontab은 deterministic 작업을 담당한다.

대상:

```text
run_kospi_snapshot.sh
run_sp500_snapshot.sh
run_backtest_refresh.sh
run_news_refresh.sh
run_event_refresh.sh
run_enrich_kr.sh
run_enrich_us.sh
```

`run_enrich_kr.sh`와 `run_enrich_us.sh`는 최종적으로 fallback 역할로 낮춘다.

### 3.2 Hermes Cron

Hermes cron은 agent 판단이 필요한 작업을 담당한다.

담당:

```text
pending candidate 조회
technical feature 해석
news/event 분석
bull/bear debate 생성
trade decision 초안 생성
structured JSON 생성
research snapshot ingest
decision memory 업데이트
```

### 3.3 WealthPulse Runtime

WealthPulse runtime은 빠르고 결정적인 작업을 담당한다.

담당:

```text
candidate source 수집
chart/market feature 계산
news/event feature pack 생성
strategy score 계산
validation
liquidity check
risk guard
position sizing
order execution
```

Hermes가 직접 주문하지 않는다. Hermes는 거래 판단 자료를 만들고, WealthPulse가 risk guard를 거쳐 주문한다.

## 4. Target Pipeline

```text
[1] Universe + Data Refresh
    run_kospi_snapshot.sh
    run_sp500_snapshot.sh
    run_news_refresh.sh
    run_event_refresh.sh

[2] Candidate Sources
    quant_strategy_signal
    technical_momentum_scan
    news_event_trigger
    portfolio_recheck
    manual_watchlist

[3] Market/News Feature Pack
    technical_features
    liquidity_features
    regime_features
    news_items
    event_items
    portfolio_context

[4] Pending Research Target
    research_ops.py pending

[5] Hermes Analyst Team
    Technical Analyst
    News Analyst
    Bull Case Agent
    Bear Case Agent
    Risk Analyst

[6] Hermes Trade Decision Agent
    rating
    action
    confidence
    size_intent_pct
    time_horizon_days
    max_loss_pct
    take_profit_pct

[7] Research Snapshot Ingest
    research_ops.py ingest-bulk

[8] Runtime Consumption
    live_layers.py
    research_scoring.py
    strategy_engine.py

[9] Deterministic Safety + Execution
    technical sanity check
    liquidity check
    risk_guard_service.py
    sizing_service.py
    order_decision_service.py
    execution_service.py

[10] Decision Memory
    decision_memory.jsonl

[11] Outcome Resolver
    realised_return
    benchmark_alpha
    reflection
```

핵심 원칙:

```text
quant strategy는 필수 gate가 아니라 candidate source 중 하나다.
Hermes agent는 quant entry 없이도 buy_watch/buy를 제안할 수 있다.
단, 실제 주문은 technical sanity check, liquidity check, validation, risk guard, sizing clamp를 모두 통과해야 한다.
```

## 5. Research Snapshot v2 Schema

저장 위치:

```text
storage/logs/research_snapshots/latest/
storage/logs/research_snapshots/history/
```

예시:

```json
{
  "provider": "hermes",
  "schema_version": "v2",
  "run_id": "hermes-research-20260429-001",
  "symbol": "005930",
  "market": "KOSPI",
  "bucket_ts": "2026-04-29T09:30:00+09:00",
  "generated_at": "2026-04-29T09:31:00+09:00",
  "research_score": 0.78,
  "confidence": 0.72,
  "time_horizon_days": 10,
  "rating": "overweight",
  "action": "buy_watch",
  "candidate_source": "technical_momentum_scan",
  "summary": "정량 추세는 살아 있고 단기 촉매도 있다.",
  "bull_case": [
    "20일선 위 추세 유지",
    "거래량 증가",
    "업종 수급 개선"
  ],
  "bear_case": [
    "단기 과열",
    "지수 조정 시 동반 하락 가능"
  ],
  "catalysts": [
    "실적 발표",
    "업종 뉴스",
    "외국인 순매수"
  ],
  "risks": [
    "지수 급락",
    "거래량 둔화",
    "환율 변동"
  ],
  "invalidation_trigger": {
    "type": "price_or_signal",
    "price_below": 70500,
    "reason": "20일선 이탈 시 thesis 무효"
  },
  "trade_plan": {
    "entry_style": "staged",
    "size_intent_pct": 8.0,
    "max_loss_pct": 4.5,
    "take_profit_pct": 12.0,
    "review_after_days": 3
  },
  "technical_features": {
    "close_vs_sma20": 1.034,
    "close_vs_sma60": 1.087,
    "rsi14": 63.2,
    "atr14_pct": 2.1,
    "volume_ratio": 1.8,
    "breakout_20d": true
  },
  "news_inputs": [
    {
      "source": "news_provider",
      "published_at": "2026-04-29T08:40:00+09:00",
      "title": "업종 수급 개선 관련 뉴스",
      "url": "https://example.com/news/1"
    }
  ],
  "evidence": [
    {
      "type": "technical",
      "source": "technical_features",
      "summary": "20일선 위 추세와 거래량 증가가 동반됨"
    },
    {
      "type": "news",
      "source": "news_inputs[0]",
      "summary": "업종 수급 개선 뉴스가 단기 촉매로 작용 가능"
    }
  ],
  "data_quality": {
    "has_recent_price": true,
    "has_technical_features": true,
    "has_news": true,
    "has_fundamental": false
  },
  "components": {
    "quant_alignment": 0.8,
    "technical_quality": 0.78,
    "news_quality": 0.65,
    "research_quality": 0.75,
    "risk_reward": 0.7,
    "freshness_score": 1.0
  },
  "warnings": [],
  "tags": ["hermes", "agent_research", "trend_following"],
  "ttl_minutes": 180
}
```

## 6. Rating And Action Contract

### 6.1 Rating

내부 표준 rating:

```text
strong_buy
overweight
hold
underweight
sell
```

의미:

```text
strong_buy   적극 진입 후보
overweight   조건부 진입 또는 비중 확대
hold         관찰
underweight  축소 또는 신규 진입 금지
sell         청산 후보
```

### 6.2 Action

실행 의도:

```text
buy
buy_watch
hold
reduce
sell
block
```

### 6.3 Runtime Mapping

```text
rating strong_buy + action buy
-> technical sanity + liquidity + risk guard 통과 시 주문 가능

rating overweight + action buy_watch
-> 조건 충족 시 소액 또는 분할 진입

rating hold
-> watch_only

rating underweight
-> 신규 진입 차단

rating sell
-> 보유 중이면 exit 후보
```

### 6.4 Agent-Primary Execution Modes

```text
quant_gated_agent
  quant entry가 있어야 주문 가능
  가장 보수적인 모드

agent_primary_quant_assisted
  quant entry는 필수가 아님
  Hermes rating/action이 주 판단
  technical sanity, liquidity, validation, risk guard는 필수
  목표 운영 모드

agent_only_paper
  Hermes 판단과 risk guard만으로 paper/log 검증
  실계좌 주문 금지
```

초기 실계좌 자동거래 목표는 `agent_primary_quant_assisted`다. `agent_only`는 연구/시뮬레이션 전용으로만 사용한다.

## 7. Hermes Cron Design

### 7.1 Pending Target Query

Hermes task 시작 시:

```bash
cd /home/user/wealth-pulse
python3 apps/api/scripts/research_ops.py pending \
  --market KOSPI \
  --market NASDAQ \
  --limit 200 \
  --mode missing_or_stale \
  > /tmp/wp_pending_research.json
```

### 7.2 Hermes Analysis Rules

Hermes는 `/tmp/wp_pending_research.json`을 읽고 각 후보를 분석한다.

요구사항:

```text
1. candidate_source를 먼저 읽어라
2. quant 신호가 있으면 참고하되 필수 gate로 취급하지 마라
3. technical_features를 차트 분석의 근거로 사용해라
4. news_inputs에 없는 뉴스/촉매를 만들지 마라
5. 현재 후보가 왜 올라왔는지 설명해라
6. bull case와 bear case를 분리해라
7. invalidation trigger를 반드시 제시해라
8. rating/action을 schema enum 중 하나로만 선택해라
9. evidence와 data_quality를 반드시 채워라
10. 확신이 낮거나 근거가 부족하면 buy가 아니라 hold 또는 buy_watch로 낮춰라
11. 최종 출력은 JSON만 생성해라
```

### 7.3 Ingest

Hermes 분석 결과 저장:

```bash
python3 apps/api/scripts/research_ops.py ingest-bulk \
  --input /tmp/wp_hermes_research_payload.json
```

## 8. Local Crontab Design

기존 crontab은 당장 유지한다.

단, `run_research_audit.sh`는 고친다.

수정 후:

```bash
#!/usr/bin/env bash
set -euo pipefail

cd /home/user/wealth-pulse

.venv/bin/python apps/api/scripts/research_ops.py status
.venv/bin/python apps/api/scripts/research_ops.py pending \
  --market KOSPI \
  --market NASDAQ \
  --limit 200 \
  --mode missing_or_stale

exec .venv/bin/python apps/api/scripts/hanna_enrich_runner.py \
  --market KOSPI \
  --market NASDAQ \
  --limit 200 \
  --mode missing_or_stale
```

이건 fallback이다. 진짜 agent 분석은 Hermes cron이 담당한다.

## 9. Code Change Scope

### 9.1 `research_store.py`

해야 할 일:

```text
schema_version v2 허용
새 필드 저장 허용
validation에서 rating/action 검사
provider hermes 지원
```

### 9.2 `research_scoring.py`

해야 할 일:

```text
ResearchScoreResult에 새 필드 추가
StoredResearchScorer가 v2 필드를 반환
missing/stale 처리 유지
```

추가 필드:

```text
rating
action
confidence
candidate_source
bull_case
bear_case
catalysts
risks
invalidation_trigger
trade_plan
technical_features
news_inputs
evidence
data_quality
```

### 9.3 `live_layers.py`

해야 할 일:

```text
Layer C에 agent_analysis 추가
Layer E에서 rating/action을 우선 반영
기존 quant-only fallback 유지
```

Layer E 판단 우선순위:

```text
risk blocked
-> blocked

research action sell
-> exit/reduce candidate

research rating strong_buy/overweight + technical sanity + liquidity ok
-> review_for_entry 또는 order_ready

research rating strong_buy/overweight + quant entry 없음 + technical sanity ok
-> agent_primary_watch 또는 small_entry_candidate

research rating hold
-> watch_only

research rating underweight/sell
-> do_not_touch 또는 exit
```

Layer E는 `quant_decision`과 `agent_decision`을 둘 다 남긴다. 초기에는 두 판단을 나란히 기록하고, agent-aware 판단이 quant-only보다 나은지 decision memory에서 검증한다.

### 9.4 `order_decision_service.py`

해야 할 일:

```text
final_action 단순 분기 제거
rating/action 기반 order summary 추가
agent_primary_quant_assisted 모드 추가
technical sanity/liquidity check 결과 반영
size_intent_pct 반영
```

### 9.5 `execution_service.py`

해야 할 일:

```text
주문 직전 candidate.final_action_snapshot.trade_plan 읽기
주문 직전 evidence/data_quality/technical sanity 상태 확인
risk guard가 size_intent_pct를 clamp
decision memory에 주문 후보 기록
```

### 9.6 `decision_memory_service.py`

새 파일:

```text
apps/api/services/decision_memory_service.py
```

역할:

```text
append pending decision
resolve outcome
store reflection
load recent lessons
```

저장 파일:

```text
storage/logs/decision_memory.jsonl
```

## 10. Decision Memory Schema

Pending:

```json
{
  "id": "decision-20260429-KOSPI-005930",
  "created_at": "2026-04-29T09:31:00+09:00",
  "symbol": "005930",
  "market": "KOSPI",
  "strategy_id": "trend_following",
  "rating": "overweight",
  "action": "buy_watch",
  "entry_price": 71500,
  "planned_holding_days": 10,
  "research_score": 0.78,
  "quant_score": 0.67,
  "risk_plan": {
    "max_loss_pct": 4.5,
    "take_profit_pct": 12.0
  },
  "status": "pending",
  "outcome": null,
  "reflection": null
}
```

Resolved:

```json
{
  "status": "resolved",
  "outcome": {
    "raw_return_pct": 6.4,
    "benchmark_return_pct": 2.1,
    "alpha_pct": 4.3,
    "holding_days": 7,
    "exit_reason": "take_profit"
  },
  "reflection": "추세 정렬과 거래량 증가 조합은 유효했다. 다음에는 같은 패턴에서 초기 비중을 조금 높여도 된다."
}
```

## 11. Execution Safety Rules

Hermes 분석은 주문 명령이 아니다.

최종 주문 조건:

```text
1. research rating/action 긍정
2. confidence가 모드별 threshold 이상
3. technical sanity check 통과
4. liquidity check 통과
5. validation gate 통과
6. evidence/data_quality 최소 기준 통과
7. risk guard 통과
8. sizing quantity > 0
9. execution mode 허용
```

`quant entry signal`은 필수 조건이 아니라 confidence 보정과 비교 기준이다. 단, `quant_gated_agent` 모드에서는 quant entry를 필수로 요구한다.

하나라도 실패하면 주문하지 않는다.

Fail-closed 원칙:

```text
Hermes output schema validation 실패 -> ingest 금지
news 근거 없음 -> catalyst 기반 buy 승격 금지
technical_features 누락 -> agent_primary 실계좌 주문 금지
research stale/missing -> 신규 매수 금지 또는 small_entry만 허용
size_intent_pct 과도함 -> risk guard가 clamp
```

## 12. Implementation Plan

### Phase 1. Cron And Ops Recovery

작업:

```text
README.md를 현재 구조 요약과 실행 진입점으로 축소
docs/ 제거
archive/ 제거
legacy cron wrapper 제거
research_ops.py는 현행 Agent/Hermes ingest 경로만 유지
fallback enrich는 fallback-only로 명시
```

완료 기준:

```text
서버에서 run_research_audit.sh 수동 실행 성공
/tmp/wealthpulse_research_audit.log 오류 없음
```

### Phase 2. Research Snapshot v2

작업:

```text
schema 확장
ingest validation 확장
Layer C 반환 확장
UI 깨지지 않게 optional field 처리
```

완료 기준:

```text
research_ops.py ingest-bulk --input sample_v2.json 성공
Layer C에서 rating/action/bull_case 조회 가능
```

### Phase 3. Hermes Agent Contract

작업:

```text
Hermes pending input 포맷 확정
Hermes output JSON schema 확정
Hermes cron task 작성
sample output ingest 테스트
```

완료 기준:

```text
Hermes가 pending 후보 1개 분석
research snapshot v2 저장
```

### Phase 4. Trade Decision Connection

작업:

```text
Layer E가 rating/action 반영
quant_decision과 agent_decision 병렬 기록
agent_primary_quant_assisted 모드 추가
order_decision_service.py 수정
technical sanity/liquidity check 추가
risk guard와 sizing clamp 유지
```

완료 기준:

```text
strong_buy/overweight 후보만 order_ready 가능
hold/underweight는 주문 안 됨
quant entry가 없어도 agent_primary 조건을 만족하면 small_entry_candidate 가능
paper/log에서 quant-only 대비 agent-aware 결과 비교 가능
```

### Phase 5. Decision Memory

작업:

```text
pending decision 저장
outcome resolver 추가
alpha/reflection 저장
Hermes prompt에 recent lessons 주입
```

완료 기준:

```text
실행 후보가 decision_memory.jsonl에 남음
N일 후 outcome resolved 가능
```

### Phase 6. Fallback Cleanup

작업:

```text
hanna_enrich_runner.py를 fallback-only로 명시
Hermes 성공 시 fallback enrich skip
provider status에 hermes 상태 표시
```

완료 기준:

```text
Hermes provider healthy면 deterministic hanna enrich가 덮어쓰지 않음
```

## 13. First Cut

바로 시작할 작업:

```text
1. research snapshot v2 schema 추가
2. candidate_source/technical_features/news_inputs/evidence/data_quality fixture 추가
3. sample Hermes output fixture 추가
4. research_ops.py ingest-bulk schema validation 추가
5. Layer C에서 v2 필드 읽게 수정
6. Layer E에서 quant_decision과 agent_decision 병렬 기록
7. agent_primary_quant_assisted 모드의 paper/log-only 판단 추가
8. legacy cron wrapper는 복구하지 않음
9. README.md는 현재 구조 요약만 유지하고 docs/archive는 제거
```

처음부터 Hermes cron과 실계좌 주문까지 한 번에 붙이지 않는다. 먼저 저장 계약, runtime 소비 경로, paper/log 비교 경로부터 고친다.
