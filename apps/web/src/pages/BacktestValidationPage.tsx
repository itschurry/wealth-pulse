import { useCallback, useEffect, useMemo, useState } from 'react';
import { getJSON, postJSON } from '../api/client';
import { ConsoleActionBar, ConsoleConfirmDialog } from '../components/ConsoleActionBar';
import { reliabilityToKorean, UI_TEXT } from '../constants/uiText';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import { defaultBacktestQuery, loadBacktestQuery, saveBacktestQuery, useBacktest } from '../hooks/useBacktest';
import type { BacktestQuery, BacktestTrade } from '../types';
import type { ActionBarStatusItem, BacktestViewModel, ConsoleSnapshot } from '../types/consoleView';
import { formatCount, formatDateTime, formatNumber, formatPercent } from '../utils/format';

interface BacktestValidationPageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
}

interface ValidationSettings {
  strategy: string;
  trainingDays: number;
  validationDays: number;
  walkForward: boolean;
  minTrades: number;
  objective: string;
}

interface RunHistoryItem {
  id: string;
  at: string;
  market: string;
  lookbackDays: number;
  status: string;
  totalReturnPct: number | null;
}

interface OptimizationHistoryItem {
  id: string;
  at: string;
  status: string;
  message: string;
}

interface SettingSaveItem {
  id: string;
  at: string;
  market: string;
  lookbackDays: number;
  strategy: string;
}

const SETTINGS_KEY = 'console_validation_settings_v1';
const RUN_HISTORY_KEY = 'console_validation_run_history_v1';
const OPT_HISTORY_KEY = 'console_validation_optimization_history_v1';
const SAVE_HISTORY_KEY = 'console_validation_save_history_v1';

function nowIso() {
  return new Date().toISOString();
}

function readArray<T>(key: string): T[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(key) || '[]') as unknown;
    return Array.isArray(parsed) ? (parsed as T[]) : [];
  } catch {
    return [];
  }
}

function writeArray<T>(key: string, value: T[]) {
  localStorage.setItem(key, JSON.stringify(value));
}

function readSettings(): ValidationSettings {
  try {
    const parsed = JSON.parse(localStorage.getItem(SETTINGS_KEY) || 'null') as Partial<ValidationSettings> | null;
    if (!parsed || typeof parsed !== 'object') {
      return {
        strategy: '공통 전략 엔진',
        trainingDays: 180,
        validationDays: 60,
        walkForward: true,
        minTrades: 20,
        objective: '수익 우선',
      };
    }
    return {
      strategy: parsed.strategy || '공통 전략 엔진',
      trainingDays: Math.max(30, Number(parsed.trainingDays) || 180),
      validationDays: Math.max(20, Number(parsed.validationDays) || 60),
      walkForward: Boolean(parsed.walkForward),
      minTrades: Math.max(1, Number(parsed.minTrades) || 20),
      objective: parsed.objective || '수익 우선',
    };
  } catch {
    return {
      strategy: '공통 전략 엔진',
      trainingDays: 180,
      validationDays: 60,
      walkForward: true,
      minTrades: 20,
      objective: '수익 우선',
    };
  }
}

function metricNumber(metrics: Record<string, unknown> | undefined, key: string): number | null {
  if (!metrics) return null;
  const numeric = Number(metrics[key]);
  return Number.isFinite(numeric) ? numeric : null;
}

