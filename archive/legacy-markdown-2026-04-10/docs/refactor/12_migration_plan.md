# 단계 12. 마이그레이션 실행 및 구구조 제거

## 목적
- 신규 IA와 신규 localStorage 구조로 안전하게 전환한다.
- 구경로와 구저장소를 제거한다.
- import 시점 부팅 의존성을 줄인다.

## 적용 순서
1. 앱 부팅 시 legacy localStorage 키를 신규 키로 마이그레이션한다.
2. 신규 IA canonical path를 기준으로 라우팅을 강제한다.
3. 설정 상태를 `/settings`에서 분리 노출한다.
4. 구키 제거와 legacy read 경로 제거를 완료한다.
5. 타입 검증과 주요 화면 smoke 확인을 수행한다.

## feature flag
- 이름: `VITE_ENABLE_REFACTOR_BUNDLE_D_NAVIGATION`
- 기본값: 활성
- 목적:
  - 신규 IA rollout 식별
  - 배포 환경에서 묶음 D 적용 여부 확인

## localStorage 전환표
- `backtest_query_v3` -> `wp_config_draft_query_v1`
- `console_validation_settings_draft_v1` -> `wp_config_draft_settings_v1`
- `console_strategy_validation_transfer_v1` -> `wp_lab_validation_transfer_v2`

## 전환 규칙
- 앱 부팅 시 legacy 키가 있으면 신규 키로 복사한다.
- 신규 키 복사 후 legacy 키는 즉시 삭제한다.
- 이후 코드에서는 신규 키만 읽는다.

## 제거/정리 대상

### 제거 완료
- `useBacktest`의 legacy draft query key 직접 읽기 제거
- `useValidationSettingsStore`의 legacy settings key 직접 읽기 제거
- `useValidationSettingsStore`의 import 시점 localStorage hydrate 제거
- 전략 프리셋 전달용 legacy transfer key 제거
- 구 IA 경로를 신규 canonical path로 정규화

### 남겨둔 호환 처리
- legacy URL path redirect는 북마크 호환을 위해 유지

## import 시점 의존성 정리
- 변경 전:
  - `useValidationSettingsStore`가 모듈 import 시점에 localStorage를 hydrate
- 변경 후:
  - 첫 `getSnapshot()` 호출 시 lazy hydrate

## 회귀 확인 체크리스트

### 프론트
- [x] `npx tsc --noEmit`
- [ ] `npm run build`
- [ ] `npm run lint`
- [ ] `/operations-dashboard` 로드
- [ ] `/orders-execution` 로드
- [ ] `/strategy-operations` 로드
- [ ] `/lab/validation` 로드
- [ ] `/research-ai/brief` 로드
- [ ] `/settings` 로드

### 백엔드/연동
- [ ] 서버 부팅
- [ ] signal 생성
- [ ] validation/guardrail 판정
- [ ] order decision
- [ ] paper order lifecycle

## 현재 검증 상태
- `npx tsc --noEmit` 통과
- `npm run build` 실패
  - 원인: `vite` 실행기 설치 상태 문제로 `node_modules/dist/node/cli.js`를 찾지 못함
- `npm run lint` 실패
  - 원인: `eslint` 실행기 설치 상태 문제로 `../package.json`을 찾지 못함

## 리스크와 후속 조치

### 1. 설정 편집 UI의 완전 분리 미완
- 현재 `BacktestValidationPage`는 실험 편집 UI를 계속 가진다.
- `/settings`는 저장 기준 관리와 상태 비교에 집중한다.
- 후속으로 설정 편집 입력 자체를 `/settings`로 옮길지 결정 필요.

### 2. 운영 대시보드 집계는 기존 DTO 조합 기반
- applied 전략, signal 요약, runtime 이상 여부는 기존 snapshot 조합으로 표시한다.
- 서버 DTO가 강화되면 운영 대시보드 집계 전용 DTO로 교체 권장.

### 3. legacy redirect 유지
- path 호환을 위해 redirect는 남겨두었다.
- 외부 링크 정리가 끝나면 redirect 목록 축소 가능.

## 삭제 목록 체크
- [x] legacy localStorage key direct read 제거
- [x] legacy transfer key direct read/remove 제거
- [x] import 시점 localStorage hydrate 제거
- [x] 신규 canonical navigation 적용
- [ ] legacy path redirect 축소
- [ ] Vite/ESLint 실행기 상태 복구 후 build/lint 재검증
