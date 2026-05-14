export const UI_TEXT = {
  appName: 'WealthPulse',
  topTabs: {
    operations: '운영',
    lab: '실험',
    analysis: '분석',
  },
  operationsTabs: {
    overview: '운영 개요',
    scanner: '장중 스캐너',
    watchDecision: '관심 시나리오',
    performance: '성과',
  },
  labTabs: {
    strategies: '전략 프리셋',
    validation: '전략 검증 랩',
    universe: '유니버스',
  },
  analysisTabs: {
    watchlist: '관심 종목',
    research: '후보 리서치',
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
    reportNotReady: '아직 오늘 투자 브리프가 생성되지 않았습니다.',
    reportInsufficientData: '오늘 투자 브리프에 사용할 데이터가 충분하지 않아 판단을 보류했습니다.',
    reportNextStep: '리서치 브리프 생성 후 시장 요약과 실행 포인트가 여기에 표시됩니다.',
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
    startEngineMessage: '엔진을 시작하면 runtime 실행용 신규 후보 평가가 재개됩니다.',
    stopEngineTitle: '엔진을 중지하시겠습니까?',
    stopEngineMessage: '엔진을 중지하면 runtime 실행 평가와 자동 집행이 멈춥니다.',
    resetRuntimeTitle: 'Runtime 계좌를 초기화하시겠습니까?',
    resetRuntimeMessage: '이 작업은 되돌릴 수 없습니다. 현재 runtime 계좌 상태와 포지션이 초기화됩니다.',
    resetValidationTitle: '서버 저장된 검증 설정을 초기화하시겠습니까?',
    resetValidationMessage: '공유 저장 기준이 기본값으로 돌아가고 현재 브라우저 초안도 함께 덮어씁니다.',
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
    paused: '일시정지',
    stopped: '중지',
    error: '오류',
    allowed: '검토 필요',
    blocked: '차단',
    active: '활성',
    inactive: '비활성',
  },
} as const;

export const REASON_CODE_KR: Record<string, string> = {
  RISK_GUARD_BLOCKED: '리스크 가드에서 진입을 차단했습니다',
  risk_veto: '리스크 가드에서 진입을 차단했습니다',
  blocked: '차단됨',
  watch_only: '감시만',
  do_not_touch: '대기',
  review_for_entry: '진입 검토',
  scan_only: '비진입 신호라 주문 리스크 평가 생략',
  quant_confirmed: '수량/퀀트 승인',
  needs_operator_review: '리서치 확증 부족',
  weak_quant: '퀀트 신호 약함',
  non_entry_signal: '비진입 신호',
  exit_signal: '청산 신호',
  order_ready: '주문 준비 완료',
  submitted: '주문 전송',
  filled: '체결 완료',
  rejected: '주문 거절',
  screened: '사전 스크리닝 실패',
  DAILY_LOSS_LIMIT_REACHED: '일일 손실 한도 도달',
  LOSS_STREAK_COOLDOWN: '연속 손실 쿨다운',
  MAX_POSITIONS_REACHED: '시장별 최대 포지션 도달',
  DUPLICATE_POSITION: '동일 종목 중복 진입 시도',
  LIQUIDITY_TOO_LOW: '유동성 부족',
  SPREAD_TOO_WIDE: '호가 스프레드 과다',
  POSITION_SIZE_LIMIT_EXCEEDED: '수량 한도 초과',
  SIZE_ZERO: '권장 수량 0',
  SIZE_LIMIT_REACHED: '수량 한도 도달',
  OK: '정상',
  unknown: '원인 미확인',
  operator_review: '리서치 확증 부족',
  insufficient_cash: '현금 부족',
  buy_failed: '매수 주문 실패',
  sell_failed: '매도 주문 실패',
  allocator_block: '전략 할당 규칙 차단',
  ev_non_positive: '기대값이 0 이하',
  daily_loss_limit_reached: '일일 손실 한도 도달',
  loss_streak_cooldown: '연속 손실 쿨다운',
  regime_risk_off: '리스크 오프 구간',
  risk_level_high: '시장 위험도 높음',
  liquidity_unknown: '유동성 정보 부족',
  liquidity_low_volume: '평균 거래량 부족',
  liquidity_low_notional: '평균 거래대금 부족',
  quote_stale: '시세 지연 데이터',
  validation_trades_low: '검증 거래수 부족',
  validation_sharpe_low: '검증 샤프 부족',
  validation_reliability_low: '검증 신뢰도 낮음',
  optimized_symbol_unreliable: '최적화 신뢰도 미달',
  max_positions_reached: '시장별 최대 포지션 도달',
  market_closed: '시장 휴장/장마감',
  exposure_or_cash_limit: '현금 또는 익스포저 한도',
  account_unavailable: '계좌 정보 없음',
  size_zero: '권장 수량 0',
  invalid_unit_price: '유효하지 않은 가격',
  research_unavailable: 'Hermes 리서치 미사용/일시 불가',
  headline_stronger_than_body: '헤드라인 강도 대비 본문 근거 약함',
  already_extended_intraday: '장중 과열로 추격 주의',
  low_evidence_density: '근거 밀도 낮음',
  theme_recycled: '반복된 테마 이슈',
  contrarian_flow_risk: '역방향 수급 리스크',
  policy_uncertainty: '정책 불확실성',
  liquidity_mismatch: '유동성 불일치',
  too_many_similar_news: '유사 뉴스 과다',
};

