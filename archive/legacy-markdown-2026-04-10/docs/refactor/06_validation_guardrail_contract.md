# 단계 6. 검증/가드레일 표준화

## 목표
- validation 결과와 guardrail 결과를 같은 구조 규칙으로 정리한다.
- UI, API, 로그가 동일한 `reason_code`를 사용한다.

## 표준 판정값
- `pass`
- `fail`
- `revalidate_required`
- `stale`
- `data_missing`
- `risk_blocked`

## DTO 규칙

### ValidationResultDto
- `status`
- `reason_code`
- `message`
- `details`
- `trace_id`

### GuardrailResultDto
- `status`
- `reason_code`
- `message`
- `details`
- `trace_id`

### ValidationGuardrailSummaryDto
- `validation_status`
- `guardrail_status`
- `final_status`
- `reason_code`
- `message`
- `details`
- `trace_id`

## reason_code 규칙
- 문자열 설명 대신 구조화된 코드 사용
- 프론트는 `reason_code`만 기준으로 배지/경고/요약을 렌더링
- message는 보조 설명이며 의미 원본이 아니다

## 현재 반영 상태
- 서버:
  - `apps/api/services/live_risk_engine.py`
  - `apps/api/services/live_layers.py`
  - `apps/api/services/execution_service.py`
  - `apps/api/services/operations_report_service.py`
- 프론트:
  - `apps/web/src/constants/uiText.ts`
  - `apps/web/src/adapters/consoleViewAdapter.ts`
  - `apps/web/src/pages/ScannerPage.tsx`
  - `apps/web/src/pages/PaperPortfolioPage.tsx`

## 남은 정리 대상
- `OK`, `FALLBACK_BLOCKED`, 대문자 reason code와 소문자 reason code 혼재 정리
- validation 전용 fail 표현과 order block 표현의 표준 축 정렬
- API 응답별 `reason_codes`, `risk_reason_code`, `reason_code` 다중 필드의 역할 축소
