import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  fetchEngineSummary,
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
import type { DashboardTab, LabTab, ResearchTab, WorkspacePage } from '../types/navigation';

const FAST_POLLING_MS = 15_000;
const MID_POLLING_MS = 30_000;
const SLOW_POLLING_MS = 60_000;

type SnapshotKey = keyof Omit<ConsoleSnapshot, 'fetchedAt'>;

interface ConsoleDataRoute {
  page: WorkspacePage;
  dashboardTab: DashboardTab;
  labTab: LabTab;
  researchTab: ResearchTab;
}

interface ConsoleDataProfile {
  signalLimit: number;
  initialTargets: SnapshotKey[];
  initialAwaitTargets?: SnapshotKey[];
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
  if (route.page === 'operations-dashboard' && route.dashboardTab === 'overview') {
    return {
      signalLimit: 80,
      initialTargets: ['engine', 'signals', 'research', 'portfolio', 'liveMarket', 'marketContext', 'validation', 'reports'],
      initialAwaitTargets: ['engine'],
      fastTargets: ['engine', 'liveMarket'],
      midTargets: ['signals', 'portfolio'],
      slowTargets: ['research', 'marketContext', 'validation', 'reports'],
    };
  }

  if (route.page === 'operations-dashboard' && route.dashboardTab === 'scanner') {
    return {
      signalLimit: 0,
      initialTargets: ['engine', 'scanner', 'research'],
      fastTargets: ['engine'],
      midTargets: ['scanner', 'research'],
      slowTargets: [],
    };
  }

  if (route.page === 'operations-dashboard' && route.dashboardTab === 'performance') {
    return {
      signalLimit: 0,
      initialTargets: ['engine', 'performance', 'research'],
      fastTargets: ['engine'],
      midTargets: ['performance'],
      slowTargets: ['research'],
    };
  }

  if (route.page === 'operations-dashboard' && route.dashboardTab === 'watch-decision') {
    return {
      signalLimit: 80,
      initialTargets: ['engine', 'signals', 'validation', 'reports', 'research', 'todayPicks', 'hannaBrief'],
      fastTargets: ['engine'],
      midTargets: ['signals'],
      slowTargets: ['reports', 'research', 'todayPicks', 'recommendations', 'macro', 'hannaBrief'],
    };
  }

  if (route.page === 'orders-execution' || route.page === 'agent-dashboard') {
    return {
      signalLimit: 0,
      initialTargets: ['engine', 'research', 'portfolio'],
      fastTargets: ['engine'],
      midTargets: ['research', 'portfolio'],
      slowTargets: [],
    };
  }

  if (route.page === 'watchlist' || (route.page === 'research-ai' && route.researchTab === 'research')) {
    return {
      signalLimit: 0,
      initialTargets: ['engine'],
      fastTargets: ['engine'],
      midTargets: [],
      slowTargets: [],
    };
  }

  if (route.page === 'lab' && route.labTab === 'validation') {
    return {
      signalLimit: 0,
      initialTargets: ['engine', 'strategies', 'research', 'validation'],
      fastTargets: ['engine'],
      midTargets: ['strategies'],
      slowTargets: ['research', 'validation'],
    };
  }

  if (route.page === 'lab' && route.labTab === 'strategies') {
    return {
      signalLimit: 0,
      initialTargets: ['engine', 'strategies', 'research'],
      fastTargets: ['engine'],
      midTargets: ['strategies'],
      slowTargets: ['research'],
    };
  }

