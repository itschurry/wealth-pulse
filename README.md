# daily-market-brief

고수익/고생존 자동투자 엔진과 설명 리포트를 함께 운영하는 프로젝트입니다. 현재 구조는 `docflow-ai` 정렬을 목표로 `apps/api`, `apps/web`, `storage` 기준으로 재구성되어 있습니다.

## Repository Layout
```text
.
├── apps/
│   ├── api/        # Python backend, FastAPI, scheduler, report pipeline
│   └── web/        # React/Vite console UI
├── storage/
│   ├── reports/    # SQLite report cache + generated artifacts
│   └── logs/       # runtime logs, watchlist, paper trading state
├── docker-compose.yml
└── .github/workflows/ci.yml
```

## Runtime Model
- 로컬 개발: `venv` 기반 직접 실행
- 배포: Docker `api + web`
- `scheduler.py`: host/systemd 운영 유지
- `LLM_PROVIDER=nemotron`: 호스트 Ollama 필요, API 컨테이너는 `OLLAMA_HOST` 로 접속

## Local Development
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r apps/api/requirements.txt

cd apps/web
npm install
cd ../..
```

백엔드:
```bash
cd apps/api
python3 api_server.py
```

프런트엔드:
```bash
cd apps/web
npm run dev
```

원샷 리포트:
```bash
cd apps/api
python3 run_once.py
```

스케줄러:
```bash
cd apps/api
python3 scheduler.py
```

기존 루트 명령도 호환 래퍼로 유지됩니다.
```bash
python3 api_server.py
python3 run_once.py
python3 scheduler.py
```

## Environment
주요 설정은 `apps/api/.env.example` 을 기준으로 합니다.

- `LLM_PROVIDER=openai|nemotron`
- `OPENAI_API_KEY`
- `NEMOTRON_MODEL`
- `OLLAMA_HOST`
- `REPORT_OUTPUT_DIR`
- `LOGS_DIR`

로컬 host-run 개발 기본값:
- API: `http://127.0.0.1:8001`
- Web dev: `http://127.0.0.1:5173`
- Web prod: `http://127.0.0.1:8081`
- Ollama: `http://127.0.0.1:11434`

## Docker Deployment
API와 Web만 컨테이너로 운영합니다. `scheduler` 는 제외합니다.

```bash
cp apps/api/.env.example apps/api/.env
# apps/api/.env 값을 실제 환경에 맞게 수정

docker compose up --build -d
docker compose ps
```

검증:
```bash
curl http://localhost:8001/health
curl -I http://localhost:8081
curl http://localhost:8081/api/health
```

Nemotron 사용 시:
- 배포 서버 호스트에 Ollama 설치 및 모델 pull
- `OLLAMA_HOST=http://host.docker.internal:11434` 또는 서버 고정 호스트명 설정
- Linux Docker에서는 compose의 `extra_hosts` 설정을 사용

## Scheduler
systemd 운영 스크립트:
```bash
cd apps/api
bash scripts/manage_scheduler_systemd.sh install
```

이 스크립트는 `storage/logs` 를 사용하고, `PYTHONPATH=apps/api` 기준으로 서비스를 설치합니다.

## Test And Build
백엔드 테스트:
```bash
cd apps/api
python -m unittest discover -s tests
```

프런트엔드 빌드:
```bash
cd apps/web
npm run build
```

Docker 빌드:
```bash
docker build -t daily-market-brief-api ./apps/api
docker build -t daily-market-brief-web ./apps/web
```
