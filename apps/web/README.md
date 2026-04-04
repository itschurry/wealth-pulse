# WealthPulse Web

React 19 + Vite 기반 investing console입니다. 현재 위치는 `apps/web` 이며, API base URL은 `VITE_API_BASE_URL` 로 제어합니다.

이 프런트엔드는 단순 리포트 뷰어가 아니라 아래 흐름을 한 화면에 연결합니다.

- Research: 투자 브리프, 리서치 후보, 관심 시나리오
- Validation: 백테스트, 최적화, re-validation, save/apply
- Execution: paper 계좌, 실행 엔진, runtime 제어
- Observability: 엔진 상태, 주문/사이클/계좌 로그, 리스크 알림

## Development
```bash
cd apps/web
npm install
npm run dev
```

기본 프록시:
- `VITE_PROXY_API_TARGET=http://127.0.0.1:8001`
- `/api` 요청을 로컬 API 서버로 전달

## Build
```bash
cd apps/web
npm run build
```

## Environment
`apps/web/.env.example`

```bash
VITE_API_BASE_URL=/api
VITE_PROXY_API_TARGET=http://127.0.0.1:8001
```

## Deployment
- 개발: Vite dev server + local API
- 배포: `apps/web/Dockerfile` + nginx
- nginx는 `/api` 를 `api:8001` 로 프록시하고 나머지는 SPA fallback 으로 처리합니다.
