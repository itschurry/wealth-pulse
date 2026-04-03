import { getJSON, postJSON } from './client';
import type {
  EngineStatusResponse,
  HannaBriefResponse,
  LiveMarketResponse,
  MacroLatestResponse,
  MarketContextResponse,
  PerformanceSummaryResponse,
  PortfolioStateResponse,
  QuantOpsActionResponse,
  PersistedValidationSettingsResponse,
  QuantOpsGuardrailPolicyResponse,
  QuantOpsWorkflowResponse,
  RecommendationsResponse,
  ResearchSnapshotLatestResponse,
  ResearchSnapshotsResponse,
  ResearchStatusResponse,
  ReportsExplainResponse,
  ScannerStatusResponse,
  SignalsRankResponse,
  StrategiesResponse,
  TodayPicksResponse,
  UniverseResponse,
  ValidationDiagnosticsResponse,
  ValidationResponse,
  WatchlistActionsResponse,
  WatchlistItem,
  WatchlistResponse,
  StockSearchResponse,
} from '../types/domain';
import type { BacktestQuery } from '../types';
import type { ValidationSettings } from '../hooks/useValidationSettingsStore';

function serializeValidationSettings(settings: ValidationSettings) {
  return {
    ...settings,
    runtime_candidate_source_mode: settings.runtimeCandidateSourceMode,
  };
}

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
    params.set('runtime_candidate_source_mode', settings.runtimeCandidateSourceMode);
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

export function fetchStrategies() {
  return getJSON<StrategiesResponse>('/api/strategies', { noStore: true });
}

export function fetchScannerStatus(refresh = false) {
  return getJSON<ScannerStatusResponse>(`/api/scanner/status?refresh=${refresh ? '1' : '0'}`, { noStore: true });
}

export function fetchUniverse(refresh = false) {
  return getJSON<UniverseResponse>(`/api/universe?refresh=${refresh ? '1' : '0'}`, { noStore: true });
}

export function fetchPerformanceSummary() {
  return getJSON<PerformanceSummaryResponse>('/api/performance/summary', { noStore: true });
}

export function toggleStrategyEnabled(strategyId: string, enabled: boolean) {
  return postJSON<StrategiesResponse>('/api/strategies/toggle', { strategy_id: strategyId, enabled });
}

export function saveStrategyPreset(payload: Record<string, unknown>) {
  return postJSON<StrategiesResponse>('/api/strategies/save', payload);
}

export function deleteStrategyPreset(strategyId: string) {
  return postJSON<{ ok: boolean; strategy_id?: string; error?: string }>('/api/strategies/delete', { strategy_id: strategyId });
}

export function fetchPortfolioState(refresh = true) {
  return getJSON<PortfolioStateResponse>(`/api/portfolio/state?refresh=${refresh ? '1' : '0'}`, { noStore: true });
}

export function fetchResearchStatus(provider = 'openclaw') {
  return getJSON<ResearchStatusResponse>(`/api/research/status?provider=${encodeURIComponent(provider)}`, { noStore: true });
}

