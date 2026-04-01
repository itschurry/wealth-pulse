# daily-market-brief 사용 매뉴얼

이 문서는 `daily-market-brief` 앱의 상세 사용 방법을 정리한 운영자용 매뉴얼입니다.

이 앱은 단순 브리프/추천 뷰어가 아니라, **리서치 → 검증 → paper/live 실행 → observability** 를 연결하는 investing workflow 도구로 읽는 편이 맞습니다.

---

## 1. 앱 소개

`daily-market-brief` 는 아래 기능을 한 번에 다루는 투자 리서치/운영 앱입니다.

먼저 제품을 4개 레이어로 보면 구조가 훨씬 명확합니다.

- **Research**: 시장 브리프, 뉴스/테마, today picks, recommendations
- **Validation**: 백테스트, walk-forward, 최적화, 재검증, save/apply
- **Execution**: paper 계좌, execution engine, runtime apply, live 전환 준비
- **Observability**: 엔진 상태, 주문/사이클/계좌 로그, risk guard, validation gate, 알림 채널

운영자가 먼저 잡아야 할 개념은 **전략 모드가 둘**이라는 점입니다.

- **퀀트 트레이딩 모드**: 백테스트 / walk-forward / 최적화로 전략을 검증하고 validation gate를 관리함
- **AI·테마·뉴스 추천 모드**: 추천 종목 / 오늘의 픽 / 뉴스·테마 브리핑을 읽고 당일 운용 판단에 반영함

둘은 **교집합(intersection)** 이 아니라 **합집합(union)** 으로 읽어야 합니다.
즉, downstream 실행 후보는 두 모드가 동시에 같은 종목을 찍어야만 생기는 구조가 아니고, `today_picks` 우선 / `recommendations` fallback을 포함한 combined candidate flow를 사용합니다.

앱이 제공하는 기능은 아래와 같습니다.

- 투자 브리프 생성과 리서치 후보 정리
- AI·테마·뉴스 추천 종목 / 오늘의 픽 제공
- 퀀트 백테스트 / walk-forward / 최적화 / 재검증 결과 조회
- 전일 대비 리포트 비교 및 설명 가능한 리포트 API 제공
- KOSPI / NASDAQ 대상 paper execution 엔진 운영
- 웹 콘솔 기반 실행 준비 상태와 observability 확인
- 텔레그램 알림 연동

구성 요소는 크게 2개입니다.

- `apps/api`: FastAPI 기반 백엔드, 리서치 파이프라인, 전략 검증, execution 엔진
- `apps/web`: React/Vite 기반 투자 콘솔

---

## 2. 주요 기능

### 2-1. 투자 브리프/리서치

- 매크로 데이터와 시장 컨텍스트를 기반으로 투자 브리프 생성
- 분석 리포트, 추천 종목, 오늘의 픽, 실행 후보 근거 조회
- 날짜별 리포트 이력 비교
- 설명 payload 기반 리포트 API 제공

### 2-2. 퀀트 검증

- baseline → diagnosis → candidate search → re-validation → save → runtime apply 흐름 관리
- 백테스트 / walk-forward / 최적화 결과 조회
- 전략 scorecard, 신뢰도, tail risk 정보 확인
- validation gate와 optimized params 상태, 저장 후보, runtime apply 상태 확인

### 2-2-1. Quant Ops 운영 규칙

퀀트 검증 화면은 이제 단순 도구 모음이 아니라 운영 플로우를 따라간다.

- optimizer 결과는 **탐색 후보**로만 표시
- 재검증(candidate re-validation) 전에는 저장 버튼이 열리지 않음
- 저장 전 후보와 runtime 반영 상태를 분리 표시
- runtime apply는 저장된 후보만 가능
- paper engine은 search 결과가 아니라 **runtime 적용본**을 우선 사용

### 2-3. AI·테마·뉴스 추천

- 추천 종목 / 오늘의 픽 / 뉴스·테마 브리핑 확인
- 추천 기반 후보와 downstream 실행 판단 근거 확인
- quant 검증과 별도로 읽되, 운영 단계에서는 합집합 후보 흐름으로 해석

### 2-4. Paper execution 엔진

