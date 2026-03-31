import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  fetchEngineStatus,
  fetchNotificationStatus,
  fetchPortfolioState,
  fetchReportsExplain,
  fetchSignals,
  fetchValidationWalkForward,
} from '../api/domain';
import { UI_TEXT } from '../constants/uiText';
import type { ConsoleDataState, ConsoleSnapshot } from '../types/consoleView';

const FAST_POLLING_MS = 8_000;
const MID_POLLING_MS = 20_000;
const SLOW_POLLING_MS = 60_000;

function emptySnapshot(): ConsoleSnapshot {
  const nowIso = new Date().toISOString();
  return {
    engine: {},
    signals: {},
    portfolio: {},
    validation: {},
    reports: {},
    notifications: {},
    fetchedAt: nowIso,
  };
}

type SnapshotKey = keyof Omit<ConsoleSnapshot, 'fetchedAt'>;

export function useConsoleData() {
  const [state, setState] = useState<ConsoleDataState>({
    snapshot: emptySnapshot(),
    loading: true,
    hasError: false,
    errorMessage: '',
  });

  const patchSnapshot = useCallback((partial: Partial<ConsoleSnapshot>, hasError: boolean) => {
    setState((prev) => ({
      snapshot: {
        ...prev.snapshot,
        ...partial,
        fetchedAt: new Date().toISOString(),
      },
      loading: false,
      hasError,
      errorMessage: hasError ? UI_TEXT.errors.partialLoadFailed : '',
    }));
  }, []);

  const fetchPartition = useCallback(async (targets: SnapshotKey[]) => {
    const tasks = targets.map((key) => {
      if (key === 'engine') return fetchEngineStatus();
      if (key === 'signals') return fetchSignals(150);
      if (key === 'portfolio') return fetchPortfolioState(true);
      if (key === 'validation') return fetchValidationWalkForward();
      if (key === 'notifications') return fetchNotificationStatus();
      return fetchReportsExplain();
    });
    const results = await Promise.allSettled(tasks);
    const partial: Partial<ConsoleSnapshot> = {};
    let hasError = false;

    results.forEach((result, idx) => {
      const key = targets[idx];
      if (result.status === 'fulfilled') {
        partial[key] = result.value;
      } else {
        hasError = true;
      }
    });
    patchSnapshot(partial, hasError);
  }, [patchSnapshot]);

  const refresh = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, hasError: false, errorMessage: '' }));
    await fetchPartition(['engine', 'signals', 'portfolio', 'validation', 'reports', 'notifications']);
  }, [fetchPartition]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void fetchPartition(['engine', 'portfolio']);
    }, FAST_POLLING_MS);
    return () => window.clearInterval(timer);
  }, [fetchPartition]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void fetchPartition(['signals']);
    }, MID_POLLING_MS);
    return () => window.clearInterval(timer);
  }, [fetchPartition]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void fetchPartition(['validation', 'reports', 'notifications']);
    }, SLOW_POLLING_MS);
    return () => window.clearInterval(timer);
  }, [fetchPartition]);

  return useMemo(
    () => ({
      ...state,
      refresh,
    }),
    [state, refresh],
  );
}
