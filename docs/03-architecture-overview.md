# 03. 아키텍처 개요

## 전체 구조

```text
Web(React/Vite)
  -> API(FastAPI)
    -> scanner / validation / quant-ops / runtime / research services
      -> storage/logs, storage/reports
      -> 외부 데이터 소스(FRED, ECOS, DART, KIS, Ollama 등)
```

## 지금 코드에서의 책임 분리

### 1) Scanner
역할:
- 유니버스/전략 기준으로 종목 후보 탐색
- Layer A/B/D/E 결과를 운영 화면에 제공
- 캐시 기반 스캔 결과 제공

대표 파일:
- `apps/api/routes/scanner.py`
- `apps/api/routes/engine.py`
- `apps/web/src/pages/ScannerPage.tsx`

핵심 특징:
- `engine/status`는 캐시된 스캔 결과를 사용하도록 설계돼 있다.
- 장중 폴링 엔드포인트에서 매번 풀스캔하지 않게 막아놨다.

### 2) Runtime
역할:
- paper/live 엔진 선택
- 자동 실행 루프 유지
- 주문/포지션/계좌/사이클 히스토리 기록
- validation gate, optimized params, risk guard 적용

대표 파일:
- `apps/api/services/execution_service.py`
- `apps/api/routes/trading.py`
- `apps/web/src/pages/PaperPortfolioPage.tsx`

핵심 특징:
- 기본은 paper engine
- live 모드도 코드 경로는 있지만 운영 전환은 `mode`로만 제어
- 서버 재시작 시 running/paused를 자동 복구하지 않고 stopped로 안전 복구

### 3) Hanna
역할:
- Layer C research scorer
- 브리프 생성
- summary_lines / warnings / tags / research_score 제공

대표 파일:
- `apps/api/routes/hanna.py`
- `apps/api/routes/research.py`
- `apps/api/services/hanna_brief_service.py`
- `apps/web/src/pages/ScannerPage.tsx`
- `apps/web/src/pages/ReportsPage.tsx`

핵심 특징:
- 구조화된 DTO/브리프 제공 전용
- `legacy_source_retained: False`, `backend_owner: hanna` 등 마이그레이션 메타 포함
- 주문 명령권 없음

## 레이어 관점

Web 코드가 아주 노골적으로 이 구조를 드러낸다.

### Layer A — Universe
- 어떤 종목이 유니버스에 포함됐는지
- inclusion reason
- scan time

### Layer B — Quant
- quant_score
- strategy_id
- quant_tags
- signal_state

### Layer C — Hanna Research
- research_score
- warnings
- tags
- summary
- provider/research 상태

### Layer D — Risk Gate
- allowed / blocked
- reason_codes
- liquidity/spread/position cap 상태

### Layer E — Final Action
- `review_for_entry`
- `watch_only`
- `blocked`
- `do_not_touch`

이 마지막 액션이 운영 의미에서 제일 중요하다.

## API 구조

### 진입점
- `apps/api/api_server.py`
  - `/health`
  - `/api/{full_path:path}` GET/POST 처리

### 라우트 등록표
- `apps/api/server.py`
  - 실제 엔드포인트 목록이 여기 다 있다.
  - 문서 갱신할 때 이 파일을 먼저 봐야 한다.

## 상태 저장 구조

`apps/api/config/settings.py` 기준:

- `STORAGE_DIR = REPO_ROOT / "storage"`
- `REPORTS_DIR = STORAGE_DIR / "reports"`
- `LOGS_DIR = STORAGE_DIR / "logs"`

즉, 현재 시스템의 핵심 persistence는 여기다.

### reports
- 브리프/리포트 산출물

### logs
- validation 설정
- quant policy
- quant state
- paper account state
- 실행 히스토리

## Web 아키텍처

### API 호출 레이어
- `apps/web/src/api/client.ts`
- `apps/web/src/api/domain.ts`

특징:
- envelope 응답 normalize
- GET timeout 20초
- no-store 옵션 사용

### 주요 운영 화면
- `ScannerPage.tsx` — 장중 스캐너
- `BacktestValidationPage.tsx` — 검증 랩
- `ReportsPage.tsx` — 브리프/알림/관심 시나리오
- `PaperPortfolioPage.tsx` — 주문/리스크 관제
- `SettingsPage.tsx` — saved/displayed/draft 상태 관리

## 실행/데이터 흐름 예시

### 스캐너 흐름
```text
전략 레지스트리/유니버스
  -> scanner 결과 생성
  -> top_candidates 저장/조회
  -> engine/status, scanner/status, web ScannerPage 반영
```

### validation 흐름
```text
draft query/settings
  -> /api/validation/backtest
  -> /api/validation/walk-forward
  -> /api/run-optimization
  -> optimized params / quant-ops workflow
```

### 실행 흐름
```text
signal book
  -> Layer D risk gate
  -> Layer E final action
  -> order placement
  -> order_events / execution_events / cycle / account_snapshot 기록
```

### 브리프 흐름
```text
runtime signal book + market context
  -> hanna brief service
  -> /api/hanna/brief 또는 /api/reports/explain
  -> ReportsPage 반영
```

## 디버깅할 때 구조적으로 봐야 할 질문

### 질문 1
문제가 스캐너 문제인가, 실행 문제인가, 리서치 문제인가?

### 질문 2
API가 비었나, 저장 파일이 비었나, 프론트 렌더링이 꼬였나?

### 질문 3
최종 차단은 Layer D인지, Layer E인지, validation gate인지?

## 지금 구조의 현실적인 특징

- DB 없는 파일 기반 운영 저장소
- polling이 많은 화면은 cache-first 설계
- Hanna를 분리해 주문 경로에서 권한 축소
- runtime이 가장 많은 운영 truth를 쥠
- Web은 "제어 UI + 해석 UI" 성격이 강함