function aggregateByReason(trades: BacktestTrade[]): Array<{ reason: string; count: number; avgPnlPct: number }> {
  const bucket = new Map<string, { count: number; sum: number }>();
  for (const trade of trades) {
    const reason = trade.reason || '기타';
    const current = bucket.get(reason) || { count: 0, sum: 0 };
    current.count += 1;
    current.sum += Number.isFinite(trade.pnl_pct) ? trade.pnl_pct : 0;
    bucket.set(reason, current);
  }
  return [...bucket.entries()]
    .map(([reason, item]) => ({
      reason,
      count: item.count,
      avgPnlPct: item.count > 0 ? item.sum / item.count : 0,
    }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 12);
}

export function BacktestValidationPage({ snapshot, loading, errorMessage, onRefresh }: BacktestValidationPageProps) {
  const { entries, push, clear } = useConsoleLogs();
  const [initialQuery] = useState<BacktestQuery>(() => loadBacktestQuery());
  const [draft, setDraft] = useState<BacktestQuery>(initialQuery);
  const [validationSettings, setValidationSettings] = useState<ValidationSettings>(() => readSettings());
  const [runHistory, setRunHistory] = useState<RunHistoryItem[]>(() => readArray<RunHistoryItem>(RUN_HISTORY_KEY));
  const [optimizationHistory, setOptimizationHistory] = useState<OptimizationHistoryItem[]>(() => readArray<OptimizationHistoryItem>(OPT_HISTORY_KEY));
  const [saveHistory, setSaveHistory] = useState<SettingSaveItem[]>(() => readArray<SettingSaveItem>(SAVE_HISTORY_KEY));
  const [runStartedAt, setRunStartedAt] = useState('');
  const [runRequested, setRunRequested] = useState(false);
  const [optimizationRunning, setOptimizationRunning] = useState(false);
  const [optimizationStartedAt, setOptimizationStartedAt] = useState('');
  const [optimizedParams, setOptimizedParams] = useState<Record<string, unknown> | null>(null);
  const [optimizationMessage, setOptimizationMessage] = useState('');
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false);
  const { data, status, run } = useBacktest(initialQuery);

  const metrics = data.metrics as Record<string, unknown> | undefined;
  const oos = snapshot.validation.segments?.oos;
  const reasonRows = useMemo(() => aggregateByReason(data.trades || []), [data.trades]);

  const viewModel = useMemo<BacktestViewModel>(() => ({
    totalReturnPct: metricNumber(metrics, 'total_return_pct'),
    oosReturnPct: oos ? metricNumber(oos as Record<string, unknown>, 'total_return_pct') : null,
    maxDrawdownPct: metricNumber(metrics, 'max_drawdown_pct'),
    profitFactor: metricNumber(metrics, 'profit_factor'),
    winRatePct: metricNumber(metrics, 'win_rate_pct'),
    tradeCount: metricNumber(metrics, 'trade_count'),
    reliability: reliabilityToKorean(String(snapshot.validation.summary?.oos_reliability || '')),
  }), [metrics, oos, snapshot.validation.summary?.oos_reliability]);

  const statusItems = useMemo<ActionBarStatusItem[]>(() => ([
    {
      label: '백테스트 상태',
      value: status === 'loading' ? '실행 중' : status === 'error' ? '실패' : '완료',
      tone: status === 'error' ? 'bad' : status === 'loading' ? 'neutral' : 'good',
    },
    {
      label: '최적화 상태',
      value: optimizationRunning ? '실행 중' : '대기',
      tone: optimizationRunning ? 'neutral' : 'good',
    },
    {
      label: 'OOS 신뢰도',
      value: viewModel.reliability || '-',
      tone: viewModel.reliability === '낮음' ? 'bad' : 'neutral',
    },
    {
      label: '최종 수익률',
      value: formatPercent(viewModel.totalReturnPct, 2),
      tone: (viewModel.totalReturnPct || 0) >= 0 ? 'good' : 'bad',
    },
  ]), [optimizationRunning, status, viewModel.reliability, viewModel.totalReturnPct]);

  const updateRunHistory = useCallback((next: RunHistoryItem[]) => {
    setRunHistory(next);
    writeArray(RUN_HISTORY_KEY, next);
  }, []);

  useEffect(() => {
    saveBacktestQuery(draft);
  }, [draft]);

  const updateOptimizationHistory = useCallback((next: OptimizationHistoryItem[]) => {
    setOptimizationHistory(next);
    writeArray(OPT_HISTORY_KEY, next);
  }, []);

  const updateSaveHistory = useCallback((next: SettingSaveItem[]) => {
    setSaveHistory(next);
    writeArray(SAVE_HISTORY_KEY, next);
  }, []);

  useEffect(() => {
    if (!runRequested || status === 'loading') return;
    const latest = runHistory[0];
    if (!latest || latest.status !== '실행 중') {
      setRunRequested(false);
      return;
    }
    const updated: RunHistoryItem = {
      ...latest,
      status: status === 'ok' ? '완료' : '실패',
      totalReturnPct: status === 'ok' ? metricNumber(metrics, 'total_return_pct') : null,
    };
    const next = [updated, ...runHistory.slice(1)];
    updateRunHistory(next);
    setRunRequested(false);
    if (status === 'ok') {
      push('success', '백테스트 실행이 완료되었습니다.');
    } else {
      push('error', '백테스트 실행이 실패했습니다.', data.error || '응답 오류');
    }
  }, [data.error, metrics, push, runHistory, runRequested, status, updateRunHistory]);

  useEffect(() => {
    let alive = true;
    const boot = async () => {
      try {
        const [statusPayload, paramsPayload] = await Promise.all([
          getJSON<{ running?: boolean }>('/api/optimization-status', { noStore: true }),
          getJSON<Record<string, unknown>>('/api/optimized-params', { noStore: true }),
        ]);
        if (!alive) return;
        setOptimizationRunning(Boolean(statusPayload.running));
        if (statusPayload.running) {
          setOptimizationStartedAt(nowIso());
          setOptimizationMessage('최적화가 백그라운드에서 실행 중입니다.');
        }
        if (paramsPayload.status === 'ok') {
          setOptimizedParams(paramsPayload);
        }
      } catch {
        if (!alive) return;
        push('warning', '최적화 상태 초기 조회에 실패했습니다.');
      }
    };
    void boot();
    return () => { alive = false; };
  }, [push]);

  useEffect(() => {
    if (!optimizationRunning) return undefined;
    const timer = window.setInterval(async () => {
      try {
        const statusPayload = await getJSON<{ running?: boolean }>('/api/optimization-status', { noStore: true });
        if (statusPayload.running) return;
        const paramsPayload = await getJSON<Record<string, unknown>>('/api/optimized-params', { noStore: true });
        setOptimizationRunning(false);
        if (paramsPayload.status === 'ok') {
          setOptimizedParams(paramsPayload);
        }
        setOptimizationMessage('최적화가 완료되었습니다.');
        push('success', '최적화가 완료되었습니다.');
        const historyItem: OptimizationHistoryItem = {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          at: nowIso(),
          status: '완료',
          message: '백그라운드 최적화 완료',
        };
        updateOptimizationHistory([historyItem, ...optimizationHistory].slice(0, 30));
      } catch {
        setOptimizationRunning(false);
        setOptimizationMessage('최적화 상태 조회 중 오류가 발생했습니다.');
        push('error', '최적화 상태 조회 중 오류가 발생했습니다.');
      }
    }, 10_000);
    return () => window.clearInterval(timer);
  }, [optimizationHistory, optimizationRunning, push, updateOptimizationHistory]);

  const handleRefreshAll = useCallback(async () => {
    onRefresh();
    await run(draft);
    push('info', '백테스트/검증 데이터를 새로고침했습니다.');
  }, [draft, onRefresh, push, run]);

  const handleRunBacktest = useCallback(async () => {
    const historyItem: RunHistoryItem = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      at: nowIso(),
      market: draft.market_scope,
      lookbackDays: draft.lookback_days,
      status: '실행 중',
      totalReturnPct: null,
    };
    updateRunHistory([historyItem, ...runHistory].slice(0, 30));
    setRunStartedAt(nowIso());
    setRunRequested(true);
    push('info', '백테스트 실행을 시작했습니다.', `시장 ${draft.market_scope.toUpperCase()}, 기간 ${draft.lookback_days}일`);
    await run(draft);
  }, [draft, push, run, runHistory, updateRunHistory]);

  const handleRunOptimization = useCallback(async () => {
    try {
      const response = await postJSON<{ status?: string; error?: string }>('/api/run-optimization');
      const payload = response.data;
      if (payload.status === 'started' || payload.status === 'already_running') {
        setOptimizationRunning(true);
        setOptimizationStartedAt(nowIso());
        setOptimizationMessage(payload.status === 'already_running'
          ? '이미 실행 중인 최적화 작업이 있습니다.'
          : '최적화를 시작했습니다.');
        push('info', payload.status === 'already_running' ? '최적화가 이미 실행 중입니다.' : '최적화를 시작했습니다.');
        const historyItem: OptimizationHistoryItem = {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          at: nowIso(),
          status: '실행 중',
          message: payload.status === 'already_running' ? '이미 실행 중' : '새 실행 시작',
        };
        updateOptimizationHistory([historyItem, ...optimizationHistory].slice(0, 30));
        return;
      }
      setOptimizationMessage(payload.error || '최적화 요청 실패');
      push('error', '최적화 요청이 실패했습니다.', payload.error || '');
    } catch {
      setOptimizationMessage('최적화 요청 중 오류가 발생했습니다.');
      push('error', '최적화 요청 중 오류가 발생했습니다.');
    }
  }, [optimizationHistory, push, updateOptimizationHistory]);

  const handleSaveSettings = useCallback(() => {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(validationSettings));
    const historyItem: SettingSaveItem = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      at: nowIso(),
      market: draft.market_scope,
      lookbackDays: draft.lookback_days,
      strategy: validationSettings.strategy,
    };
    updateSaveHistory([historyItem, ...saveHistory].slice(0, 30));
    push('success', '검증 설정을 저장했습니다.');
  }, [draft.lookback_days, draft.market_scope, push, saveHistory, updateSaveHistory, validationSettings.strategy]);

  const handleResetSettings = useCallback(() => {
    const resetQuery = defaultBacktestQuery(draft.market_scope);
    setDraft(resetQuery);
    setValidationSettings({
      strategy: '공통 전략 엔진',
      trainingDays: 180,
      validationDays: 60,
      walkForward: true,
      minTrades: 20,
      objective: '수익 우선',
    });
    push('info', '백테스트/검증 설정을 기본값으로 초기화했습니다.');
  }, [draft.market_scope, push]);

  const settingsPanel = (
    <div style={{ display: 'grid', gap: 12 }}>
      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>시장</span>
        <select
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          value={draft.market_scope}
          onChange={(event) => setDraft((prev) => ({ ...prev, market_scope: event.target.value as BacktestQuery['market_scope'] }))}
        >
          <option value="kospi">KOSPI</option>
          <option value="nasdaq">NASDAQ</option>
        </select>
      </label>
      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>전략</span>
        <input
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          value={validationSettings.strategy}
          onChange={(event) => setValidationSettings((prev) => ({ ...prev, strategy: event.target.value }))}
        />
      </label>
      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>기간(일)</span>
        <input
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          type="number"
          value={draft.lookback_days}
          onChange={(event) => setDraft((prev) => ({ ...prev, lookback_days: Math.max(180, Number(event.target.value) || 180) }))}
        />
      </label>
      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>학습기간(일)</span>
        <input
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          type="number"
          value={validationSettings.trainingDays}
          onChange={(event) => setValidationSettings((prev) => ({ ...prev, trainingDays: Math.max(30, Number(event.target.value) || 30) }))}
        />
      </label>
      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>검증기간(일)</span>
        <input
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          type="number"
          value={validationSettings.validationDays}
          onChange={(event) => setValidationSettings((prev) => ({ ...prev, validationDays: Math.max(20, Number(event.target.value) || 20) }))}
        />
      </label>
      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>Walk-forward</span>
        <select
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          value={validationSettings.walkForward ? 'on' : 'off'}
          onChange={(event) => setValidationSettings((prev) => ({ ...prev, walkForward: event.target.value === 'on' }))}
        >
          <option value="on">사용</option>
          <option value="off">미사용</option>
        </select>
      </label>
      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>최소 거래수</span>
        <input
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          type="number"
          value={validationSettings.minTrades}
          onChange={(event) => setValidationSettings((prev) => ({ ...prev, minTrades: Math.max(1, Number(event.target.value) || 1) }))}
        />
      </label>
      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>목표함수</span>
        <select
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          value={validationSettings.objective}
          onChange={(event) => setValidationSettings((prev) => ({ ...prev, objective: event.target.value }))}
        >
          <option>수익 우선</option>
          <option>수익+안정 균형</option>
        </select>
      </label>
      <button className="console-action-button is-primary" onClick={handleSaveSettings}>설정 저장</button>
      <button className="console-action-button is-danger" onClick={() => setResetConfirmOpen(true)}>초기화</button>
    </div>
  );

  const segmentTrain = snapshot.validation.segments?.train as Record<string, unknown> | undefined;
  const segmentValidation = snapshot.validation.segments?.validation as Record<string, unknown> | undefined;
  const segmentOos = snapshot.validation.segments?.oos as Record<string, unknown> | undefined;
  const globalParams = (optimizedParams?.global_params as Record<string, unknown> | undefined) || {};

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell" style={{ display: 'grid', gap: 16 }}>
          <ConsoleActionBar
            title="백테스트/검증 운용"
            subtitle="실행·최적화 상태를 관리하고 OOS 성과와 파라미터 신뢰도를 점검합니다."
            lastUpdated={snapshot.fetchedAt}
            loading={loading || status === 'loading'}
            errorMessage={errorMessage}
            statusItems={statusItems}
            onRefresh={handleRefreshAll}
            logs={entries}
            onClearLogs={clear}
            actions={[
              { label: '백테스트 실행', onClick: () => { void handleRunBacktest(); }, tone: 'primary' },
              { label: '최적화 실행', onClick: () => { void handleRunOptimization(); }, tone: 'default', disabled: optimizationRunning },
            ]}
            settingsPanel={settingsPanel}
          />

          <div className="page-section" style={{ display: 'grid', gap: 12 }}>
            <div style={{ fontSize: 14, fontWeight: 700 }}>실행 패널</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10 }}>
              <label style={{ display: 'grid', gap: 6 }}>
                <span style={{ fontSize: 12, color: 'var(--text-4)' }}>시장</span>
                <select className="backtest-input-wrap" style={{ padding: '0 12px' }} value={draft.market_scope} onChange={(event) => setDraft((prev) => ({ ...prev, market_scope: event.target.value as BacktestQuery['market_scope'] }))}>
                  <option value="kospi">KOSPI</option>
                  <option value="nasdaq">NASDAQ</option>
                </select>
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span style={{ fontSize: 12, color: 'var(--text-4)' }}>전략</span>
                <input className="backtest-input-wrap" style={{ padding: '0 12px' }} value={validationSettings.strategy} onChange={(event) => setValidationSettings((prev) => ({ ...prev, strategy: event.target.value }))} />
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span style={{ fontSize: 12, color: 'var(--text-4)' }}>기간(일)</span>
                <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" value={draft.lookback_days} onChange={(event) => setDraft((prev) => ({ ...prev, lookback_days: Math.max(180, Number(event.target.value) || 180) }))} />
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span style={{ fontSize: 12, color: 'var(--text-4)' }}>학습기간</span>
                <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" value={validationSettings.trainingDays} onChange={(event) => setValidationSettings((prev) => ({ ...prev, trainingDays: Math.max(30, Number(event.target.value) || 30) }))} />
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span style={{ fontSize: 12, color: 'var(--text-4)' }}>검증기간</span>
                <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" value={validationSettings.validationDays} onChange={(event) => setValidationSettings((prev) => ({ ...prev, validationDays: Math.max(20, Number(event.target.value) || 20) }))} />
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span style={{ fontSize: 12, color: 'var(--text-4)' }}>Walk-forward</span>
                <select className="backtest-input-wrap" style={{ padding: '0 12px' }} value={validationSettings.walkForward ? 'on' : 'off'} onChange={(event) => setValidationSettings((prev) => ({ ...prev, walkForward: event.target.value === 'on' }))}>
                  <option value="on">사용</option>
                  <option value="off">미사용</option>
                </select>
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span style={{ fontSize: 12, color: 'var(--text-4)' }}>최소 거래수</span>
                <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" value={validationSettings.minTrades} onChange={(event) => setValidationSettings((prev) => ({ ...prev, minTrades: Math.max(1, Number(event.target.value) || 1) }))} />
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span style={{ fontSize: 12, color: 'var(--text-4)' }}>목표함수</span>
                <select className="backtest-input-wrap" style={{ padding: '0 12px' }} value={validationSettings.objective} onChange={(event) => setValidationSettings((prev) => ({ ...prev, objective: event.target.value }))}>
                  <option>수익 우선</option>
                  <option>수익+안정 균형</option>
                </select>
              </label>
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button className="console-action-button is-primary" onClick={() => { void handleRunBacktest(); }}>백테스트 실행</button>
              <button className="console-action-button" onClick={() => { void handleRunOptimization(); }} disabled={optimizationRunning}>최적화 실행</button>
              <button className="console-action-button" onClick={handleSaveSettings}>설정 저장</button>
              <button className="console-action-button is-danger" onClick={() => setResetConfirmOpen(true)}>초기화</button>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 10 }}>
            <div className="page-section" style={{ padding: 14 }}>
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>백테스트 수익률</div>
              <div style={{ marginTop: 8, fontSize: 20, fontWeight: 800 }}>{formatPercent(viewModel.totalReturnPct, 2)}</div>
            </div>
            <div className="page-section" style={{ padding: 14 }}>
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>OOS 수익률</div>
              <div style={{ marginTop: 8, fontSize: 20, fontWeight: 800 }}>{formatPercent(viewModel.oosReturnPct, 2)}</div>
            </div>
            <div className="page-section" style={{ padding: 14 }}>
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>MDD</div>
              <div style={{ marginTop: 8, fontSize: 20, fontWeight: 800 }}>{formatPercent(viewModel.maxDrawdownPct, 2)}</div>
            </div>
            <div className="page-section" style={{ padding: 14 }}>
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>Profit Factor</div>
              <div style={{ marginTop: 8, fontSize: 20, fontWeight: 800 }}>{formatNumber(viewModel.profitFactor, 2)}</div>
            </div>
            <div className="page-section" style={{ padding: 14 }}>
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>승률</div>
              <div style={{ marginTop: 8, fontSize: 20, fontWeight: 800 }}>{formatPercent(viewModel.winRatePct, 2)}</div>
            </div>
            <div className="page-section" style={{ padding: 14 }}>
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>거래수 / 신뢰도</div>
              <div style={{ marginTop: 8, fontSize: 20, fontWeight: 800 }}>{formatNumber(viewModel.tradeCount, 0)} / {viewModel.reliability || '-'}</div>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 12 }}>
            <div className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 14, fontWeight: 700 }}>상태/로그 패널</div>
              <div style={{ marginTop: 10, display: 'grid', gap: 6, fontSize: 12, color: 'var(--text-3)' }}>
                <div>실행 상태: {status === 'loading' ? '실행 중' : status === 'error' ? '실패' : '완료'}</div>
                <div>시작 시각: {formatDateTime(runStartedAt)}</div>
                <div>최적화 시작 시각: {formatDateTime(optimizationStartedAt)}</div>
                <div>최근 메시지: {optimizationMessage || '-'}</div>
              </div>
              <div style={{ marginTop: 10, display: 'grid', gap: 6 }}>
                {[
                  { step: '요청', done: runRequested || status !== 'loading' },
                  { step: '실행', done: status === 'loading' || status === 'ok' || status === 'error' },
                  { step: '완료', done: status === 'ok' },
                  { step: '실패', done: status === 'error' },
                ].map((stage) => (
                  <div key={stage.step} style={{ border: '1px solid var(--border)', borderRadius: 10, padding: '8px 10px', fontSize: 12, color: stage.done ? 'var(--text-1)' : 'var(--text-4)' }}>
                    {stage.step}: {stage.done ? '반영됨' : '대기'}
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 10, display: 'grid', gap: 6 }}>
                {entries.slice(0, 5).map((entry) => (
                  <div key={entry.id} style={{ fontSize: 12, color: 'var(--text-3)' }}>
                    {formatDateTime(entry.timestamp)} · {entry.message}
                  </div>
                ))}
              </div>
            </div>

            <div className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 14, fontWeight: 700 }}>전략/시장/구간 성과</div>
              <div style={{ marginTop: 10, display: 'grid', gap: 6, fontSize: 12, color: 'var(--text-3)' }}>
                <div>전략: {validationSettings.strategy}</div>
                <div>시장: {draft.market_scope.toUpperCase()}</div>
                <div>학습 구간 수익률: {formatPercent(metricNumber(segmentTrain, 'total_return_pct'), 2)}</div>
                <div>검증 구간 수익률: {formatPercent(metricNumber(segmentValidation, 'total_return_pct'), 2)}</div>
                <div>OOS 구간 수익률: {formatPercent(metricNumber(segmentOos, 'total_return_pct'), 2)}</div>
              </div>
            </div>

            <div className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 14, fontWeight: 700 }}>진입·청산 사유별 성과</div>
              <div style={{ marginTop: 10, display: 'grid', gap: 6 }}>
                {reasonRows.map((row) => (
                  <div key={row.reason} style={{ border: '1px solid var(--border)', borderRadius: 10, padding: '8px 10px', fontSize: 12 }}>
                    <div>{row.reason}</div>
                    <div style={{ color: 'var(--text-3)', marginTop: 4 }}>거래 {formatCount(row.count, '건')} · 평균 {formatPercent(row.avgPnlPct, 2)}</div>
                  </div>
                ))}
                {reasonRows.length === 0 && <div style={{ fontSize: 12, color: 'var(--text-4)' }}>{UI_TEXT.empty.noReasonBreakdown}</div>}
              </div>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 12 }}>
            <div className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 14, fontWeight: 700 }}>최근 OOS 요약</div>
              <div style={{ marginTop: 10, display: 'grid', gap: 6, fontSize: 12, color: 'var(--text-3)' }}>
                <div>윈도우 수: {formatCount(snapshot.validation.summary?.windows, '개')}</div>
                <div>양수 OOS 윈도우: {formatCount(snapshot.validation.summary?.positive_windows, '개')}</div>
                <div>신뢰도: {reliabilityToKorean(String(snapshot.validation.summary?.oos_reliability || ''))}</div>
              </div>
            </div>

            <div className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 14, fontWeight: 700 }}>최적 파라미터</div>
              <div style={{ marginTop: 10, display: 'grid', gap: 6 }}>
                {Object.entries(globalParams).slice(0, 10).map(([key, value]) => (
                  <div key={key} style={{ fontSize: 12, color: 'var(--text-3)' }}>
                    {key}: {typeof value === 'number' ? formatNumber(value, 4) : String(value)}
                  </div>
                ))}
                {Object.keys(globalParams).length === 0 && <div style={{ fontSize: 12, color: 'var(--text-4)' }}>{UI_TEXT.empty.noOptimizedParams}</div>}
              </div>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 12 }}>
            <div className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 14, fontWeight: 700 }}>최근 실행 이력</div>
              <div style={{ marginTop: 10, display: 'grid', gap: 6 }}>
                {runHistory.slice(0, 10).map((item) => (
                  <div key={item.id} style={{ border: '1px solid var(--border)', borderRadius: 10, padding: '8px 10px', fontSize: 12 }}>
                    <div>{formatDateTime(item.at)} · {item.market.toUpperCase()} · {item.lookbackDays}일</div>
                    <div style={{ color: 'var(--text-3)', marginTop: 4 }}>상태 {item.status} · 수익률 {formatPercent(item.totalReturnPct, 2)}</div>
                  </div>
                ))}
                {runHistory.length === 0 && <div style={{ fontSize: 12, color: 'var(--text-4)' }}>{UI_TEXT.empty.noRunHistory}</div>}
              </div>
            </div>

            <div className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 14, fontWeight: 700 }}>최근 최적화 이력</div>
              <div style={{ marginTop: 10, display: 'grid', gap: 6 }}>
                {optimizationHistory.slice(0, 10).map((item) => (
                  <div key={item.id} style={{ border: '1px solid var(--border)', borderRadius: 10, padding: '8px 10px', fontSize: 12 }}>
                    <div>{formatDateTime(item.at)} · {item.status}</div>
                    <div style={{ color: 'var(--text-3)', marginTop: 4 }}>{item.message}</div>
                  </div>
                ))}
                {optimizationHistory.length === 0 && <div style={{ fontSize: 12, color: 'var(--text-4)' }}>{UI_TEXT.empty.noOptimizationHistory}</div>}
              </div>
            </div>

            <div className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 14, fontWeight: 700 }}>실패 로그 / 설정 저장 이력</div>
              <div style={{ marginTop: 10, display: 'grid', gap: 6 }}>
                {entries.filter((item) => item.level === 'error').slice(0, 5).map((item) => (
                  <div key={item.id} style={{ border: '1px solid var(--down-border)', borderRadius: 10, padding: '8px 10px', fontSize: 12, background: 'var(--down-bg)' }}>
                    {formatDateTime(item.timestamp)} · {item.message}
                  </div>
                ))}
                {entries.every((item) => item.level !== 'error') && <div style={{ fontSize: 12, color: 'var(--text-4)' }}>실패 로그가 없습니다.</div>}
                <div style={{ borderTop: '1px solid var(--border)', marginTop: 8, paddingTop: 8, display: 'grid', gap: 6 }}>
                  {saveHistory.slice(0, 5).map((item) => (
                    <div key={item.id} style={{ fontSize: 12, color: 'var(--text-3)' }}>
                      {formatDateTime(item.at)} · {item.market.toUpperCase()} · {item.lookbackDays}일 · {item.strategy}
                    </div>
                  ))}
                  {saveHistory.length === 0 && <div style={{ fontSize: 12, color: 'var(--text-4)' }}>{UI_TEXT.empty.noSaveHistory}</div>}
                </div>
              </div>
            </div>
          </div>

          {optimizationMessage && <div style={{ color: 'var(--text-3)', fontSize: 12 }}>{optimizationMessage}</div>}
          {loading && <div style={{ color: 'var(--text-3)', fontSize: 12 }}>{UI_TEXT.common.loading}</div>}
        </div>
      </div>

      <ConsoleConfirmDialog
        open={resetConfirmOpen}
        title={UI_TEXT.confirm.resetValidationTitle}
        message={UI_TEXT.confirm.resetValidationMessage}
        tone="danger"
        onConfirm={() => {
          handleResetSettings();
          setResetConfirmOpen(false);
        }}
        onCancel={() => setResetConfirmOpen(false)}
      />
    </div>
  );
}
