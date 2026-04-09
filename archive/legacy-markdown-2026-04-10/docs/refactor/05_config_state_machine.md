# 단계 5. 설정 상태 전이 모델

## 목표 상태
`draft -> saved -> approved -> applied -> displayed`

## 현재 반영 상태
- `draft`
  - 프론트 편집 상태
  - `localStorage` 캐시 허용
- `saved`
  - 서버에 저장된 기준 설정
  - `PersistedValidationSettingsResponse.state.saved`
- `displayed`
  - 화면이 기준으로 삼는 서버 스냅샷
  - 현재는 `saved`와 동일 값으로 반환

## 아직 분리되지 않은 상태
- `approved`
- `applied`

이 두 상태는 단계 5 후속 작업에서 API와 런타임 저장소를 분리하면서 추가한다.

## DTO 초안
- `ConfigStateSnapshotDto`
  - `status`
  - `query`
  - `settings`
  - `version`
  - `updated_at`
  - `source`
- `ValidationConfigStateDto`
  - `saved`
  - `approved`
  - `applied`
  - `displayed`

## API 원칙
- 조회 API는 상태 스냅샷과 공통 메타를 함께 반환한다.
- 저장 API는 `saved` 상태를 갱신하고 `displayed` 스냅샷도 함께 반환한다.
- `approved`, `applied` 도입 후에는 저장/승인/적용 API를 분리한다.

## 프론트 동작 원칙
- `unsaved` 판단은 `draft` 와 `saved` 비교로만 계산한다.
- 서버 저장값을 화면에 다시 로드할 때는 서버 응답을 기준으로 `saved/displayed`를 갱신한다.
- `loadSavedIntoDraft()` 는 서버 저장값을 사용자의 편집 초안으로 복사한다.

## 다음 구현 순서
1. `approved` 저장소와 승인 API 정의
2. 런타임 `applied` 저장소와 적용 API 정의
3. UI 배지를 `draft/saved/approved/applied/displayed` 기준으로 분리
4. 실행 화면에서 `displayed` 와 `applied` 차이를 노출
