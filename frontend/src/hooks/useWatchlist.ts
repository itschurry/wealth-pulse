import { useState, useCallback } from 'react';
import type { WatchlistItem } from '../types';

const KEY = 'watchlist_v1';

function load(): WatchlistItem[] {
  try { return JSON.parse(localStorage.getItem(KEY) || '[]'); }
  catch { return []; }
}

export function useWatchlist() {
  const [items, setItems] = useState<WatchlistItem[]>(load);

  const save = useCallback((list: WatchlistItem[]) => {
    localStorage.setItem(KEY, JSON.stringify(list));
    setItems(list);
  }, []);

  const add = useCallback(async (code: string, name: string, market: string) => {
    const current = load();
    if (current.find(x => x.code === code)) return;
    let price: number | undefined;
    let change_pct: number | undefined;
    let resolvedName = name;
    try {
      const res = await fetch(`/api/stock/${code}`, { cache: 'no-store' });
      const d = await res.json();
      if (!d.error) { price = d.price; change_pct = d.change_pct; resolvedName = d.name || name; }
    } catch {}
    save([...current, { code, name: resolvedName, market, price, change_pct }]);
  }, [save]);

  const remove = useCallback((code: string) => {
    save(load().filter(x => x.code !== code));
  }, [save]);

  const refreshPrices = useCallback(async () => {
    const current = load();
    if (!current.length) return;
    const updated = await Promise.all(current.map(async item => {
      try {
        const res = await fetch(`/api/stock/${item.code}`, { cache: 'no-store' });
        const d = await res.json();
        if (!d.error) return { ...item, price: d.price, change_pct: d.change_pct };
      } catch {}
      return item;
    }));
    save(updated);
  }, [save]);

  return { items, add, remove, refreshPrices };
}
