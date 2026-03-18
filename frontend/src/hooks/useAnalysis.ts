import { useState, useEffect, useCallback } from 'react';
import type { AnalysisData } from '../types';

export function useAnalysis() {
  const [data, setData] = useState<AnalysisData>({});
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading');

  const refresh = useCallback(async () => {
    setStatus('loading');
    try {
      const res = await fetch('/api/analysis', { cache: 'no-store' });
      const d: AnalysisData = await res.json();
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
