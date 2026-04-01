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

export interface ReliabilityGapItem {
  metric?: string;
  current?: number | null;
  required?: number;
  gap?: number | null;
  direction?: string;
  blocking?: boolean;
}

export interface ReliabilityUpliftChange {
  metric?: string;
  from?: number | null;
  to?: number | null;
  delta?: number | null;
}

export interface ReliabilityUpliftPath {
  cost?: number;
  label?: string;
  reason?: string;
  changes?: ReliabilityUpliftChange[];
}

export interface ReliabilityDiagnosticPayload {
  target_label?: string;
  current?: {
    label?: string;
    reason?: string;
    trade_count?: number;
    validation_signals?: number;
    validation_sharpe?: number;
    max_drawdown_pct?: number | null;
    passes_minimum_gate?: boolean;
    is_reliable?: boolean;
  };
  target_reached?: boolean;
  blocking_factors?: ReliabilityGapItem[];
  threshold_gaps?: ReliabilityGapItem[];
  uplift_search?: {
    target_label?: string;
    already_satisfies_target?: boolean;
    searched_candidates?: number;
    feasible?: boolean;
    recommended_path?: ReliabilityUpliftPath | null;
    alternatives?: ReliabilityUpliftPath[];
  };
}

export interface SizeRecommendation {
  quantity?: number;
  reason?: string;
  risk_budget_krw?: number;
  qty_by_risk?: number;
  qty_by_cash?: number;
  qty_by_caps?: number;
  unit_price_krw?: number;
  stop_distance_krw?: number;
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

export interface ExitReasonAnalysisRow {
  key?: string;
  label?: string;
  category?: string;
  count?: number;
  share_of_trades_pct?: number;
  net_pnl_pct?: number;
  gross_pnl_pct?: number;
  gross_profit_pct?: number;
  gross_loss_pct?: number;
  profit_share_pct?: number;
  loss_share_pct?: number;
  avg_pnl_pct?: number;
  median_pnl_pct?: number;
  avg_win_pct?: number;
  avg_loss_pct?: number;
  win_rate_pct?: number;
  loss_rate_pct?: number;
  avg_holding_days?: number;
  raw_reasons?: string[];
}

export interface ExitReasonFocusItem {
  kind?: string;
  key?: string;
  label?: string;
  count?: number;
  summary?: string;
  gross_loss_pct?: number;
  gross_profit_pct?: number;
  loss_share_pct?: number;
  profit_share_pct?: number;
  avg_pnl_pct?: number;
}

export interface ExitScopeWeaknessRow {
  key?: string;
  label?: string;
  count?: number;
  loss_trades?: number;
  gross_loss_pct?: number;
  loss_share_pct?: number;
  net_pnl_pct?: number;
  avg_pnl_pct?: number;
  avg_loss_pct?: number;
  top_reason_key?: string | null;
  top_reason_label?: string | null;
  top_reason_loss_share_pct?: number;
  markets?: string[];
  summary?: string;
}

export interface ExitReasonConcentrationVerdict {
  key?: string;
  label?: string;
  count?: number;
  gross_loss_pct?: number;
  loss_share_pct?: number;
  symbol_count?: number;
  sector_count?: number;
  symbol_distribution_level?: string;
  symbol_distribution_label?: string;
  symbol_top_share_pct?: number;
  sector_distribution_level?: string;
  sector_distribution_label?: string;
  sector_top_share_pct?: number;
  strategy_issue_bias?: string;
  strategy_issue_label?: string;
  top_symbols?: ExitScopeWeaknessRow[];
  top_sectors?: ExitScopeWeaknessRow[];
  summary?: string;
}

export interface ExitReasonAnalysisPayload {
  trade_count?: number;
  gross_loss_pct?: number;
  gross_profit_pct?: number;
  net_pnl_pct?: number;
  reasons?: ExitReasonAnalysisRow[];
  symbol_weaknesses?: ExitScopeWeaknessRow[];
  sector_weaknesses?: ExitScopeWeaknessRow[];
  concentration_verdicts?: ExitReasonConcentrationVerdict[];
  focus_items?: ExitReasonFocusItem[];
  summary_lines?: string[];
}

export interface ExitReasonWeaknessCluster {
  segment?: string;
  segment_label?: string;
  key?: string;
  label?: string;
  count?: number;
  gross_loss_pct?: number;
  loss_share_pct?: number;
  avg_pnl_pct?: number;
  summary?: string;
}

export interface ExitReasonPersistentWeakness {
  key?: string;
  label?: string;
  segments?: string[];
  combined_gross_loss_pct?: number;
  combined_count?: number;
  max_loss_share_pct?: number;
  summary?: string;
}

export interface ValidationSegmentPayload extends Record<string, number | string | Record<string, unknown> | StrategyScorecardPayload | ExitReasonAnalysisPayload | undefined> {
  strategy_scorecard?: StrategyScorecardPayload;
  exit_reason_analysis?: ExitReasonAnalysisPayload;
}

export interface ValidationWalkForwardExitReasonPayload {
  overall?: ExitReasonAnalysisPayload;
  train?: ExitReasonAnalysisPayload;
  validation?: ExitReasonAnalysisPayload;
  oos?: ExitReasonAnalysisPayload;
  weakness_clusters?: ExitReasonWeaknessCluster[];
  persistent_negative_reasons?: ExitReasonPersistentWeakness[];
  headlines?: string[];
}

export interface ValidationResponse {
  ok?: boolean;
  metrics?: Record<string, number | string | Record<string, unknown>>;
  scorecard?: StrategyScorecardPayload;
  reliability_diagnostic?: ReliabilityDiagnosticPayload;
  segments?: {
    train?: ValidationSegmentPayload;
    validation?: ValidationSegmentPayload;
    oos?: ValidationSegmentPayload;
  };
  summary?: {
    windows?: number;
    positive_windows?: number;
    positive_window_ratio?: number;
    oos_reliability?: string;
    composite_score?: number;
    reliability_diagnostic?: ReliabilityDiagnosticPayload;
    exit_reason_analysis?: ValidationWalkForwardExitReasonPayload;
  };
}

export interface WalkForwardDiagnosisPayload {
  label?: string;
  target_label?: string;
  summary_lines?: string[];
  strengths?: string[];
  blockers?: Array<{
    metric?: string;
    current?: number;
    threshold?: number;
    direction?: string;
    severity?: string;
    summary?: string;
  }>;
  target_adjustments?: Array<{
    metric?: string;
    current?: number;
    target?: number;
    gap?: number;
    direction?: string;
    summary?: string;
  }>;
}

export interface ValidationDiagnosticsResponse {
  ok?: boolean;
  validation?: ValidationResponse;
  diagnosis?: WalkForwardDiagnosisPayload;
  research?: {
    target_label?: string;
    base_label?: string;
    best_label?: string;
    trials_run?: number;
    trial_limit?: number;
    improvement_found?: boolean;
    notes?: string[];
    errors?: string[];
    suggestions?: Array<{
      probe_label?: string;
      rationale?: string;
      label?: string;
      reached_target?: boolean;
      improvement?: number;
      changes?: string[];
      patch?: Record<string, unknown>;
      metrics?: Record<string, number>;
      diagnosis?: WalkForwardDiagnosisPayload;
    }>;
  };
  error?: string;
}

export interface PersistedValidationSettingsResponse {
  ok?: boolean;
  query?: Record<string, unknown>;
  settings?: Record<string, unknown>;
  saved_at?: string;
  source?: string;
  error?: string;
}

export interface QuantOpsDecisionPayload {
  status?: string;
  label?: string;
  summary?: string;
  hard_reasons?: string[];
}

export interface QuantOpsGuardrailsPayload {
  can_save?: boolean;
  can_apply?: boolean;
  reasons?: string[];
}

export interface QuantOpsSearchResultPayload {
  available?: boolean;
  version?: string;
  optimized_at?: string;
  is_stale?: boolean;
  global_params?: Record<string, unknown>;
  param_count?: number;
  per_symbol_count?: number;
  n_symbols_optimized?: number;
  n_reliable?: number;
  n_medium?: number;
  global_overlay_source?: string;
  context?: {
    market?: string;
    top_n?: number;
    symbols?: string[];
    lookback_days?: number;
    validation_days?: number;
  };
  source?: string;
}

export interface QuantOpsCandidatePayload {
  id?: string;
  created_at?: string;
  saved_at?: string;
  applied_at?: string;
  source?: string;
  strategy_label?: string;
  search_version?: string;
  search_optimized_at?: string;
  search_is_stale?: boolean;
  base_query?: Record<string, unknown>;
  candidate_query?: Record<string, unknown>;
  settings?: Record<string, unknown>;
  patch?: Record<string, unknown>;
  patch_lines?: string[];
  metrics?: {
    oos_return_pct?: number;
    profit_factor?: number;
    max_drawdown_pct?: number;
    trade_count?: number;
    win_rate_pct?: number;
    positive_window_ratio?: number;
    windows?: number;
    reliability?: string;
    composite_score?: number;
    expected_shortfall_5_pct?: number;
    return_p05_pct?: number;
    reliability_target_reached?: boolean;
  };
  decision?: QuantOpsDecisionPayload;
  guardrails?: QuantOpsGuardrailsPayload;
  diagnosis?: WalkForwardDiagnosisPayload;
  research?: ValidationDiagnosticsResponse['research'];
  validation?: ValidationResponse;
  save_note?: string;
  runtime_candidate_source_mode?: string;
}

export interface QuantOpsCandidateStatePayload {
  status?: string;
  active?: boolean;
  reasons?: string[];
  candidate_id?: string;
  search_version?: string;
  baseline_matches?: boolean;
}

export interface QuantOpsRuntimeApplyPayload {
  available?: boolean;
  status?: string;
  active?: boolean;
  reasons?: string[];
  candidate_id?: string;
  applied_at?: string;
  applied_symbol_count?: number;
  applied_symbols?: string[];
  version?: string;
  effective_source?: string;
  source?: string;
  engine_state?: string;
  next_run_at?: string;
  runtime_candidate_source_mode?: string;
}

export interface QuantOpsSymbolApprovalPayload {
  status?: string;
  note?: string;
  reason?: string;
  updated_at?: string;
  candidate_id?: string;
}

export interface QuantOpsSymbolSearchPayload {
  symbol?: string;
  search_version?: string;
  search_optimized_at?: string;
  search_is_stale?: boolean;
  patch?: Record<string, unknown>;
  patch_lines?: string[];
  snapshot?: Record<string, unknown>;
}

export interface QuantOpsSymbolWorkflowItemPayload {
  symbol?: string;
  search_candidate?: QuantOpsSymbolSearchPayload;
  latest_candidate?: QuantOpsCandidatePayload;
  approval?: QuantOpsSymbolApprovalPayload;
  saved_candidate?: QuantOpsCandidatePayload;
  latest_guardrails?: QuantOpsGuardrailsPayload;
  saved_guardrails?: QuantOpsGuardrailsPayload;
  runtime?: {
    applied?: boolean;
    candidate_id?: string;
    applied_at?: string;
  };
}

export interface QuantOpsWorkflowResponse {
  ok?: boolean;
  search_result?: QuantOpsSearchResultPayload;
  search_handoff?: {
    requested_at?: string;
    completed_at?: string;
    status?: string;
    error?: string;
    candidate_id?: string;
    search_version?: string;
    decision_status?: string;
    decision_label?: string;
    query?: Record<string, unknown>;
    settings?: Record<string, unknown>;
  };
  latest_candidate?: QuantOpsCandidatePayload;
  latest_candidate_state?: QuantOpsCandidateStatePayload;
  saved_candidate?: QuantOpsCandidatePayload;
  saved_candidate_state?: QuantOpsCandidateStatePayload;
  symbol_candidates?: QuantOpsSymbolWorkflowItemPayload[];
  symbol_summary?: {
    search_count?: number;
    validated_count?: number;
    approved_count?: number;
    saved_count?: number;
    runtime_applied_count?: number;
  };
  latest_symbol_candidates?: Record<string, QuantOpsCandidatePayload>;
  saved_symbol_candidates?: Record<string, QuantOpsCandidatePayload>;
  runtime_apply?: QuantOpsRuntimeApplyPayload;
  stage_status?: Record<string, string>;
  notes?: string[];
  error?: string;
}

export interface QuantOpsActionResponse {
  ok?: boolean;
  symbol?: string;
  candidate?: QuantOpsCandidatePayload;
  approval?: QuantOpsSymbolApprovalPayload;
  guardrails?: QuantOpsGuardrailsPayload;
  symbol_apply?: Record<string, unknown>;
  runtime_apply?: QuantOpsRuntimeApplyPayload;
  workflow?: QuantOpsWorkflowResponse;
  engine?: EngineStatusResponse;
  error?: string;
  details?: Record<string, unknown>;
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
