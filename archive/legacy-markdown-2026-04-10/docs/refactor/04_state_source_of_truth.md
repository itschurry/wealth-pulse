# 단계 4. 상태 원본 단일화

## 목표
- 프론트는 `draft` 임시 편집 상태만 로컬에 보관한다.
- 서버가 `saved` 및 `displayed` 상태의 단일 원본이 된다.
- 동일 의미의 설정을 여러 저장소에서 각자 유지하지 않는다.

## 현재 적용 범위
- `apps/web/src/hooks/useValidationSettingsStore.ts`
- `apps/api/services/backtest_params_store.py`
- `apps/web/src/types/domain.ts`

## 상태 원본 규칙
- `draft`
  - 위치: 브라우저 `localStorage`
  - 용도: 사용자가 아직 서버 저장 전 편집 중인 값
  - 저장 키
    - `wp_config_draft_query_v1`
    - `wp_config_draft_settings_v1`
  - 호환 마이그레이션
    - `backtest_query_v3 -> wp_config_draft_query_v1`
    - `console_validation_settings_draft_v1 -> wp_config_draft_settings_v1`
- `saved`
  - 위치: 서버 파일 저장소
  - 원본: `apps/api/services/backtest_params_store.py`
  - 응답 DTO: `PersistedValidationSettingsResponse.state.saved`
- `displayed`
  - 위치: 서버 응답
  - 원본: 현재는 `saved`와 동일 스냅샷을 반환
  - 응답 DTO: `PersistedValidationSettingsResponse.state.displayed`

## 제거/축소한 중복
- 프론트 localStorage의 `savedQuery`, `savedSettings`, `lastSavedAt` 영구 저장 제거
- 서버 스냅샷은 메모리 상태로만 유지하고 재조회 시 서버 응답을 신뢰

## 상태 메타 규칙
- 서버 응답은 다음 공통 메타를 포함한다.
  - `version`
  - `updated_at`
  - `source`
- 각 상태 스냅샷은 다음 필드를 포함한다.
  - `status`
  - `query`
  - `settings`
  - `version`
  - `updated_at`
  - `source`

## 남은 정리 대상
- `BacktestQuery`의 flat legacy 필드와 `portfolio_constraints`/`strategy_params` 중복 제거
- 런타임 JSON 로더와 실행 설정 병합 지점의 `saved/applied` 경계 정리
- `approved`, `applied` 상태 스냅샷 실제 저장소 분리
