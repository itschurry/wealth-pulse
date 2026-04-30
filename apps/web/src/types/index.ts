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
  agent_context?: {
    owner?: string;
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
      technical_view?: string;
      setup_quality?: string;
    }>;
  };
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
  commentary_owner?: string | null;
  risk_note?: string | null;
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
  commentary_owner?: string | null;
  risk_note?: string | null;
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
  commentary_owner?: string | null;
  risk_note?: string | null;
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
  market?: string;
  sector?: string;
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

export type StrategyKind = 'trend_following' | 'mean_reversion' | 'defensive';
export type RegimeMode = 'auto' | 'manual';
export type RiskProfile = 'conservative' | 'balanced' | 'aggressive';

export interface PortfolioConstraints {
  market_scope: 'kospi' | 'nasdaq' | 'all';
  initial_cash: number;
  max_positions: number;
  max_holding_days: number;
}

export interface BacktestQuery {
  market_scope: 'kospi' | 'nasdaq' | 'all';
  lookback_days: number;
  strategy_kind: StrategyKind;
  regime_mode: RegimeMode;
  risk_profile: RiskProfile;
  portfolio_constraints: PortfolioConstraints;
  strategy_params: Record<string, number | string | boolean | null>;
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
export interface PositionSizingMeta {
  mode?: string;
  label?: string;
  risk_per_trade_pct?: number;
  previous_default?: string;
  current_default?: string;
  changes_comparison_baseline?: boolean;
  comparison_note?: string;
}

export interface BacktestData {
  generated_at?: string;
  universe?: string;
  strategy?: string;
  strategy_kind?: StrategyKind | string;
  resolved_strategy_kind?: StrategyKind | 'regime_selected' | string;
  regime_mode?: RegimeMode | string;
  resolved_regime?: string;
  risk_profile?: RiskProfile | string;
  portfolio_constraints?: PortfolioConstraints;
  strategy_params?: Record<string, unknown>;
  position_sizing?: string;
  risk_per_trade_pct?: number;
  position_sizing_meta?: PositionSizingMeta;
  execution_summary?: {
    strategy_kind?: StrategyKind | string;
    regime_mode?: RegimeMode | string;
    resolved_strategy_kind?: StrategyKind | string;
    resolved_regime?: string;
    risk_profile?: RiskProfile | string;
    position_sizing?: string;
    risk_per_trade_pct?: number;
    position_sizing_meta?: PositionSizingMeta;
    test_period_days?: number;
    markets?: string[];
    strategy_mix?: Array<{ value?: string; count?: number; share_pct?: number }>;
    regime_mix?: Array<{ value?: string; count?: number; share_pct?: number }>;
    selected_strategies_by_regime?: Array<{
      regime?: string;
      resolved_strategy_kind?: string;
      trade_count?: number;
      strategy_mix?: Array<{ value?: string; count?: number; share_pct?: number }>;
    }>;
  };
  performance_summary?: {
    cagr_pct?: number;
    max_drawdown_pct?: number;
    win_rate_pct?: number;
    profit_factor?: number;
    trade_count?: number;
  };
  parameter_band?: {
    label?: string;
    summary?: string;
    parameter_bands?: Record<string, {
      label?: string;
      selected?: unknown;
      min?: number;
      max?: number;
      step?: number;
      candidates?: number[];
    }>;
  };
  regime_breakdown?: Array<{
    regime?: string;
    trade_count?: number;
    win_rate_pct?: number;
    avg_return_pct?: number;
    profit_factor?: number;
    strategy_kinds?: string[];
  }>;
  failure_modes?: Array<{
    reason?: string;
    count?: number;
    avg_pnl_pct?: number;
  }>;
  scorecard?: {
    composite_score?: number;
    components?: Record<string, number>;
    tail_risk?: Record<string, number>;
  };
  config?: {
    initial_cash?: number;
    base_currency?: 'KRW' | 'USD';
    max_positions?: number;
    buy_fee_rate?: number;
    sell_fee_rate?: number;
    max_holding_days?: number;
    lookback_days?: number;
    markets?: string[];
    strategy_kind?: StrategyKind | string;
    regime_mode?: RegimeMode | string;
    risk_profile?: RiskProfile | string;
    portfolio_constraints?: PortfolioConstraints;
    strategy_params?: Record<string, unknown>;
    position_sizing?: string;
    risk_per_trade_pct?: number;
    position_sizing_meta?: PositionSizingMeta;
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

export interface RuntimeStrategyProfile {
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

export interface RuntimePosition {
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

export interface RuntimeOrderEvent {
  order_id: string;
  trace_id?: string;
  ts: string;
  timestamp?: string;
  submitted_at?: string;
  filled_at?: string;
  side: 'buy' | 'sell';
  order_type: 'market' | 'limit';
  code: string;
  name: string;
  market: 'KOSPI' | 'NASDAQ';
  quantity: number | null;
  filled_quantity?: number | null;
  filled_price_local: number | null;
  filled_price_krw: number | null;
  fx_rate: number | null;
  notional_local?: number | null;
  notional_krw: number | null;
  fee_local?: number | null;
  fee_krw?: number | null;
  realized_pnl_local?: number | null;
  realized_pnl_krw?: number | null;
  status: 'intent' | 'submitted' | 'accepted' | 'partial_fill' | 'filled' | 'failed' | 'canceled';
  execution_status?: string;
  lifecycle_state?: string;
  success?: boolean;
  reason_code?: string;
  failure_reason?: string;
}

export interface RuntimeAccountData {
  mode: 'paper' | 'real' | 'live' | string;
  base_currency: 'MULTI' | 'KRW' | 'USD' | string;
  created_at?: string;
  updated_at?: string;
  days_elapsed?: number;
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
  positions: RuntimePosition[];
  orders: RuntimeOrderEvent[];
  error?: string;
}

export interface RuntimeSeedPositionInput {
  code: string;
  name?: string;
  market: 'KOSPI' | 'NASDAQ';
  quantity: number;
  avg_price_local: number;
}

export interface RuntimeEngineConfig {
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
  rotation?: {
    enabled?: boolean;
    min_score_gap?: number;
    daily_limit?: number;
    min_holding_days?: number;
  };
  market_profiles?: Partial<Record<'KOSPI' | 'NASDAQ', RuntimeStrategyProfile>>;
}

export interface RuntimeSkippedItem {
  code?: string;
  name?: string;
  market?: string;
  reason?: string;
}


export interface RuntimeWorkflowItem {
  signal_key?: string;
  workflow_stage?: string;
  execution_status?: string;
  orderable?: boolean;
  order_quantity?: number;
  blocked_reason?: string;
  last_order_side?: string;
  last_order_success?: boolean;
  last_order_at?: string;
  last_order_reason?: string;
  market?: string;
  code?: string;
  name?: string;
  strategy_name?: string;
  strategy_id?: string;
  final_action?: string;
  timestamp?: string;
  logged_at?: string;
  fetched_at?: string;
  quote_source?: string;
  quote_fetched_at?: string;
  quote_freshness?: string;
  quote_exclusion_reason?: string;
  quote_validation?: {
    grade?: 'A' | 'B' | 'C' | 'D' | string;
    source?: string;
    source_count?: number;
    reason?: string;
    notes?: string[];
    exclusion_reason?: string;
  };
}

export interface RuntimeWorkflowSummary {
  counts?: Record<string, number>;
  lifecycle_counts?: Record<string, number>;
  items?: RuntimeWorkflowItem[];
  count?: number;
}

export interface RuntimeEngineState {
  engine_state?: 'idle' | 'running' | 'paused' | 'stopped' | 'error' | string;
  running: boolean;
  execution_mode?: 'paper' | 'live' | string;
  started_at?: string;
  paused_at?: string;
  stopped_at?: string;
  last_run_at?: string;
  next_run_at?: string;
  last_success_at?: string;
  last_error?: string;
  last_error_at?: string;
  latest_cycle_id?: string;
  today_order_counts?: {
    buy?: number;
    sell?: number;
    failed?: number;
  };
  order_failure_summary?: {
    today_failed?: number;
    insufficient_cash_failed?: number;
    repeated_insufficient_cash?: Array<{
      market?: string;
      code?: string;
      count?: number;
      last_at?: string;
      reason?: string;
    }>;
    top_reason?: string;
    top_reason_count?: number;
    latest_failure_reason?: string;
    latest_failure_at?: string;
    cooldown_recommended?: boolean;
  };
  today_realized_pnl?: number;
  current_equity?: number;
  validation_policy?: {
    validation_gate_enabled?: boolean;
    validation_min_trades?: number;
    validation_min_sharpe?: number;
    validation_block_on_low_reliability?: boolean;
    validation_require_optimized_reliability?: boolean;
  };
  optimized_params?: {
    version?: string;
    optimized_at?: string;
    is_stale?: boolean;
    source?: string;
    effective_source?: string;
  };
  last_summary?: {
    cycle_id?: string;
    started_at?: string;
    finished_at?: string;
    executed_buy_count?: number;
    executed_sell_count?: number;
    candidate_counts_by_market?: Record<string, number>;
    blocked_reason_counts?: Record<string, number>;
    skip_reason_counts?: Record<string, number>;
    skipped?: RuntimeSkippedItem[];
    closed_markets?: string[];
    pnl_snapshot?: {
      realized_today?: number;
      unrealized?: number;
      equity_krw?: number;
    };
    validation_gate_summary?: {
      enabled?: boolean;
      min_trades?: number;
      min_sharpe?: number;
      blocked_reason_counts?: Record<string, number>;
      blocked_count_by_market?: Record<string, number>;
    };
    market_stats?: Record<string, {
      candidate_count?: number;
      market_closed?: boolean;
      executed_buy_count?: number;
      executed_sell_count?: number;
      blocked_count?: number;
      skipped_count?: number;
    }>;
    rotation_summary?: {
      attempted_count?: number;
      executed_count?: number;
      executed?: Array<{
        market?: string;
        sell_code?: string;
        buy_code?: string;
        score_gap?: number;
      }>;
      blocked?: Array<{
        market?: string;
        reason?: string;
        sell_code?: string;
        buy_code?: string;
        score_gap?: number;
      }>;
    };
  };
  config?: Partial<RuntimeEngineConfig>;
  workflow_summary?: RuntimeWorkflowSummary;
  execution_lifecycle_summary?: {
    counts?: Record<string, number>;
    terminal_counts?: Record<string, number>;
    reason_counts?: Record<string, number>;
    count?: number;
    order_count?: number;
  };
}
