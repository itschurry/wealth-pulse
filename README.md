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
- `LLM_PROVIDER=ollama`: 호스트 Ollama 필요, API 컨테이너는 `OLLAMA_HOST` 로 접속

## Local Development
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

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

## Environment
주요 설정은 `apps/api/.env.example` 을 기준으로 합니다.

- `LLM_PROVIDER=openai|ollama`
- `OPENAI_API_KEY`
- `OLLAMA_MODEL`
- `OLLAMA_HOST`
- `REPORT_OUTPUT_DIR` (선택)
- `LOGS_DIR` (선택)

모의투자 운영(알림/엔진) 필수 설정:
- `TELEGRAM_ENABLED=true`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

로컬 host-run 개발 기본값:
- API: `http://127.0.0.1:8001`
- Web dev: `http://127.0.0.1:5173`
- Web prod: `http://127.0.0.1:8081`
- Ollama: `http://127.0.0.1:11434`
- Report output: `storage/reports`
- Logs: `storage/logs`

## Paper Trading Operations
백엔드 실행 후 아래 API로 모의투자 엔진을 운용할 수 있습니다.

```bash
# 상태 조회
curl http://127.0.0.1:8001/api/paper/engine/status

# 시작/일시정지/재개/중지
curl -X POST http://127.0.0.1:8001/api/paper/engine/start -H "Content-Type: application/json" -d '{"markets":["KOSPI","NASDAQ"],"interval_seconds":300}'
curl -X POST http://127.0.0.1:8001/api/paper/engine/pause
curl -X POST http://127.0.0.1:8001/api/paper/engine/resume
curl -X POST http://127.0.0.1:8001/api/paper/engine/stop
```

운영 로그/스냅샷 API:
- `GET /api/paper/engine/cycles?limit=30`
- `GET /api/paper/orders?limit=60`
- `GET /api/paper/account/history?limit=60`
- `GET /api/signals/snapshots?limit=120`
- `GET /api/system/notifications/status`

실행 상태 payload(`state`) 주요 필드:
- `engine_state`, `running`, `started_at`, `last_run_at`, `next_run_at`
- `last_success_at`, `last_error`, `last_summary`, `latest_cycle_id`
- `current_config`, `today_order_counts`, `today_realized_pnl`, `current_equity`
- `validation_policy`, `optimized_params`

## Runtime Logs
모의투자 운영 중 아래 파일이 누적됩니다.

```text
storage/logs/engine_state.json
storage/logs/engine_cycles/YYYY-MM-DD.jsonl
storage/logs/order_events.jsonl
storage/logs/signal_snapshots.jsonl
storage/logs/account_snapshots.jsonl
```

알림 채널은 텔레그램만 사용합니다. 발송 실패 시 엔진 루프는 계속 동작하고 경고만 남깁니다.

## Docker Deployment
API와 Web만 컨테이너로 운영합니다. `scheduler` 는 제외합니다.

```bash
cp apps/api/.env.example apps/api/.env
# apps/api/.env 값을 실제 환경에 맞게 수정

docker compose up --build -d
docker compose ps
```

로컬에서 `python3 run_once.py` 또는 `python3 scheduler.py` 를 직접 실행할 때는
`REPORT_OUTPUT_DIR`, `LOGS_DIR` 를 `.env` 에 넣지 않는 편이 안전합니다.
비워두면 자동으로 `storage/reports`, `storage/logs` 를 사용합니다.

검증:
```bash
curl http://localhost:8001/health
curl -I http://localhost:8081
curl http://localhost:8081/api/system/mode
```

Ollama 사용 시:
- 배포 서버 호스트에 Ollama 설치 및 모델 pull
- `OLLAMA_HOST=http://host.docker.internal:11434` 또는 서버 고정 호스트명 설정
- Linux Docker에서는 compose의 `extra_hosts` 설정을 사용

## Scheduler
systemd 운영 스크립트:
```bash
cd apps/api
bash scripts/manage_scheduler_systemd.sh install
```

이 스크립트는 루트 `requirements.txt` 를 동기화하고, `storage/logs` 를 사용하며,
`PYTHONPATH=apps/api` 기준으로 서비스를 설치합니다.

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
docker compose build api
docker build -t daily-market-brief-web ./apps/web
```
