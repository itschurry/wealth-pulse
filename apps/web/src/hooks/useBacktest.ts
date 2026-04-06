import { useCallback, useEffect, useState } from 'react';
import { getJSON } from '../api/client';
import type { BacktestData, BacktestQuery, PortfolioConstraints, RiskProfile, StrategyKind } from '../types';

function defaultPortfolioConstraints(marketScope: BacktestQuery['market_scope'] = 'kospi'): PortfolioConstraints {
  if (marketScope === 'nasdaq') {
    return { market_scope: 'nasdaq', initial_cash: 10_000, max_positions: 5, max_holding_days: 30 };
  }
  if (marketScope === 'all') {
    return { market_scope: 'all', initial_cash: 10_000_000, max_positions: 6, max_holding_days: 20 };
  }
  return { market_scope: 'kospi', initial_cash: 10_000_000, max_positions: 5, max_holding_days: 15 };
}

function defaultStrategyParams(strategyKind: StrategyKind, marketScope: BacktestQuery['market_scope']): Record<string, number | null> {
  const marketKey = marketScope === 'nasdaq' ? 'NASDAQ' : 'KOSPI';
  if (strategyKind === 'mean_reversion') {
    return {
      rsi_min: marketKey === 'NASDAQ' ? 20 : 18,
      rsi_max: marketKey === 'NASDAQ' ? 44 : 42,
      volume_ratio_min: marketKey === 'NASDAQ' ? 0.9 : 0.85,
      bb_pct_max: marketKey === 'NASDAQ' ? 0.2 : 0.18,
      stoch_k_max: marketKey === 'NASDAQ' ? 28 : 24,
      stop_loss_pct: marketKey === 'NASDAQ' ? 4.5 : 4,
      take_profit_pct: marketKey === 'NASDAQ' ? 10 : 9,
    };
  }
  if (strategyKind === 'defensive') {
    return {
      rsi_min: marketKey === 'NASDAQ' ? 46 : 45,
      rsi_max: marketKey === 'NASDAQ' ? 64 : 63,
      volume_ratio_min: marketKey === 'NASDAQ' ? 1.25 : 1.2,
      stop_loss_pct: marketKey === 'NASDAQ' ? 3.5 : 3,
      take_profit_pct: marketKey === 'NASDAQ' ? 7 : 6,
      trade_suppression_threshold: marketKey === 'NASDAQ' ? 6 : 5.5,
    };
  }
  return {
    rsi_min: 45,
    rsi_max: marketKey === 'NASDAQ' ? 74 : 72,
    volume_ratio_min: marketKey === 'NASDAQ' ? 1.15 : 1.05,
    adx_min: 18,
    stop_loss_pct: marketKey === 'NASDAQ' ? 6 : 5,
    take_profit_pct: null,
  };
}

function syncLegacyFields(strategyParams: Record<string, unknown>) {
  return {
    rsi_min: Number(strategyParams.rsi_min ?? 45),
    rsi_max: Number(strategyParams.rsi_max ?? 62),
    volume_ratio_min: Number(strategyParams.volume_ratio_min ?? 1),
    stop_loss_pct: strategyParams.stop_loss_pct == null ? null : Number(strategyParams.stop_loss_pct),
    take_profit_pct: strategyParams.take_profit_pct == null ? null : Number(strategyParams.take_profit_pct),
    adx_min: strategyParams.adx_min == null ? null : Number(strategyParams.adx_min),
    mfi_min: strategyParams.mfi_min == null ? null : Number(strategyParams.mfi_min),
    mfi_max: strategyParams.mfi_max == null ? null : Number(strategyParams.mfi_max),
    bb_pct_min: strategyParams.bb_pct_min == null ? null : Number(strategyParams.bb_pct_min),
    bb_pct_max: strategyParams.bb_pct_max == null ? null : Number(strategyParams.bb_pct_max),
    stoch_k_min: strategyParams.stoch_k_min == null ? null : Number(strategyParams.stoch_k_min),
    stoch_k_max: strategyParams.stoch_k_max == null ? null : Number(strategyParams.stoch_k_max),
  };
}

export function defaultBacktestQuery(
  marketScope: BacktestQuery['market_scope'] = 'kospi',
  strategyKind: StrategyKind = 'trend_following',
  riskProfile: RiskProfile = 'balanced',
): BacktestQuery {
  const portfolio = defaultPortfolioConstraints(marketScope);
  const strategyParams = defaultStrategyParams(strategyKind, marketScope);
  const maxHoldingDays = Number(strategyParams.max_holding_days ?? portfolio.max_holding_days);
  return {
    market_scope: marketScope,
    lookback_days: 1095,
    strategy_kind: strategyKind,
    regime_mode: 'auto',
    risk_profile: riskProfile,
    portfolio_constraints: { ...portfolio, max_holding_days: maxHoldingDays },
    strategy_params: strategyParams,
    initial_cash: portfolio.initial_cash,
    max_positions: portfolio.max_positions,
    max_holding_days: maxHoldingDays,
    ...syncLegacyFields(strategyParams),
  };
}

export const DEFAULT_BACKTEST_QUERY: BacktestQuery = defaultBacktestQuery('kospi');

const BACKTEST_QUERY_STORAGE_KEY = 'backtest_query_v3';

function buildQueryString(query: BacktestQuery) {
  const params = new URLSearchParams();
  params.set('market_scope', query.market_scope);
  params.set('lookback_days', String(query.lookback_days));
  params.set('strategy_kind', query.strategy_kind);
  params.set('regime_mode', query.regime_mode);
  params.set('risk_profile', query.risk_profile);
  params.set('portfolio_constraints', JSON.stringify(query.portfolio_constraints));
  params.set('strategy_params', JSON.stringify(query.strategy_params));
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
  return params.toString();
}

