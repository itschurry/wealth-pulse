export interface EVMetrics {
  expected_value?: number;
  win_probability?: number;
  expected_upside?: number;
  expected_downside?: number;
  expected_holding_days?: number;
  reliability?: string;
}

export interface SizeRecommendation {
  quantity?: number;
  reason?: string;
  risk_budget_krw?: number;
}

export interface DomainSignal {
  code?: string;
  name?: string;
  market?: string;
  sector?: string;
  strategy_type?: string;
  entry_allowed?: boolean;
  reason_codes?: string[];
  ev_metrics?: EVMetrics;
  size_recommendation?: SizeRecommendation;
  execution_realism?: {
    slippage_model_version?: string;
    liquidity_gate_status?: string;
    slippage_bps?: number;
  };
}

export interface SignalsRankResponse {
  ok?: boolean;
  generated_at?: string;
  regime?: string;
  risk_level?: string;
  count?: number;
  signals?: DomainSignal[];
  risk_guard_state?: {
    entry_allowed?: boolean;
    reasons?: string[];
    daily_loss_left?: number;
    cooldown_until?: string;
  };
}

export interface EngineStatusResponse {
  ok?: boolean;
  mode?: {
    mode?: string;
    report_enabled?: boolean;
    paper_enabled?: boolean;
    live_enabled?: boolean;
  };
  execution?: {
    state?: {
      running?: boolean;
      started_at?: string;
      last_run_at?: string;
      last_error?: string;
    };
    account?: {
      equity_krw?: number;
      cash_krw?: number;
      cash_usd?: number;
      positions?: Array<Record<string, unknown>>;
    };
  };
  allocator?: {
    strategy_counts?: Record<string, number>;
    entry_allowed_count?: number;
    blocked_count?: number;
    regime?: string;
    risk_level?: string;
  };
  risk_guard_state?: {
    entry_allowed?: boolean;
    reasons?: string[];
    daily_loss_left?: number;
  };
}

export interface PortfolioStateResponse {
  ok?: boolean;
  account?: {
    equity_krw?: number;
    cash_krw?: number;
    cash_usd?: number;
    positions?: Array<Record<string, unknown>>;
  };
  regime?: string;
  risk_level?: string;
  risk_guard_state?: {
    entry_allowed?: boolean;
    reasons?: string[];
    daily_loss_left?: number;
  };
}

export interface ValidationResponse {
  ok?: boolean;
  metrics?: Record<string, number | string | Record<string, unknown>>;
  segments?: {
    train?: Record<string, number>;
    validation?: Record<string, number>;
    oos?: Record<string, number>;
  };
  summary?: {
    windows?: number;
    positive_windows?: number;
    oos_reliability?: string;
  };
}

export interface ReportsExplainResponse {
  ok?: boolean;
  generated_at?: string;
  analysis?: {
    summary_lines?: string[];
  };
  signal_reasoning?: Array<{
    code?: string;
    strategy_type?: string;
    entry_allowed?: boolean;
    reason_codes?: string[];
  }>;
}
