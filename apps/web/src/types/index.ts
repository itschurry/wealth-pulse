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
  analysis_playbook?: {
    market_regime?: string;
    short_term_bias?: 'bullish' | 'neutral' | 'defensive';
    mid_term_bias?: 'bullish' | 'neutral' | 'defensive';
    favored_sectors?: string[];
    avoided_sectors?: string[];
    tactical_setups?: string[];
    invalid_setups?: string[];
    key_risks?: string[];
    event_watchlist?: Array<{
      name?: string;
      timing?: string;
      importance?: string;
      note?: string;
    }>;
    stock_candidates_short_term?: Array<{
      name?: string;
      code?: string;
      market?: string;
      sector?: string;
      thesis?: string;
      action?: 'buy' | 'watch' | 'avoid';
      confidence?: number;
      reasons?: string[];
      risks?: string[];
      technical_snapshot?: TechnicalSnapshot | null;
      technical_view?: string;
      setup_quality?: string;
    }>;
    stock_candidates_mid_term?: Array<{
      name?: string;
      code?: string;
      market?: string;
      sector?: string;
      thesis?: string;
      action?: 'buy' | 'watch' | 'avoid';
      confidence?: number;
      reasons?: string[];
      risks?: string[];
      technical_snapshot?: TechnicalSnapshot | null;
      technical_view?: string;
      setup_quality?: string;
    }>;
    gating_rules?: string[];
    date?: string;
    generated_at?: string;
  };
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
  horizon?: 'short_term' | 'mid_term';
  gate_status?: 'passed' | 'blocked' | 'caution';
  gate_reasons?: string[];
  playbook_alignment?: number;
  ai_thesis?: string;
  playbook_ref?: string | null;
  technical_snapshot?: TechnicalSnapshot | null;
  technical_view?: string | null;
  setup_quality?: string | null;
}

export interface RecommendationsData {
  generated_at?: string;
  date?: string;
  strategy?: string;
  universe?: string;
  playbook_ref?: string | null;
  signal_counts?: Record<string, number>;
  recommendations: RecommendationItem[];
  rejected_candidates?: RecommendationItem[];
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
  atr14?: number | null;
  atr14_pct?: number | null;
  breakout_20d?: boolean | null;
  breakout_20d_high?: number | null;
  trend?: 'bullish' | 'bearish' | 'neutral';

  adx14?: number | null;
  mfi14?: number | null;
  bb_upper?: number | null;
  bb_lower?: number | null;
  bb_pct?: number | null;
  obv_trend?: 'up' | 'down' | 'flat' | null;
  stoch_k?: number | null;
  stoch_d?: number | null;
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
  theme_score?: number;
  matched_themes?: string[];
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
  theme_score?: number;
  theme_hit_count?: number;
  matched_themes?: string[];
  keyword_gate_passed?: boolean;
  horizon?: 'short_term' | 'mid_term';
  gate_status?: 'passed' | 'blocked' | 'caution';
  gate_reasons?: string[];
  playbook_alignment?: number;
  ai_thesis?: string;
  technical_snapshot?: TechnicalSnapshot | null;
  technical_view?: string | null;
  setup_quality?: string | null;
  // Phase 5: 신뢰도 정보 필드 추가
  strategy_reliability?: 'high' | 'medium' | 'low' | 'insufficient';
  validation_trades?: number;
  validation_sharpe?: number;
  is_reliable?: boolean;
  reliability_reason?: string;
}

