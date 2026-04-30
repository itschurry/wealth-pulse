import { useCallback, useEffect, useRef, useState } from 'react';
import { getJSON, postJSON } from '../api/client';
import type { RuntimeAccountData, RuntimeEngineConfig, RuntimeEngineState, RuntimeSeedPositionInput, RuntimeSkippedItem, RuntimeWorkflowSummary } from '../types';

const EMPTY_ACCOUNT: RuntimeAccountData = {
  mode: 'paper',
  base_currency: 'MULTI',
  initial_cash_krw: 0,
  initial_cash_usd: 0,
  cash_krw: 0,
  cash_usd: 0,
  market_value_krw: 0,
  market_value_usd: 0,
  equity_krw: 0,
  starting_equity_krw: 0,
  fx_rate: 0,
  realized_pnl_krw: 0,
  realized_pnl_usd: 0,
  total_fees_krw: 0,
  total_fees_usd: 0,
  positions: [],
  orders: [],
};

type RuntimeOrderResponse = { ok?: boolean; error?: string; account?: RuntimeAccountData };
type RuntimeAutoInvestResponse = {
  ok?: boolean;
  error?: string;
  account?: RuntimeAccountData;
  executed?: unknown[];
  skipped?: RuntimeSkippedItem[];
  message?: string;
  [key: string]: unknown;
};
type RuntimeEngineResponse = {
  ok?: boolean;
  error?: string;
  state?: RuntimeEngineState;
  account?: RuntimeAccountData;
  message?: string;
  [key: string]: unknown;
};
type RuntimeCyclesResponse = {
  ok?: boolean;
  cycles?: Record<string, unknown>[];
  count?: number;
  error?: string;
};
type RuntimeOrderEventsResponse = {
  ok?: boolean;
  orders?: Record<string, unknown>[];
  count?: number;
  error?: string;
};
type RuntimeAccountHistoryResponse = {
  ok?: boolean;
  history?: Record<string, unknown>[];
  count?: number;
  error?: string;
};
type RuntimeHistoryClearResponse = {
  ok?: boolean;
  error?: string;
  account_reset?: boolean;
  clear_count?: {
    order_events?: number;
    signal_snapshots?: number;
    account_snapshots?: number;
    engine_cycles?: number;
  };
  account?: RuntimeAccountData;
};
type SignalSnapshotsResponse = {
  ok?: boolean;
  snapshots?: Record<string, unknown>[];
  count?: number;
  error?: string;
};

type RuntimeWorkflowResponse = {
  ok?: boolean;
  workflow?: RuntimeWorkflowSummary;
  error?: string;
};

