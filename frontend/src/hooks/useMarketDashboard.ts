import { useCallback, useEffect, useState } from 'react';
import type { MarketDashboardData } from '../types';

const CLIENT_CACHE_TTL = 60_000;

let cachedDashboard: MarketDashboardData | null = null;
let cachedAt = 0;

export function useMarketDashboard() {
  const [data, setData] = useState<MarketDashboardData>(cachedDashboard || {});
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>(cachedDashboard ? 'ok' : 'loading');

  const refresh = useCallback(async (force = false) => {
    const isFresh = cachedDashboard && Date.now() - cachedAt < CLIENT_CACHE_TTL;
    if (!force && isFresh) {
      setData(cachedDashboard || {});
      setStatus('ok');
      return;
    }

    if (!cachedDashboard) {
      setStatus('loading');
    }

    try {
      const res = await fetch('/api/market-dashboard', { cache: 'no-store' });
      const next: MarketDashboardData = await res.json();
      cachedDashboard = next;
      cachedAt = Date.now();
      setData(next);
      setStatus(next.error ? 'error' : 'ok');
    } catch {
      setStatus(cachedDashboard ? 'ok' : 'error');
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { data, status, refresh };
}
