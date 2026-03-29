import { useState, useEffect, useCallback } from 'react';
import { getJSON } from '../api/client';
import type { RecommendationsData } from '../types';

export function useRecommendations() {
  const [data, setData] = useState<RecommendationsData>({ recommendations: [] });
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading');

  const refresh = useCallback(async () => {
    setStatus('loading');
    try {
      const d = await getJSON<RecommendationsData>('/api/recommendations', { noStore: true });
      if ((d as { error?: string }).error) {
        setData({ recommendations: [], error: (d as { error?: string }).error });
        setStatus('error');
        return;
      }
      setData({ ...d, recommendations: d.recommendations || [] });
      setStatus('ok');
    } catch {
      setStatus('error');
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 3 * 60 * 60 * 1000);
    return () => clearInterval(id);
  }, [refresh]);

  return { data, status, refresh };
}
