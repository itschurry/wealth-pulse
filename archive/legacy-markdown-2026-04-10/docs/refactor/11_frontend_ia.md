# 단계 11. 프론트 IA 재구성

## 목적
- 운영 화면과 실험 화면을 분리한다.
- 자동거래 파이프라인 상태를 첫 화면에서 이해 가능하게 만든다.
- 설정 상태(`draft`, `saved`, `displayed`)를 전용 화면에서 관리한다.

## 상위 메뉴
1. `운영 대시보드`
2. `주문/체결`
3. `전략 운영 상태`
4. `실험실(Lab)`
5. `리서치/AI`
6. `설정`

## 페이지 맵

### 1. 운영 대시보드
- canonical path: `/operations-dashboard`
- 하위 보조 화면:
  - `/operations-dashboard`
  - `/operations-dashboard/scanner`
  - `/operations-dashboard/performance`
- 책임:
  - 현재 applied 전략 상태 노출
  - 오늘 signal 수, allowed/blocked 요약
  - blocked reason 관찰 진입점
  - 데이터/런타임 이상 여부 확인
  - 운영 성과 확인

### 2. 주문/체결
- canonical path: `/orders-execution`
- 책임:
  - 주문 lifecycle 추적
  - 차단 사유와 포지션 현황 확인
  - paper order 상태 점검

### 3. 전략 운영 상태
- canonical path: `/strategy-operations`
- 책임:
  - approved/applied 전략 상태 확인
  - 운영 반영 대상 전략 조회
  - 운영 모드에서 프리셋 생성/삭제 금지

### 4. 실험실(Lab)
- canonical path:
  - `/lab/validation`
  - `/lab/strategies`
  - `/lab/universe`
- 책임:
  - 백테스트
  - 전략 탐색/복제/실험
  - 재검증
  - 유니버스 비교

### 5. 리서치/AI
- canonical path:
  - `/research-ai/brief`
  - `/research-ai/alerts`
  - `/research-ai/watch-decisions`
  - `/research-ai/watchlist`
  - `/research-ai/research`
- 책임:
  - 투자 브리프
  - 리스크 알림
  - 관심 시나리오
  - 관심 종목 및 리서치 스냅샷

### 6. 설정
- canonical path: `/settings`
- 책임:
  - `draft`, `saved`, `displayed` 설정 상태 비교
  - 서버 저장 기준 동기화/저장/초기화
  - 현재 applied 전략과 설정 상태를 같이 확인
  - 실험실 편집 화면으로 이동

## legacy 경로 -> 신규 경로
- `/`, `/home`, `/dashboard`, `/overview` -> `/operations-dashboard`
- `/operations/overview` -> `/operations-dashboard`
- `/operations/scanner` -> `/operations-dashboard/scanner`
- `/operations/performance` -> `/operations-dashboard/performance`
- `/operations/orders`, `/paper` -> `/orders-execution`
- `/operations/strategies`, `/console/strategies` -> `/strategy-operations`
- `/console/scanner`, `/signals` -> `/operations-dashboard/scanner`
- `/console/performance` -> `/operations-dashboard/performance`
- `/console/validation`, `/console/validation-lab`, `/backtest` -> `/lab/validation`
- `/console/universe` -> `/lab/universe`
- `/console/watchlist` -> `/research-ai/watchlist`
- `/console/research` -> `/research-ai/research`
- `/reports`, `/reports/today*`, `/analysis/brief` -> `/research-ai/brief`
- `/reports/alerts`, `/reports/action-board`, `/analysis/alerts` -> `/research-ai/alerts`
- `/reports/watch-decision`, `/analysis/watch-decisions` -> `/research-ai/watch-decisions`
- `/analysis/watchlist` -> `/research-ai/watchlist`
- `/analysis/research` -> `/research-ai/research`

## 운영/실험/분석 분리 규칙
- 운영 대시보드, 주문/체결, 전략 운영 상태에서는 백테스트/탐색/프리셋 생성 UI를 노출하지 않는다.
- 실험실에서만 백테스트, 유니버스 비교, 프리셋 생성/복제를 수행한다.
- 리서치/AI는 참고 자료와 인사이트 조회 전용으로 유지한다.
- 설정은 전역 상태 확인과 서버 저장 기준 관리만 담당한다.

## 우려 사항과 대응

### 1. `App.tsx` 집중도 과다
- 우려:
  - 라우팅, canonical redirect, 메뉴 구성이 한 파일에 집중되어 변경 영향이 크다.
- 대응:
  - 상위 메뉴와 하위 탭을 도메인 기준으로 재편
  - legacy path는 모두 canonical path로 강제 정규화

### 2. 실험 상태와 설정 상태 혼재
- 우려:
  - `BacktestValidationPage`가 실험 UI와 설정 저장 흐름을 함께 다룬다.
- 대응:
  - 설정 전용 화면 `/settings` 추가
  - 실험 편집은 Lab에 두고, saved/displayed 비교와 저장 액션은 설정 화면에서 확인

### 3. 운영 첫 화면 가시성 부족
- 우려:
  - 기존 운영 홈에서 현재 applied 전략과 파이프라인 상태가 구조적으로 분리되어 있었다.
- 대응:
  - 운영 대시보드를 전용 1차 진입점으로 고정
  - scanner/performance는 운영 보조 화면으로 배치

### 4. 숨은 legacy 경로 잔존 위험
- 우려:
  - 기존 `/console/*`, `/analysis/*`, `/operations/*` 북마크가 계속 남아 있을 수 있다.
- 대응:
  - `toRouteState()`에서 전부 신규 canonical path로 리다이렉트

## 완료 기준
- 운영자는 운영 메뉴만으로 주문/차단/전략 반영 상태를 확인할 수 있다.
- 실험 기능은 Lab에만 남는다.
- 설정 상태는 `/settings`에서 `draft`, `saved`, `displayed` 기준으로 분리되어 보인다.
- legacy path 접근 시 신규 canonical path로 강제 이동한다.
