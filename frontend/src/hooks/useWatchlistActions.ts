import { useCallback, useEffect, useState } from 'react';
import type { WatchlistActionsData, WatchlistItem } from '../types';

export function useWatchlistActions(items: WatchlistItem[]) {
  const [data, setData] = useState<WatchlistActionsData>({ actions: [] });
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading');

  const refresh = useCallback(async () => {
    if (items.length === 0) {
      setData({ actions: [] });
      setStatus('ok');
      return;
    }

    setStatus('loading');
    try {
      const res = await fetch('/api/watchlist-actions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items }),
      });
      const d: WatchlistActionsData = await res.json();
      setData({ ...d, actions: d.actions || [] });
      setStatus((d as { error?: string }).error ? 'error' : 'ok');
    } catch {
      setStatus('error');
    }
  }, [items]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { data, status, refresh };
}
