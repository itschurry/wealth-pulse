# 단계 8. API 계약 재정의

## 목표
- 프론트와 백엔드가 같은 응답 의미를 보게 한다.
- snake_case 는 서버 내부, camelCase 는 프론트 내부로 분리한다.
- 변환 지점은 프론트 API client / adapter 1곳으로 제한한다.

## 1차 적용 범위
- `signals`
- `validation`
- `quant_ops`
- `paper trading`

`runtime config` 는 현재 별도 단일 계약이 없는 상태라 1차에서는 위 네 도메인에 포함된 설정 API부터 정리한다.

## 서버 응답 규약

### 성공
```json
{
  "data": {},
  "meta": {
    "version": "2026-04-bundle-c1",
    "updated_at": "2026-04-06T00:00:00Z",
    "source": "signals_rank",
    "trace_id": "uuid"
  }
}
```

### 실패
```json
{
  "error": {
    "error_code": "http_409",
    "message": "candidate conflict",
    "details": {}
  },
  "meta": {
    "version": "2026-04-bundle-c1",
    "updated_at": "2026-04-06T00:00:00Z",
    "source": "quant_ops_save_candidate",
    "trace_id": "uuid"
  }
}
```

## 적용 원칙
- 기존 라우트 핸들러는 당장 전면 수정하지 않는다.
- `api_server` 에서 우선 대상 경로만 선택적으로 envelope 를 씌운다.
- 기존 payload 안의 `trace_id`, `version`, `updated_at`, `source` 가 있으면 최대한 재사용한다.
- 기존 프론트 화면은 envelope 를 직접 알지 않게 하고 `apps/web/src/api/client.ts` 에서 자동 언랩한다.

## 프론트 adapter 원칙
- `getJSON`:
  성공 envelope 는 `data` 만 반환
  실패 envelope 는 레거시 화면 호환을 위해 `ok: false`, `error`, `message`, `error_code` 형태로 평탄화
- `postJSON`:
  반환 구조는 유지하되 `data` 내부를 언랩
  실패 envelope 는 `response.ok = false` 와 함께 평탄화된 `data` 를 제공

## 1차 완료 조건
- `signals`, `validation`, `quant_ops`, `paper` 관련 엔드포인트가 공통 `meta` 필드를 가진다.
- 프론트 각 화면이 `response.data.data` 나 직접 shape 봉합 코드를 만들지 않는다.
- 오류 응답에서 최소 `error_code`, `message`, `details`, `trace_id` 를 확보한다.

## 후속 작업
- route/service 단에서 DTO 를 명시적으로 반환하도록 전환
- snake_case -> camelCase adapter 를 도메인별 파일로 분리
- `runtime config` 전용 DTO 추가
