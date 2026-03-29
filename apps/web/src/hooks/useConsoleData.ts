import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  fetchEngineStatus,
  fetchPortfolioState,
  fetchReportsExplain,
  fetchSignals,
  fetchValidationWalkForward,
} from '../api/domain';
import { UI_TEXT } from '../constants/uiText';
import type { ConsoleDataState, ConsoleSnapshot } from '../types/consoleView';

const POLLING_MS = 30_000;

function emptySnapshot(): ConsoleSnapshot {
  const nowIso = new Date().toISOString();
  return {
    engine: {},
    signals: {},
    portfolio: {},
    validation: {},
    reports: {},
    fetchedAt: nowIso,
  };
}

export function useConsoleData() {
  const [state, setState] = useState<ConsoleDataState>({
    snapshot: emptySnapshot(),
    loading: true,
    hasError: false,
    errorMessage: '',
  });

  const refresh = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true }));
    const results = await Promise.allSettled([
      fetchEngineStatus(),
      fetchSignals(150),
      fetchPortfolioState(true),
      fetchValidationWalkForward(),
      fetchReportsExplain(),
    ]);

    const [engineResult, signalsResult, portfolioResult, validationResult, reportsResult] = results;
    const hasError = results.some((item) => item.status === 'rejected');
    const nextSnapshot: ConsoleSnapshot = {
      engine: engineResult.status === 'fulfilled' ? engineResult.value : {},
      signals: signalsResult.status === 'fulfilled' ? signalsResult.value : {},
      portfolio: portfolioResult.status === 'fulfilled' ? portfolioResult.value : {},
      validation: validationResult.status === 'fulfilled' ? validationResult.value : {},
      reports: reportsResult.status === 'fulfilled' ? reportsResult.value : {},
      fetchedAt: new Date().toISOString(),
    };

    setState({
      snapshot: nextSnapshot,
      loading: false,
      hasError,
      errorMessage: hasError ? UI_TEXT.errors.partialLoadFailed : '',
    });
  }, []);

  useEffect(() => {
    let mounted = true;
    const refreshSafely = async () => {
      if (!mounted) return;
      await refresh();
    };
    void refreshSafely();
    const timer = window.setInterval(() => {
      void refreshSafely();
    }, POLLING_MS);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, [refresh]);

  return useMemo(
    () => ({
      ...state,
      refresh,
    }),
    [state, refresh],
  );
}
