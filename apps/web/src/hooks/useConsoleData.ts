import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  fetchEngineStatus,
  fetchHannaBrief,
  fetchLiveMarket,
  fetchMacroLatest,
  fetchMarketContext,
  fetchPerformanceSummary,
  fetchPortfolioState,
  fetchRecommendations,
  fetchReportsExplain,
  fetchResearchStatus,
  fetchScannerStatus,
  fetchSignals,
  fetchStrategies,
  fetchTodayPicks,
  fetchUniverse,
  fetchValidationWalkForwardWithOptions,
} from '../api/domain';
import { UI_TEXT } from '../constants/uiText';
import type { ConsoleDataState, ConsoleSnapshot } from '../types/consoleView';
import type { ConsoleTab, ReportTab, TopSection } from '../types/navigation';

const FAST_POLLING_MS = 15_000;
const MID_POLLING_MS = 30_000;
const SLOW_POLLING_MS = 60_000;

type SnapshotKey = keyof Omit<ConsoleSnapshot, 'fetchedAt'>;

interface ConsoleDataRoute {
  section: TopSection;
  consoleTab: ConsoleTab;
  reportTab: ReportTab;
}

interface ConsoleDataProfile {
  signalLimit: number;
  initialTargets: SnapshotKey[];
  fastTargets: SnapshotKey[];
  midTargets: SnapshotKey[];
  slowTargets: SnapshotKey[];
}

function emptySnapshot(): ConsoleSnapshot {
  const nowIso = new Date().toISOString();
  return {
    engine: {},
    signals: {},
    strategies: {},
    scanner: {},
    universe: {},
    performance: {},
    portfolio: {},
    research: {},
    validation: {},
    reports: {},
    liveMarket: {},
    marketContext: {},
    todayPicks: {},
    recommendations: {},
    macro: {},
    hannaBrief: {},
    fetchedAt: nowIso,
  };
}

function resolveDataProfile(route: ConsoleDataRoute): ConsoleDataProfile {
  if (route.section === 'home') {
    return {
      signalLimit: 40,
      initialTargets: ['engine', 'signals', 'research', 'portfolio', 'liveMarket'],
      fastTargets: ['engine', 'liveMarket'],
      midTargets: ['signals', 'portfolio'],
      slowTargets: ['research', 'marketContext'],
    };
  }

  if (route.section === 'reports') {
    return {
      signalLimit: 80,
      initialTargets: ['engine', 'signals', 'validation', 'reports', 'research', 'todayPicks', 'hannaBrief'],
      fastTargets: ['engine'],
      midTargets: ['signals'],
      slowTargets: ['reports', 'research', 'todayPicks', 'recommendations', 'macro', 'hannaBrief'],
    };
  }

  if (route.consoleTab === 'orders') {
    return {
      signalLimit: 0,
      initialTargets: ['engine', 'research', 'portfolio'],
      fastTargets: ['engine'],
      midTargets: ['research', 'portfolio'],
      slowTargets: [],
    };
  }

  if (route.consoleTab === 'strategies') {
    return {
      signalLimit: 0,
      initialTargets: ['engine', 'strategies', 'research'],
      fastTargets: ['engine'],
      midTargets: ['strategies'],
      slowTargets: ['research'],
    };
  }

  if (route.consoleTab === 'scanner') {
    return {
      signalLimit: 0,
      initialTargets: ['engine', 'scanner', 'research'],
      fastTargets: ['engine'],
      midTargets: ['scanner', 'research'],
      slowTargets: [],
    };
  }

  if (route.consoleTab === 'universe') {
    return {
      signalLimit: 0,
      initialTargets: ['universe', 'research'],
      fastTargets: [],
      midTargets: ['universe'],
      slowTargets: ['research'],
    };
  }

  if (route.consoleTab === 'performance') {
    return {
      signalLimit: 0,
      initialTargets: ['engine', 'performance', 'research'],
      fastTargets: ['engine'],
      midTargets: ['performance'],
      slowTargets: ['research'],
    };
  }

  if (route.consoleTab === 'watchlist' || route.consoleTab === 'research') {
    return {
      signalLimit: 0,
      initialTargets: ['engine'],
      fastTargets: ['engine'],
      midTargets: [],
      slowTargets: [],
    };
  }

  return {
    signalLimit: 0,
    initialTargets: ['engine', 'strategies', 'research'],
    fastTargets: ['engine'],
    midTargets: ['strategies'],
    slowTargets: ['research'],
  };
}

export function useConsoleData(route: ConsoleDataRoute) {
  const [state, setState] = useState<ConsoleDataState>({
    snapshot: emptySnapshot(),
    loading: true,
    hasError: false,
    errorMessage: '',
  });
  const profile = useMemo(
    () => resolveDataProfile(route),
    [route.consoleTab, route.reportTab, route.section],
  );

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

  const fetchPartition = useCallback(async (targets: SnapshotKey[], scannerRefresh = false, scannerCacheOnly = false) => {
    if (targets.length === 0) return;

    const tasks = targets.map((key) => {
      if (key === 'engine') return fetchEngineStatus();
      if (key === 'signals') return fetchSignals(profile.signalLimit);
      if (key === 'strategies') return fetchStrategies();
      if (key === 'scanner') return fetchScannerStatus(scannerRefresh, scannerCacheOnly);
      if (key === 'universe') return fetchUniverse();
      if (key === 'performance') return fetchPerformanceSummary();
      if (key === 'portfolio') return fetchPortfolioState();
      if (key === 'research') return fetchResearchStatus();
      if (key === 'validation') return fetchValidationWalkForwardWithOptions(undefined, undefined, { cacheOnly: true });
      if (key === 'reports') return fetchReportsExplain();
      if (key === 'liveMarket') return fetchLiveMarket();
      if (key === 'marketContext') return fetchMarketContext();
      if (key === 'todayPicks') return fetchTodayPicks();
      if (key === 'recommendations') return fetchRecommendations();
      if (key === 'macro') return fetchMacroLatest();
      if (key === 'hannaBrief') return fetchHannaBrief();
      return Promise.resolve({});
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
  }, [patchSnapshot, profile.signalLimit]);

  const refresh = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, hasError: false, errorMessage: '' }));
    await fetchPartition(profile.initialTargets, false, true);
    if (profile.initialTargets.includes('scanner')) {
      void fetchPartition(['scanner'], true, false).catch(() => {});
    }
  }, [fetchPartition, profile.initialTargets]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (profile.fastTargets.length === 0) return undefined;
    const timer = window.setInterval(() => {
      void fetchPartition(profile.fastTargets, false, true);
    }, FAST_POLLING_MS);
    return () => window.clearInterval(timer);
  }, [fetchPartition, profile.fastTargets]);

  useEffect(() => {
    if (profile.midTargets.length === 0) return undefined;
    const timer = window.setInterval(() => {
      void fetchPartition(profile.midTargets, false, true);
    }, MID_POLLING_MS);
    return () => window.clearInterval(timer);
  }, [fetchPartition, profile.midTargets]);

  useEffect(() => {
    if (profile.slowTargets.length === 0) return undefined;
    const timer = window.setInterval(() => {
      void fetchPartition(profile.slowTargets, false, true);
    }, SLOW_POLLING_MS);
    return () => window.clearInterval(timer);
  }, [fetchPartition, profile.slowTargets]);

  return useMemo(
    () => ({
      ...state,
      refresh,
    }),
    [state, refresh],
  );
}
