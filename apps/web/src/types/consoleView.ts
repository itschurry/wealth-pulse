import type {
  DomainSignal,
  EngineStatusResponse,
  HannaBriefResponse,
  LiveMarketResponse,
  MacroLatestResponse,
  MarketContextResponse,
  PerformanceSummaryResponse,
  PortfolioStateResponse,
  RecommendationsResponse,
  ResearchStatusResponse,
  ReportsExplainResponse,
  ScannerStatusResponse,
  SignalsRankResponse,
  StrategiesResponse,
  TodayPicksResponse,
  UniverseResponse,
  ValidationResponse,
} from './domain';

export interface ConsoleSnapshot {
  engine: EngineStatusResponse;
  signals: SignalsRankResponse;
  strategies: StrategiesResponse;
  scanner: ScannerStatusResponse;
  universe: UniverseResponse;
  performance: PerformanceSummaryResponse;
  portfolio: PortfolioStateResponse;
  research: ResearchStatusResponse;
  validation: ValidationResponse;
  reports: ReportsExplainResponse;
  liveMarket: LiveMarketResponse;
  marketContext: MarketContextResponse;
  todayPicks: TodayPicksResponse;
  recommendations: RecommendationsResponse;
  macro: MacroLatestResponse;
  hannaBrief: HannaBriefResponse;
  fetchedAt: string;
}

export interface ConsoleDataState {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  hasError: boolean;
  errorMessage: string;
}

export interface TodayReportView {
  generatedAt: string;
  dataAsOf: string;
  statusItems: Array<{
    label: string;
    value: string;
    tone?: 'neutral' | 'good' | 'bad';
  }>;
  summaryLines: string[];
  judgmentTitle: '관망' | '선별' | '공격' | '축소';
  judgmentLines: string[];
  actionItems: Array<{
    label: string;
    detail: string;
    tone?: 'neutral' | 'good' | 'bad';
  }>;
  watchPoints: string[];
  hasReportContent: boolean;
}

export interface WatchDecisionCandidate {
  key: string;
  symbol: string;
  market: string;
  strategyLabel: string;
  actionLabel: string;
  actionTone: 'good' | 'neutral' | 'bad';
  scoreLabel: string;
  evLabel: string;
  reliabilityLabel: string;
  primaryReason: string;
  secondaryDetail: string;
  chips: string[];
}

export interface WatchDecisionView {
  mode: '관망' | '선별' | '공격' | '축소';
  rationale: string[];
  stanceTitle: string;
  stanceSummary: string;
  allowedCount: number;
  blockedCount: number;
  focusCandidates: WatchDecisionCandidate[];
  blockedCandidates: WatchDecisionCandidate[];
  researchQueue: string[];
}

export interface SignalTableRow {
  signal: DomainSignal;
  symbol: string;
  statusLabel: '추천' | '차단';
  reasonSummary: string;
}

export type ConsoleLogLevel = 'info' | 'success' | 'warning' | 'error';

export interface ConsoleLogEntry {
  id: string;
  timestamp: string;
  level: ConsoleLogLevel;
  message: string;
  context?: string;
  source?: string;
}

export interface ActionBarStatusItem {
  label: string;
  value: string;
  tone?: 'neutral' | 'good' | 'bad';
}

export interface ActionBarAction {
  label: string;
  onClick: () => void;
  tone?: 'default' | 'primary' | 'danger';
  disabled?: boolean;
  disabledReason?: string;
  busy?: boolean;
  busyLabel?: string;
  confirmTitle?: string;
  confirmMessage?: string;
  confirmLabel?: string;
  confirmDetails?: string[];
}

export interface PaperViewModel {
  totalEquityKrw: number;
  cashKrw: number;
  cashUsd: number;
  unrealizedPnlKrw: number;
  realizedPnlKrw: number;
  positionCount: number;
}

export interface BacktestViewModel {
  totalReturnPct: number | null;
  oosReturnPct: number | null;
  maxDrawdownPct: number | null;
  profitFactor: number | null;
  winRatePct: number | null;
  tradeCount: number | null;
  reliability: string;
}
