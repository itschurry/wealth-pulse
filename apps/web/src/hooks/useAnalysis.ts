import { useState, useEffect, useCallback } from 'react';
import { getJSON } from '../api/client';
import type { AnalysisData } from '../types';

export function useAnalysis() {
  const [data, setData] = useState<AnalysisData>({});
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading');

  const refresh = useCallback(async () => {
    setStatus('loading');
    try {
      const d = await getJSON<AnalysisData>('/api/analysis', { noStore: true });
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