- KOSPI / NASDAQ 대상 paper trading 엔진 구동
- 시작 / 일시정지 / 재개 / 중지 API 제공
- 주문/계좌/사이클 로그 확인
- 알림 실패 시에도 엔진 루프는 계속 진행
- live 전환 전 실행 흐름을 검증하는 운영용 환경으로 사용

### 2-5. 투자 운영 콘솔

- 웹 콘솔에서 시스템 상태, 리서치 브리프, 실행 후보, 엔진 상태 확인
- API 결과를 운영자 관점에서 빠르게 점검
- 로컬 개발과 Docker 배포 모두 지원

---

## 3. 스크린샷

아래 이미지는 로컬 실행 환경에서 실제 렌더링한 화면 캡처입니다.
문서 설명용으로 대표 화면 3장을 넣었습니다.

### 3-1. 개요 대시보드

![개요 대시보드](./assets/screenshots/overview.png)

- 콘솔 진입 후 시스템 개요, 엔진 요약, 리스크 가드 상태를 보는 화면
- 운영 상태를 한 장에서 빠르게 점검할 때 쓰기 좋음

### 3-2. 투자 브리프 화면

![투자 브리프 화면](./assets/screenshots/report.png)

- 오늘 결론, 실행 액션, 금지/회피 포인트, 참고 근거를 읽는 화면
- 아침 투자 브리프나 운영 전 점검용 화면으로 적합

### 3-3. Paper 실행 운영 화면

![Paper 실행 운영 화면](./assets/screenshots/paper.png)

- 엔진 시작/정지, 위험 상태, 현금/자산 상태, 당일 주문/체결 결과를 보는 화면
- 운영 제어와 상태 점검을 같이 처리하는 핵심 화면

> 참고
>
> - 실제 PNG 캡처는 `docs/assets/screenshots/` 아래에 저장됨
> - 기존 SVG 플레이스홀더는 문서 목업/대체 이미지 용도로 유지함

---

## 4. 아키텍처

### 4-1. 전체 구조 그림

![아키텍처 개요](./assets/architecture-overview.svg)

### 4-2. 아키텍처 설명

핵심 흐름은 단순해.

1. 사용자가 웹 콘솔(`apps/web`) 또는 직접 API를 호출
2. 백엔드(`apps/api`)가 quant 검증, AI 추천 브리프 생성, 엔진 제어를 수행
3. 결과는 `storage/reports`, `storage/logs` 에 저장
4. 필요 시 OpenAI/Ollama, FRED/ECOS/DART, KIS 같은 외부 소스를 사용
5. 텔레그램/이메일로 운영 알림 발송

### 4-3. 런타임 관점 정리

- **web**: React + Vite UI, `/api` 프록시
- **api**: FastAPI 서버, quant 검증 + AI 추천/브리프 + 모의투자 엔진 처리
- **storage/reports**: 리포트 결과, explain payload, SQLite 캐시
- **storage/logs**: 엔진 상태, 주문, 계좌, 사이클 로그
- **scheduler.py**: 주기 실행 담당
- **docker-compose**: `api + web` 배포 담당

---

## 5. 저장소 구조

```text
.
├── apps/
│   ├── api/        # Python backend, report pipeline, scheduler, paper trading
│   └── web/        # React/Vite console UI
├── docs/           # 운영 문서, 기준선 문서, 이미지 자산
├── storage/
│   ├── reports/    # 리포트 결과물, SQLite 캐시
│   └── logs/       # 엔진 상태/사이클/주문/계좌 로그
├── docker-compose.yml
└── requirements.txt
```

---

## 6. 실행 방식

현재 권장 운영 모델은 아래 기준입니다.

- 로컬 개발: Python venv + Vite dev server
- 배포: Docker로 `api + web` 실행
- 스케줄러: 필요 시 `scheduler.py` 직접 실행 또는 systemd 설치
- Ollama 사용 시: API 컨테이너가 호스트 Ollama에 접속

---

## 7. 사전 요구사항

### 7-1. 로컬 개발 기준

- Python 3.11+
- Node.js 20+
- npm
- Docker / Docker Compose
- 선택: OpenAI API Key 또는 Ollama