export interface TodayPicksData {
  generated_at?: string;
  date?: string;
  market_tone?: string;
  strategy?: string;
  playbook_ref?: string | null;
  picks: TodayPickItem[];
  auto_candidates?: TodayPickItem[];
  auto_candidate_limit?: number;
  auto_candidate_total?: number;
  auto_candidate_market_counts?: Record<string, number>;
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
  gate_status?: 'passed' | 'blocked' | 'caution';
  gate_reasons?: string[];
  horizon?: 'short_term' | 'mid_term';
  playbook_alignment?: number | null;
  ai_thesis?: string | null;
  technical_view?: string | null;
  setup_quality?: string | null;
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

export interface BacktestMetricData {
  final_equity: number;
  total_return_pct: number;
  cagr_pct: number;
  max_drawdown_pct: number;
  trade_count: number;
  win_rate_pct: number;
  avg_trade_return_pct: number;
  sharpe: number;
}

export interface BacktestTrade {
  code: string;
  name: string;
  entry_date: string;
  exit_date: string;
  entry_price: number;
  exit_price: number;
  shares: number;
  pnl: number;
  pnl_pct: number;
  holding_days: number;
  reason: string;
}

export interface BacktestEquityPoint {
  date: string;
  cash: number;
  market_value: number;
  equity: number;
  positions: Array<{
    code: string;
    name: string;
    market?: string;
    shares: number;
    price: number;
    value: number;
  }>;
}

export interface BacktestQuery {
  market_scope: 'kospi' | 'nasdaq';
  lookback_days: number;
  initial_cash: number;
  max_positions: number;
  max_holding_days: number;
  rsi_min: number;
  rsi_max: number;
  volume_ratio_min: number;
  stop_loss_pct?: number | null;
  take_profit_pct?: number | null;

