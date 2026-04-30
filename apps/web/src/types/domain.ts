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

export interface LayerASnapshot {
  layer?: 'A' | string;
  universe_rule?: string;
  scan_time?: string;
  market?: string;
  inclusion_reason?: string;
  source_context?: {
    strategy_id?: string;
    universe_symbol_count?: number;
  };
}

export interface LayerBSnapshot {
  layer?: 'B' | string;
  strategy_id?: string;
  quant_score?: number;
  signal_state?: string;
  quant_tags?: string[];
  technical_snapshot?: {
    current_price?: number;
    volume_ratio?: number;
    rsi14?: number;
    atr14_pct?: number;
    quote_source?: string;
    quote_fetched_at?: string;
    freshness?: 'fresh' | 'stale' | 'invalid' | 'missing' | string;
    freshness_detail?: {
      status?: 'fresh' | 'stale' | 'invalid' | 'missing' | string;
      is_stale?: boolean;
      reason?: string;
      fetched_at?: string;
    };
    validation?: {
      grade?: 'A' | 'B' | 'C' | 'D' | string;
      source?: string;
      source_count?: number;
      reason?: string;
      notes?: string[];
      exclusion_reason?: string | null;
    };
  };
}

export interface LayerCSnapshot {
  layer?: 'C' | string;
  provider?: string;
  provider_status?: string;
  research_unavailable?: boolean;
  research_score?: number | null;
  components?: Record<string, number>;
  warnings?: string[];
  tags?: string[];
  summary?: string;
  ttl_minutes?: number;
  generated_at?: string;
  freshness?: 'fresh' | 'stale' | 'invalid' | 'missing' | string;
  freshness_detail?: {
    status?: 'fresh' | 'stale' | 'invalid' | 'missing' | string;
    is_stale?: boolean;
    ttl_minutes?: number;
    generated_at?: string;
    ingested_at?: string;
    stale_at?: string;
    age_minutes?: number | null;
    reason?: string;
  };
  validation?: {
    grade?: 'A' | 'B' | 'C' | 'D' | string;
    source?: string;
    source_count?: number;
    reason?: string;
    notes?: string[];
    exclusion_reason?: string | null;
  };
}

export interface LayerDSnapshot {
  layer?: 'D' | string;
  allowed?: boolean;
  blocked?: boolean;
  reason_codes?: string[];
  final_allowed_size?: number;
  execution_decision?: string;
  position_cap_state?: string;
  liquidity_state?: string;
  spread_state?: string;
  risk_guard_state?: Record<string, unknown>;
}

export interface LayerESnapshot {
  layer?: 'E' | string;
  final_action?: 'review_for_entry' | 'watch_only' | 'blocked' | 'do_not_touch' | string;
  decision_reason?: string;
  timestamp?: string;
  source_context?: Record<string, unknown>;
}

export interface LayerEventSnapshot {
  layer?: 'A' | 'B' | 'C' | 'D' | 'E' | string;
  status?: string;
  snapshot?: Record<string, unknown>;
}

