# daily-market-brief Web

React 19 + Vite 기반 운영 콘솔입니다. 현재 위치는 `apps/web` 이며, API base URL은 `VITE_API_BASE_URL` 로 제어합니다.

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