export function useRuntimeTrading(options?: { autoRefreshEnabled?: boolean }) {
  const [account, setAccount] = useState<RuntimeAccountData>(EMPTY_ACCOUNT);
  const [engineState, setEngineState] = useState<RuntimeEngineState>({ running: false, engine_state: 'stopped' });
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading');
  const [lastError, setLastError] = useState<string>('');
  const [cycles, setCycles] = useState<Record<string, unknown>[]>([]);
  const [orderEvents, setOrderEvents] = useState<Record<string, unknown>[]>([]);
  const [accountHistory, setAccountHistory] = useState<Record<string, unknown>[]>([]);
  const [signalSnapshots, setSignalSnapshots] = useState<Record<string, unknown>[]>([]);
  const [workflowSummary, setWorkflowSummary] = useState<RuntimeWorkflowSummary>({ counts: {}, items: [], count: 0 });
  const autoRefreshEnabled = options?.autoRefreshEnabled ?? true;
  const accountRequestIdRef = useRef(0);
  const engineRequestIdRef = useRef(0);
  const runtimeLogsRequestIdRef = useRef(0);

  const invalidateAccountRequests = useCallback(() => {
    accountRequestIdRef.current += 1;
  }, []);

  const invalidateEngineRequests = useCallback(() => {
    engineRequestIdRef.current += 1;
  }, []);

  const invalidateRuntimeLogRequests = useCallback(() => {
    runtimeLogsRequestIdRef.current += 1;
  }, []);

  const refresh = useCallback(async (refreshQuotes = true) => {
    const requestId = accountRequestIdRef.current + 1;
    accountRequestIdRef.current = requestId;
    try {
      const payload = await getJSON<RuntimeAccountData>(`/api/runtime/account?refresh=${refreshQuotes ? '1' : '0'}`, { noStore: true });
      if (accountRequestIdRef.current !== requestId) {
        return payload;
      }
      setAccount(payload);
      setStatus(payload.error ? 'error' : 'ok');
      setLastError(payload.error || '');
      return payload;
    } catch {
      if (accountRequestIdRef.current !== requestId) {
        return null;
      }
      setStatus('error');
      setLastError('모의계좌 정보를 불러오지 못했습니다.');
      return null;
    }
  }, []);

  const placeOrder = useCallback(async (params: {
    side: 'buy' | 'sell';
    code: string;
    market: 'KOSPI' | 'NASDAQ';
    quantity: number;
    order_type: 'market' | 'limit';
    limit_price?: number | null;
    stop_loss_pct?: number | null;
    take_profit_pct?: number | null;
  }) => {
    invalidateAccountRequests();
    invalidateRuntimeLogRequests();
    try {
      const response = await postJSON<RuntimeOrderResponse>('/api/runtime/order', params);
      const payload = response.data;
      if (!response.ok || !payload.ok) {
        const message = payload.error || '모의 주문에 실패했습니다.';
        setLastError(message);
        return { ok: false, error: message };
      }
      setAccount(payload.account || EMPTY_ACCOUNT);
      setStatus('ok');
      setLastError('');
      return { ok: true };
    } catch {
      const message = '모의 주문 요청 중 오류가 발생했습니다.';
      setLastError(message);
      return { ok: false, error: message };
    }
  }, [invalidateAccountRequests, invalidateRuntimeLogRequests]);

  const reset = useCallback(async (params?: {
    initial_cash_krw?: number;
    initial_cash_usd?: number;
    seed_positions?: RuntimeSeedPositionInput[];
  }) => {
    invalidateAccountRequests();
    invalidateEngineRequests();
    invalidateRuntimeLogRequests();
    try {
      const response = await postJSON<RuntimeOrderResponse>('/api/runtime/reset', params || {});
      const payload = response.data;
      if (!response.ok || !payload.ok) {
        const message = payload.error || '모의계좌 초기화에 실패했습니다.';
        setLastError(message);
        return { ok: false, error: message };
      }
      setAccount(payload.account || EMPTY_ACCOUNT);
      setStatus('ok');
      setLastError('');
      return { ok: true };
    } catch {
      const message = '모의계좌 초기화 요청 중 오류가 발생했습니다.';
      setLastError(message);
      return { ok: false, error: message };
    }
  }, [invalidateAccountRequests, invalidateEngineRequests, invalidateRuntimeLogRequests]);

  const autoInvest = useCallback(async (params?: {
    market?: 'KOSPI' | 'NASDAQ';
    max_positions?: number;
    min_score?: number;
    include_neutral?: boolean;
    theme_gate_enabled?: boolean;
    theme_min_score?: number;
    theme_min_news?: number;
    theme_priority_bonus?: number;
    theme_focus?: Array<'automotive' | 'robotics' | 'physical_ai'>;
  }) => {
    invalidateAccountRequests();
    invalidateRuntimeLogRequests();
    try {
      const response = await postJSON<RuntimeAutoInvestResponse>('/api/runtime/auto-invest', params || {});
      const payload = response.data;
      if (!response.ok || !payload.ok) {
        const message = payload.error || '추천 기반 자동매수 실행에 실패했습니다.';
        setLastError(message);
        return { ok: false, error: message, payload };
      }
      setAccount(payload.account || EMPTY_ACCOUNT);
      setStatus('ok');
      setLastError('');
      return { ok: true, payload };
    } catch {
      const message = '추천 기반 자동매수 요청 중 오류가 발생했습니다.';
      setLastError(message);
      return { ok: false, error: message };
    }
  }, [invalidateAccountRequests, invalidateRuntimeLogRequests]);

  const refreshEngineStatus = useCallback(async () => {
    const requestId = engineRequestIdRef.current + 1;
    engineRequestIdRef.current = requestId;
    try {
      const payload = await getJSON<RuntimeEngineResponse>('/api/runtime/engine/status', { noStore: true });
      if (engineRequestIdRef.current !== requestId) {
        return { ok: false, error: 'stale' };
      }
      if (!payload.ok) {
        const message = payload.error || '자동매매 상태 조회에 실패했습니다.';
        setLastError(message);
        return { ok: false, error: message };
      }
      if (payload.account) {
        setAccount(payload.account as RuntimeAccountData);
      }
      const nextState = (payload.state || { running: false, engine_state: 'stopped' }) as RuntimeEngineState;
      setEngineState(nextState);
      if (nextState.workflow_summary) {
        setWorkflowSummary(nextState.workflow_summary);
      }
      return { ok: true, payload };
    } catch {
      if (engineRequestIdRef.current !== requestId) {
        return { ok: false, error: 'stale' };
      }
      const message = '자동매매 상태 조회 중 오류가 발생했습니다.';
      setLastError(message);
      return { ok: false, error: message };
    }
  }, []);

  const refreshRuntimeLogs = useCallback(async () => {
    const requestId = runtimeLogsRequestIdRef.current + 1;
    runtimeLogsRequestIdRef.current = requestId;
    try {
      const settled = await Promise.allSettled([
        getJSON<RuntimeCyclesResponse>('/api/runtime/engine/cycles?limit=30', { noStore: true }),
        getJSON<RuntimeOrderEventsResponse>('/api/runtime/orders?limit=60', { noStore: true }),
        getJSON<RuntimeAccountHistoryResponse>('/api/runtime/account/history?limit=60', { noStore: true }),
        getJSON<SignalSnapshotsResponse>('/api/signals/snapshots?limit=120', { noStore: true }),
        getJSON<RuntimeWorkflowResponse>('/api/runtime/workflow?limit=120', { noStore: true }),
      ]) as [
        PromiseSettledResult<RuntimeCyclesResponse>,
        PromiseSettledResult<RuntimeOrderEventsResponse>,
        PromiseSettledResult<RuntimeAccountHistoryResponse>,
        PromiseSettledResult<SignalSnapshotsResponse>,
        PromiseSettledResult<RuntimeWorkflowResponse>,
      ];
      if (runtimeLogsRequestIdRef.current !== requestId) {
        return { ok: false, error: 'stale' };
      }
      const [cyclesResult, ordersResult, historyResult, snapshotsResult, workflowResult] = settled;
      const cyclesPayload = cyclesResult.status === 'fulfilled' && cyclesResult.value.ok !== false ? cyclesResult.value : null;
      const ordersPayload = ordersResult.status === 'fulfilled' && ordersResult.value.ok !== false ? ordersResult.value : null;
      const historyPayload = historyResult.status === 'fulfilled' && historyResult.value.ok !== false ? historyResult.value : null;
      const snapshotsPayload = snapshotsResult.status === 'fulfilled' && snapshotsResult.value.ok !== false ? snapshotsResult.value : null;
      const workflowPayload = workflowResult.status === 'fulfilled' && workflowResult.value.ok !== false ? workflowResult.value : null;
      setCycles(Array.isArray(cyclesPayload?.cycles) ? cyclesPayload.cycles : []);
      setOrderEvents(Array.isArray(ordersPayload?.orders) ? ordersPayload.orders : []);
      setAccountHistory(Array.isArray(historyPayload?.history) ? historyPayload.history : []);
      setSignalSnapshots(Array.isArray(snapshotsPayload?.snapshots) ? snapshotsPayload.snapshots : []);
      setWorkflowSummary(workflowPayload?.workflow || { counts: {}, items: [], count: 0 });
      const failedCount = settled.filter((item) => item.status === 'rejected').length + [cyclesPayload, ordersPayload, historyPayload, snapshotsPayload, workflowPayload].filter((item) => !item).length;
      return failedCount > 0 ? { ok: false, error: 'partial_runtime_log_failure' } : { ok: true };
    } catch {
      if (runtimeLogsRequestIdRef.current !== requestId) {
        return { ok: false, error: 'stale' };
      }
      return { ok: false };
    }
  }, []);

  const clearHistory = useCallback(async (payload: {
    clear_all?: boolean;
    clear_orders?: boolean;
    clear_signals?: boolean;
    clear_accounts?: boolean;
    clear_cycles?: boolean;
    reset_account?: boolean;
    clear_account_state?: boolean;
    hard_reset?: boolean;
    initial_cash_krw?: number;
    initial_cash_usd?: number;
  } = { clear_all: true }) => {
    invalidateAccountRequests();
    invalidateEngineRequests();
    invalidateRuntimeLogRequests();
    try {
      const response = await postJSON<RuntimeHistoryClearResponse>('/api/runtime/history/clear', payload);
      const payloadData = response.data;
      if (!response.ok || !payloadData.ok) {
        const message = payloadData.error || '논리 실행 로그 정리에 실패했습니다.';
        setLastError(message);
        return { ok: false, error: message };
      }
      setLastError('');
      return {
        ok: true,
        clear_count: payloadData.clear_count || {},
        account_reset: payloadData.account_reset || false,
        account: payloadData.account as RuntimeAccountData,
      };
    } catch {
      const message = '논리 실행 로그 정리 요청 중 오류가 발생했습니다.';
      setLastError(message);
      return { ok: false, error: message };
    }
  }, [invalidateAccountRequests, invalidateEngineRequests, invalidateRuntimeLogRequests]);

  const clearRuntimeLogs = useCallback(() => {
    setCycles([]);
    setOrderEvents([]);
    setAccountHistory([]);
    setSignalSnapshots([]);
    setWorkflowSummary({ counts: {}, items: [], count: 0 });
  }, []);

  const startEngine = useCallback(async (params?: Partial<RuntimeEngineConfig>) => {
    invalidateEngineRequests();
    invalidateRuntimeLogRequests();
    try {
      const response = await postJSON<RuntimeEngineResponse>('/api/runtime/engine/start', params || {});
      const payload = response.data;
      if (!response.ok || !payload.ok) {
        const message = payload.error || '자동매매 실행에 실패했습니다.';
        setLastError(message);
        return { ok: false, error: message };
      }
      if (payload.account) {
        setAccount(payload.account as RuntimeAccountData);
      }
      if (payload.state) {
        setEngineState(payload.state as RuntimeEngineState);
      }
      setLastError('');
      return { ok: true, payload };
    } catch {
      const message = '자동매매 실행 요청 중 오류가 발생했습니다.';
      setLastError(message);
      return { ok: false, error: message };
    }
  }, [invalidateEngineRequests, invalidateRuntimeLogRequests]);

  const stopEngine = useCallback(async () => {
    invalidateEngineRequests();
    invalidateRuntimeLogRequests();
    try {
      const response = await postJSON<RuntimeEngineResponse>('/api/runtime/engine/stop');
      const payload = response.data;
      if (!response.ok || !payload.ok) {
        const message = payload.error || '자동매매 중지에 실패했습니다.';
        setLastError(message);
        return { ok: false, error: message };
      }
      if (payload.account) {
        setAccount(payload.account as RuntimeAccountData);
      }
      if (payload.state) {
        setEngineState(payload.state as RuntimeEngineState);
      } else {
        setEngineState({ running: false, engine_state: 'stopped' });
      }
      setLastError('');
      return { ok: true, payload };
    } catch {
      const message = '자동매매 중지 요청 중 오류가 발생했습니다.';
      setLastError(message);
      return { ok: false, error: message };
    }
  }, [invalidateEngineRequests, invalidateRuntimeLogRequests]);

  const pauseEngine = useCallback(async () => {
    invalidateEngineRequests();
    invalidateRuntimeLogRequests();
    try {
      const response = await postJSON<RuntimeEngineResponse>('/api/runtime/engine/pause');
      const payload = response.data;
      if (!response.ok || !payload.ok) {
        const message = payload.error || '자동매매 일시정지에 실패했습니다.';
        setLastError(message);
        return { ok: false, error: message };
      }
      if (payload.account) {
        setAccount(payload.account as RuntimeAccountData);
      }
      if (payload.state) {
        setEngineState(payload.state as RuntimeEngineState);
      }
      setLastError('');
      return { ok: true, payload };
    } catch {
      const message = '자동매매 일시정지 요청 중 오류가 발생했습니다.';
      setLastError(message);
      return { ok: false, error: message };
    }
  }, [invalidateEngineRequests, invalidateRuntimeLogRequests]);

  const resumeEngine = useCallback(async () => {
    invalidateEngineRequests();
    invalidateRuntimeLogRequests();
    try {
      const response = await postJSON<RuntimeEngineResponse>('/api/runtime/engine/resume');
      const payload = response.data;
      if (!response.ok || !payload.ok) {
        const message = payload.error || '자동매매 재개에 실패했습니다.';
        setLastError(message);
        return { ok: false, error: message };
      }
      if (payload.account) {
        setAccount(payload.account as RuntimeAccountData);
      }
      if (payload.state) {
        setEngineState(payload.state as RuntimeEngineState);
      }
      setLastError('');
      return { ok: true, payload };
    } catch {
      const message = '자동매매 재개 요청 중 오류가 발생했습니다.';
      setLastError(message);
      return { ok: false, error: message };
    }
  }, [invalidateEngineRequests, invalidateRuntimeLogRequests]);

  useEffect(() => {
    refresh(true);
    refreshEngineStatus();
    refreshRuntimeLogs();
  }, [refresh, refreshEngineStatus, refreshRuntimeLogs]);

  useEffect(() => {
    if (!autoRefreshEnabled) return undefined;
    if (!(engineState.running || engineState.engine_state === 'paused')) return undefined;
    const timer = window.setInterval(() => {
      refreshEngineStatus();
      refresh(false);
      refreshRuntimeLogs();
    }, 8000);
    return () => window.clearInterval(timer);
  }, [autoRefreshEnabled, engineState.engine_state, engineState.running, refresh, refreshEngineStatus, refreshRuntimeLogs]);

  return {
    account,
    engineState,
    cycles,
    orderEvents,
    accountHistory,
    signalSnapshots,
    workflowSummary,
    status,
    lastError,
    refresh,
    placeOrder,
    reset,
    autoInvest,
    refreshEngineStatus,
    refreshRuntimeLogs,
    clearRuntimeLogs,
    startEngine,
    stopEngine,
    pauseEngine,
    resumeEngine,
    clearHistory,
  };
}