### 7-2. 외부 연동 선택 항목

- FRED API Key
- ECOS API Key
- DART API Key
- 텔레그램 봇 토큰 / 채팅 ID
- 이메일 SMTP 계정

---

## 8. 초기 설치

```bash
cd /home/user/daily-market-brief

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd apps/web
npm install
cd ../..
```

---

## 9. 환경 변수 설정

### 9-1. 백엔드 설정 파일 생성

```bash
cp apps/api/.env.example apps/api/.env
```

### 9-2. 백엔드 주요 환경 변수

`apps/api/.env`

#### OpenAI 사용

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_SIGNAL_MODEL=gpt-4o-mini
OPENAI_PLAYBOOK_MODEL=gpt-4o-mini
```

#### Ollama 사용

```bash
LLM_PROVIDER=ollama
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=nemotron-3-super
```

#### 거시 데이터 연동

```bash
FRED_API_KEY=your-fred-api-key
ECOS_API_KEY=your-ecos-api-key
DART_API_KEY=your-dart-api-key
```

#### 한국투자증권 Open API

```bash
KIS_APP_KEY=
KIS_APP_SECRET=
KIS_ACCOUNT_CANO=
KIS_ACCOUNT_ACNT_PRDT_CD=
```

#### 텔레그램 알림

```bash
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
REPORT_WEB_URL=http://localhost:8081
```

#### 이메일 발송

```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
REPORT_RECIPIENT=...
DELIVERY_METHOD=email
```

발송 방식을 끄거나 조합하려면:

```bash
DELIVERY_METHOD=none
# 또는 telegram / email / both
```

### 9-3. 웹 환경 변수

```bash
cp apps/web/.env.example apps/web/.env
```

`apps/web/.env`

```bash
VITE_API_BASE_URL=/api
VITE_PROXY_API_TARGET=http://127.0.0.1:8001
```

---

## 10. 로컬 실행 방법

### 10-1. 백엔드 실행

```bash
cd /home/user/daily-market-brief/apps/api
python3 api_server.py
```

기본 주소:

- API: `http://127.0.0.1:8001`
- Health: `http://127.0.0.1:8001/health`

### 10-2. 프런트엔드 실행

```bash
cd /home/user/daily-market-brief/apps/web
npm run dev
```

기본 주소:

- Web Dev: `http://127.0.0.1:5173`

### 10-3. 기본 동작 확인

```bash
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8001/api/system/mode
curl http://127.0.0.1:8001/api/recommendations
curl http://127.0.0.1:8001/api/today-picks
```

---

## 11. Docker 실행 방법

이 프로젝트는 기본적으로 `api + web` 을 컨테이너로 띄웁니다.
`scheduler.py` 는 compose 기본 대상이 아닙니다.

### 11-1. 실행

```bash
cd /home/user/daily-market-brief
cp apps/api/.env.example apps/api/.env
# .env 수정

docker compose up -d --build
```

### 11-2. 상태 확인

```bash
docker compose ps
curl http://127.0.0.1:8001/health
curl -I http://127.0.0.1:8081
curl http://127.0.0.1:8081/api/system/mode
```

### 11-3. 기본 포트

- API: `8001`
- Web: `8081`

### 11-4. 볼륨 마운트

- `./storage/reports -> /reports`
- `./storage/logs -> /logs`

### 11-5. Ollama 사용 시

컨테이너 내부에서 호스트 Ollama를 사용하도록 기본값이 설정되어 있습니다.

```bash
OLLAMA_HOST=http://host.docker.internal:11434
```

Linux에서는 compose의 `extra_hosts` 설정을 통해 연결합니다.

---

## 12. 리포트 생성 방법

### 12-1. 원샷 실행

하루치 리포트를 즉시 생성하려면:

```bash
cd /home/user/daily-market-brief/apps/api
python3 run_once.py
```

이 작업으로 보통 아래 데이터가 갱신됩니다.

- 분석 리포트
- 추천 종목
- 오늘의 픽
- 매크로 데이터
- 시장 컨텍스트
- 설명 payload / 캐시

### 12-2. 스케줄러 실행

```bash
cd /home/user/daily-market-brief/apps/api
python3 scheduler.py
```

