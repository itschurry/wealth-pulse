import { useState, useEffect, useCallback } from 'react';
import type { MarketData } from '../types';

export function useMarket() {
  const [data, setData] = useState<MarketData>({});
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading');
  const [updatedAt, setUpdatedAt] = useState('');

  const refresh = useCallback(async () => {
    setStatus('loading');
    try {
      const res = await fetch('/api/live-market', { cache: 'no-store' });
      const d: MarketData = await res.json();
      setData(d);
      setUpdatedAt(d.updated_at || '');
      setStatus('ok');
    } catch {
      setStatus('error');
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { data, status, updatedAt, refresh };
}
