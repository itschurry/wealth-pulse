import { useCallback, useEffect, useState } from 'react';
import { getJSON, postJSON } from '../api/client';
import type { PaperAccountData, PaperEngineConfig, PaperEngineState, PaperSeedPositionInput, PaperSkippedItem } from '../types';

const EMPTY_ACCOUNT: PaperAccountData = {
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

type PaperOrderResponse = { ok?: boolean; error?: string; account?: PaperAccountData };
type PaperAutoInvestResponse = {
  ok?: boolean;
  error?: string;
  account?: PaperAccountData;
  executed?: unknown[];
  skipped?: PaperSkippedItem[];
  message?: string;
  [key: string]: unknown;
};
type PaperEngineResponse = {
  ok?: boolean;
  error?: string;
  state?: PaperEngineState;
  account?: PaperAccountData;
  message?: string;
  [key: string]: unknown;
};

export function usePaperTrading() {
  const [account, setAccount] = useState<PaperAccountData>(EMPTY_ACCOUNT);
  const [engineState, setEngineState] = useState<PaperEngineState>({ running: false });
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading');
  const [lastError, setLastError] = useState<string>('');

  const refresh = useCallback(async (refreshQuotes = true) => {
    try {
      const payload = await getJSON<PaperAccountData>(`/api/paper/account?refresh=${refreshQuotes ? '1' : '0'}`, { noStore: true });
      setAccount(payload);
      setStatus(payload.error ? 'error' : 'ok');
      setLastError(payload.error || '');
      return payload;
    } catch {
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
  }) => {
    try {
      const response = await postJSON<PaperOrderResponse>('/api/paper/order', params);
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
  }, []);

  const reset = useCallback(async (params?: {
    initial_cash_krw?: number;
    initial_cash_usd?: number;
    paper_days?: number;
    seed_positions?: PaperSeedPositionInput[];
  }) => {
    try {
      const response = await postJSON<PaperOrderResponse>('/api/paper/reset', params || {});
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
  }, []);

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
    try {
      const response = await postJSON<PaperAutoInvestResponse>('/api/paper/auto-invest', params || {});
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
  }, []);

  const refreshEngineStatus = useCallback(async () => {
    try {
      const payload = await getJSON<PaperEngineResponse>('/api/paper/engine/status', { noStore: true });
      if (!payload.ok) {
        const message = payload.error || '자동매매 상태 조회에 실패했습니다.';
        setLastError(message);
        return { ok: false, error: message };
      }
      if (payload.account) {
        setAccount(payload.account as PaperAccountData);
      }
      setEngineState((payload.state || { running: false }) as PaperEngineState);
      return { ok: true, payload };
    } catch {
      const message = '자동매매 상태 조회 중 오류가 발생했습니다.';
      setLastError(message);
      return { ok: false, error: message };
    }
  }, []);

  const startEngine = useCallback(async (params?: Partial<PaperEngineConfig>) => {
    try {
      const response = await postJSON<PaperEngineResponse>('/api/paper/engine/start', params || {});
      const payload = response.data;
      if (!response.ok || !payload.ok) {
        const message = payload.error || '자동매매 실행에 실패했습니다.';
        setLastError(message);
        return { ok: false, error: message };
      }
      if (payload.state) {
        setEngineState(payload.state as PaperEngineState);
      }
      setLastError('');
      return { ok: true, payload };
    } catch {
      const message = '자동매매 실행 요청 중 오류가 발생했습니다.';
      setLastError(message);
      return { ok: false, error: message };
    }
  }, []);

  const stopEngine = useCallback(async () => {
    try {
      const response = await postJSON<PaperEngineResponse>('/api/paper/engine/stop');
      const payload = response.data;
      if (!response.ok || !payload.ok) {
        const message = payload.error || '자동매매 중지에 실패했습니다.';
        setLastError(message);
        return { ok: false, error: message };
      }
      if (payload.state) {
        setEngineState(payload.state as PaperEngineState);
      } else {
        setEngineState({ running: false });
      }
      setLastError('');
      return { ok: true, payload };
    } catch {
      const message = '자동매매 중지 요청 중 오류가 발생했습니다.';
      setLastError(message);
      return { ok: false, error: message };
    }
  }, []);

  useEffect(() => {
    refresh(true);
    refreshEngineStatus();
  }, [refresh, refreshEngineStatus]);

  useEffect(() => {
    if (!engineState.running) return undefined;
    const timer = window.setInterval(() => {
      refreshEngineStatus();
      refresh(false);
    }, 8000);
    return () => window.clearInterval(timer);
  }, [engineState.running, refresh, refreshEngineStatus]);

  return {
    account,
    engineState,
    status,
    lastError,
    refresh,
    placeOrder,
    reset,
    autoInvest,
    refreshEngineStatus,
    startEngine,
    stopEngine,
  };
}
