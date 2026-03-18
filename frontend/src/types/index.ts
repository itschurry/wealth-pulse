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
  price?: number;
  change_pct?: number;
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
