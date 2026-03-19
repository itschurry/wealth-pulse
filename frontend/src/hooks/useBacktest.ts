import { useCallback, useEffect, useState } from 'react';
import type { BacktestData, BacktestQuery } from '../types';

export const DEFAULT_BACKTEST_QUERY: BacktestQuery = {
  market_scope: 'all',
  lookback_days: 1095,
  initial_cash: 10_000_000,
  max_positions: 5,
  max_holding_days: 30,
  rsi_min: 45,
  rsi_max: 68,
  volume_ratio_min: 1.2,
  stop_loss_pct: 7,
  take_profit_pct: 18,
};

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
  return params.toString();
}

export function useBacktest(initialQuery: BacktestQuery = DEFAULT_BACKTEST_QUERY) {
  const [query, setQuery] = useState<BacktestQuery>(initialQuery);
  const [data, setData] = useState<BacktestData>({});
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading');

  const run = useCallback(async (nextQuery: BacktestQuery) => {
    setStatus('loading');
    try {
      const res = await fetch(`/api/backtest/run?${buildQueryString(nextQuery)}`, { cache: 'no-store' });
      const payload: BacktestData = await res.json();
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
