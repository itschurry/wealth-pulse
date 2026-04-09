# NASDAQ Layer C / Validation Follow-up

작성일: 2026-04-04

## 오늘 정리된 것

### 1. Hanna / Research / Layer C
- Hanna 관련 cron 수동 실행으로 snapshot / enrich / audit 경로를 모두 점검함.
- NASDAQ research snapshot이 생성되지 않던 문제를 추적함.
- 원인은 `hanna_enrich_runner.py` → `research_store.py` ingest 경로 정합 문제였음.
- 최종적으로 NASDAQ research snapshot ingest 성공 확인:
  - `accepted = 10`
  - `received_valid = 10`
  - `rejected = 0`
- 생성된 최신 NASDAQ snapshot 예시:
  - `AKAM`
  - `ADM`
  - `AEE`
  - `AFL`
  - `ACGL`
  - `COST`
  - `CSX`
  - `INTC`
  - `LIN`
  - `NFLX`

### 2. 장중 스캐너 Layer C 반영
- 처음에는 NASDAQ Layer C가 안 보였지만, 원인은 미구현이 아니었음.
- 실제 문제는:
  1. snapshot은 생성되었지만
  2. scanner cache row가 stale 상태였고
  3. refresh 이후 새 scanner row가 snapshot 이전 상태를 계속 보고 있었음
- `us_momentum_v1` 전략 row를 새 snapshot 기준으로 다시 스캔한 뒤,
  NASDAQ 후보(`AKAM`)에서 아래 값 확인:
  - `research_status = healthy`
  - `research_unavailable = false`
  - `research_score = 0.94`
- 결론: NASDAQ도 장중 스캐너에서 Layer C 정상 반영 확인 완료.

### 3. Validation / Revalidate 병목 구조 수정
- 기존 구조는:
  - `revalidate_optimizer_candidate()`
  - `run_validation_diagnostics()`
  - `run_walk_forward_validation()`
  - full backtest rerun
  까지 강결합되어 있어 revalidate가 지나치게 무거웠음.
- 수정 후 구조:
  - `run_validation_diagnostics(mode="light")`
  - revalidate는 light diagnostics만 사용
  - full walk-forward / local research는 별도 full 경로로 분리
- 목적:
  - 후보 재검증은 가볍게
  - full validation은 필요할 때만 수행

### 4. Guardrail 정책 보정
- NASDAQ 후보가 `reliability = medium`인데도,
  다른 지표가 충분히 좋아서 near miss가 0개면 오히려 `hold`로 떨어지는 문제가 있었음.
- 수정:
  - `medium`
  - `near_miss_metrics == 0`
  - 수익 / 손익비 / 낙폭 / expected shortfall 조건이 충분히 양호
  이면 `limited_adopt`로 승격 가능하도록 guardrail 분기 보정.

### 5. 백테스트 유니버스 분리
- 운영용 snapshot universe와 백테스트용 universe를 분리함.
- 백테스트는 고정 universe 사용:
  - `apps/api/config/universes/kospi100.json`
  - `apps/api/config/universes/sp100.json`
- `backtest_universe.py`는 이제 snapshot 대신 고정 json만 읽음.
- KOSPI는 시총 상위 100 기준,
  미국은 SP100 고정 티커 기반으로 관리.

### 6. JSON 파싱 병목 개선
- 공통 JSON 유틸 추가:
  - `apps/api/services/json_utils.py`
- 적용:
  - optional `orjson`
  - file mtime/size 기반 cache
- 적용 대상:
  - `universe_builder.py`
  - `optimized_params_store.py`
  - `paper_runtime_store.py`
  - `quant_ops_service.py`
  - `research_store.py`
- 추가로 universe snapshot은 `latest.summary.json` 분리 도입.

## 현재 상태

### 확인 완료
- NASDAQ 전략 registry 등록 완료
- NASDAQ research snapshot ingest 성공
- NASDAQ scanner cache 생성 확인
- NASDAQ Layer C 정상 반영 확인
- validation revalidate 병목 구조 분리 완료
- 백테스트 고정 universe 분리 완료

### 아직 남은 것
1. **`test.py` 정리**
   - 임시 디버그 파일이면 제거 필요
   - 유지할 거면 역할을 명확히 해야 함

2. **`strategy_candidates` materialization 정리**
   - optimizer 결과와 quant workflow 기대 형식이 아직 완전히 예쁘게 맞는 상태는 아님
   - `optimized_params.json` 기반 search artifact와 workflow handoff 포맷 정리 필요

3. **saved_candidate / runtime_apply 정합 재점검**
   - NASDAQ Layer C는 붙었지만,
     quant workflow 기준 `saved_candidate` / `runtime_apply`가 새 후보 기준으로 완전히 정합한지 다시 점검 필요

4. **stale scanner refresh 경로 개선**
   - 현재는 강제 refresh/재스캔으로 해결 가능
   - 향후 `scanner/status?refresh=1`가 stale cache를 더 확실히 갈아끼우게 개선 여지 있음

5. **남은 테스트 1건 라벨 차이**
   - `플랫폼` vs `Information Technology`
   - 구조 수정과 무관한 라벨/기대값 차이
   - 나중에 테스트 기대값 또는 라벨 normalize 정리 필요

## 오늘 들어간 커밋
- `f2c2160` feat: 한나 크론 및 검증 흐름 정리
- `4c8087b` feat: 백테스트 유니버스 및 JSON 파싱 병목 개선
- `c919360` refactor: 검증 워크플로우와 백테스트 유니버스 분리
- `d949604` fix: 나스닥 레이어C 및 리서치 인제스트 정합화

## 참고 메모
- NASDAQ Layer C가 안 보인다고 해서 미구현으로 단정하면 안 됨.
- 실제로는 아래 단계 중 어디서 끊기는지 봐야 함:
  1. strategy registry
  2. strategy scan cache
  3. research snapshot latest
  4. scanner row refresh
- 이번 케이스는 결국 research ingest + stale scanner row 문제가 겹쳐 있었음.
