import { useCallback, useEffect, useState } from 'react';
import type { MarketContextData } from '../types';

export function useMarketContext() {
  const [data, setData] = useState<MarketContextData>({});
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading');

  const refresh = useCallback(async () => {
    setStatus('loading');
    try {
      const res = await fetch('/api/market-context/latest', { cache: 'no-store' });
      const d: MarketContextData = await res.json();
      setData(d);
      setStatus(d.error ? 'error' : 'ok');
    } catch {
      setStatus('error');
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { data, status, refresh };
}