function readNumber(value: unknown, fallback: number) {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function readNullableNumber(value: unknown, fallback: number | null | undefined) {
  if (value === null) return null;
  return typeof value === 'number' && Number.isFinite(value) ? value : (fallback ?? null);
}

function normalizeStrategyKind(value: unknown): StrategyKind {
  if (value === 'mean_reversion' || value === 'defensive') return value;
  return 'trend_following';
}

function normalizeRiskProfile(value: unknown): RiskProfile {
  if (value === 'conservative' || value === 'aggressive') return value;
  return 'balanced';
}

function normalizeBacktestQuery(value: unknown): BacktestQuery {
  const raw = value && typeof value === 'object' ? (value as Partial<BacktestQuery>) : {};
  const marketScope = raw.market_scope === 'nasdaq'
    ? 'nasdaq'
    : raw.market_scope === 'all'
      ? 'all'
      : 'kospi';
  const strategyKind = normalizeStrategyKind(raw.strategy_kind);
  const riskProfile = normalizeRiskProfile(raw.risk_profile);
  const preset = defaultBacktestQuery(marketScope, strategyKind, riskProfile);
  const portfolioRaw = raw.portfolio_constraints && typeof raw.portfolio_constraints === 'object'
    ? raw.portfolio_constraints
    : {};
  const strategyParams = (raw.strategy_params && typeof raw.strategy_params === 'object'
    ? raw.strategy_params
    : preset.strategy_params) as Record<string, unknown>;
  const maxHoldingDays = readNumber(
    (portfolioRaw as Partial<PortfolioConstraints>).max_holding_days,
    readNumber(raw.max_holding_days, preset.max_holding_days),
  );
  const nextQuery: BacktestQuery = {
    market_scope: marketScope,
    lookback_days: readNumber(raw.lookback_days, preset.lookback_days),
    strategy_kind: strategyKind,
    regime_mode: raw.regime_mode === 'manual' ? 'manual' : 'auto',
    risk_profile: riskProfile,
    portfolio_constraints: {
      market_scope: marketScope,
      initial_cash: readNumber((portfolioRaw as Partial<PortfolioConstraints>).initial_cash, preset.portfolio_constraints.initial_cash),
      max_positions: readNumber((portfolioRaw as Partial<PortfolioConstraints>).max_positions, preset.portfolio_constraints.max_positions),
      max_holding_days: maxHoldingDays,
    },
    strategy_params: strategyParams as Record<string, number | string | boolean | null>,
    initial_cash: readNumber(raw.initial_cash, preset.initial_cash),
    max_positions: readNumber(raw.max_positions, preset.max_positions),
    max_holding_days: maxHoldingDays,
    ...syncLegacyFields(strategyParams),
  };
  return {
    ...nextQuery,
    stop_loss_pct: readNullableNumber(raw.stop_loss_pct, nextQuery.stop_loss_pct),
    take_profit_pct: readNullableNumber(raw.take_profit_pct, nextQuery.take_profit_pct),
    adx_min: readNullableNumber(raw.adx_min, nextQuery.adx_min),
    mfi_min: readNullableNumber(raw.mfi_min, nextQuery.mfi_min),
    mfi_max: readNullableNumber(raw.mfi_max, nextQuery.mfi_max),
    bb_pct_min: readNullableNumber(raw.bb_pct_min, nextQuery.bb_pct_min),
    bb_pct_max: readNullableNumber(raw.bb_pct_max, nextQuery.bb_pct_max),
    stoch_k_min: readNullableNumber(raw.stoch_k_min, nextQuery.stoch_k_min),
    stoch_k_max: readNullableNumber(raw.stoch_k_max, nextQuery.stoch_k_max),
  };
}

export function loadBacktestQuery() {
  try {
    return normalizeBacktestQuery(JSON.parse(localStorage.getItem(BACKTEST_QUERY_STORAGE_KEY) || 'null'));
  } catch {
    return { ...DEFAULT_BACKTEST_QUERY };
  }
}

export function saveBacktestQuery(query: BacktestQuery) {
  localStorage.setItem(BACKTEST_QUERY_STORAGE_KEY, JSON.stringify(query));
}

export function useBacktest(initialQuery: BacktestQuery = DEFAULT_BACKTEST_QUERY, options?: { autoRun?: boolean }) {
  const autoRun = options?.autoRun ?? true;
  const [query, setQuery] = useState<BacktestQuery>(initialQuery);
  const [data, setData] = useState<BacktestData>({});
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>(autoRun ? 'loading' : 'ok');
  const [lastError, setLastError] = useState('');

  const run = useCallback(async (nextQuery: BacktestQuery) => {
    setStatus('loading');
    setLastError('');
    try {
      const payload = await getJSON<BacktestData>(`/api/backtest/run?${buildQueryString(nextQuery)}`, { noStore: true });
      setData(payload);
      setQuery(nextQuery);
      const ok = !payload.error;
      setStatus(ok ? 'ok' : 'error');
      setLastError(payload.error || '');
      return { ok, payload, error: payload.error || '' };
    } catch {
      setStatus('error');
      const error = '백테스트 응답을 불러오지 못했습니다.';
      setLastError(error);
      return { ok: false, payload: null, error };
    }
  }, []);

  useEffect(() => {
    if (!autoRun) return;
    run(initialQuery);
  }, [autoRun, initialQuery, run]);

  return { data, query, status, lastError, run, setQuery };
}
