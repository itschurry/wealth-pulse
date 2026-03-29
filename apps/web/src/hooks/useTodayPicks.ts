import { useCallback, useEffect, useState } from 'react';
import type { TodayPicksData } from '../types';

export function useTodayPicks() {
  const [data, setData] = useState<TodayPicksData>({ picks: [] });
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading');

  const refresh = useCallback(async () => {
    setStatus('loading');
    try {
      const res = await fetch('/api/today-picks', { cache: 'no-store' });
      const d: TodayPicksData = await res.json();
      if ((d as { error?: string }).error) {
        setData({ picks: [], error: (d as { error?: string }).error });
        setStatus('error');
        return;
      }
      setData({ ...d, picks: d.picks || [] });
      setStatus('ok');
    } catch {
      setStatus('error');
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { data, status, refresh };
}
