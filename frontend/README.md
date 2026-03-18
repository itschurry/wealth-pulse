# Frontend (daily-market-brief)

daily-market-brief의 웹 UI(React + TypeScript + Vite) 프로젝트입니다.

이 프론트는 "리포트 우선(read-first)" UX를 기준으로 동작합니다.

- 기본 진입: 오늘 리포트
- 실시간 시장 화면: 보조 참고용

## Tech Stack

- React 19
- TypeScript
- Vite

## 실행 방법

프로젝트 루트에서 API가 먼저 동작 중이어야 합니다.

### 개발 모드

```bash
cd frontend
npm install
npm run dev
```

기본 개발 서버: http://localhost:5173

### 프로덕션 빌드

```bash
cd frontend
npm run build
npm run preview
```

## API 의존성

프론트는 아래 엔드포인트를 사용합니다.

- /api/live-market
- /api/analysis
- /api/recommendations
- /api/macro/latest
- /api/market-context/latest
- /api/stock-search
- /api/stock/:code

백엔드 구현은 루트의 [api_server.py](../api_server.py)를 참고하세요.

## 주요 화면 구성

- 오늘 리포트: 생성된 분석 본문과 요약 확인
- 의사결정 보드: 리포트 기반 행동 항목 정리
- 실시간 참고: 시장/거시/컨텍스트 카드 확인
- 관심 종목: 개별 종목 추적
- 추천 허브: AI 추천 및 점수 확인

## 디렉토리 안내

- 앱 진입: [src/main.tsx](src/main.tsx), [src/App.tsx](src/App.tsx)
- 컴포넌트: [src/components](src/components)
- 훅: [src/hooks](src/hooks)
- 타입: [src/types/index.ts](src/types/index.ts)

## 참고

- 루트 README: [../README.md](../README.md)
- 도커 실행은 루트 기준으로 진행하세요.
