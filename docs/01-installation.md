# 01. 설치와 실행

## 전제

현재 코드 기준 운영 시작점은 사실상 `docker-compose.yml` 하나다.

- API 컨테이너: Python 3.11 + FastAPI + uvicorn
- Web 컨테이너: Vite build 결과를 80 포트로 서빙
- 외부 DB/Redis 컨테이너: 없음
- 상태 저장: `storage/logs`, `storage/reports` 볼륨

## 포트

- API: `8001:8001`
- Web: `8081:80`

브라우저 접근:

- `http://localhost:8081`
- `http://localhost:8001/health`

## 디렉터리 기준

### 호스트
- `./storage/reports` → 컨테이너 `/reports`
- `./storage/logs` → 컨테이너 `/logs`

### API 내부 환경 변수
- `PYTHONPATH=/app/apps/api`
- `REPORT_OUTPUT_DIR=/reports`
- `LOGS_DIR=/logs`
- `PAPER_TRADING_STATE_PATH=/logs/paper_account_state.json`
- `OLLAMA_HOST=${OLLAMA_HOST:-http://host.docker.internal:11434}`

## 환경 변수 파일

도커 컴포즈는 API에 아래 파일을 주입한다.

- `./apps/api/.env`

코드상 `apps/api/config/settings.py`는 아래 두 곳을 env 파일 후보로 본다.

- `apps/api/.env`
- `REPO_ROOT/.env`

실제 운영은 `docker-compose.yml` 기준으로 `apps/api/.env`를 먼저 맞추면 된다.

## 필요한 주요 키 종류

실제 값은 적지 않는다. 이름만 적는다.

- FRED 계열: `FRED_API_KEY`, `FRED_KEY`, `FRED_API`
- ECOS/BOK 계열: `ECOS_API_KEY`, `BOK_ECOS_API_KEY`, `ECOS_KEY`
- DART 계열: `DART_API_KEY`, `OPENDART_API_KEY`
- KIS 계열:
  - `KIS_APP_KEY`
  - `KIS_APP_SECRET`
  - `KIS_ACCOUNT_CANO`
  - `KIS_ACCOUNT_ACNT_PRDT_CD`
  - `KIS_BASE_URL`

## 첫 실행

```bash
cd /home/user/wealth-pulse
docker compose up -d --build
```

## 상태 확인

```bash
docker compose ps
curl http://localhost:8001/health
curl http://localhost:8001/api/system/mode
curl http://localhost:8001/api/engine/status
```

정상이면 `/health`가 아래처럼 나온다.

```json
{"status":"ok"}
```

## API 단독 구조 이해

`apps/api/Dockerfile` 기준:

1. 루트 `requirements.txt` 설치
2. `apps/api` 복사
3. `uvicorn api_server:app --host 0.0.0.0 --port 8001` 실행

즉, Python 의존성은 루트 `requirements.txt`가 기준이다.

## Web 단독 구조 이해

`apps/web/package.json` 기준:

- React 19
- Vite 8
- TypeScript 5

개발 스크립트:

```bash
cd apps/web
npm install
npm run dev
```

빌드:

```bash
npm run build
```

운영은 보통 compose를 쓰는 게 맞다. 굳이 따로 띄우는 건 디버깅할 때만.

## 주요 마운트와 결과물

### 리포트
- 호스트: `storage/reports`
- 컨테이너: `/reports`
- 용도: 브리프/리포트 산출물

### 로그/상태
- 호스트: `storage/logs`
- 컨테이너: `/logs`
- 용도: paper 계좌 상태, validation 저장값, quant-ops 정책, 엔진 히스토리

## 부팅 후 기본 점검 순서

### 1. 컨테이너 상태
```bash
docker compose ps
```

### 2. API 헬스체크
```bash
curl http://localhost:8001/health
```

### 3. 엔진/스캐너/리서치 상태
```bash
curl http://localhost:8001/api/engine/status
curl http://localhost:8001/api/paper/engine/status
curl http://localhost:8001/api/scanner/status
curl http://localhost:8001/api/research/status
```

### 4. Web 접속
브라우저에서 `http://localhost:8081`

확인 화면:
- 장중 스캐너
- 전략 검증
- 투자 브리프/리스크 알림
- 주문/리스크
- 설정 상태 관리

## 장애 포인트

### API만 안 뜸
보통 아래 중 하나다.
- `apps/api/.env` 키 누락
- 외부 리서치/Ollama 연결 문제
- Python 패키지 설치 실패
- `storage/logs` 권한 문제

### Web만 안 뜸
보통 아래 중 하나다.
- API health 실패로 web `depends_on` 대기
- 프론트 빌드 실패

### compose는 떴는데 기능이 비어 있음
그건 서비스 다운이 아니라 **데이터 소스 미준비**일 가능성이 더 크다.
예:
- research snapshot 없음
- scanner cache 없음
- validation 결과 없음
- engine 미시작

## 운영 권장 명령

```bash
# 전체 재빌드/재기동
docker compose up -d --build

# 로그 확인
docker compose logs -f api
docker compose logs -f web

# 재시작
docker compose restart api
docker compose restart web
```

## 설치 후 바로 봐야 할 파일

- `docker-compose.yml`
- `apps/api/Dockerfile`
- `apps/api/config/settings.py`
- `apps/api/api_server.py`
- `apps/web/package.json`