### 12-3. systemd 설치

```bash
cd /home/user/daily-market-brief/apps/api
bash scripts/manage_scheduler_systemd.sh install
```

이 스크립트는 루트 `requirements.txt` 기준으로 의존성을 맞추고,
`storage/logs` 를 사용하며 `PYTHONPATH=apps/api` 기준으로 서비스 설치합니다.

---

## 13. 웹 콘솔 사용 방법

웹 콘솔은 운영자 시점에서 아래 기능 확인용입니다.

- quant 백테스트/최적화와 validation gate 확인
- AI·테마·뉴스 추천 / 오늘의 픽 / 브리프 확인
- 모의투자 엔진 상태 확인
- downstream 후보를 교집합이 아닌 합집합으로 해석하며 API 결과를 시각적으로 확인

### 개발 환경

```bash
cd /home/user/daily-market-brief/apps/web
npm run dev
```

### 배포 환경

```bash
docker compose up -d --build
# 이후 http://127.0.0.1:8081 접속
```

---

## 14. 모의투자 엔진 사용 방법

백엔드가 먼저 떠 있어야 합니다.

중요:

- quant 검증(백테스트/최적화)은 이 엔진의 validation gate와 sizing 기준을 담당함
- AI·테마·뉴스 추천은 `today_picks` / `recommendations` 후보 소스를 담당함
- 실제 downstream 집행은 둘을 교집합으로 강제하지 않고, combined candidate flow(오늘의 픽 우선 / 추천 fallback)를 사용함

### 14-1. 상태 조회

```bash
curl http://127.0.0.1:8001/api/paper/engine/status
```

### 14-2. 엔진 시작

```bash
curl -X POST http://127.0.0.1:8001/api/paper/engine/start \
  -H "Content-Type: application/json" \
  -d '{"markets":["KOSPI","NASDAQ"],"interval_seconds":300}'
```

### 14-3. 일시정지 / 재개 / 중지

```bash
curl -X POST http://127.0.0.1:8001/api/paper/engine/pause
curl -X POST http://127.0.0.1:8001/api/paper/engine/resume
curl -X POST http://127.0.0.1:8001/api/paper/engine/stop
```

### 14-4. 운영 로그 확인 API

```bash
curl "http://127.0.0.1:8001/api/paper/engine/cycles?limit=30"
curl "http://127.0.0.1:8001/api/paper/orders?limit=60"
curl "http://127.0.0.1:8001/api/paper/account/history?limit=60"
curl "http://127.0.0.1:8001/api/signals/snapshots?limit=120"
curl "http://127.0.0.1:8001/api/system/notifications/status"
```

### 14-5. 상태 payload에서 자주 볼 필드

- `engine_state`
- `running`
- `started_at`
- `last_run_at`
- `next_run_at`
- `last_success_at`
- `last_error`
- `last_summary`
- `latest_cycle_id`
- `current_config`
- `today_order_counts`
- `today_realized_pnl`
- `current_equity`
- `validation_policy`
- `optimized_params`

---

## 15. 주요 API 예시

### 15-1. 시스템/상태

```bash
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8001/api/system/mode
curl http://127.0.0.1:8001/api/system/notifications/status
```

### 15-2. AI 추천/리포트

```bash
curl http://127.0.0.1:8001/api/reports
curl http://127.0.0.1:8001/api/analysis
curl http://127.0.0.1:8001/api/recommendations
curl http://127.0.0.1:8001/api/today-picks
curl "http://127.0.0.1:8001/api/compare?base_date=2026-03-31&prev_date=2026-03-30"
```

### 15-3. 매크로/시장 컨텍스트

```bash
curl http://127.0.0.1:8001/api/macro/latest
curl http://127.0.0.1:8001/api/market-context/latest
curl http://127.0.0.1:8001/api/market-dashboard
```

### 15-4. 시그널/종목

```bash
curl http://127.0.0.1:8001/api/signals/rank
curl http://127.0.0.1:8001/api/signals/snapshots
curl http://127.0.0.1:8001/api/stock-search
```

### 15-5. 검증/최적화

