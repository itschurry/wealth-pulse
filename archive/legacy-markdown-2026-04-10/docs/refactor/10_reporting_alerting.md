# 단계 10. 리포트/알림 재설계

## 목표
- 운영자가 로그를 뒤지지 않고도 signal, blocked, filled, failed, data health 를 바로 본다.

## 운영 리포트 DTO
- `generated_at`
- `report.today_signal_count`
- `report.blocked_count`
- `report.blocked_reason_counts`
- `report.execution_counts`
- `report.execution_event_counts`
- `report.strategy_performance`
- `report.data_health`
- `alerts[]`

## 알림 severity
- `info`
- `warning`
- `critical`

## 1차 API
- `/api/reports/operations`
- `/api/performance/summary`
  - `live.operations_report`
  - `live.alerts`

## 집계 원본
- signal snapshot
- execution lifecycle event

## 1차 알림 규칙
- `stale_signal_data`
- `data_missing`
- `execution_failed`
- `operations_normal`

## 후속 작업
- 전략별 손익과 blocked 이유를 동일 trace_id 축으로 연결
- UI 에서 운영 알림 센터를 별도 섹션으로 노출
- live/paper 공통 alert policy 도입
