import { useCallback, useEffect, useState } from 'react';
import type { MacroData } from '../types';

export function useMacro() {
  const [data, setData] = useState<MacroData>({});
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading');

  const refresh = useCallback(async () => {
    setStatus('loading');
    try {
      const res = await fetch('/api/macro/latest', { cache: 'no-store' });
      const d: MacroData = await res.json();
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
