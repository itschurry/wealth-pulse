import { getJSON } from './client';
import type {
  EngineStatusResponse,
  PortfolioStateResponse,
  ReportsExplainResponse,
  SignalsRankResponse,
  ValidationResponse,
} from '../types/domain';

export function fetchEngineStatus() {
  return getJSON<EngineStatusResponse>('/api/engine/status', { noStore: true });
}

export function fetchSignals(limit = 100) {
  return getJSON<SignalsRankResponse>(`/api/signals/rank?limit=${encodeURIComponent(String(limit))}`, { noStore: true });
}

export function fetchPortfolioState(refresh = true) {
  return getJSON<PortfolioStateResponse>(`/api/portfolio/state?refresh=${refresh ? '1' : '0'}`, { noStore: true });
}

export function fetchValidationBacktest() {
  return getJSON<ValidationResponse>('/api/validation/backtest', { noStore: true });
}

export function fetchValidationWalkForward() {
  return getJSON<ValidationResponse>('/api/validation/walk-forward', { noStore: true });
}

export function fetchReportsExplain() {
  return getJSON<ReportsExplainResponse>('/api/reports/explain', { noStore: true });
}