export function fetchResearchSnapshots(params: {
  symbol: string;
  market: string;
  provider?: string;
  bucketStart?: string;
  bucketEnd?: string;
  descending?: boolean;
  limit?: number;
}) {
  const query = new URLSearchParams();
  query.set('symbol', params.symbol);
  query.set('market', params.market);
  if (params.provider) query.set('provider', params.provider);
  if (params.bucketStart) query.set('bucket_start', params.bucketStart);
  if (params.bucketEnd) query.set('bucket_end', params.bucketEnd);
  if (typeof params.limit === 'number') query.set('limit', String(params.limit));
  if (typeof params.descending === 'boolean') query.set('descending', params.descending ? '1' : '0');
  const queryString = query.toString();
  return getJSON<ResearchSnapshotsResponse>(`/api/research/snapshots${queryString ? `?${queryString}` : ''}`, { noStore: true });
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

export function fetchValidationSettings() {
  return getJSON<PersistedValidationSettingsResponse>('/api/validation/settings', { noStore: true });
}

export async function saveValidationSettings(query: BacktestQuery, settings: ValidationSettings): Promise<PersistedValidationSettingsResponse> {
  const response = await postJSON<PersistedValidationSettingsResponse>('/api/validation/settings/save', { query, settings: serializeValidationSettings(settings) });
  return response.data;
}

export async function resetValidationSettings(): Promise<PersistedValidationSettingsResponse> {
  const response = await postJSON<PersistedValidationSettingsResponse>('/api/validation/settings/reset', {});
  return response.data;
}

export function fetchQuantOpsPolicy() {
  return getJSON<QuantOpsGuardrailPolicyResponse>('/api/quant-ops/policy', { noStore: true });
}

export function saveQuantOpsPolicy(policy: Record<string, unknown>) {
  return postJSON<QuantOpsGuardrailPolicyResponse>('/api/quant-ops/policy/save', { policy });
}

export function resetQuantOpsPolicy() {
  return postJSON<QuantOpsGuardrailPolicyResponse>('/api/quant-ops/policy/reset', {});
}

export function fetchQuantOpsWorkflow() {
  return getJSON<QuantOpsWorkflowResponse>('/api/quant-ops/workflow', { noStore: true });
}

export function revalidateQuantOpsCandidate(query: BacktestQuery, settings: ValidationSettings) {
  return postJSON<QuantOpsActionResponse>('/api/quant-ops/revalidate', { query, settings: serializeValidationSettings(settings) });
}

export function revalidateQuantOpsSymbolCandidate(symbol: string, query: BacktestQuery, settings: ValidationSettings) {
  return postJSON<QuantOpsActionResponse>('/api/quant-ops/revalidate-symbol', { symbol, query, settings: serializeValidationSettings(settings) });
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

export function fetchLiveMarket() {
  return getJSON<LiveMarketResponse>('/api/live-market', { noStore: true });
}

export function fetchMarketContext() {
  return getJSON<MarketContextResponse>('/api/market-context/latest', { noStore: true });
}

export function fetchTodayPicks(date?: string) {
  const qs = date ? `?date=${encodeURIComponent(date)}` : '';
  return getJSON<TodayPicksResponse>(`/api/today-picks${qs}`, { noStore: true });
}

export function fetchRecommendations(date?: string) {
  const qs = date ? `?date=${encodeURIComponent(date)}` : '';
  return getJSON<RecommendationsResponse>(`/api/recommendations${qs}`, { noStore: true });
}

export function fetchMacroLatest() {
  return getJSON<MacroLatestResponse>('/api/macro/latest', { noStore: true });
}

export function fetchHannaBrief(date?: string) {
  const qs = date ? `?date=${encodeURIComponent(date)}` : '';
  return getJSON<HannaBriefResponse>(`/api/hanna/brief${qs}`, { noStore: true });
}

export function fetchReportsIndex() {
  return getJSON<{ dates?: string[] }>('/api/reports/index', { noStore: true });
}

export function fetchWatchlist() {
  return getJSON<WatchlistResponse>('/api/watchlist', { noStore: true });
}

export function saveWatchlist(items: WatchlistItem[]) {
  return postJSON<WatchlistResponse>('/api/watchlist/save', { items });
}

export function fetchWatchlistActions(items: WatchlistItem[]) {
  return postJSON<WatchlistActionsResponse>('/api/watchlist-actions', { items });
}

export function searchStocks(query: string) {
  return getJSON<StockSearchResponse>(`/api/stock-search?q=${encodeURIComponent(query)}`, { noStore: true });
}

export function fetchResearchSnapshotLatest(params: { symbol: string; market: string }) {
  const query = new URLSearchParams({ symbol: params.symbol, market: params.market });
  return getJSON<ResearchSnapshotLatestResponse>(`/api/research/snapshots/latest?${query.toString()}`, { noStore: true });
}