  if (route.page === 'lab' && route.labTab === 'universe') {
    return {
      signalLimit: 0,
      initialTargets: ['engine', 'universe'],
      fastTargets: ['engine'],
      midTargets: ['universe'],
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
    [route.dashboardTab, route.labTab, route.page, route.researchTab],
  );
  const routeKey = useMemo(
    () => [route.page, route.dashboardTab, route.labTab, route.researchTab].join('::'),
    [route.dashboardTab, route.labTab, route.page, route.researchTab],
  );
  const routeVersionRef = useRef(0);
  const requestVersionRef = useRef<Record<SnapshotKey, number>>({
    engine: 0,
    signals: 0,
    strategies: 0,
    scanner: 0,
    universe: 0,
    performance: 0,
    portfolio: 0,
    research: 0,
    validation: 0,
    reports: 0,
    liveMarket: 0,
    marketContext: 0,
    todayPicks: 0,
    recommendations: 0,
    macro: 0,
    hannaBrief: 0,
  });

  useEffect(() => {
    routeVersionRef.current += 1;
    requestVersionRef.current = {
      engine: 0,
      signals: 0,
      strategies: 0,
      scanner: 0,
      universe: 0,
      performance: 0,
      portfolio: 0,
      research: 0,
      validation: 0,
      reports: 0,
      liveMarket: 0,
      marketContext: 0,
      todayPicks: 0,
      recommendations: 0,
      macro: 0,
      hannaBrief: 0,
    };
    setState({
      snapshot: emptySnapshot(),
      loading: true,
      hasError: false,
      errorMessage: '',
    });
  }, [routeKey]);

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

  const isFailedPayload = useCallback((value: unknown) => {
    if (!value || typeof value !== 'object') return false;
    const candidate = value as { ok?: boolean };
    return candidate.ok === false;
  }, []);

  const fetchPartition = useCallback(async (targets: SnapshotKey[], scannerRefresh = false, scannerCacheOnly = false) => {
    if (targets.length === 0) return;

    const routeVersion = routeVersionRef.current;
    const targetVersions = Object.fromEntries(
      targets.map((key) => {
        const nextVersion = (requestVersionRef.current[key] || 0) + 1;
        requestVersionRef.current[key] = nextVersion;
        return [key, nextVersion];
      }),
    ) as Record<SnapshotKey, number>;

    const tasks = targets.map((key) => {
      if (key === 'engine') return fetchEngineSummary();
      if (key === 'signals') return fetchSignals(profile.signalLimit);
      if (key === 'strategies') return fetchStrategies();
      if (key === 'scanner') return fetchScannerStatus(scannerRefresh, scannerCacheOnly);
      if (key === 'universe') return fetchUniverse();
      if (key === 'performance') return fetchPerformanceSummary();
      if (key === 'portfolio') return fetchPortfolioState(false);
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
      const isStale = routeVersionRef.current !== routeVersion || requestVersionRef.current[key] !== targetVersions[key];
      if (isStale) {
        return;
      }
      if (result.status === 'fulfilled') {
        if (isFailedPayload(result.value)) {
          hasError = true;
          return;
        }
        partial[key] = result.value;
      } else {
        hasError = true;
      }
    });
    if (routeVersionRef.current !== routeVersion) {
      return;
    }
    if (Object.keys(partial).length === 0 && !hasError) {
      return;
    }
    patchSnapshot(partial, hasError);
  }, [isFailedPayload, patchSnapshot, profile.signalLimit]);

  const refresh = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, hasError: false, errorMessage: '' }));

    const seen = new Set<SnapshotKey>();
    const buckets: SnapshotKey[][] = [];
    const addBucket = (keys: SnapshotKey[]) => {
      const filtered = keys.filter((key) => profile.initialTargets.includes(key) && !seen.has(key));
      if (filtered.length === 0) return;
      filtered.forEach((key) => seen.add(key));
      buckets.push(filtered);
    };

    addBucket(profile.initialAwaitTargets || profile.fastTargets);
    addBucket(profile.fastTargets);
    addBucket(profile.midTargets);
    addBucket(profile.slowTargets);
    addBucket(profile.initialTargets);

    const [firstBucket, ...remainingBuckets] = buckets;
    if (firstBucket) {
      await fetchPartition(firstBucket, false, true);
    }
    remainingBuckets.forEach((keys) => {
      void fetchPartition(keys, false, true).catch(() => undefined);
    });

    if (profile.initialTargets.includes('scanner')) {
      void fetchPartition(['scanner'], true, false).catch(() => undefined);
    }
  }, [fetchPartition, profile.fastTargets, profile.initialAwaitTargets, profile.initialTargets, profile.midTargets, profile.slowTargets]);

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

  return {
    snapshot: state.snapshot,
    loading: state.loading,
    hasError: state.hasError,
    errorMessage: state.errorMessage,
    refresh,
  };
}
