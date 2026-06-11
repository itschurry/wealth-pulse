# WealthPulse Storage

`storage`는 애플리케이션 소스가 아니라 로컬 런타임 데이터다. Docker는 이 경로를 API 컨테이너 안으로 마운트한다.

```text
storage/logs    -> /logs
storage/reports -> /reports
```

코드는 저장 경로를 직접 하드코딩하지 말고 `apps/api/config/settings.py`의 `LOGS_DIR`, `REPORT_OUTPUT_DIR` 기준으로 써야 한다.

## 구조

```text
storage
├── logs
│   ├── runtime
│   ├── audit
│   ├── config
│   └── cache
└── reports
```

## `storage/logs/runtime`

현재 실행 상태를 둔다.

- engine/account state
- runtime event stream
- candidate monitor DB
- research run status
- `hermes_research_runner.log`

이 경로는 운영 중 계속 변한다. 장애 분석에서 가장 먼저 본다.

## `storage/logs/audit`

감사 로그를 둔다.

- Agent run 기록
- Risk Gate 통과/차단 기록
- 주문 intent와 주문 결과

매매 판단을 나중에 복기할 때 기준이 되는 데이터다.

## `storage/logs/config`

운영자가 바꾸는 설정을 둔다.

- risk config
- watchlist
- strategy registry
- guardrail policy
- validation config

집중투자 모드 설정도 이 계층의 설정으로 관리된다.

## `storage/logs/cache`

다시 만들 수 있는 캐시를 둔다.

- research snapshots
- universe snapshots
- strategy scan outputs
- broker token cache

캐시는 지울 수 있지만, 장중에 지우면 research/agent 판단이 차단될 수 있다. 운영 중 삭제하지 마.

## `storage/reports`

생성 리포트 저장소다.

- `market_brief.db`: 리포트 라우트가 쓰는 SQLite 캐시

## SQLite 주의

API 실행 중에는 SQLite sidecar가 생긴다.

- `*.db-wal`
- `*.db-shm`

컨테이너가 떠 있는 동안 이 파일들을 직접 삭제하지 마. DB가 깨질 수 있다.

## 정리 기준

지워도 되는 것:

- 오래된 일회성 dump
- 코드에서 더 이상 참조하지 않는 실험 산출물
- 명확히 재생성 가능한 오래된 cache 파일

지우면 안 되는 것:

- `logs/runtime`의 현재 상태 DB
- `logs/audit`의 감사 DB
- `logs/config`의 운영 설정
- API 실행 중인 SQLite sidecar

## 확인 명령

```bash
find storage/logs -maxdepth 2 -type f | sort
tail -n 100 storage/logs/runtime/hermes_research_runner.log
curl http://localhost:8001/api/research/status
```