```bash
curl -X POST http://127.0.0.1:8001/api/run-optimization
curl http://127.0.0.1:8001/api/optimization-status
curl http://127.0.0.1:8001/api/optimized-params
curl -X POST http://127.0.0.1:8001/api/validation/backtest
curl -X POST http://127.0.0.1:8001/api/validation/walk-forward
```

---

## 16. 생성 파일과 로그 위치

### 16-1. 리포트/캐시

```text
storage/reports/
```

예:

- SQLite 캐시
- 날짜별 리포트 결과물
- 설명용 데이터

### 16-2. 런타임 로그

```text
storage/logs/
├── engine_state.json
├── engine_cycles/YYYY-MM-DD.jsonl
├── order_events.jsonl
├── signal_snapshots.jsonl
└── account_snapshots.jsonl
```

알림 채널은 텔레그램 중심으로 동작합니다.
발송 실패 시 엔진 루프를 끊기보다 경고를 남기고 다음 루프로 계속 진행합니다.

---

## 17. 테스트 / 빌드 / 점검

### 17-1. 백엔드 테스트

```bash
cd /home/user/daily-market-brief/apps/api
python -m unittest discover -s tests
```

### 17-2. 프런트엔드 빌드

```bash
cd /home/user/daily-market-brief/apps/web
npm run build
```

### 17-3. Docker 빌드

```bash
cd /home/user/daily-market-brief
docker compose build api

docker build -t daily-market-brief-web ./apps/web
```

### 17-4. 기본 점검 루틴

```bash
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8001/api/recommendations
curl http://127.0.0.1:8001/api/paper/engine/status
curl http://127.0.0.1:8081/api/system/mode
```

---

## 18. 운영 팁

### 로컬 직접 실행할 때

`REPORT_OUTPUT_DIR`, `LOGS_DIR` 를 `.env` 에 고정하지 않는 편이 안전합니다.
비워두면 기본적으로 `storage/reports`, `storage/logs` 를 사용합니다.

### Docker로 실행할 때

compose가 `/reports`, `/logs` 로 override 하므로 로컬 경로와 컨테이너 경로를 섞지 않는 편이 좋습니다.

### 자주 틀리는 부분

- API는 떠 있는데 Web에서 안 보임 → `VITE_PROXY_API_TARGET` 확인
- Docker에서 Ollama 연결 실패 → `OLLAMA_HOST` 확인
- 텔레그램 알림 안 감 → `TELEGRAM_ENABLED`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 확인
- 리포트가 비어 있음 → 먼저 `python3 run_once.py` 실행

---

## 19. 관련 문서

- API 문서: [`api.md`](./api.md)
- 웹 UI 사용 매뉴얼: [`ui-manual.md`](./ui-manual.md)
- 신뢰도 기준선 문서: [`quant-reliability-baseline-2026-03-31.md`](./quant-reliability-baseline-2026-03-31.md)

---

## 20. 추천 실행 순서

처음 세팅할 때 무난한 순서:

```bash
cd /home/user/daily-market-brief
cp apps/api/.env.example apps/api/.env
# .env 수정

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd apps/web && npm install && cd ../..

# 백엔드 실행
cd apps/api
python3 api_server.py

# 새 터미널에서 프런트 실행
cd /home/user/daily-market-brief/apps/web
npm run dev

# 새 터미널에서 원샷 리포트 생성
cd /home/user/daily-market-brief/apps/api
python3 run_once.py
```

Docker 선호 시:

```bash
cd /home/user/daily-market-brief
cp apps/api/.env.example apps/api/.env
# .env 수정

docker compose up -d --build
```

---

추가 API 호출 예시와 엔드포인트 설명은 [`api.md`](./api.md) 참고.


## 실행 후보 소스 모드

실행 단계에서는 리서치 후보와 퀀트 검증 후보를 같은 것으로 취급하지 않는다.

- `quant_only`가 기본값이다. 저장된 quant candidate / runtime overlay만 실행 후보로 사용한다.
- `research_only`는 브리프 기반 후보만 실행 후보로 사용한다.
- `hybrid`는 둘을 분리 수집한 뒤 합집합 후보 풀로 노출한다.

안전한 운영 시작점은 계속 `quant_only` 다.
