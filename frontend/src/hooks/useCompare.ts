import { useCallback, useEffect, useState } from 'react';
import type { CompareData } from '../types';

export function useCompare() {
  const [data, setData] = useState<CompareData>({});
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading');

  const refresh = useCallback(async () => {
    setStatus('loading');
    try {
      const res = await fetch('/api/compare', { cache: 'no-store' });
      const d: CompareData = await res.json();
      setData(d);
      setStatus((d as { error?: string }).error ? 'error' : 'ok');
    } catch {
      setStatus('error');
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { data, status, refresh };
}