export function reasonCodeToKorean(code: string): string {
  if (code.startsWith('research_warning:')) {
    const warning = code.replace('research_warning:', '');
    return `Hermes 경고 · ${REASON_CODE_KR[warning] || warning}`;
  }
  return REASON_CODE_KR[code] || code;
}

const FRESHNESS_KR: Record<string, string> = {
  fresh: '최신',
  stale: '지연',
  invalid: '무효',
  missing: '없음',
  derived: '파생',
  unknown: '알 수 없음',
};

const GRADE_KR: Record<string, string> = {
  A: 'A등급',
  B: 'B등급',
  C: 'C등급',
  D: 'D등급',
};

const PROVIDER_STATUS_KR: Record<string, string> = {
  healthy: '정상',
  degraded: '불안정',
  timeout: '응답 지연',
  research_unavailable: '리서치 미사용/불가',
  stale_ingest: '수집 지연',
  stale: '지연',
  invalid: '무효',
  missing: '없음',
  unknown: '알 수 없음',
};

const PROVIDER_SOURCE_KR: Record<string, string> = {
  default: '기본',
  healthy: '정상',
  degraded: '불안정',
  research_unavailable: '리서치 미사용/불가',
  latest_snapshot_directory: '저장 스냅샷 기준',
  candidate_monitor_active_slots: '활성 후보 기준',
};

const STRATEGY_LIFECYCLE_KR: Record<string, string> = {
  applied: '적용 중',
  approved: '준비됨',
  stale: '재확인 필요',
  blocked: '보관됨',
  candidate: '초안',
};

export function freshnessToKorean(value: string | null | undefined): string {
  const normalized = String(value || '').trim().toLowerCase();
  return FRESHNESS_KR[normalized] || normalized || FRESHNESS_KR.unknown;
}

export function gradeToKorean(value: string | null | undefined): string {
  const normalized = String(value || '').trim().toUpperCase();
  return GRADE_KR[normalized] || '등급 없음';
}

export function providerStatusToKorean(value: string | null | undefined): string {
  const normalized = String(value || '').trim().toLowerCase();
  return PROVIDER_STATUS_KR[normalized] || normalized || PROVIDER_STATUS_KR.unknown;
}

export function providerSourceToKorean(value: string | null | undefined): string {
  const normalized = String(value || '').trim().toLowerCase();
  return PROVIDER_SOURCE_KR[normalized] || normalized || '-';
}

export function strategyLifecycleToKorean(value: string | null | undefined): string {
  const normalized = String(value || '').trim().toLowerCase();
  return STRATEGY_LIFECYCLE_KR[normalized] || normalized || '-';
}

const STRATEGY_TYPE_KR: Record<string, string> = {
  breakout: '돌파',
  pullback: '눌림목',
  'event-driven': '이벤트',
  'news-theme momentum': '뉴스/테마 모멘텀',
  'mean-reversion': '평균회귀',
  trend_following: '추세 추종',
  mean_reversion: '평균 회귀',
  defensive: '방어형',
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

const RISK_PROFILE_KR: Record<string, string> = {
  conservative: '보수형',
  balanced: '균형형',
  aggressive: '공격형',
};

export function riskProfileToKorean(value: string | null | undefined): string {
  const normalized = String(value || '').trim().toLowerCase();
  return RISK_PROFILE_KR[normalized] || normalized || '-';
}