export interface DomainSignal {
  code?: string;
  name?: string;
  market?: string;
  sector?: string;
  strategy_type?: string;
  score?: number;
  quant_score?: number;
  entry_allowed?: boolean;
  reason_codes?: string[];
  candidate_source?: string;
  candidate_source_label?: string;
  candidate_source_detail?: string;
  candidate_source_tier?: string;
  candidate_source_priority?: number;
  candidate_source_mode?: string;
  /** Legacy compatibility field. Prefer candidate_source_mode in new UI code. */
  candidate_runtime_source_mode?: string;
  candidate_research_source?: string;
  research_status?: string;
  research_unavailable?: boolean;
  research_score?: number | null;
  final_action?: 'review_for_entry' | 'watch_only' | 'blocked' | 'do_not_touch' | string;
  final_action_snapshot?: LayerESnapshot;
  layer_a?: LayerASnapshot;
  layer_b?: LayerBSnapshot;
  layer_c?: LayerCSnapshot;
  layer_d?: LayerDSnapshot;
  layer_e?: LayerESnapshot;
  layer_events?: LayerEventSnapshot[];
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
    reliability_reason?: string;
    freshness?: 'derived' | 'fresh' | 'stale' | 'invalid' | 'missing' | string;
    freshness_detail?: {
      status?: string;
      is_stale?: boolean;
      reason?: string;
    };
    validation?: {
      grade?: 'A' | 'B' | 'C' | 'D' | string;
      source?: string;
      source_count?: number;
      reason?: string;
      notes?: string[];
      exclusion_reason?: string | null;
    };
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

export interface StrategyRegistryItem {
  strategy_id?: string;
  strategy_kind?: string;
  name?: string;
  version?: number;
  enabled?: boolean;
  /** Internal compatibility status. UI must map this to candidate/approved/applied/blocked/stale terms. */
  status?: 'draft' | 'ready' | 'paused' | 'archived';
  market?: string;
  universe_rule?: string;
  scan_cycle?: string;
  enabled_at?: string;
  entry_rule?: string;
  exit_rule?: string;
  params?: Record<string, unknown>;
  risk_limits?: {
    max_positions?: number;
    position_size_pct?: number;
    daily_loss_limit_pct?: number;
    min_liquidity?: number;
    max_spread_pct?: number;
  };
  research_summary?: {
    backtest_return_pct?: number;
    max_drawdown_pct?: number;
    win_rate_pct?: number;
    sharpe?: number;
    walk_forward_return_pct?: number;
  };
}

export interface StrategiesResponse {
  ok?: boolean;
  items?: StrategyRegistryItem[];
  count?: number;
  summary?: {
    total?: number;
    enabled?: number;
    counts?: Record<string, number>;
  };
  error?: string;
}

export interface StrategyMetadataField {
  name?: string;
  label?: string;
  type?: string;
  min?: number;
  max?: number;
  step?: number;
  options?: string[];
}

export interface StrategyMetadataItem {
  strategy_kind?: string;
  label?: string;
  description?: string;
  regimes?: string[];
  editable_fields?: StrategyMetadataField[];
  defaults_by_market?: Record<string, Record<string, unknown>>;
  defaults_by_market_and_risk?: Record<string, Record<string, Record<string, unknown>>>;
  hidden_params?: string[];
  deprecated_params?: string[];
}

export interface StrategiesMetadataResponse {
  ok?: boolean;
  regime_modes?: Array<{ value?: string; label?: string; description?: string }>;
  risk_profiles?: Array<{ value?: string; label?: string; description?: string }>;
  portfolio_fields?: StrategyMetadataField[];
  portfolio_defaults?: Record<string, Record<string, unknown>>;
  available_strategies?: StrategyMetadataItem[];
  default_request?: Record<string, unknown>;
}

export interface ScannerCandidate extends DomainSignal {
  signal_id?: string;
  strategy_id?: string;
  strategy_name?: string;
  signal_state?: string;
  candidate_rank?: number;
  last_scanned_at?: string;
  reasons?: string[];
  risk_check?: {
    passed?: boolean;
    reason_code?: string;
    message?: string;
  };
}

export interface ScannerStatusItem {
  strategy_id?: string;
  strategy_name?: string;
  approval_status?: string;
  enabled?: boolean;
  market?: string;
  universe_rule?: string;
  scan_cycle?: string;
  last_scan_at?: string;
  next_scan_at?: string;
  candidate_count?: number;
  scanned_symbol_count?: number;
  universe_symbol_count?: number;
  strategy_support_count?: number;
  strategy_role?: string;
  scan_duration_ms?: number;
  status?: string;
  top_candidates?: ScannerCandidate[];
}

export interface ScannerStatusResponse {
  ok?: boolean;
  items?: ScannerStatusItem[];
  count?: number;
  refreshing?: boolean;
  source?: 'strategy_scan_cache' | 'live_scan' | string;
}

export interface UniverseSnapshot {
  rule_name?: string;
  market?: string;
  created_at?: string;
  updated_at?: string;
  symbol_count?: number;
  excluded_count?: number;
  freshness?: 'fresh' | 'stale' | 'invalid' | 'missing' | string;
  is_stale?: boolean;
  freshness_detail?: {
    status?: 'fresh' | 'stale' | 'invalid' | 'missing' | string;
    is_stale?: boolean;
    max_age_minutes?: number;
    generated_at?: string;
    age_minutes?: number | null;
    reason?: string;
  };
  validation?: {
    grade?: 'A' | 'B' | 'C' | 'D' | string;
    source?: string;
    source_count?: number;
    reason?: string;
    notes?: string[];
    exclusion_reason?: string | null;
  };
  symbols?: Array<{
    code?: string;
    name?: string;
    market?: string;
    sector?: string;
  }>;
  excluded?: Array<{
    code?: string;
    name?: string;
    market?: string;
    sector?: string;
    reason?: string;
  }>;
  recent_changes?: {
    added?: string[];
    removed?: string[];
    added_count?: number;
    removed_count?: number;
  };
}

export interface UniverseResponse {
  ok?: boolean;
  items?: UniverseSnapshot[];
  count?: number;
}

export interface CandidateResearchSnapshot {
  provider?: string;
  schema_version?: string;
  run_id?: string;
  symbol?: string;
  name?: string;
  market?: string;
  bucket_ts?: string;
  generated_at?: string;
  ingested_at?: string;
  research_score?: number | null;
  components?: Record<string, number>;
  warnings?: string[];
  tags?: string[];
  summary?: string;
  ttl_minutes?: number;
  freshness?: 'fresh' | 'stale' | 'invalid' | 'missing' | string;
  is_stale?: boolean;
  freshness_detail?: {
    status?: 'fresh' | 'stale' | 'invalid' | 'missing' | string;
    is_stale?: boolean;
    ttl_minutes?: number;
    generated_at?: string;
    ingested_at?: string;
    stale_at?: string;
    age_minutes?: number | null;
    reason?: string;
  };
  validation?: {
    grade?: 'A' | 'B' | 'C' | 'D' | string;
    source?: string;
    source_count?: number;
    reason?: string;
    notes?: string[];
    exclusion_reason?: string | null;
  };
}

export interface CandidateResearchHistoryResponse {
  ok?: boolean;
  provider?: string;
  symbol?: string;
  market?: string;
  bucket_start?: string;
  bucket_end?: string;
  descending?: boolean;
  limit?: number;
  count?: number;
  snapshots?: CandidateResearchSnapshot[];
  error?: string;
}

export interface CandidateMonitorSlot {
  market?: string;
  symbol?: string;
  code?: string;
  name?: string;
  strategy_id?: string;
  strategy_name?: string;
  candidate_rank?: number | null;
  last_scanned_at?: string;
  research_status?: string;
  research_unavailable?: boolean;
  snapshot_exists?: boolean;
  snapshot_fresh?: boolean;
  snapshot_generated_at?: string;
  snapshot_research_score?: number | null;
  validation_grade?: string;
  final_action?: string;
  signal_state?: string;
  slot_type?: 'held' | 'core' | 'promotion' | string;
  priority?: number;
  reason?: string;
}

export interface CandidateMonitorPromotionEvent {
  id?: number;
  market?: string;
  symbol?: string;
  name?: string;
  event_type?: string;
  reason?: string;
  created_at?: string;
  slot_type?: string;
  strategy_id?: string;
}

export interface CandidateMonitorMarketWatchlist {
  ok?: boolean;
  market?: string;
  state?: {
    generated_at?: string;
    source?: string;
    session_date?: string;
    core_limit?: number;
    promotion_limit?: number;
    candidate_pool_count?: number;
    active_count?: number;
    held_count?: number;
    metadata?: {
      pool_limit?: number;
      core_selected?: number;
      promotion_selected?: number;
      held_symbols?: string[];
    };
  };
  candidate_pool?: CandidateMonitorSlot[];
  active_slots?: CandidateMonitorSlot[];
  core_slots?: CandidateMonitorSlot[];
  promotion_slots?: CandidateMonitorSlot[];
  held_slots?: CandidateMonitorSlot[];
  events?: CandidateMonitorPromotionEvent[];
}

export interface CandidateMonitorStatusItem {
  market?: string;
  candidate_pool_count?: number;
  active_count?: number;
  core_count?: number;
  promotion_count?: number;
  held_count?: number;
  generated_at?: string;
  session_date?: string;
  source?: string;
  metadata?: {
    pool_limit?: number;
    core_selected?: number;
    promotion_selected?: number;
    held_symbols?: string[];
  };
}

export interface CandidateMonitorStatusResponse {
  ok?: boolean;
  markets?: string[];
  count?: number;
  items?: CandidateMonitorStatusItem[];
  source?: string;
  refresh?: boolean;
  error?: string;
}

export interface CandidateMonitorWatchlistResponse {
  ok?: boolean;
  markets?: string[];
  count?: number;
  items?: CandidateMonitorMarketWatchlist[];
  pending_count?: number;
  pending_items?: CandidateMonitorSlot[];
  source?: string;
  refresh?: boolean;
  error?: string;
}

export interface CandidateMonitorPromotionsResponse {
  ok?: boolean;
  markets?: string[];
  count?: number;
  items?: CandidateMonitorPromotionEvent[];
  source?: string;
  refresh?: boolean;
  error?: string;
}

export interface ResearchStatusResponse {
  ok?: boolean;
  provider?: string;
  status?: string;
  freshness?: string;
  source?: string;
  source_of_truth?: string;
  last_received_at?: string;
  last_generated_at?: string;
  last_run_id?: string;
  accepted_last_run?: number;
  rejected_last_run?: number;
  received_valid_last_run?: number;
  deduped_count_last_run?: number;
  coverage_count?: number;
  fresh_symbol_count?: number;
  stale_symbol_count?: number;
  latest_bucket_ts?: string;
  accept_ratio?: number;
  error?: string;
}

export interface PerformanceSummaryResponse {
  ok?: boolean;
  live?: {
    today_signal_count?: number;
    today_order_count?: number;
    today_filled_count?: number;
    today_reject_count?: number;
    today_screened_block_count?: number;
    total_order_count?: number;
    total_filled_count?: number;
    total_reject_count?: number;
    total_screened_count?: number;
    realized_pnl_krw?: number;
    realized_pnl_usd?: number;
    unrealized_pnl_krw?: number;
    unrealized_pnl_usd?: number;
    total_return_pct?: number;
    initial_cash_krw?: number;
    initial_cash_usd?: number;
    cash_krw?: number;
    cash_usd?: number;
    equity_krw?: number;
    starting_equity_krw?: number;
    fx_rate?: number;
    market_value_krw?: number;
    market_value_usd?: number;
    market_value_krw_only?: number;
    market_value_usd_krw?: number;
    avg_notional_krw?: number;
    positions?: number;
    order_history?: Array<{
      logged_at?: string;
      code?: string;
      name?: string;
      market?: string;
      currency?: 'KRW' | 'USD' | string;
      side?: string;
      quantity?: number | null;
      filled_price_local?: number | null;
      filled_price_krw?: number | null;
      notional_local?: number | null;
      notional_krw?: number | null;
      fx_rate?: number | null;
      status?: string;
      status_label?: string;
      is_filled?: boolean;
      order_id?: string;
      trace_id?: string;
    }>;
    filled_history?: Array<{
      logged_at?: string;
      code?: string;
      name?: string;
      market?: string;
      currency?: 'KRW' | 'USD' | string;
      side?: string;
      quantity?: number | null;
      filled_price_local?: number | null;
      filled_price_krw?: number | null;
      notional_local?: number | null;
      notional_krw?: number | null;
      fx_rate?: number | null;
      status?: string;
      status_label?: string;
      is_filled?: boolean;
      order_id?: string;
      trace_id?: string;
    }>;
    operations_report?: {
      today_signal_count?: number;
      blocked_count?: number;
      blocked_reason_counts?: Record<string, number>;
      execution_counts?: Record<string, number>;
      execution_event_counts?: Record<string, number>;
      strategy_performance?: Array<{
        strategy_id?: string;
        strategy_name?: string;
        submitted_count?: number;
        filled_count?: number;
        failed_count?: number;
      }>;
      data_health?: {
        stale_count?: number;
        data_missing_count?: number;
      };
    };
    alerts?: Array<{
      severity?: 'info' | 'warning' | 'critical' | string;
      alert_code?: string;
      message?: string;
      details?: Record<string, unknown>;
    }>;
  };
}

export interface OperationsReportResponse {
  ok?: boolean;
  generated_at?: string;
  report?: {
    today_signal_count?: number;
    blocked_count?: number;
    blocked_reason_counts?: Record<string, number>;
    execution_counts?: Record<string, number>;
    execution_event_counts?: Record<string, number>;
    strategy_performance?: Array<{
      strategy_id?: string;
      strategy_name?: string;
      submitted_count?: number;
      filled_count?: number;
      failed_count?: number;
    }>;
    data_health?: {
      stale_count?: number;
      data_missing_count?: number;
    };
  };
  alerts?: Array<{
    severity?: 'info' | 'warning' | 'critical' | string;
    alert_code?: string;
    message?: string;
    details?: Record<string, unknown>;
  }>;
}

export interface EngineStatusResponse {
  ok?: boolean;
  error?: string;
  mode?: {
    current_mode?: string;
    mode?: string;
    report_enabled?: boolean;
    paper_enabled?: boolean;
    live_enabled?: boolean;
  };
  execution?: {
    execution_mode?: string;
    state?: {
      execution_mode?: string;
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
      mode?: string;
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
  source?: string;
  generated_at?: string;
  served_at?: string;
  freshness?: 'fresh' | 'stale' | 'derived' | 'missing' | string;
  freshness_detail?: {
    status?: string;
    is_stale?: boolean;
    reason?: string;
    generated_at?: string;
    served_at?: string;
  };
  validation?: {
    grade?: 'A' | 'B' | 'C' | 'D' | string;
    source?: string;
    source_count?: number;
    reason?: string;
    notes?: string[];
    exclusion_reason?: string;
  };
  segments?: {
    train?: ValidationSegmentPayload & ValidationResponse;
    validation?: ValidationSegmentPayload & ValidationResponse;
    oos?: ValidationSegmentPayload & ValidationResponse;
  };
  summary?: {
    windows?: number;
    positive_windows?: number;
    positive_window_ratio?: number;
    oos_reliability?: string;
    composite_score?: number;
    reliability_diagnostic?: ReliabilityDiagnosticPayload;
    exit_reason_analysis?: ValidationWalkForwardExitReasonPayload;
    validation?: ValidationResponse['validation'];
    freshness?: ValidationResponse['freshness'];
    freshness_detail?: ValidationResponse['freshness_detail'];
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

export interface ConfigStateSnapshotDto {
  status?: 'draft' | 'saved' | 'approved' | 'applied' | 'displayed';
  query?: Record<string, unknown>;
  settings?: Record<string, unknown>;
  version?: number;
  updated_at?: string;
  source?: string;
}

export interface ValidationConfigStateDto {
  saved?: ConfigStateSnapshotDto | null;
  approved?: ConfigStateSnapshotDto | null;
  applied?: ConfigStateSnapshotDto | null;
  displayed?: ConfigStateSnapshotDto | null;
}

export interface PersistedValidationSettingsResponse {
  ok?: boolean;
  query?: Record<string, unknown>;
  settings?: Record<string, unknown>;
  saved_at?: string;
  version?: number;
  updated_at?: string;
  source?: string;
  state?: ValidationConfigStateDto;
  error?: string;
}

export interface QuantOpsGuardrailPolicyPayload {
  version?: number;
  thresholds?: {
    reject?: {
      blocked_reliability_levels?: string[];
      min_profit_factor?: number;
      min_oos_return_pct?: number;
      max_drawdown_pct?: number;
      min_expected_shortfall_5_pct?: number;
    };
    adopt?: {
      required_reliability?: string;
      min_oos_return_pct?: number;
      min_profit_factor?: number;
      max_drawdown_pct?: number;
      min_positive_window_ratio?: number;
      min_expected_shortfall_5_pct?: number;
    };
    limited_adopt?: {
      allowed_reliability_levels?: string[];
      min_oos_return_pct?: number;
      min_profit_factor?: number;
      max_drawdown_pct?: number;
      min_positive_window_ratio?: number;
      min_expected_shortfall_5_pct?: number;
      min_near_miss_count?: number;
      max_near_miss_count?: number;
    };
    limited_adopt_runtime?: {
      risk_per_trade_pct_multiplier?: number;
      risk_per_trade_pct_cap?: number;
      max_positions_per_market_cap?: number;
      max_symbol_weight_pct_cap?: number;
      max_market_exposure_pct_cap?: number;
    };
  };
}

export interface QuantOpsGuardrailPolicyResponse {
  ok?: boolean;
  policy?: QuantOpsGuardrailPolicyPayload;
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

export interface QuantOpsStrategyCandidatePayload {
  key?: string;
  label?: string;
  summary?: string;
  source?: string;
  reliability?: string;
  is_reliable?: boolean;
  reliability_reason?: string;
  composite_score?: number;
  profit_factor?: number;
  validation_sharpe?: number;
  trade_count?: number;
  max_drawdown_pct?: number;
  patch?: Record<string, unknown>;
  patch_lines?: string[];
}

export interface QuantOpsSearchResultPayload {
  available?: boolean;
  version?: string;
  optimized_at?: string;
  is_stale?: boolean;
  global_params?: Record<string, unknown>;
  param_count?: number;
  per_symbol_count?: number;
  strategy_candidate_count?: number;
  strategy_candidates_ready?: boolean;
  strategy_candidate_payload_missing?: boolean;
  n_symbols_optimized?: number;
  n_reliable?: number;
  n_medium?: number;
  global_overlay_source?: string;
  strategy_candidate_source?: string;
  context?: {
    market?: string;
    top_n?: number;
    symbols?: string[];
    lookback_days?: number;
    validation_days?: number;
  };
  source?: string;
  candidate_count?: number;
  candidates?: QuantOpsStrategyCandidatePayload[];
  strategy_candidates?: QuantOpsStrategyCandidatePayload[];
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
  guardrail_policy?: QuantOpsGuardrailPolicyResponse["policy"] & { saved_at?: string; source?: string };
  diagnosis?: WalkForwardDiagnosisPayload;
  research?: ValidationDiagnosticsResponse['research'];
  validation?: ValidationResponse;
  save_note?: string;
  runtime_candidate_source_mode?: string;
  search_candidate_key?: string;
  search_candidate_label?: string;
  search_candidate_summary?: string;
  search_candidate_source?: string;
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
  guardrail_policy?: QuantOpsGuardrailPolicyResponse["policy"] & { saved_at?: string; source?: string };
}

export interface QuantOpsWorkflowResponse {
  ok?: boolean;
  guardrail_policy?: QuantOpsGuardrailPolicyResponse["policy"] & { saved_at?: string; source?: string };
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
  runtime_apply?: QuantOpsRuntimeApplyPayload;
  stage_status?: Record<string, string>;
  notes?: string[];
  error?: string;
}

export interface QuantOpsActionResponse {
  ok?: boolean;
  candidate?: QuantOpsCandidatePayload;
  guardrails?: QuantOpsGuardrailsPayload;
  runtime_apply?: QuantOpsRuntimeApplyPayload;
  workflow?: QuantOpsWorkflowResponse;
  engine?: EngineStatusResponse;
  error?: string;
  message?: string;
  details?: Record<string, unknown>;
}

export interface ReportsExplainResponse {
  ok?: boolean;
  owner?: string;
  brief_type?: string;
  generated_at?: string;
  summary_lines?: string[];
  brief?: {
    owner?: string;
    brief_type?: string;
    generated_at?: string;
    summary_lines?: string[];
    report_reasoning?: Record<string, unknown>;
    analysis?: {
      summary_lines?: string[];
    };
  };
  analysis?: {
    summary_lines?: string[];
  };
}

export interface LiveMarketResponse {
  kospi?: number;
  kospi_pct?: number;
  kosdaq?: number;
  kosdaq_pct?: number;
  usd_krw?: number;
  nasdaq?: number;
  nasdaq_pct?: number;
  sp100?: number;
  sp100_pct?: number;
  wti?: number;
  wti_pct?: number;
  updated_at?: string;
  market_sessions?: Record<string, {
    label?: string;
    status?: string;
    status_label?: string;
    local_time?: string;
    is_open?: boolean;
    is_trading_day?: boolean;
  }>;
}

export interface MarketContextResponse {
  regime?: string;
  risk_level?: string;
  risks?: string[];
  summary?: string;
  inflation_signal?: string;
  labor_signal?: string;
  policy_signal?: string;
  yield_curve_signal?: string;
  dollar_signal?: string;
}

export interface TodayPickItem {
  code?: string;
  name?: string;
  market?: string;
  signal?: string;
  signal_label?: string;
  expected_value?: number;
  win_probability?: number;
  score?: number;
  confidence?: number;
  reasons?: string[];
  risks?: string[];
}

export interface TodayPicksResponse {
  generated_at?: string;
  picks?: TodayPickItem[];
  auto_candidates?: TodayPickItem[];
  market_tone?: string;
}

export interface RecommendationItem {
  code?: string;
  name?: string;
  market?: string;
  sector?: string;
  ticker?: string;
  signal?: string;
  ev_label?: string;
  signal_label?: string;
  regime?: string;
  risk_level?: string;
  recommendation_reason?: string;
  confidence?: string | number;
  reasons?: string[];
  risks?: string[];
  score?: number;
  expected_value?: number;
  win_probability?: number;
  gate_status?: string;
}

export interface RecommendationsResponse {
  generated_at?: string;
  recommendations?: RecommendationItem[];
  rejected_candidates?: RecommendationItem[];
  risk_guard_state?: Record<string, unknown>;
  regime?: string;
  risk_level?: string;
}

export interface MacroLatestResponse {
  generated_at?: string;
  [key: string]: unknown;
}

export interface WatchlistItem {
  code: string;
  name: string;
  market: string;
  price?: number;
  change_pct?: number;
}

export interface AgentRunSummary {
  candidate_count?: number;
  decisions?: number;
  risk_approved?: number;
  risk_rejected?: number;
  orders_submitted?: number;
  orders_skipped?: number;
  error?: string;
}

export interface AgentRunItem {
  id?: number;
  run_id?: number;
  trigger?: string;
  execution_channel?: string;
  status?: string;
  started_at?: string;
  finished_at?: string;
  created_at?: string;
  summary?: AgentRunSummary;
  [key: string]: unknown;
}

export interface AgentDecisionItem {
  id?: number;
  run_id?: number;
  symbol?: string;
  name?: string;
  market?: string;
  action?: 'BUY' | 'SELL' | 'HOLD' | string;
  confidence?: number;
  schema_valid?: boolean;
  created_at?: string;
  payload?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface AgentOrderItem {
  id?: number;
  run_id?: number;
  symbol?: string;
  name?: string;
  market?: string;
  action?: string;
  execution_channel?: string;
  status?: string;
  created_at?: string;
  submitted_at?: string;
  payload?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface AgentRunsResponse {
  ok?: boolean;
  items?: AgentRunItem[];
  error?: string;
}

export interface AgentDecisionsResponse {
  ok?: boolean;
  items?: AgentDecisionItem[];
  error?: string;
}

export interface AgentOrdersResponse {
  ok?: boolean;
  items?: AgentOrderItem[];
  error?: string;
}

export interface AgentRunResponse {
  ok?: boolean;
  run_id?: number;
  summary?: AgentRunSummary;
  candidate_source?: string;
  decision_source?: string;
  error?: string;
}

export interface AgentRiskConfigResponse {
  ok?: boolean;
  config?: {
    min_confidence?: number;
    min_reward_risk_ratio?: number;
    max_symbol_position_ratio?: number;
    allow_additional_buy?: boolean;
    cooldown_minutes?: number;
    daily_loss_limit_pct?: number;
    max_daily_orders?: number;
    [key: string]: unknown;
  };
  error?: string;
}

export interface AgentBrokerStatusResponse {
  ok?: boolean;
  broker?: string;
  configured?: boolean;
  account_configured?: boolean;
  base_url?: string;
  credentials?: Record<string, string>;
  connectivity_checked?: boolean;
  order_execution_managed_by_runtime?: boolean;
  error?: string;
}

export interface WatchlistResponse {
  items?: WatchlistItem[];
  ok?: boolean;
  error?: string;
}

export interface StockSearchResult {
  name: string;
  code: string;
  market: string;
}

export interface StockSearchResponse {
  results?: StockSearchResult[];
}

export interface WatchlistActionItem extends WatchlistItem {
  technicals?: Record<string, unknown>;
  investor_flow?: Record<string, unknown>;
}

export interface WatchlistAction {
  code?: string;
  name?: string;
  market?: string;
  action?: string;
  reason?: string;
  confidence?: string;
}

export interface WatchlistActionsResponse {
  items?: WatchlistActionItem[];
  actions?: WatchlistAction[];
  error?: string;
}

export interface CandidateResearchLatestResponse {
  ok?: boolean;
  provider?: string;
  symbol?: string;
  market?: string;
  snapshot?: CandidateResearchSnapshot;
  error?: string;
}
