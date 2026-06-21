import { getJSON, postJSON } from './client';
import type {
  AgentBrokerStatusResponse,
  AgentDecisionsResponse,
  AgentOrdersResponse,
  AgentRiskConfigResponse,
  AgentRunResponse,
  AgentRunsResponse,
  EngineStatusResponse,
  LiveMarketResponse,
  MacroLatestResponse,
  MarketContextResponse,
  PerformanceSummaryResponse,
  PortfolioStateResponse,
  RecommendationsResponse,
  CandidateMonitorPromotionsResponse,
  CandidateMonitorStatusResponse,
  CandidateMonitorWatchlistResponse,
  CandidateResearchHistoryResponse,
  CandidateResearchLatestResponse,
  ResearchStatusResponse,
  ReportsExplainResponse,
  ScannerStatusResponse,
  SignalsRankResponse,
  TodayPicksResponse,
  UniverseResponse,
  WatchlistActionsResponse,
  WatchlistItem,
  WatchlistResponse,
  StockSearchResponse,
} from '../types/domain';

export function fetchEngineSummary() {
  return getJSON<EngineStatusResponse>('/api/engine/summary', { noStore: true });
}

export function fetchEngineStatus() {
  return getJSON<EngineStatusResponse>('/api/engine/status', { noStore: true });
}

export function fetchAgentRuns(limit = 20) {
  return getJSON<AgentRunsResponse>(`/api/agent/runs?limit=${encodeURIComponent(String(limit))}`, { noStore: true });
}

export function fetchAgentDecisions(limit = 50) {
  return getJSON<AgentDecisionsResponse>(`/api/agent/decisions?limit=${encodeURIComponent(String(limit))}`, { noStore: true });
}

export function fetchAgentOrders(limit = 50) {
  return getJSON<AgentOrdersResponse>(`/api/agent/orders?limit=${encodeURIComponent(String(limit))}`, { noStore: true });
}

export function fetchAgentRiskConfig() {
  return getJSON<AgentRiskConfigResponse>('/api/risk/config', { noStore: true });
}

export function fetchAgentBrokerStatus() {
  return getJSON<AgentBrokerStatusResponse>('/api/broker/kis/status', { noStore: true });
}

export async function runAgent(payload: Record<string, unknown> = {}) {
  const response = await postJSON<AgentRunResponse>('/api/agent/run', {
    candidate_source: 'monitor_watchlist',
    decision_source: 'research_snapshot',
    limit: 5,
    mode: 'missing_or_stale',
    include_research_snapshot: true,
    trigger: 'ui_agent_dashboard',
    ...payload,
  });
  return response.data;
}

export function fetchSignals(limit = 100) {
  return getJSON<SignalsRankResponse>(`/api/signals/rank?limit=${encodeURIComponent(String(limit))}`, { noStore: true });
}

export function fetchScannerStatus(refresh = false, cacheOnly = false) {
  return getJSON<ScannerStatusResponse>(
    `/api/scanner/status?refresh=${refresh ? '1' : '0'}&cache_only=${cacheOnly ? '1' : '0'}`,
    { noStore: true },
  );
}

export function fetchUniverse(refresh = false) {
  return getJSON<UniverseResponse>(`/api/universe?refresh=${refresh ? '1' : '0'}`, { noStore: true });
}

export function fetchPerformanceSummary() {
  return getJSON<PerformanceSummaryResponse>('/api/performance/summary', { noStore: true });
}

export function fetchPortfolioState(refresh = true) {
  return getJSON<PortfolioStateResponse>(`/api/portfolio/state?refresh=${refresh ? '1' : '0'}`, { noStore: true });
}

export function fetchResearchStatus(provider = 'default') {
  return getJSON<ResearchStatusResponse>(`/api/research/status?provider=${encodeURIComponent(provider)}`, { noStore: true });
}

export function fetchCandidateMonitorStatus(params?: {
  market?: string[];
  refresh?: boolean;
}) {
  const query = new URLSearchParams();
  params?.market?.forEach((item) => {
    if (item) query.append('market', item);
  });
  if (typeof params?.refresh === 'boolean') query.set('refresh', params.refresh ? '1' : '0');
  const queryString = query.toString();
  return getJSON<CandidateMonitorStatusResponse>(`/api/monitor/status${queryString ? `?${queryString}` : ''}`, { noStore: true });
}

export function fetchCandidateMonitorWatchlist(params?: {
  market?: string[];
  refresh?: boolean;
  limit?: number;
  mode?: 'missing_or_stale' | 'missing_only' | 'stale_only';
}) {
  const query = new URLSearchParams();
  params?.market?.forEach((item) => {
    if (item) query.append('market', item);
  });
  if (typeof params?.refresh === 'boolean') query.set('refresh', params.refresh ? '1' : '0');
  if (typeof params?.limit === 'number') query.set('limit', String(params.limit));
  if (params?.mode) query.set('mode', params.mode);
  const queryString = query.toString();
  return getJSON<CandidateMonitorWatchlistResponse>(`/api/monitor/watchlist${queryString ? `?${queryString}` : ''}`, { noStore: true });
}

export function fetchCandidateMonitorPromotions(params?: {
  market?: string[];
  refresh?: boolean;
  limit?: number;
}) {
  const query = new URLSearchParams();
  params?.market?.forEach((item) => {
    if (item) query.append('market', item);
  });
  if (typeof params?.refresh === 'boolean') query.set('refresh', params.refresh ? '1' : '0');
  if (typeof params?.limit === 'number') query.set('limit', String(params.limit));
  const queryString = query.toString();
  return getJSON<CandidateMonitorPromotionsResponse>(`/api/monitor/promotions${queryString ? `?${queryString}` : ''}`, { noStore: true });
}

export function fetchCandidateResearchHistory(params?: {
  symbol?: string;
  market?: string;
  provider?: string;
  bucketStart?: string;
  bucketEnd?: string;
  descending?: boolean;
  limit?: number;
}) {
  const query = new URLSearchParams();
  if (params?.symbol) query.set('symbol', params.symbol);
  if (params?.market) query.set('market', params.market);
  if (params?.provider) query.set('provider', params.provider);
  if (params?.bucketStart) query.set('bucket_start', params.bucketStart);
  if (params?.bucketEnd) query.set('bucket_end', params.bucketEnd);
  if (typeof params?.limit === 'number') query.set('limit', String(params.limit));
  if (typeof params?.descending === 'boolean') query.set('descending', params.descending ? '1' : '0');
  const queryString = query.toString();
  return getJSON<CandidateResearchHistoryResponse>(`/api/research/snapshots${queryString ? `?${queryString}` : ''}`, { noStore: true });
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

export function fetchCandidateResearchLatest(params: { symbol: string; market: string }) {
  const query = new URLSearchParams({ symbol: params.symbol, market: params.market });
  return getJSON<CandidateResearchLatestResponse>(`/api/research/snapshots/latest?${query.toString()}`, { noStore: true });
}
