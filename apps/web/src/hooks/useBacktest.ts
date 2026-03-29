import { useCallback, useEffect, useState } from 'react';
import { getJSON } from '../api/client';
import type { BacktestData, BacktestQuery } from '../types';

const BACKTEST_MARKET_PRESETS = {
  // kospi: {
  //   initial_cash: 10_000_000,
  //   max_positions: 5,
  //   max_holding_days: 15,
  //   rsi_min: 45,
  //   rsi_max: 62,
  //   volume_ratio_min: 1.0,
  //   stop_loss_pct: 5,
  //   take_profit_pct: null,
  // },
  // nasdaq: {
  //   initial_cash: 10_000,
  //   max_positions: 5,
  //   max_holding_days: 30,
  //   rsi_min: 45,
  //   rsi_max: 68,
  //   volume_ratio_min: 1.2,
  //   stop_loss_pct: null,
  //   take_profit_pct: null,
  // },

  kospi: {
    initial_cash: 10_000_000,
    max_positions: 5,
    max_holding_days: 15,
    rsi_min: 45,
    rsi_max: 62,
    volume_ratio_min: 1.0,
    stop_loss_pct: 5,
    take_profit_pct: null,
    adx_min: 10,
    mfi_min: 20,
    mfi_max: 80,
    bb_pct_min: 0.05,
    bb_pct_max: 0.95,
    stoch_k_min: 10,
    stoch_k_max: 90,
  },
  nasdaq: {
    initial_cash: 10_000,
    max_positions: 5,
    max_holding_days: 30,
    rsi_min: 45,
    rsi_max: 68,
    volume_ratio_min: 1.2,
    stop_loss_pct: null,
    take_profit_pct: null,
    adx_min: 10,
    mfi_min: 20,
    mfi_max: 80,
    bb_pct_min: 0.05,
    bb_pct_max: 0.95,
    stoch_k_min: 10,
    stoch_k_max: 90,
  },
};
export function defaultBacktestQuery(marketScope: BacktestQuery['market_scope'] = 'kospi'): BacktestQuery {
  const preset = BACKTEST_MARKET_PRESETS[marketScope];
  return {
    market_scope: marketScope,
    lookback_days: 1095,
    ...preset,
  };
}

export const DEFAULT_BACKTEST_QUERY: BacktestQuery = defaultBacktestQuery('kospi');

const BACKTEST_QUERY_STORAGE_KEY = 'backtest_query_v2';

function buildQueryString(query: BacktestQuery) {
  const params = new URLSearchParams();
  params.set('market_scope', query.market_scope);
  params.set('lookback_days', String(query.lookback_days));
  params.set('initial_cash', String(query.initial_cash));
  params.set('max_positions', String(query.max_positions));
  params.set('max_holding_days', String(query.max_holding_days));
  params.set('rsi_min', String(query.rsi_min));
  params.set('rsi_max', String(query.rsi_max));
  params.set('volume_ratio_min', String(query.volume_ratio_min));
  if (query.stop_loss_pct !== null && query.stop_loss_pct !== undefined) {
    params.set('stop_loss_pct', String(query.stop_loss_pct));
  }
  if (query.take_profit_pct !== null && query.take_profit_pct !== undefined) {
    params.set('take_profit_pct', String(query.take_profit_pct));
  }

  if (query.adx_min !== null && query.adx_min !== undefined) {
    params.set('adx_min', String(query.adx_min));
  }
  if (query.mfi_min !== null && query.mfi_min !== undefined) {
    params.set('mfi_min', String(query.mfi_min));
  }
  if (query.mfi_max !== null && query.mfi_max !== undefined) {
    params.set('mfi_max', String(query.mfi_max));
  }
  if (query.bb_pct_min !== null && query.bb_pct_min !== undefined) {
    params.set('bb_pct_min', String(query.bb_pct_min));
  }
  if (query.bb_pct_max !== null && query.bb_pct_max !== undefined) {
    params.set('bb_pct_max', String(query.bb_pct_max));
  }
  if (query.stoch_k_min !== null && query.stoch_k_min !== undefined) {
    params.set('stoch_k_min', String(query.stoch_k_min));
  }
  if (query.stoch_k_max !== null && query.stoch_k_max !== undefined) {
    params.set('stoch_k_max', String(query.stoch_k_max));
  }
  return params.toString();
}
function readNumber(value: unknown, fallback: number) {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function readNullableNumber(value: unknown, fallback: number | null | undefined) {
  if (value === null) return null;
  return typeof value === 'number' && Number.isFinite(value) ? value : (fallback ?? null);
}

function normalizeBacktestQuery(value: unknown): BacktestQuery {
  const raw = value && typeof value === 'object' ? (value as Partial<BacktestQuery>) : {};
  const marketScope = raw.market_scope === 'nasdaq' ? 'nasdaq' : 'kospi';
  const preset = defaultBacktestQuery(marketScope);
  return {
    market_scope: marketScope,
    lookback_days: readNumber(raw.lookback_days, preset.lookback_days),
    initial_cash: readNumber(raw.initial_cash, preset.initial_cash),
    max_positions: readNumber(raw.max_positions, preset.max_positions),
    max_holding_days: readNumber(raw.max_holding_days, preset.max_holding_days),
    rsi_min: readNumber(raw.rsi_min, preset.rsi_min),
    rsi_max: readNumber(raw.rsi_max, preset.rsi_max),
    volume_ratio_min: readNumber(raw.volume_ratio_min, preset.volume_ratio_min),
    stop_loss_pct: readNullableNumber(raw.stop_loss_pct, preset.stop_loss_pct),
    take_profit_pct: readNullableNumber(raw.take_profit_pct, preset.take_profit_pct),

    adx_min: readNullableNumber(raw.adx_min, preset.adx_min),
    mfi_min: readNullableNumber(raw.mfi_min, preset.mfi_min),
    mfi_max: readNullableNumber(raw.mfi_max, preset.mfi_max),
    bb_pct_min: readNullableNumber(raw.bb_pct_min, preset.bb_pct_min),
    bb_pct_max: readNullableNumber(raw.bb_pct_max, preset.bb_pct_max),
    stoch_k_min: readNullableNumber(raw.stoch_k_min, preset.stoch_k_min),
    stoch_k_max: readNullableNumber(raw.stoch_k_max, preset.stoch_k_max),
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

export function useBacktest(initialQuery: BacktestQuery = DEFAULT_BACKTEST_QUERY) {
  const [query, setQuery] = useState<BacktestQuery>(initialQuery);
  const [data, setData] = useState<BacktestData>({});
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading');

  const run = useCallback(async (nextQuery: BacktestQuery) => {
    setStatus('loading');
    try {
      const payload = await getJSON<BacktestData>(`/api/backtest/run?${buildQueryString(nextQuery)}`, { noStore: true });
      setData(payload);
      setQuery(nextQuery);
      setStatus(payload.error ? 'error' : 'ok');
    } catch {
      setStatus('error');
    }
  }, []);

  useEffect(() => {
    run(initialQuery);
  }, [initialQuery, run]);

  return { data, query, status, run, setQuery };
}
