import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  fetchEngineStatus,
  fetchPerformanceSummary,
  fetchReportsExplain,
  fetchResearchStatus,
  fetchScannerStatus,
  fetchSignals,
  fetchStrategies,
  fetchUniverse,
  fetchValidationWalkForward,
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
    fetchedAt: nowIso,
  };
}

function resolveDataProfile(route: ConsoleDataRoute): ConsoleDataProfile {
  if (route.section === 'home') {
    return {
      signalLimit: 40,
      initialTargets: ['engine', 'signals', 'research'],
      fastTargets: ['engine'],
      midTargets: ['signals'],
      slowTargets: ['research'],
    };
  }

  if (route.section === 'reports') {
    return {
      signalLimit: 80,
      initialTargets: ['engine', 'signals', 'validation', 'reports', 'research'],
      fastTargets: ['engine'],
      midTargets: ['signals'],
      slowTargets: ['validation', 'reports', 'research'],
    };
  }

  if (route.consoleTab === 'orders') {
    return {
      signalLimit: 0,
      initialTargets: ['engine', 'research'],
      fastTargets: ['engine'],
      midTargets: ['research'],
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

  const fetchPartition = useCallback(async (targets: SnapshotKey[], scannerRefresh = false) => {
    if (targets.length === 0) return;

    const tasks = targets.map((key) => {
      if (key === 'engine') return fetchEngineStatus();
      if (key === 'signals') return fetchSignals(profile.signalLimit);
      if (key === 'strategies') return fetchStrategies();
      if (key === 'scanner') return fetchScannerStatus(scannerRefresh);
      if (key === 'universe') return fetchUniverse();
      if (key === 'performance') return fetchPerformanceSummary();
      if (key === 'research') return fetchResearchStatus();
      if (key === 'validation') return fetchValidationWalkForward();
      if (key === 'reports') return fetchReportsExplain();
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
    await fetchPartition(profile.initialTargets, true);
  }, [fetchPartition, profile.initialTargets]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (profile.fastTargets.length === 0) return undefined;
    const timer = window.setInterval(() => {
      void fetchPartition(profile.fastTargets, false);
    }, FAST_POLLING_MS);
    return () => window.clearInterval(timer);
  }, [fetchPartition, profile.fastTargets]);

  useEffect(() => {
    if (profile.midTargets.length === 0) return undefined;
    const timer = window.setInterval(() => {
      void fetchPartition(profile.midTargets, false);
    }, MID_POLLING_MS);
    return () => window.clearInterval(timer);
  }, [fetchPartition, profile.midTargets]);

  useEffect(() => {
    if (profile.slowTargets.length === 0) return undefined;
    const timer = window.setInterval(() => {
      void fetchPartition(profile.slowTargets, false);
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
