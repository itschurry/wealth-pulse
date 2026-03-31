export interface EVMetrics {
  expected_value?: number;
  win_probability?: number;
  expected_upside?: number;
  expected_downside?: number;
  expected_holding_days?: number;
  reliability?: string;
}

export interface StrategyScorecardPayload {
  composite_score?: number;
  components?: Record<string, number>;
  tail_risk?: Record<string, number>;
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
  score?: number;
  entry_allowed?: boolean;
  reason_codes?: string[];
  ev_metrics?: EVMetrics;
  size_recommendation?: SizeRecommendation;
  strategy_scorecard?: StrategyScorecardPayload;
  validation_snapshot?: {
    composite_score?: number;
    score_components?: Record<string, number>;
    tail_risk?: Record<string, number>;
    strategy_scorecard?: StrategyScorecardPayload;
    validation_trades?: number;
    trade_count?: number;
    validation_sharpe?: number;
    max_drawdown_pct?: number | null;
    strategy_reliability?: string;
  };
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
      engine_state?: string;
      running?: boolean;
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
      };
      last_summary?: Record<string, unknown>;
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
  scorecard?: StrategyScorecardPayload;
  segments?: {
    train?: Record<string, number | string | Record<string, unknown>>;
    validation?: Record<string, number | string | Record<string, unknown>>;
    oos?: Record<string, number | string | Record<string, unknown>>;
  };
  summary?: {
    windows?: number;
    positive_windows?: number;
    oos_reliability?: string;
    composite_score?: number;
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

export interface NotificationStatusResponse {
  ok?: boolean;
  channel?: string;
  enabled?: boolean;
  configured?: boolean;
  chat_id_configured?: boolean;
  last_sent_at?: string;
  last_error?: string;
}
