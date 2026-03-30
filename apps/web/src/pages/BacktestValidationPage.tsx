import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { getJSON, postJSON } from '../api/client';
import { ConsoleActionBar, ConsoleConfirmDialog } from '../components/ConsoleActionBar';
import { reliabilityToKorean, UI_TEXT } from '../constants/uiText';
import { useBacktest } from '../hooks/useBacktest';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import {
  formatValidationSettingsLabel,
  useValidationSettingsStore,
} from '../hooks/useValidationSettingsStore';
import { useToast } from '../hooks/useToast';
import type { BacktestQuery, BacktestTrade } from '../types';
import type { ActionBarStatusItem, BacktestViewModel, ConsoleSnapshot } from '../types/consoleView';
import { formatCount, formatDateTime, formatNumber, formatPercent } from '../utils/format';

interface BacktestValidationPageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
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

type BacktestPhase = 'idle' | 'requesting' | 'running' | 'finalizing' | 'success' | 'error';
type OptimizationPhase = 'idle' | 'requesting' | 'queued' | 'running' | 'success' | 'error';

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
    .sort((left, right) => right.count - left.count)
    .slice(0, 8);
}

function formatElapsed(startedAt: string) {
  if (!startedAt) return '-';
  const started = new Date(startedAt).getTime();
  if (!Number.isFinite(started)) return '-';
  const diff = Math.max(0, Math.floor((Date.now() - started) / 1000));
  const minutes = Math.floor(diff / 60);
  const seconds = diff % 60;
  if (minutes === 0) return `${seconds}초`;
  return `${minutes}분 ${String(seconds).padStart(2, '0')}초`;
}

function backtestPhaseLabel(phase: BacktestPhase): string {
  if (phase === 'requesting') return '요청 중';
  if (phase === 'running') return '실행 중';
  if (phase === 'finalizing') return '정리 중';
  if (phase === 'success') return '완료';
  if (phase === 'error') return '실패';
  return '대기';
}

function optimizationPhaseLabel(phase: OptimizationPhase): string {
  if (phase === 'requesting') return '요청 중';
  if (phase === 'queued') return '큐 등록';
  if (phase === 'running') return '실행 중';
  if (phase === 'success') return '완료';
  if (phase === 'error') return '실패';
  return '대기';
}

function buildPhaseIndex(phase: BacktestPhase): number {
  if (phase === 'requesting') return 0;
  if (phase === 'running') return 1;
  if (phase === 'finalizing') return 2;
  if (phase === 'success' || phase === 'error') return 3;
  return 0;
}

function buildOptimizationPhaseIndex(phase: OptimizationPhase): number {
  if (phase === 'requesting') return 0;
  if (phase === 'queued') return 1;
  if (phase === 'running') return 2;
  if (phase === 'success' || phase === 'error') return 3;
  return 0;
}

function updateHistoryItem<T extends { id: string }>(items: T[], id: string, next: Partial<T>) {
  return items.map((item) => (item.id === id ? { ...item, ...next } : item));
}

function renderHistoryList<T extends { id: string; at: string }>(
  items: T[],
  emptyMessage: string,
  render: (item: T) => React.ReactNode,
) {
  if (items.length === 0) {
    return <div className="empty-inline">{emptyMessage}</div>;
  }
  return (
    <div className="history-list">
      {items.map((item) => (
        <div key={item.id} className="history-item">
          {render(item)}
        </div>
      ))}
    </div>
  );
}

