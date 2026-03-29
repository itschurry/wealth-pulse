import { useCallback, useMemo, useState } from 'react';
import type { ConsoleLogEntry, ConsoleLogLevel } from '../types/consoleView';

const MAX_LOGS = 120;

function nowIso() {
  return new Date().toISOString();
}

export function useConsoleLogs(initial: ConsoleLogEntry[] = []) {
  const [entries, setEntries] = useState<ConsoleLogEntry[]>(initial);

  const push = useCallback((level: ConsoleLogLevel, message: string, context?: string) => {
    const next: ConsoleLogEntry = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      timestamp: nowIso(),
      level,
      message,
      context,
    };
    setEntries((prev) => [next, ...prev].slice(0, MAX_LOGS));
  }, []);

  const clear = useCallback(() => {
    setEntries([]);
  }, []);

  return useMemo(
    () => ({
      entries,
      push,
      clear,
    }),
    [entries, push, clear],
  );
}
