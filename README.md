# daily-market-brief

단순 일일 시장 브리프 앱이 아니라, **리서치 → 검증 → paper/live 실행 → observability** 를 한 루프에 묶는 investing app입니다.

핵심 제품 프레임은 아래 4단계입니다.

1. **Research**
   - 매크로/시장/뉴스/테마 데이터를 모아서 당일 투자 가설과 후보를 정리함
2. **Validation**
   - 퀀트 백테스트 / walk-forward / 최적화 / 재검증으로 실행 가능한 전략만 남김
3. **Execution**
   - paper engine에서 후보를 실제 실행 흐름으로 태우고, 이후 live 전환 준비 상태를 확인함
4. **Observability**
   - 엔진 상태, 주문/사이클/계좌 로그, risk guard, validation gate를 운영 관점에서 추적함

즉, 이 프로젝트는 **브리프 생성기 + 추천 뷰어**가 아니라, 투자 의사결정과 실행 준비를 연결하는 운영용 제품에 가깝습니다.

핵심은 전략 모드가 **둘**이라는 점입니다.

1. **퀀트 트레이딩 모드**
   - 백테스트 / walk-forward / 최적화로 전략을 검증함
2. **AI·테마·뉴스 추천 모드**
   - 오늘의 픽, 추천 종목, 뉴스/테마 기반 브리핑을 읽고 운용 판단에 반영함

이 둘은 **교집합이 아니라 합집합** 기준으로 읽어야 합니다.
즉, downstream 실행 후보는 둘 다 동시에 맞아야만 생기는 구조가 아니고, `today_picks` 우선 / `recommendations` fallback 흐름을 포함한 combined candidate flow로 동작합니다.

## 주요 기능

- 매크로/시장 컨텍스트 기반 투자 브리프 생성
- AI·테마·뉴스 리서치 후보 / 오늘의 픽 조회
- 퀀트 백테스트 / walk-forward / 최적화 / 재검증 워크플로우 운영
- paper execution 엔진 운용 및 live 전환 전 실행 준비 상태 점검
- 주문/사이클/계좌/리스크 가드/validation gate 관측
- 전일 대비 리포트 비교 및 설명 가능한 리포트 API 제공
- 웹 콘솔 기반 투자 운영 상태 확인
- 텔레그램 알림 연동

## Quant Ops 워크플로우

이제 퀀트 운영 흐름을 아래처럼 명시적으로 따라가도록 정리했어.

1. **Baseline** — 저장된 설정으로 백테스트 실행
2. **Diagnosis** — 차단 요인, tail risk, exit weakness 진단
3. **Candidate Search** — optimizer 결과를 탐색 후보로만 취급
4. **Re-validation** — optimizer global overlay를 현재 baseline 기준으로 다시 검증
5. **Per-Symbol Approval** — 종목 후보를 재검증하고 운영자가 승인/보류/거절 상태를 명시
6. **Save** — 재검증 통과 + 승인된 후보만 저장
7. **Runtime Apply** — 저장된 후보만 paper/runtime 설정으로 반영

중요한 분리:

- `optimized_params.json` = **탐색 결과(search)**
- `runtime_optimized_params.json` = **운영 반영(runtime)**
- `storage/logs/quant_ops_state.json` = **후보 / 저장 / 반영 상태 추적**
- `storage/logs/backtest_validation_settings.json` = **공유 baseline 저장값(브라우저/기기 공통)**
- 종목별로도 `latest/approval/saved/runtime-applied` 상태를 별도로 추적

즉, optimizer 결과를 바로 런타임에 쓰지 않고, 중간에 재검증/저장 가드를 하나 더 둔다.
종목 후보도 승인/저장 가드를 통과한 것만 runtime `per_symbol` overlay에 포함된다.

## 저장소 구조

```text
.
├── apps/
│   ├── api/        # FastAPI backend, research pipeline, validation, execution engine
│   └── web/        # React/Vite investing console UI
├── docs/           # 제품/운영 문서, 사용 매뉴얼
├── storage/
│   ├── reports/    # 투자 브리프 결과물, SQLite 캐시
│   └── logs/       # 엔진 상태/주문/계좌/사이클/observability 로그
├── docker-compose.yml
└── requirements.txt
```

## 빠른 시작

### 로컬 개발

```bash
cd ~/wealth-pulse

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp apps/api/.env.example apps/api/.env
cd apps/web && npm install && cd ../..

cd apps/api && python3 api_server.py
# 새 터미널
cd ~/wealth-pulse/apps/web && npm run dev
```

### Docker 실행

```bash
cd ~/wealth-pulse
cp apps/api/.env.example apps/api/.env
# .env 수정

docker compose up -d --build
```

## 기본 접속 주소

- API: `http://127.0.0.1:8001`
- Web Dev: `http://127.0.0.1:5173`
- Web Prod: `http://127.0.0.1:8081`
- Health: `http://127.0.0.1:8001/health`

## 자주 쓰는 명령

### 원샷 리포트 생성

```bash
cd apps/api
python3 run_once.py
```

### 스케줄러 실행

```bash
cd apps/api
python3 scheduler.py
```

### 모의투자 엔진 상태 조회

```bash
curl http://127.0.0.1:8001/api/paper/engine/status
```

### 모의투자 엔진 시작

```bash
curl -X POST http://127.0.0.1:8001/api/paper/engine/start \
  -H "Content-Type: application/json" \
  -d '{"markets":["KOSPI","NASDAQ"],"interval_seconds":300}'
```

## 문서

- 상세 사용 매뉴얼: [`docs/usage.md`](docs/usage.md)
- API 문서: [`docs/api.md`](docs/api.md)
- 웹 UI 사용 매뉴얼: [`docs/ui-manual.md`](docs/ui-manual.md)
- 사용 매뉴얼 내 포함: 기능 소개 / 실제 스크린샷 / 아키텍처 다이어그램 / 리서치→검증→실행 흐름
- 최근 신뢰도 기준선 문서: [`docs/quant-reliability-baseline-2026-03-31.md`](docs/quant-reliability-baseline-2026-03-31.md)

## 환경 변수 핵심

백엔드 `.env` 예시:

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

Ollama 사용 시:

```bash
LLM_PROVIDER=ollama
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=nemotron-3-super
```

정확한 설정 항목과 운영 절차는 `docs/usage.md` 참고.

## 테스트 / 빌드

### 백엔드 테스트

```bash
cd apps/api
python -m unittest discover -s tests
```

### 프런트엔드 빌드

```bash
cd apps/web
npm run build
```

### Docker 빌드

```bash
docker compose up -d --build
```

## 라이선스

`LICENSE` 참고.