function ProcessStepper({
  title,
  steps,
  activeIndex,
  error,
  detail,
  timestamp,
}: {
  title: string;
  steps: string[];
  activeIndex: number;
  error?: boolean;
  detail: string;
  timestamp?: string;
}) {
  return (
    <div className="process-card">
      <div className="process-card-head">
        <div>
          <div className="process-card-title">{title}</div>
          <div className="process-card-detail">{detail}</div>
        </div>
        <div className={`inline-badge ${error ? 'is-danger' : activeIndex === 0 ? '' : 'is-success'}`}>
          {timestamp ? formatDateTime(timestamp) : '대기'}
        </div>
      </div>
      <div className="process-stepper">
        {steps.map((step, index) => {
          const done = index < activeIndex;
          const active = index === activeIndex;
          return (
            <div key={step} className={`process-step ${done ? 'is-done' : ''} ${active ? 'is-active' : ''} ${error && active ? 'is-error' : ''}`}>
              <span className="process-step-dot" aria-hidden="true" />
              <span>{step}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SummaryMetricCard({ label, value, detail, tone = 'neutral' }: { label: string; value: string; detail: string; tone?: 'neutral' | 'good' | 'bad' }) {
  return (
    <div className={`summary-metric-card ${tone !== 'neutral' ? `is-${tone}` : ''}`}>
      <div className="summary-metric-label">{label}</div>
      <div className="summary-metric-value">{value}</div>
      <div className="summary-metric-detail">{detail}</div>
    </div>
  );
}

function FieldBlock({ label, help, children }: { label: string; help?: string; children: ReactNode }) {
  return (
    <label className="settings-field">
      <span className="settings-field-label">{label}</span>
      {help && <span className="settings-field-help">{help}</span>}
      {children}
    </label>
  );
}

export function BacktestValidationPage({ snapshot, loading, errorMessage, onRefresh }: BacktestValidationPageProps) {
  const { pushToast } = useToast();
  const { entries, push, clear } = useConsoleLogs();
  const validationStore = useValidationSettingsStore();
  const [initialQuery] = useState<BacktestQuery>(() => validationStore.savedQuery);
  const { data, run } = useBacktest(initialQuery);
  const [runHistory, setRunHistory] = useState<RunHistoryItem[]>(() => readArray<RunHistoryItem>(RUN_HISTORY_KEY));
  const [optimizationHistory, setOptimizationHistory] = useState<OptimizationHistoryItem[]>(() => readArray<OptimizationHistoryItem>(OPT_HISTORY_KEY));
  const [saveHistory, setSaveHistory] = useState<SettingSaveItem[]>(() => readArray<SettingSaveItem>(SAVE_HISTORY_KEY));
  const [backtestPhase, setBacktestPhase] = useState<BacktestPhase>('idle');
  const [optimizationPhase, setOptimizationPhase] = useState<OptimizationPhase>('idle');
  const [runStartedAt, setRunStartedAt] = useState('');
  const [runFinishedAt, setRunFinishedAt] = useState('');
  const [optimizationStartedAt, setOptimizationStartedAt] = useState('');
  const [optimizationUpdatedAt, setOptimizationUpdatedAt] = useState('');
  const [backtestMessage, setBacktestMessage] = useState('현재 저장된 설정 요약을 확인한 뒤 실행하면 됩니다.');
  const [optimizationMessage, setOptimizationMessage] = useState('최적화는 백그라운드 작업으로 분리되어 실행됩니다.');
  const [optimizationRunning, setOptimizationRunning] = useState(false);
  const [optimizedParams, setOptimizedParams] = useState<Record<string, unknown> | null>(null);
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false);
  const [settingsSaving, setSettingsSaving] = useState(false);

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

  const settingsSummaryLines = useMemo(
    () => formatValidationSettingsLabel(validationStore.draftSettings, validationStore.draftQuery),
    [validationStore.draftQuery, validationStore.draftSettings],
  );

  const segmentTrain = snapshot.validation.segments?.train as Record<string, unknown> | undefined;
  const segmentValidation = snapshot.validation.segments?.validation as Record<string, unknown> | undefined;
  const segmentOos = snapshot.validation.segments?.oos as Record<string, unknown> | undefined;
  const globalParams = (optimizedParams?.global_params as Record<string, unknown> | undefined) || {};
  const validationPolicy = snapshot.engine.execution?.state?.validation_policy;
  const optimizedState = snapshot.engine.execution?.state?.optimized_params;
  const minTradesPolicy = Math.max(1, Number(validationPolicy?.validation_min_trades || 1));

  const statusItems = useMemo<ActionBarStatusItem[]>(() => ([
    {
      label: '백테스트',
      value: backtestPhaseLabel(backtestPhase),
      tone: backtestPhase === 'success' ? 'good' : backtestPhase === 'error' ? 'bad' : 'neutral',
    },
    {
      label: '최적화',
      value: optimizationPhaseLabel(optimizationPhase),
      tone: optimizationPhase === 'success' ? 'good' : optimizationPhase === 'error' ? 'bad' : 'neutral',
    },
    {
      label: '설정 상태',
      value: validationStore.unsaved ? '저장 필요' : '저장됨',
      tone: validationStore.unsaved ? 'bad' : 'good',
    },
    {
      label: 'OOS 신뢰도',
      value: viewModel.reliability || '-',
      tone: viewModel.reliability === '낮음' ? 'bad' : 'neutral',
    },
  ]), [backtestPhase, optimizationPhase, validationStore.unsaved, viewModel.reliability]);

  const adoptionDecision = useMemo(() => {
    const oosReturn = viewModel.oosReturnPct ?? null;
    const profitFactor = viewModel.profitFactor ?? null;
    const drawdownAbs = Math.abs(viewModel.maxDrawdownPct ?? 0);
    const tradeCount = viewModel.tradeCount ?? 0;
    const reliability = viewModel.reliability || '-';
    const gateEnabled = Boolean(validationPolicy?.validation_gate_enabled);

    if (
      oosReturn !== null
      && oosReturn > 0
      && reliability === '높음'
      && (profitFactor ?? 0) >= 1.1
      && drawdownAbs <= 20
      && tradeCount >= minTradesPolicy
    ) {
      return {
        label: '즉시 사용 가능',
        tone: 'good' as const,
        action: '현재 설정으로 실거래 반영 후보입니다. 포지션 한도만 보수적으로 시작하세요.',
      };
    }

    if (
      oosReturn === null
      || reliability === '낮음'
      || (profitFactor ?? 0) < 0.95
      || oosReturn < -2
      || drawdownAbs > 30
      || (gateEnabled && tradeCount < minTradesPolicy)
    ) {
      return {
        label: '거절',
        tone: 'bad' as const,
        action: '현재 상태로는 운영 반영 금지. 파라미터/기간 재설정 후 재검증이 필요합니다.',
      };
    }

    return {
      label: '보류',
      tone: 'neutral' as const,
      action: '결정 보류 상태입니다. 최적화 실행 후 OOS/낙폭 재확인 뒤 채택 여부를 결정하세요.',
    };
  }, [
    minTradesPolicy,
    validationPolicy?.validation_gate_enabled,
    viewModel.maxDrawdownPct,
    viewModel.oosReturnPct,
    viewModel.profitFactor,
    viewModel.reliability,
    viewModel.tradeCount,
  ]);

  const updateRunHistory = useCallback((next: RunHistoryItem[]) => {
    setRunHistory(next);
    writeArray(RUN_HISTORY_KEY, next);
  }, []);

  const updateOptimizationHistory = useCallback((next: OptimizationHistoryItem[]) => {
    setOptimizationHistory(next);
    writeArray(OPT_HISTORY_KEY, next);
  }, []);

  const updateSaveHistory = useCallback((next: SettingSaveItem[]) => {
    setSaveHistory(next);
    writeArray(SAVE_HISTORY_KEY, next);
  }, []);

  useEffect(() => {
    let alive = true;

    const boot = async () => {
      try {
        const [statusPayload, paramsPayload] = await Promise.all([
          getJSON<{ running?: boolean }>('/api/optimization-status', { noStore: true }),
          getJSON<Record<string, unknown>>('/api/optimized-params', { noStore: true }),
        ]);

        if (!alive) return;

        if (statusPayload.running) {
          setOptimizationRunning(true);
          setOptimizationPhase('running');
          setOptimizationStartedAt(nowIso());
          setOptimizationMessage('이미 실행 중인 최적화 작업을 추적 중입니다.');
        }

        if (paramsPayload.status === 'ok') {
          setOptimizedParams(paramsPayload);
        }
      } catch {
        if (!alive) return;
        push('warning', '최적화 상태 초기 조회에 실패했습니다.', '실행 시 다시 상태를 확인합니다.', 'optimization');
      }
    };

    void boot();

    return () => {
      alive = false;
    };
  }, [push]);

  useEffect(() => {
    if (!optimizationRunning) return undefined;
    const timer = window.setInterval(async () => {
      try {
        const statusPayload = await getJSON<{ running?: boolean }>('/api/optimization-status', { noStore: true });
        if (statusPayload.running) {
          setOptimizationPhase((current) => (current === 'queued' ? 'running' : current));
          setOptimizationMessage('최적화가 백그라운드에서 계속 실행 중입니다.');
          return;
        }

        const paramsPayload = await getJSON<Record<string, unknown>>('/api/optimized-params', { noStore: true });
        setOptimizationRunning(false);
        setOptimizationPhase('success');
        setOptimizationUpdatedAt(nowIso());
        setOptimizationMessage('최적화가 완료되었습니다. 최신 파라미터를 확인하세요.');
        if (paramsPayload.status === 'ok') setOptimizedParams(paramsPayload);
        push('success', '최적화가 완료되었습니다.', '결과 카드가 갱신되었습니다.', 'optimization');
        pushToast({
          tone: 'success',
          title: '최적화 완료',
          description: '최신 파라미터와 상태 카드가 갱신되었습니다.',
        });
        const historyItem: OptimizationHistoryItem = {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          at: nowIso(),
          status: '완료',
          message: '백그라운드 최적화 완료',
        };
        updateOptimizationHistory([historyItem, ...optimizationHistory].slice(0, 30));
      } catch {
        setOptimizationRunning(false);
        setOptimizationPhase('error');
        setOptimizationUpdatedAt(nowIso());
        setOptimizationMessage('최적화 상태 조회 중 오류가 발생했습니다.');
        push('error', '최적화 상태 조회 중 오류가 발생했습니다.', '로그와 서버 상태를 확인하세요.', 'optimization');
        pushToast({
          tone: 'error',
          title: '최적화 상태 조회 실패',
          description: '최적화 로그와 서버 상태를 확인해 주세요.',
        });
      }
    }, 8_000);
    return () => window.clearInterval(timer);
  }, [optimizationHistory, optimizationRunning, push, pushToast, updateOptimizationHistory]);

  const handleRefreshAll = useCallback(() => {
    onRefresh();
    push('info', '검증 화면 데이터를 새로고침했습니다.', '실행 상태와 리포트 스냅샷을 다시 불러옵니다.', 'refresh');
    pushToast({
      tone: 'info',
      title: '화면을 새로고침했습니다.',
      description: '실행 상태와 리포트 스냅샷을 최신 값으로 다시 불러옵니다.',
    });
  }, [onRefresh, push, pushToast]);

  const handleRunBacktest = useCallback(async () => {
    if (backtestPhase === 'requesting' || backtestPhase === 'running' || backtestPhase === 'finalizing') return;

    const historyId = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    updateRunHistory([
      {
        id: historyId,
        at: nowIso(),
        market: validationStore.draftQuery.market_scope,
        lookbackDays: validationStore.draftQuery.lookback_days,
        status: '실행 중',
        totalReturnPct: null,
      },
      ...runHistory,
    ].slice(0, 30));

    setRunStartedAt(nowIso());
    setRunFinishedAt('');
    setBacktestPhase('requesting');
    setBacktestMessage('백테스트 요청을 전송했습니다.');
    push('info', '백테스트 실행을 시작했습니다.', `시장 ${validationStore.draftQuery.market_scope.toUpperCase()}, 기간 ${validationStore.draftQuery.lookback_days}일`, 'backtest');
    pushToast({ tone: 'info', title: '백테스트 실행 시작', description: '완료될 때까지 중복 실행은 잠시 잠깁니다.' });

    await Promise.resolve();
    setBacktestPhase('running');
    setBacktestMessage('서버에서 성과 계산과 검증 요약을 생성하고 있습니다.');

    const result = await run(validationStore.draftQuery);
    setBacktestPhase('finalizing');
    setBacktestMessage('결과를 정리 중입니다.');
    await new Promise((resolve) => window.setTimeout(resolve, 180));

    const finishedAt = nowIso();
    setRunFinishedAt(finishedAt);

    if (result.ok) {
      setBacktestPhase('success');
      setBacktestMessage('백테스트가 완료되었습니다.');
      updateRunHistory(updateHistoryItem([
        {
          id: historyId,
          at: finishedAt,
          market: validationStore.draftQuery.market_scope,
          lookbackDays: validationStore.draftQuery.lookback_days,
          status: '완료',
          totalReturnPct: metricNumber(result.payload?.metrics as Record<string, unknown> | undefined, 'total_return_pct'),
        },
        ...runHistory,
      ].slice(0, 30), historyId, {
        status: '완료',
        totalReturnPct: metricNumber(result.payload?.metrics as Record<string, unknown> | undefined, 'total_return_pct'),
      }));
      push('success', '백테스트가 완료되었습니다.', '성과 요약과 최근 실행 이력이 갱신되었습니다.', 'backtest');
      pushToast({ tone: 'success', title: '백테스트 완료', description: '성과 요약과 최근 실행 이력이 갱신되었습니다.' });
      return;
    }

    setBacktestPhase('error');
    setBacktestMessage(result.error || '백테스트 실행 중 오류가 발생했습니다.');
    updateRunHistory(updateHistoryItem([
      {
        id: historyId,
        at: finishedAt,
        market: validationStore.draftQuery.market_scope,
        lookbackDays: validationStore.draftQuery.lookback_days,
        status: '실패',
        totalReturnPct: null,
      },
      ...runHistory,
    ].slice(0, 30), historyId, { status: '실패', totalReturnPct: null }));
    push('error', '백테스트 실행이 실패했습니다.', result.error || '상단 로그 보기에서 상세 원인을 확인하세요.', 'backtest');
    pushToast({ tone: 'error', title: '백테스트 실패', description: result.error || '로그와 서버 상태를 확인해 주세요.' });
  }, [backtestPhase, push, pushToast, run, runHistory, updateRunHistory, validationStore.draftQuery]);

  const handleRunOptimization = useCallback(async () => {
    if (optimizationRunning || optimizationPhase === 'requesting') return;

    setOptimizationPhase('requesting');
    setOptimizationStartedAt(nowIso());
    setOptimizationUpdatedAt('');
    setOptimizationMessage('최적화 요청을 전송하고 있습니다.');

    try {
      const response = await postJSON<{ status?: string; error?: string }>('/api/run-optimization');
      const payload = response.data;

      if (payload.status === 'started' || payload.status === 'already_running') {
        const alreadyRunning = payload.status === 'already_running';
        setOptimizationRunning(true);
        setOptimizationPhase(alreadyRunning ? 'running' : 'queued');
        setOptimizationMessage(alreadyRunning ? '이미 실행 중인 최적화 작업을 추적합니다.' : '최적화가 큐에 등록되었습니다.');
        push('info', alreadyRunning ? '최적화가 이미 실행 중입니다.' : '최적화를 시작했습니다.', '완료 전까지 동일 작업은 다시 실행되지 않습니다.', 'optimization');
        pushToast({
          tone: 'info',
          title: alreadyRunning ? '최적화 작업 확인' : '최적화 시작',
          description: alreadyRunning ? '이미 실행 중인 작업을 계속 모니터링합니다.' : '완료되면 결과 카드와 로그가 자동으로 갱신됩니다.',
        });
        const historyItem: OptimizationHistoryItem = {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          at: nowIso(),
          status: alreadyRunning ? '실행 중' : '큐 등록',
          message: alreadyRunning ? '이미 실행 중인 작업에 연결' : '새 최적화 요청',
        };
        updateOptimizationHistory([historyItem, ...optimizationHistory].slice(0, 30));
        return;
      }

      setOptimizationPhase('error');
      setOptimizationMessage(payload.error || '최적화 요청 실패');
      push('error', '최적화 요청이 실패했습니다.', payload.error || '', 'optimization');
      pushToast({ tone: 'error', title: '최적화 요청 실패', description: payload.error || '백엔드 최적화 엔드포인트를 확인해 주세요.' });
    } catch {
      setOptimizationPhase('error');
      setOptimizationMessage('최적화 요청 중 오류가 발생했습니다.');
      push('error', '최적화 요청 중 오류가 발생했습니다.', '네트워크 또는 서버 상태를 확인하세요.', 'optimization');
      pushToast({ tone: 'error', title: '최적화 요청 실패', description: '요청 전송 중 오류가 발생했습니다.' });
    }
  }, [optimizationHistory, optimizationPhase, optimizationRunning, push, pushToast, updateOptimizationHistory]);

  const handleSaveSettings = useCallback(async () => {
    if (settingsSaving) return;
    setSettingsSaving(true);
    await new Promise((resolve) => window.setTimeout(resolve, 120));
    const savedAt = validationStore.saveDraft();
    const historyItem: SettingSaveItem = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      at: savedAt,
      market: validationStore.draftQuery.market_scope,
      lookbackDays: validationStore.draftQuery.lookback_days,
      strategy: validationStore.draftSettings.strategy,
    };
    updateSaveHistory([historyItem, ...saveHistory].slice(0, 30));
    push('success', '검증 설정을 저장했습니다.', `${validationStore.draftQuery.market_scope.toUpperCase()} · ${validationStore.draftQuery.lookback_days}일`, 'settings');
    pushToast({ tone: 'success', title: '설정 저장 완료', description: '실행 패널 요약과 저장 필요 배지가 즉시 갱신되었습니다.' });
    setSettingsSaving(false);
  }, [push, pushToast, saveHistory, settingsSaving, updateSaveHistory, validationStore]);

  const handleResetSettings = useCallback(() => {
    validationStore.resetDraft();
    setBacktestMessage('설정 초안을 기본값으로 되돌렸습니다. 저장 후 실행할 수 있습니다.');
    push('warning', '검증 설정 초안을 기본값으로 되돌렸습니다.', '저장 전까지는 저장 필요 상태가 유지됩니다.', 'settings');
    pushToast({ tone: 'warning', title: '설정 초안 초기화', description: '기본값으로 되돌렸습니다. 저장하면 실행 패널에 반영됩니다.' });
  }, [push, pushToast, validationStore]);

  const settingsPanel = (
    <div className="settings-panel-grid">
      <FieldBlock label="시장" help="백테스트 대상 시장을 선택합니다.">
        <select
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          value={validationStore.draftQuery.market_scope}
          onChange={(event) => validationStore.setDraftQuery((prev) => ({ ...prev, market_scope: event.target.value as BacktestQuery['market_scope'] }))}
        >
          <option value="kospi">KOSPI</option>
          <option value="nasdaq">NASDAQ</option>
        </select>
      </FieldBlock>

      <FieldBlock label="전략 이름" help="실행 패널과 저장 이력에 함께 표시됩니다.">
        <input
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          value={validationStore.draftSettings.strategy}
          onChange={(event) => validationStore.setDraftSettings((prev) => ({ ...prev, strategy: event.target.value }))}
          placeholder="예: 공통 전략 엔진"
        />
      </FieldBlock>

      <FieldBlock label="백테스트 기간(일)" help="최소 180일, 30일 단위 권장">
        <input
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          type="number"
          min={180}
          step={30}
          value={validationStore.draftQuery.lookback_days}
          onChange={(event) => validationStore.setDraftQuery((prev) => ({ ...prev, lookback_days: Math.max(180, Number(event.target.value) || 180) }))}
        />
      </FieldBlock>

      <FieldBlock label="학습 기간(일)" help="최소 30일, 10일 단위">
        <input
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          type="number"
          min={30}
          step={10}
          value={validationStore.draftSettings.trainingDays}
          onChange={(event) => validationStore.setDraftSettings((prev) => ({ ...prev, trainingDays: Math.max(30, Number(event.target.value) || 30) }))}
        />
      </FieldBlock>

      <FieldBlock label="검증 기간(일)" help="최소 20일, 10일 단위">
        <input
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          type="number"
          min={20}
          step={10}
          value={validationStore.draftSettings.validationDays}
          onChange={(event) => validationStore.setDraftSettings((prev) => ({ ...prev, validationDays: Math.max(20, Number(event.target.value) || 20) }))}
        />
      </FieldBlock>

      <FieldBlock label="Walk-forward" help="구간별 재학습 여부">
        <select
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          value={validationStore.draftSettings.walkForward ? 'on' : 'off'}
          onChange={(event) => validationStore.setDraftSettings((prev) => ({ ...prev, walkForward: event.target.value === 'on' }))}
        >
          <option value="on">사용</option>
          <option value="off">미사용</option>
        </select>
      </FieldBlock>

      <FieldBlock label="최소 거래 수(건)" help="검증 통과 최소 거래 수">
        <input
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          type="number"
          min={1}
          step={1}
          value={validationStore.draftSettings.minTrades}
          onChange={(event) => validationStore.setDraftSettings((prev) => ({ ...prev, minTrades: Math.max(1, Number(event.target.value) || 1) }))}
        />
      </FieldBlock>

      <FieldBlock label="목표 함수" help="최적화 판단 기준">
        <select
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          value={validationStore.draftSettings.objective}
          onChange={(event) => validationStore.setDraftSettings((prev) => ({ ...prev, objective: event.target.value }))}
        >
          <option>수익 우선</option>
          <option>수익+안정 균형</option>
        </select>
      </FieldBlock>

      <div className="settings-panel-actions">
        <button className="console-action-button is-primary" onClick={() => { void handleSaveSettings(); }} disabled={settingsSaving}>
          {settingsSaving ? <span className="button-content"><span className="button-spinner" aria-hidden="true" />저장 중...</span> : '설정 저장'}
        </button>
        <button className="console-action-button is-danger" onClick={() => setResetConfirmOpen(true)} disabled={settingsSaving}>초안 초기화</button>
      </div>
    </div>
  );

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell" style={{ display: 'grid', gap: 16 }}>
          <ConsoleActionBar
            title="검증 콘솔"
            subtitle="설정은 상단 패널에서 저장하고, 이 화면에서는 실행/상태/결과만 봅니다."
            lastUpdated={snapshot.fetchedAt}
            loading={loading}
            errorMessage={errorMessage}
            statusItems={statusItems}
            onRefresh={handleRefreshAll}
            logs={entries}
            onClearLogs={clear}
            settingsPanel={settingsPanel}
            settingsDirty={validationStore.unsaved}
            settingsSavedAt={validationStore.lastSavedAt}
          />

          <div className="validation-layout">
            <div className="validation-report-column">
              <div className={`page-section validation-report-card decision-state-card is-${adoptionDecision.tone}`}>
                <div className="section-kicker">Adoption Decision</div>
                <div className="section-head-row">
                  <div>
                    <div className="section-title">전략 채택 상태: {adoptionDecision.label}</div>
                    <div className="section-copy">{adoptionDecision.action}</div>
                  </div>
                  <div className={`inline-badge ${adoptionDecision.tone === 'good' ? 'is-success' : adoptionDecision.tone === 'bad' ? 'is-danger' : 'is-warning'}`}>
                    {adoptionDecision.label}
                  </div>
                </div>
                <div className="summary-metric-grid">
                  <SummaryMetricCard
                    label="OOS 수익률"
                    value={formatPercent(viewModel.oosReturnPct, 2)}
                    detail={`신뢰도 ${viewModel.reliability || '-'} · 윈도우 ${formatCount(snapshot.validation.summary?.windows, '개')}`}
                    tone={(viewModel.oosReturnPct || 0) >= 0 ? 'good' : 'bad'}
                  />
                  <SummaryMetricCard
                    label="낙폭 / PF"
                    value={`${formatPercent(viewModel.maxDrawdownPct, 2)} / ${formatNumber(viewModel.profitFactor, 2)}`}
                    detail={`거래 ${formatCount(viewModel.tradeCount, '건')} · 승률 ${formatPercent(viewModel.winRatePct, 2)}`}
                  />
                  <SummaryMetricCard
                    label="정책 Gate"
                    value={validationPolicy?.validation_gate_enabled ? '활성' : '비활성'}
                    detail={`min trades ${formatNumber(validationPolicy?.validation_min_trades, 0)} · optimized ${String(optimizedState?.version || '-')}`}
                  />
                </div>
              </div>

              <div className="validation-report-grid">
                <div className="page-section" style={{ padding: 16 }}>
                  <div className="section-title">구간 성과</div>
                  <div className="detail-list">
                    <div>전략: {validationStore.draftSettings.strategy}</div>
                    <div>시장: {validationStore.draftQuery.market_scope.toUpperCase()}</div>
                    <div>학습 구간 수익률: {formatPercent(metricNumber(segmentTrain, 'total_return_pct'), 2)}</div>
                    <div>검증 구간 수익률: {formatPercent(metricNumber(segmentValidation, 'total_return_pct'), 2)}</div>
                    <div>OOS 구간 수익률: {formatPercent(metricNumber(segmentOos, 'total_return_pct'), 2)}</div>
                  </div>
                </div>

                <div className="page-section" style={{ padding: 16 }}>
                  <div className="section-title">최적 파라미터</div>
                  <div className="detail-list">
                    {Object.entries(globalParams).slice(0, 8).map(([key, value]) => (
                      <div key={key}>{key}: {typeof value === 'number' ? formatNumber(value, 4) : String(value)}</div>
                    ))}
                    {Object.keys(globalParams).length === 0 && <div className="empty-inline">{UI_TEXT.empty.noOptimizedParams}</div>}
                  </div>
                </div>
              </div>
            </div>

            <div className="validation-console-column">
              <div className="page-section validation-console-card">
                <div className="section-kicker">Execution</div>
                <div className="section-head-row">
                  <div>
                    <div className="section-title">실행 패널</div>
                    <div className="section-copy">설정 확인 후 백테스트/최적화만 빠르게 실행합니다.</div>
                  </div>
                  <div className={`inline-badge ${validationStore.unsaved ? 'is-warning' : 'is-success'}`}>
                    {validationStore.unsaved ? '저장 필요' : '저장됨'}
                  </div>
                </div>

                <div className="summary-rail is-compact">
                  {settingsSummaryLines.slice(0, 3).map((line) => (
                    <div key={line} className="summary-rail-item">{line}</div>
                  ))}
                </div>

                {validationStore.unsaved && (
                  <div className="inline-warning-card">저장하지 않은 변경 사항이 있습니다. 실행값 확정 전 저장을 권장합니다.</div>
                )}

                <div className="execution-button-row is-split">
                  <button
                    className="console-action-button is-primary"
                    onClick={() => { void handleRunBacktest(); }}
                    disabled={backtestPhase === 'requesting' || backtestPhase === 'running' || backtestPhase === 'finalizing'}
                  >
                    {backtestPhase === 'requesting' || backtestPhase === 'running' || backtestPhase === 'finalizing'
                      ? <span className="button-content"><span className="button-spinner" aria-hidden="true" />백테스트 진행 중...</span>
                      : '백테스트 실행'}
                  </button>
                  <button
                    className="console-action-button"
                    onClick={() => { void handleRunOptimization(); }}
                    disabled={optimizationRunning || optimizationPhase === 'requesting'}
                  >
                    {optimizationRunning || optimizationPhase === 'requesting'
                      ? <span className="button-content"><span className="button-spinner" aria-hidden="true" />최적화 진행 중...</span>
                      : '최적화 실행'}
                  </button>
                </div>

                <div className="validation-inline-status">
                  <div>백테스트: {backtestPhaseLabel(backtestPhase)} · {backtestMessage}</div>
                  <div>최적화: {optimizationPhaseLabel(optimizationPhase)} · {optimizationMessage}</div>
                  <div>최근 실행: {runFinishedAt ? formatDateTime(runFinishedAt) : '없음'}</div>
                </div>
              </div>

              <div className="process-grid">
                <ProcessStepper
                  title="백테스트 진행"
                  steps={['요청', '계산', '정리', backtestPhase === 'error' ? '실패' : '완료']}
                  activeIndex={buildPhaseIndex(backtestPhase)}
                  error={backtestPhase === 'error'}
                  detail={`경과 ${formatElapsed(runStartedAt)}`}
                  timestamp={runStartedAt || runFinishedAt}
                />
                <ProcessStepper
                  title="최적화 진행"
                  steps={['요청', '큐', '실행', optimizationPhase === 'error' ? '실패' : '완료']}
                  activeIndex={buildOptimizationPhaseIndex(optimizationPhase)}
                  error={optimizationPhase === 'error'}
                  detail={`경과 ${formatElapsed(optimizationStartedAt)}`}
                  timestamp={optimizationStartedAt || optimizationUpdatedAt}
                />
              </div>
            </div>
          </div>

          <div className="page-section" style={{ padding: 16 }}>
            <div className="section-head-row">
              <div>
                <div className="section-title">참고 이력 / 로그</div>
                <div className="section-copy">채택 판단 후 필요할 때만 보는 보조 기록입니다.</div>
              </div>
            </div>
            <div className="validation-history-grid">
              <div>
                <div className="section-subtitle">실행 이력</div>
                {renderHistoryList(runHistory.slice(0, 6), UI_TEXT.empty.noRunHistory, (item) => (
                  <>
                    <div>{formatDateTime(item.at)} · {item.market.toUpperCase()} · {item.lookbackDays}일</div>
                    <div className="history-item-copy">상태 {item.status} · 수익률 {formatPercent(item.totalReturnPct, 2)}</div>
                  </>
                ))}
              </div>
              <div>
                <div className="section-subtitle">최적화 / 저장 / 실패 로그</div>
                <div className="history-list">
                  {optimizationHistory.slice(0, 3).map((item) => (
                    <div key={item.id} className="history-item">
                      <div>{formatDateTime(item.at)} · {item.status}</div>
                      <div className="history-item-copy">{item.message}</div>
                    </div>
                  ))}
                  {saveHistory.slice(0, 3).map((item) => (
                    <div key={item.id} className="history-item">
                      <div>{formatDateTime(item.at)} · {item.market.toUpperCase()}</div>
                      <div className="history-item-copy">{item.lookbackDays}일 · {item.strategy}</div>
                    </div>
                  ))}
                  {entries.filter((item) => item.level === 'error').slice(0, 2).map((item) => (
                    <div key={item.id} className="history-item is-danger">
                      <div>{formatDateTime(item.timestamp)} · {item.message}</div>
                      {item.context && <div className="history-item-copy">{item.context}</div>}
                    </div>
                  ))}
                  {optimizationHistory.length === 0 && saveHistory.length === 0 && entries.every((item) => item.level !== 'error') && <div className="empty-inline">최근 이력이 없습니다.</div>}
                </div>
              </div>
              <div>
                <div className="section-subtitle">사유별 성과</div>
                <div className="history-list">
                  {reasonRows.map((row) => (
                    <div key={row.reason} className="history-item">
                      <div>{row.reason}</div>
                      <div className="history-item-copy">거래 {formatCount(row.count, '건')} · 평균 {formatPercent(row.avgPnlPct, 2)}</div>
                    </div>
                  ))}
                  {reasonRows.length === 0 && <div className="empty-inline">{UI_TEXT.empty.noReasonBreakdown}</div>}
                </div>
              </div>
            </div>
          </div>

          {loading && <div style={{ color: 'var(--text-3)', fontSize: 12 }}>{UI_TEXT.common.loading}</div>}
        </div>
      </div>

      <ConsoleConfirmDialog
        open={resetConfirmOpen}
        title={UI_TEXT.confirm.resetValidationTitle}
        message={UI_TEXT.confirm.resetValidationMessage}
        details={[
          '백테스트 기간, 학습/검증 기간, 목표 함수 초안이 기본값으로 되돌아갑니다.',
          '저장하지 않은 변경 사항은 모두 사라집니다.',
        ]}
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
