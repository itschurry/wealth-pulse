# WealthPulse 트러블슈팅

이 문서는 운영 중 자주 만나는 문제를 정리한다.

---

## 1. 장중 스캐너에서 모든 종목이 `research_unavailable`

먼저 기억할 것:
이 증상은 프론트 버그일 수도 있지만, 실제로는 **후보 종목 research snapshot 부재**인 경우가 많다.

### 가능한 원인
1. 실제로 research snapshot이 없음
2. market key mismatch (`KR` vs `KOSPI`)
3. scanner/status와 signals API의 데이터 원본 차이
4. stale cache 또는 오래된 컨테이너 코드

### 먼저 확인할 것
- `운영 콘솔 -> 리서치 스냅샷` 화면
- `/api/research/status`
- `/api/research/snapshots/latest?symbol=...&market=...`
- `/api/scanner/status`
- `/api/signals/{code}`

### 해석
- `research_status = missing`
- `research_unavailable = true`
- `research_score = null`
이면 보통 해당 종목 snapshot이 없는 상태다.

### 해결 방향
- scanner 후보 종목 기준 bulk ingest 수행
- canonical market 사용 (`KOSPI`)
- UI가 어떤 API를 보는지 확인

---

## 2. scanner/status가 느리거나 타임아웃

### 원인
refresh 요청마다 live scan 전체를 다시 돌리면 느려진다.

### 해결 방향
- 캐시 우선 응답
- background refresh
- stale cache 허용 범위 운영

### 기대 동작
- `refresh=1` 요청 시 즉시 캐시 반환
- 뒤에서 refresh 수행

---

## 3. backend에선 Layer C가 보이는데 UI에선 안 보임

이 경우 먼저 화면이 무엇을 그리고 있는지 확인해야 한다.
장중 스캐너는 `signals`가 아니라 `scanner/status`를 그릴 수 있다.

### 원인 후보
1. UI가 `signals/rank` 가 아니라 `scanner/status` 를 봄
2. UI가 `layer_c` 대신 flattened field만 읽음
3. 캐시가 예전 응답을 유지함

### 확인 포인트
- 프론트 fetch 함수가 어떤 endpoint를 쓰는지
- 장중 스캐너 화면이 `snapshot.scanner` 인지 `snapshot.signals` 인지
- `candidate.layer_c` 필드를 실제로 렌더링하는지

---

## 4. signals/rank 또는 signals/{code} 에러

### 예시
- `_now_iso is not defined`

### 의미
보통 최근 수정에서 import 또는 helper 참조가 빠진 상태다.

### 해결
- 에러 난 서비스 파일에서 import 확인
- 컨테이너 rebuild 후 force recreate

---

## 5. 코드 고쳤는데 UI가 그대로임

frontend build 완료와 backend 컨테이너 재기동은 같은 뜻이 아니다.
둘 다 확인해야 한다.

### 원인 후보
1. 컨테이너가 재생성되지 않음
2. 엔진/프로세스가 옛 코드 메모리 상태 유지
3. 브라우저가 예전 응답을 표시 중

### 해결
- `docker compose up -d --build --force-recreate api web`
- 필요 시 엔진 stop/start
- UI 새로고침

---

## 6. Hanna가 붙었는데 final_action이 `do_not_touch`

이건 정상일 수 있다.

의미:
- Layer C는 정상 동작
- 하지만 Layer B quant가 약하거나 Layer D risk가 보수적으로 막음
- 최종 액션은 Layer E 기준

즉 Hanna 미동작으로 오해하면 안 된다.

---

## 7. scanner 후보가 있는데 research가 없음

이건 현재 구조상 정상적으로 발생할 수 있다.
scanner 후보와 Hanna ingest는 다른 파이프라인이기 때문이다.

### 의미
scanner와 Hanna는 다른 파이프라인이다.
scanner 후보가 먼저 생기고, 그다음 Hanna snapshot이 붙을 수 있다.

### 해결
- current scanner candidates 추출
- 해당 심볼 기준 OpenClaw research bulk ingest
- 이후 `운영 콘솔 -> 리서치 스냅샷` 또는 장중 스캐너 상세에서 Layer C 반영 확인

---

## 8. 화면별 빠른 확인 순서

### UI 기준
1. `내 대시보드`
2. `운영 콘솔 -> 전략 검증 랩`
3. `운영 콘솔 -> 장중 스캐너`
4. `운영 콘솔 -> 리서치 스냅샷`
5. `리서치 리포트 -> 투자 브리프`

### API 기준

문제가 생기면 아래 순서로 본다.

1. `/health`
2. `/api/research/status`
3. `/api/scanner/status`
4. `/api/signals/rank`
5. `/api/signals/{code}`
6. research snapshot latest
7. engine status

이 순서면 대체로 어디가 꼬였는지 빠르게 좁혀진다.

---

## 9. 지금 문서 기준으로 없는 것으로 봐야 할 것

아래는 현재 매뉴얼 기준 핵심 운영 플로우가 아니다.
- 오래된 구현 메모
- 중간 단계 migration 문서
- 과거 임시 검증 문서

운영자는 새 매뉴얼 3종과 `api.md`만 기준으로 본다.