  adx_min?: number | null;
  mfi_min?: number | null;
  mfi_max?: number | null;
  bb_pct_min?: number | null;
  bb_pct_max?: number | null;
  stoch_k_min?: number | null;
  stoch_k_max?: number | null;
}
export interface BacktestData {
  generated_at?: string;
  universe?: string;
  strategy?: string;
  config?: {
    initial_cash?: number;
    base_currency?: 'KRW' | 'USD';
    max_positions?: number;
    buy_fee_rate?: number;
    sell_fee_rate?: number;
    max_holding_days?: number;
    lookback_days?: number;
    markets?: string[];
    rsi_min?: number;
    rsi_max?: number;
    volume_ratio_min?: number;
    adx_min?: number | null;
    mfi_min?: number | null;
    mfi_max?: number | null;
    bb_pct_min?: number | null;
    bb_pct_max?: number | null;
    stoch_k_min?: number | null;
    stoch_k_max?: number | null;
    stop_loss_pct?: number | null;
    take_profit_pct?: number | null;
    market_profiles?: Record<string, {
      market?: string;
      max_positions?: number;
      max_holding_days?: number;
      rsi_min?: number;
      rsi_max?: number;
      volume_ratio_min?: number;
      stop_loss_pct?: number | null;
      take_profit_pct?: number | null;
      signal_interval?: string;
      signal_range?: string;
    }>;
  };
  symbols?: Array<{
    code: string;
    name: string;
    market?: string;
  }>;
  metrics?: BacktestMetricData;
  trades?: BacktestTrade[];
  equity_curve?: BacktestEquityPoint[];
  error?: string;
}

export interface PaperStrategyProfile {
  market: 'KOSPI' | 'NASDAQ';
  max_positions: number;
  max_holding_days: number;
  rsi_min: number;
  rsi_max: number;
  volume_ratio_min: number;
  adx_min?: number | null;
  mfi_min?: number | null;
  mfi_max?: number | null;
  bb_pct_min?: number | null;
  bb_pct_max?: number | null;
  stoch_k_min?: number | null;
  stoch_k_max?: number | null;
  stop_loss_pct?: number | null;
  take_profit_pct?: number | null;
  signal_interval: '1m' | '2m' | '5m' | '15m' | '30m' | '60m' | '90m' | '1d';
  signal_range: '1d' | '5d' | '1mo' | '3mo' | '6mo' | '1y';
}

export interface PaperPosition {
  code: string;
  name: string;
  market: 'KOSPI' | 'NASDAQ';
  currency: 'KRW' | 'USD';
  quantity: number;
  entry_ts?: string;
  avg_price_krw: number;
  avg_price_local: number;
  last_price_krw: number;
  last_price_local: number;
  fx_rate: number;
  market_value_krw: number;
  unrealized_pnl_krw: number;
  unrealized_pnl_pct: number;
  updated_at?: string;
}

export interface PaperOrderEvent {
  order_id: string;
  ts: string;
  side: 'buy' | 'sell';
  order_type: 'market' | 'limit';
  code: string;
  name: string;
  market: 'KOSPI' | 'NASDAQ';
  quantity: number;
  filled_price_local: number;
  filled_price_krw: number;
  fx_rate: number;
  notional_local?: number;
  notional_krw: number;
  fee_local?: number;
  fee_krw: number;
  realized_pnl_local?: number;
  realized_pnl_krw: number;
  status: 'filled';
}

export interface PaperAccountData {
  mode: 'paper';
  base_currency: 'MULTI';
  created_at?: string;
  updated_at?: string;
  paper_days?: number;
  days_elapsed?: number;
  days_left?: number;
  initial_cash_krw: number;
  initial_cash_usd: number;
  cash_krw: number;
  cash_usd: number;
  market_value_krw: number;
  market_value_usd: number;
  equity_krw: number;
  starting_equity_krw?: number;
  fx_rate: number;
  realized_pnl_krw: number;
  realized_pnl_usd: number;
  total_fees_krw: number;
  total_fees_usd: number;
  positions: PaperPosition[];
  orders: PaperOrderEvent[];
  error?: string;
}

export interface PaperSeedPositionInput {
  code: string;
  name?: string;
  market: 'KOSPI' | 'NASDAQ';
  quantity: number;
  avg_price_local: number;
}

export interface PaperEngineConfig {
  interval_seconds: number;
  markets: Array<'KOSPI' | 'NASDAQ'>;
  max_positions_per_market: number;
  min_score: number;
  include_neutral: boolean;
  theme_gate_enabled: boolean;
  theme_min_score: number;
  theme_min_news: number;
  theme_priority_bonus?: number;
  theme_focus: Array<'automotive' | 'robotics' | 'physical_ai'>;
  daily_buy_limit: number;
  daily_sell_limit: number;
  max_orders_per_symbol_per_day: number;
  rsi_min: number;
  rsi_max: number;
  volume_ratio_min: number;
  adx_min?: number | null;
  mfi_min?: number | null;
  mfi_max?: number | null;
  bb_pct_min?: number | null;
  bb_pct_max?: number | null;
  stoch_k_min?: number | null;
  stoch_k_max?: number | null;
  min_entry_signals?: number;
  signal_interval: '1m' | '2m' | '5m' | '15m' | '30m' | '60m' | '90m' | '1d';
  signal_range: '1d' | '5d' | '1mo' | '3mo' | '6mo' | '1y';
  stop_loss_pct: number;
  take_profit_pct: number;
  max_holding_days: number;
  market_profiles?: Partial<Record<'KOSPI' | 'NASDAQ', PaperStrategyProfile>>;
}

export interface PaperSkippedItem {
  code?: string;
  name?: string;
  market?: string;
  reason?: string;
}

export interface PaperEngineState {
  running: boolean;
  started_at?: string;
  last_run_at?: string;
  last_error?: string;
  last_summary?: {
    executed_buy_count?: number;
    executed_sell_count?: number;
    candidate_counts_by_market?: Record<string, number>;
    skip_reason_counts?: Record<string, number>;
    skipped?: PaperSkippedItem[];
    closed_markets?: string[];
    market_stats?: Record<string, {
      candidate_count?: number;
      market_closed?: boolean;
      executed_buy_count?: number;
      executed_sell_count?: number;
      skipped_count?: number;
    }>;
  };
  config?: Partial<PaperEngineConfig>;
}
