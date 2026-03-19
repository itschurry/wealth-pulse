# daily-market-brief

리포트 우선(read-first) 투자 보조 앱입니다.

이 프로젝트는 매크로/시장/뉴스/공시/일정/수급을 수집해 하루치 분석과 추천을 생성하고, 결과를 웹앱에서 읽기 쉽게 제공합니다.
실시간 데이터는 보조 참고용이며, 기본 사용 흐름은 "리포트 생성 후 나중에 읽고 판단"입니다.

## 핵심 기능

- 미국 + 한국 거시 지표 수집
  - 미국: FRED
  - 한국: ECOS
- 핵심 경제 일정 / 공시 / 수급 수집
  - 경제 일정: BLS 공식 캘린더
  - 공시: DART
  - 수급: 네이버 금융 종목별 외국인·기관 동향
- 시장 데이터 수집
  - KOSPI, KOSDAQ, S&P100, NASDAQ, USD/KRW, WTI, Gold, BTC
- AI 분석 및 추천 생성
  - 분석 결과/추천/거시/시장 컨텍스트를 JSON 캐시로 저장
- React 웹앱에서 리포트 중심 UX 제공
  - 기본 진입: 오늘 리포트
  - 실시간 시장 화면은 보조 참고용

## 프로젝트 구조

- 파이프라인: [main.py](main.py)
- 1회 실행: [run_once.py](run_once.py)
- 스케줄러 실행: [scheduler.py](scheduler.py)
- API 서버: [api_server.py](api_server.py)
- 거시 수집(미국+한국): [collectors/macro_collector.py](collectors/macro_collector.py), [collectors/ecos_collector.py](collectors/ecos_collector.py)
- 경제 일정 수집: [collectors/calendar_collector.py](collectors/calendar_collector.py)
- 공시 수집: [collectors/disclosure_collector.py](collectors/disclosure_collector.py)
- 수급 수집: [collectors/flow_collector.py](collectors/flow_collector.py)
- 프론트엔드: [frontend](frontend)
- Docker 실행 진입: [Dockerfile](Dockerfile), [docker-compose.yml](docker-compose.yml), [entrypoint.sh](entrypoint.sh)

## 환경 변수

샘플 파일: [.env.example](.env.example)

필수(권장)

- OPENAI_API_KEY
- OPENAI_SIGNAL_MODEL (선택, 기본값: OPENAI_MODEL)
- FRED_API_KEY
- ECOS_API_KEY
- DART_API_KEY

선택

- KIS_APP_KEY, KIS_APP_SECRET
- KIS_ACCOUNT_CANO, KIS_ACCOUNT_ACNT_PRDT_CD
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID
- REPORT_WEB_URL
- SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, REPORT_RECIPIENT
- DELIVERY_METHOD (telegram / email / both / none)
- REPORT_OUTPUT_DIR (기본: ./report)

로컬에서는 .env를 생성해 사용하세요.

## 로컬 실행

### 1) 백엔드 의존성 설치

```bash
pip install -r requirements.txt
```

### 2) 프론트엔드 설치/빌드

```bash
cd frontend
npm install
npm run build
cd ..
```

### 3) 리포트 1회 생성

```bash
python3 run_once.py
```

### 4) API + 웹앱 실행

```bash
python3 api_server.py
```

별도 터미널에서 정적 웹은 nginx/docker 기준으로 제공됩니다. 로컬 단독 개발 시에는 frontend dev 서버를 사용해도 됩니다.

### 5) 한국투자증권 Open API 연결 테스트

`.env`에 아래 값을 넣은 뒤 테스트할 수 있습니다.

- `KIS_APP_KEY`
- `KIS_APP_SECRET`
- `KIS_ACCOUNT_CANO`, `KIS_ACCOUNT_ACNT_PRDT_CD`
- `KIS_ACCOUNT_ACNT_PRDT_CD`를 비워두면 기본값 `01`로 처리합니다.
- 현재 KIS 연동 코드는 실전 투자 서버만 사용합니다.

