import { getJSON, postJSON } from './client';
import type {
  EngineStatusResponse,
  NotificationStatusResponse,
  PortfolioStateResponse,
  QuantOpsActionResponse,
  QuantOpsWorkflowResponse,
  ReportsExplainResponse,
  SignalsRankResponse,
  ValidationDiagnosticsResponse,
  ValidationResponse,
} from '../types/domain';
import type { BacktestQuery } from '../types';
import type { ValidationSettings } from '../hooks/useValidationSettingsStore';

function buildValidationQueryString(query?: BacktestQuery, settings?: ValidationSettings) {
  const params = new URLSearchParams();
  if (query) {
    params.set('market_scope', query.market_scope);
    params.set('lookback_days', String(query.lookback_days));
    params.set('initial_cash', String(query.initial_cash));
    params.set('max_positions', String(query.max_positions));
    params.set('max_holding_days', String(query.max_holding_days));
    params.set('rsi_min', String(query.rsi_min));
    params.set('rsi_max', String(query.rsi_max));
    params.set('volume_ratio_min', String(query.volume_ratio_min));
    if (query.stop_loss_pct !== null && query.stop_loss_pct !== undefined) params.set('stop_loss_pct', String(query.stop_loss_pct));
    if (query.take_profit_pct !== null && query.take_profit_pct !== undefined) params.set('take_profit_pct', String(query.take_profit_pct));
    if (query.adx_min !== null && query.adx_min !== undefined) params.set('adx_min', String(query.adx_min));
    if (query.mfi_min !== null && query.mfi_min !== undefined) params.set('mfi_min', String(query.mfi_min));
    if (query.mfi_max !== null && query.mfi_max !== undefined) params.set('mfi_max', String(query.mfi_max));
    if (query.bb_pct_min !== null && query.bb_pct_min !== undefined) params.set('bb_pct_min', String(query.bb_pct_min));
    if (query.bb_pct_max !== null && query.bb_pct_max !== undefined) params.set('bb_pct_max', String(query.bb_pct_max));
    if (query.stoch_k_min !== null && query.stoch_k_min !== undefined) params.set('stoch_k_min', String(query.stoch_k_min));
    if (query.stoch_k_max !== null && query.stoch_k_max !== undefined) params.set('stoch_k_max', String(query.stoch_k_max));
  }
  if (settings) {
    params.set('training_days', String(settings.trainingDays));
    params.set('validation_days', String(settings.validationDays));
    params.set('walk_forward', settings.walkForward ? 'true' : 'false');
    params.set('validation_min_trades', String(settings.minTrades));
    params.set('objective', settings.objective);
  }
  const queryString = params.toString();
  return queryString ? `?${queryString}` : '';
}

export function fetchEngineStatus() {
  return getJSON<EngineStatusResponse>('/api/engine/status', { noStore: true });
}

export function fetchSignals(limit = 100) {
  return getJSON<SignalsRankResponse>(`/api/signals/rank?limit=${encodeURIComponent(String(limit))}`, { noStore: true });
}

export function fetchPortfolioState(refresh = true) {
  return getJSON<PortfolioStateResponse>(`/api/portfolio/state?refresh=${refresh ? '1' : '0'}`, { noStore: true });
}

export function fetchValidationBacktest(query?: BacktestQuery, settings?: ValidationSettings) {
  return getJSON<ValidationResponse>(`/api/validation/backtest${buildValidationQueryString(query, settings)}`, { noStore: true });
}

export function fetchValidationWalkForward(query?: BacktestQuery, settings?: ValidationSettings) {
  return getJSON<ValidationResponse>(`/api/validation/walk-forward${buildValidationQueryString(query, settings)}`, { noStore: true });
}

export function fetchValidationDiagnostics(query?: BacktestQuery, settings?: ValidationSettings) {
  return getJSON<ValidationDiagnosticsResponse>(`/api/validation/diagnostics${buildValidationQueryString(query, settings)}`, { noStore: true });
}

export function fetchQuantOpsWorkflow() {
  return getJSON<QuantOpsWorkflowResponse>('/api/quant-ops/workflow', { noStore: true });
}

export function revalidateQuantOpsCandidate(query: BacktestQuery, settings: ValidationSettings) {
  return postJSON<QuantOpsActionResponse>('/api/quant-ops/revalidate', { query, settings });
}

export function revalidateQuantOpsSymbolCandidate(symbol: string, query: BacktestQuery, settings: ValidationSettings) {
  return postJSON<QuantOpsActionResponse>('/api/quant-ops/revalidate-symbol', { symbol, query, settings });
}

export function setQuantOpsSymbolApproval(symbol: string, status: 'approved' | 'rejected' | 'hold', note?: string) {
  return postJSON<QuantOpsActionResponse>('/api/quant-ops/set-symbol-approval', { symbol, status, note });
}

export function saveQuantOpsSymbolCandidate(symbol: string, note?: string) {
  return postJSON<QuantOpsActionResponse>('/api/quant-ops/save-symbol-candidate', { symbol, note });
}

export function saveQuantOpsCandidate(candidateId?: string, note?: string) {
  return postJSON<QuantOpsActionResponse>('/api/quant-ops/save-candidate', { candidate_id: candidateId, note });
}

export function applyQuantOpsRuntime(candidateId?: string) {
  return postJSON<QuantOpsActionResponse>('/api/quant-ops/apply-runtime', { candidate_id: candidateId });
}

export function fetchReportsExplain() {
  return getJSON<ReportsExplainResponse>('/api/reports/explain', { noStore: true });
}

export function fetchNotificationStatus() {
  return getJSON<NotificationStatusResponse>('/api/system/notifications/status', { noStore: true });
}
