import { useCallback, useEffect, useState } from 'react';
import type { WatchlistItem } from '../types';

const KEY = 'watchlist_v1';

function loadLocal(): WatchlistItem[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) || '[]');
  } catch {
    return [];
  }
}

function saveLocal(list: WatchlistItem[]) {
  localStorage.setItem(KEY, JSON.stringify(list));
}

export function useWatchlist() {
  const [items, setItems] = useState<WatchlistItem[]>(loadLocal);

  const syncRemote = useCallback(async (list: WatchlistItem[]) => {
    const res = await fetch('/api/watchlist/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: list }),
    });
    const payload = await res.json();
    if (!res.ok || payload.ok === false) {
      throw new Error(payload.error || '관심종목 저장에 실패했습니다.');
    }
    return Array.isArray(payload.items) ? (payload.items as WatchlistItem[]) : list;
  }, []);

  const save = useCallback(async (list: WatchlistItem[]) => {
    saveLocal(list);
    setItems(list);
    try {
      const remoteItems = await syncRemote(list);
      saveLocal(remoteItems);
      setItems(remoteItems);
      return remoteItems;
    } catch {
      return list;
    }
  }, [syncRemote]);

  const refresh = useCallback(async () => {
    const localItems = loadLocal();
    try {
      const res = await fetch('/api/watchlist', { cache: 'no-store' });
      const payload = await res.json();
      const remoteItems = Array.isArray(payload.items) ? (payload.items as WatchlistItem[]) : [];
      if (remoteItems.length > 0 || localItems.length === 0) {
        saveLocal(remoteItems);
        setItems(remoteItems);
        return remoteItems;
      }
      const synced = await syncRemote(localItems);
      saveLocal(synced);
      setItems(synced);
      return synced;
    } catch {
      setItems(localItems);
      return localItems;
    }
  }, [syncRemote]);

  const add = useCallback(async (code: string, name: string, market: string) => {
    const current = loadLocal();
    if (current.find((x) => x.code === code && x.market === market)) return;
    let price: number | undefined;
    let change_pct: number | undefined;
    let resolvedName = name;
    try {
      const res = await fetch(`/api/stock/${code}?market=${encodeURIComponent(market)}`, { cache: 'no-store' });
      const d = await res.json();
      if (!d.error) {
        price = d.price;
        change_pct = d.change_pct;
        resolvedName = d.name || name;
      }
    } catch {
      // 가격 조회 실패 시에도 관심종목 자체는 저장한다.
    }
    await save([...current, { code, name: resolvedName, market, price, change_pct }]);
  }, [save]);

  const remove = useCallback(async (code: string) => {
    const next = loadLocal().filter((x) => x.code !== code);
    await save(next);
  }, [save]);

  const refreshPrices = useCallback(async () => {
    const current = loadLocal();
    if (!current.length) return;
    const updated = await Promise.all(current.map(async (item) => {
      try {
        const res = await fetch(`/api/stock/${item.code}?market=${encodeURIComponent(item.market)}`, { cache: 'no-store' });
        const d = await res.json();
        if (!d.error) return { ...item, price: d.price, change_pct: d.change_pct };
      } catch {
        // 개별 종목 시세 실패는 기존 값을 유지한다.
      }
      return item;
    }));
    await save(updated);
  }, [save]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { items, add, remove, refreshPrices, refresh };
}