토큰 발급만 확인:

```bash
.venv/bin/python scripts/test_kis_connection.py --token-only
```

토큰 발급 + 국내 현재가 조회 테스트:

```bash
.venv/bin/python scripts/test_kis_connection.py --symbol 005930
```

관련 코드:

- [broker/kis_client.py](broker/kis_client.py)
- [scripts/test_kis_connection.py](scripts/test_kis_connection.py)

잔고 조회:

```bash
.venv/bin/python scripts/test_kis_account.py balance
```

주문 가능 금액/수량 조회:

```bash
.venv/bin/python scripts/test_kis_account.py orderable --symbol 005930 --price 70000
```

실전 지정가 매수 주문:

```bash
.venv/bin/python scripts/test_kis_account.py buy --symbol 005930 --qty 1 --price 70000 --confirm
```

관련 코드:

- [scripts/test_kis_account.py](scripts/test_kis_account.py)

## KOSPI50 + S&P50 가상 백테스트

최근 3년 KOSPI50과 S&P50 종목 일봉을 바탕으로, 미국 종목은 USD/KRW 환율을 반영해 원화 기준으로 가상 자금 백테스트를 돌릴 수 있습니다.

```bash
.venv/bin/python scripts/run_kospi_backtest.py
```

옵션 예시:

```bash
.venv/bin/python scripts/run_kospi_backtest.py --initial-cash 10000000 --max-positions 5 --max-holding-days 30
```

결과 파일:

- [report/kospi_backtest_latest.json](report/kospi_backtest_latest.json)

## Docker 실행

```bash
docker compose up --build -d
```

접속

- 웹앱: http://localhost:8080

컨테이너는 nginx(정적 프론트) + python API 서버를 함께 실행합니다.

## 스케줄러 사용

현재 [scheduler.py](scheduler.py)는 KST 기준 3시간 간격(06/09/12/15/18/21시)으로 실행되도록 설정되어 있습니다.

```bash
python3 scheduler.py
```

수동 실행만 원하면 [run_once.py](run_once.py)만 사용하세요.

Ubuntu에서 systemd 서비스로 백그라운드 실행이 필요하면 관리 스크립트를 사용할 수 있습니다.

```bash
./scripts/manage_scheduler_systemd.sh install
./scripts/manage_scheduler_systemd.sh status
./scripts/manage_scheduler_systemd.sh logs
```

중지/제거:

```bash
./scripts/manage_scheduler_systemd.sh stop
./scripts/manage_scheduler_systemd.sh uninstall
```

## 생성 산출물

리포트 결과는 [report](report) 디렉토리에 JSON 캐시로 저장됩니다.

- *_analysis.json
- *_ai_signals.json
- *_recommendations.json
- *_macro.json
- *_calendar.json
- *_disclosures.json
- *_investor_flows.json
- *_market_context.json

## API 엔드포인트

- GET /api/live-market
- GET /api/analysis
- GET /api/recommendations
- GET /api/macro/latest
- GET /api/market-context/latest
- GET /api/stock-search?q=키워드
- GET /api/stock/{code}

구현 참고: [api_server.py](api_server.py)

## 사용 흐름 권장

1. 스케줄러 또는 run_once로 리포트 생성
2. 웹앱 접속 후 오늘 리포트 탭부터 확인
3. 의사결정 보드에서 행동 포인트 정리
4. 실시간 시장 탭은 보조 확인 용도로 사용

## 보안 주의

- .env, API 키는 절대 커밋하지 마세요.
- 현재 [.gitignore](.gitignore)에 .env 및 생성 산출물 제외 규칙이 포함되어 있습니다.

## 라이선스

개인 용도라면 없어도 되지만, 공개 저장소라면 LICENSE 추가를 권장합니다.
