export type TabId = 'assistant' | 'market' | 'holdings' | 'analysis' | 'recommendations';

export interface MarketData {
  kospi?: number; kospi_pct?: number;
  kosdaq?: number; kosdaq_pct?: number;
  sp100?: number; sp100_pct?: number;
  nasdaq?: number; nasdaq_pct?: number;
  usd_krw?: number;
  wti?: number; wti_pct?: number;
  gold?: number; gold_pct?: number;
  btc?: number; btc_pct?: number;
  updated_at?: string;
}

export interface AnalysisData {
  generated_at?: string;
  summary_lines?: string[];
  analysis_html?: string;
  date?: string;
  error?: string;
}

export interface MacroItem {
  key: string;
  label: string;
  as_of?: string;
  source?: string;
  display_value?: string;
  summary?: string;
}

export interface MacroData {
  date?: string;
  items?: MacroItem[];
  summary?: string[];
  error?: string;
}

export interface MarketContextData {
  date?: string;
  context?: {
    regime?: string;
    risk_level?: string;
    inflation_signal?: string;
    labor_signal?: string;
    policy_signal?: string;
    yield_curve_signal?: string;
    dollar_signal?: string;
    summary?: string;
    risks?: string[];
    supports?: string[];
  };
  error?: string;
}

export interface MarketDashboardData {
  market?: MarketData;
  macro?: MacroData;
  context?: MarketContextData;
  error?: string;
}

export interface RecommendationItem {
  rank: number;
  name: string;
  ticker: string;
  sector: string;
  signal: '추천' | '중립' | '회피';
  score: number;
  confidence: number;
  risk_level: '낮음' | '중간' | '높음';
  reasons: string[];
  risks: string[];
}

export interface RecommendationsData {
  generated_at?: string;
  date?: string;
  strategy?: string;
  universe?: string;
  signal_counts?: Record<string, number>;
  recommendations: RecommendationItem[];
  backtest?: {
    window?: string;
    hit_rate?: number | null;
    avg_return?: number | null;
    max_drawdown?: number | null;
    note?: string;
  };
  error?: string;
}

export interface WatchlistItem {
  code: string;
  name: string;
  market: string;
  price?: number | null;
  change_pct?: number | null;
}

export interface TechnicalSnapshot {
  current_price?: number | null;
  change_pct?: number | null;
  sma20?: number | null;
  sma60?: number | null;
  volume?: number | null;
  volume_avg20?: number | null;
  volume_ratio?: number | null;
  rsi14?: number | null;
  macd?: number | null;
  macd_signal?: number | null;
  macd_hist?: number | null;
  trend?: 'bullish' | 'bearish' | 'neutral';
}

export interface InvestorFlowSnapshot {
  date?: string;
  foreign_net_1d?: number | null;
  foreign_net_5d?: number | null;
  institution_net_1d?: number | null;
  institution_net_5d?: number | null;
}

export interface StockSearchResult {
  code: string;
  name: string;
  market: string;
}

export interface RecommendedWatchlistItem extends WatchlistItem {
  score: number;
  confidence: number;
  signal: string;
  reasons: string[];
  riskLevel: string;
  evidence: string[];
}

export interface AutoRecommendedItem {
  name: string;
  code?: string;
  market?: string;
  score: number;
  confidence: number;
  signal: string;
  reasons: string[];
  evidence: string[];
  isAuto: true;
  source: 'catalog' | 'search';
}

export interface AssistantRiskSignal {
  title: string;
  detail: string;
  level: 'high' | 'medium';
}

export interface RelatedNewsItem {
  title: string;
  url: string;
  source: string;
  published: string;
  summary?: string;
}

export interface TodayPickItem {
  name: string;
  code?: string;
  market?: string;
  sector?: string;
  signal: string;
  score: number;
  confidence: number;
  reasons: string[];
  risks: string[];
  catalysts: string[];
  related_news: RelatedNewsItem[];
}

export interface TodayPicksData {
  generated_at?: string;
  date?: string;
  market_tone?: string;
  strategy?: string;
  picks: TodayPickItem[];
  error?: string;
}

export interface WatchlistActionItem extends WatchlistItem {
  action: 'buy' | 'hold' | 'sell' | 'watch';
  signal: string;
  score: number;
  confidence: number;
  reasons: string[];
  risks: string[];
  related_news: RelatedNewsItem[];
  technicals?: TechnicalSnapshot | null;
  investor_flow?: InvestorFlowSnapshot | null;
  changed_from_yesterday?: {
    previous_signal?: string;
    score_diff?: number;
  } | null;
}

export interface WatchlistActionsData {
  generated_at?: string;
  date?: string;
  actions: WatchlistActionItem[];
  error?: string;
}

export interface CompareChangeItem {
  name: string;
  ticker?: string;
  status?: 'new' | 'changed';
  current_signal?: string;
  previous_signal?: string;
  score_diff: number;
}

export interface CompareData {
  base_date?: string;
  prev_date?: string;
  summary_lines?: {
    base: string[];
    prev: string[];
  };
  signal_counts?: {
    base: Record<string, number>;
    prev: Record<string, number>;
  };
  recommendation_changes?: CompareChangeItem[];
  today_pick_changes?: CompareChangeItem[];
  context_changes?: Array<{
    field: string;
    previous?: string;
    current?: string;
  }>;
  new_risks?: string[];
  resolved_risks?: string[];
  error?: string;
}
