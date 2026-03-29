export const UI_TEXT = {
  appName: '자동투자 운영 콘솔',
  topTabs: {
    console: '콘솔',
    reports: '리포트',
  },
  consoleTabs: {
    overview: '개요',
    signals: '신호',
    paper: '모의투자',
    validation: '백테스트/검증',
  },
  reportTabs: {
    todayReport: '오늘 리포트',
    actionBoard: '액션보드',
    watchDecision: '관망/관심목표 판단',
  },
  common: {
    refresh: '새로고침',
    loading: '데이터를 불러오는 중입니다.',
    noData: '표시할 데이터가 없습니다.',
    unknown: '알 수 없음',
    yes: '예',
    no: '아니오',
  },
  empty: {
    signalsNoMatches: '오늘 조건을 만족한 신호가 없습니다.',
    signalsMissingData: '신호 데이터가 비어 있습니다. 최신 수집 상태와 로그를 확인하세요.',
    reportNotReady: '아직 오늘 리포트가 생성되지 않았습니다.',
    reportInsufficientData: '오늘 브리핑에 사용할 데이터가 충분하지 않아 판단을 보류했습니다.',
    reportNextStep: '리포트 생성 후 시장 요약과 액션 포인트가 여기에 표시됩니다.',
    noPositions: '현재 보유 종목이 없습니다.',
    noTrades: '아직 실행된 거래가 없어 성과를 계산하지 않았습니다.',
    noLogs: '아직 기록된 로그가 없습니다. 새로고침 후 다시 확인하거나 작업을 실행하세요.',
    noSkipReasons: '최근 실행에서 기록된 스킵 사유가 없습니다.',
    noRunHistory: '아직 실행 이력이 없습니다. 백테스트를 실행하면 기록이 쌓입니다.',
    noOptimizationHistory: '아직 최적화 이력이 없습니다.',
    noSaveHistory: '아직 저장된 설정 이력이 없습니다.',
    noReasonBreakdown: '사유별 성과를 계산할 거래 데이터가 아직 없습니다.',
    noOptimizedParams: '최적화 결과가 아직 없습니다. 최적화 실행 후 여기에 표시됩니다.',
  },
  confirm: {
    defaultTitle: '작업을 진행하시겠습니까?',
    defaultMessage: '이 작업은 현재 화면 상태에 영향을 줄 수 있습니다.',
    startEngineTitle: '엔진을 시작하시겠습니까?',
    startEngineMessage: '엔진을 시작하면 신규 신호 평가가 재개됩니다.',
    stopEngineTitle: '엔진을 중지하시겠습니까?',
    stopEngineMessage: '엔진을 중지하면 신규 신호 평가와 자동 실행이 멈춥니다.',
    resetPaperTitle: '모의투자 계좌를 초기화하시겠습니까?',
    resetPaperMessage: '이 작업은 되돌릴 수 없습니다. 현재 계좌 상태와 포지션이 초기화됩니다.',
    resetValidationTitle: '검증 설정을 초기화하시겠습니까?',
    resetValidationMessage: '저장하지 않은 변경 내용이 사라지고 기본값으로 돌아갑니다.',
    clearLogsTitle: '로그를 비우시겠습니까?',
    clearLogsMessage: '로그를 비우면 기존 기록을 현재 화면에서 다시 확인할 수 없습니다.',
    confirmAction: '확인',
    cancelAction: '취소',
  },
  errors: {
    loadFailed: '데이터를 불러오지 못했습니다.',
    partialLoadFailed: '일부 데이터를 불러오지 못했습니다.',
    symbolNameMissing: '종목명 매핑 미완성',
  },
  status: {
    running: '실행 중',
    stopped: '중지',
    allowed: '추천',
    blocked: '차단',
    active: '활성',
    inactive: '비활성',
  },
} as const;

export const REASON_CODE_KR: Record<string, string> = {
  allocator_block: '전략 할당 규칙 차단',
  ev_non_positive: '기대값이 0 이하',
  daily_loss_limit_reached: '일일 손실 한도 도달',
  loss_streak_cooldown: '연속 손실 쿨다운',
  regime_risk_off: '리스크 오프 구간',
  risk_level_high: '시장 위험도 높음',
  liquidity_unknown: '유동성 정보 부족',
  liquidity_low_volume: '평균 거래량 부족',
  liquidity_low_notional: '평균 거래대금 부족',
  exposure_or_cash_limit: '현금 또는 익스포저 한도',
  account_unavailable: '계좌 정보 없음',
  size_zero: '권장 수량 0',
  invalid_unit_price: '유효하지 않은 가격',
};

export function reasonCodeToKorean(code: string): string {
  return REASON_CODE_KR[code] || code;
}

const STRATEGY_TYPE_KR: Record<string, string> = {
  breakout: '돌파',
  pullback: '눌림목',
  'event-driven': '이벤트',
  'news-theme momentum': '뉴스/테마 모멘텀',
  'mean-reversion': '평균회귀',
};

const RELIABILITY_KR: Record<string, string> = {
  high: '높음',
  medium: '보통',
  low: '낮음',
  insufficient: '부족',
};

export function strategyTypeToKorean(strategyType: string): string {
  return STRATEGY_TYPE_KR[strategyType] || strategyType || '-';
}

export function reliabilityToKorean(reliability: string): string {
  return RELIABILITY_KR[reliability] || reliability || '-';
}
