import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ChangeEvent, ReactNode } from 'react';
import { getJSON, postJSON } from '../api/client';
import { fetchValidationWalkForward } from '../api/domain';
import { ConsoleActionBar, ConsoleConfirmDialog } from '../components/ConsoleActionBar';
import { reliabilityToKorean, UI_TEXT } from '../constants/uiText';
import { useBacktest } from '../hooks/useBacktest';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import {
  formatValidationSettingsLabel,
  useValidationSettingsStore,
} from '../hooks/useValidationSettingsStore';
import { useToast } from '../hooks/useToast';
import type { BacktestData, BacktestQuery, BacktestTrade } from '../types';
import type { ActionBarStatusItem, BacktestViewModel, ConsoleSnapshot } from '../types/consoleView';
import type { ValidationResponse } from '../types/domain';
import {
  buildScoreComponentRows,
  buildTailRiskRows,
  describeScoreDecision,
  extractStrategyScorecard,
  strongestComponents,
  tailRiskHeadline,
  weakestComponents,
} from '../utils/strategyScorecard';
import { formatCount, formatDateTime, formatNumber, formatPercent } from '../utils/format';

interface BacktestValidationPageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
}

type ValidationStoreSnapshot = ReturnType<typeof useValidationSettingsStore>;

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
const EXECUTED_RUN_KEY = 'console_validation_executed_run_v1';

interface ExecutedRunState {
  executedAt: string;
  query: BacktestQuery;
  settings: ValidationStoreSnapshot['savedSettings'];
  backtest: BacktestData;
  validation: ValidationResponse;
}

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

function readJson<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

function writeJson<T>(key: string, value: T) {
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


function SettingsSection({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <section className="settings-panel-section">
      <div className="settings-panel-section-head">
        <div className="settings-panel-section-title">{title}</div>
        {description && <div className="settings-panel-section-copy">{description}</div>}
      </div>
      <div className="settings-panel-section-grid">{children}</div>
    </section>
  );
}

export function BacktestValidationPage({ snapshot, loading, errorMessage, onRefresh }: BacktestValidationPageProps) {
  const { pushToast } = useToast();
  const { entries, push, clear } = useConsoleLogs();
  const validationStore = useValidationSettingsStore();
  const [initialQuery] = useState<BacktestQuery>(() => validationStore.savedQuery);
  const { run } = useBacktest(initialQuery, { autoRun: false });
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
  const [executedRun, setExecutedRun] = useState<ExecutedRunState | null>(() => readJson<ExecutedRunState>(EXECUTED_RUN_KEY));

  const activeBacktest = executedRun?.backtest || null;
  const validationResult = executedRun?.validation || snapshot.validation;
  const metrics = activeBacktest?.metrics as Record<string, unknown> | undefined;
  const oos = validationResult.segments?.oos;
  const reasonRows = useMemo(() => aggregateByReason(activeBacktest?.trades || []), [activeBacktest?.trades]);

  const viewModel = useMemo<BacktestViewModel>(() => ({
    totalReturnPct: metricNumber(metrics, 'total_return_pct'),
    oosReturnPct: oos ? metricNumber(oos as Record<string, unknown>, 'total_return_pct') : null,
    maxDrawdownPct: metricNumber(metrics, 'max_drawdown_pct'),
    profitFactor: metricNumber(metrics, 'profit_factor'),
    winRatePct: metricNumber(metrics, 'win_rate_pct'),
    tradeCount: metricNumber(metrics, 'trade_count'),
    reliability: reliabilityToKorean(String(validationResult.summary?.oos_reliability || '')),
  }), [metrics, oos, validationResult.summary?.oos_reliability]);

  const settingsSummaryLines = useMemo(
    () => formatValidationSettingsLabel(validationStore.draftSettings, validationStore.draftQuery),
    [validationStore.draftQuery, validationStore.draftSettings],
  );
  const savedSettingsSummaryLines = useMemo(
    () => formatValidationSettingsLabel(validationStore.savedSettings, validationStore.savedQuery),
    [validationStore.savedQuery, validationStore.savedSettings],
  );
  const executedSettingsSummaryLines = useMemo(
    () => executedRun ? formatValidationSettingsLabel(executedRun.settings, executedRun.query) : [],
    [executedRun],
  );

  const segmentTrain = validationResult.segments?.train as Record<string, unknown> | undefined;
  const segmentValidation = validationResult.segments?.validation as Record<string, unknown> | undefined;
  const segmentOos = validationResult.segments?.oos as Record<string, unknown> | undefined;
  const globalParams = (optimizedParams?.global_params as Record<string, unknown> | undefined) || {};
  const validationPolicy = snapshot.engine.execution?.state?.validation_policy;
  const optimizedState = snapshot.engine.execution?.state?.optimized_params;
  const minTradesPolicy = Math.max(1, Number(validationPolicy?.validation_min_trades || 1));

  const walkForwardScorecard = useMemo(
    () => extractStrategyScorecard(validationResult.scorecard || segmentOos?.strategy_scorecard),
    [segmentOos, validationResult.scorecard],
  );
  const latestBacktestScorecard = useMemo(
    () => extractStrategyScorecard(activeBacktest?.scorecard),
    [activeBacktest?.scorecard],
  );
  const primaryScorecard = walkForwardScorecard || latestBacktestScorecard;
  const primaryScoreSource = walkForwardScorecard ? 'Walk-forward OOS' : latestBacktestScorecard ? '최근 백테스트' : '데이터 없음';
  const scoreDecision = useMemo(() => describeScoreDecision(primaryScorecard), [primaryScorecard]);
  const scoreComponentRows = useMemo(() => buildScoreComponentRows(primaryScorecard), [primaryScorecard]);
  const tailRows = useMemo(() => buildTailRiskRows(primaryScorecard), [primaryScorecard]);
  const bestComponents = useMemo(() => strongestComponents(primaryScorecard), [primaryScorecard]);
  const weakComponents = useMemo(() => weakestComponents(primaryScorecard), [primaryScorecard]);
  const tailHeadline = useMemo(() => tailRiskHeadline(primaryScorecard), [primaryScorecard]);

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

  const refreshValidationResult = useCallback(async (query: BacktestQuery, settings: ValidationStoreSnapshot['savedSettings']) => {
    try {
      return await fetchValidationWalkForward(query, settings);
    } catch {
      push('warning', '검증 요약을 다시 계산하지 못했습니다.', '백엔드 validation 응답을 확인하세요.', 'backtest');
      return null;
    }
  }, [push]);

  const handleRefreshAll = useCallback(async () => {
    onRefresh();

    try {
      const [statusPayload, paramsPayload] = await Promise.all([
        getJSON<{ running?: boolean }>('/api/optimization-status', { noStore: true }),
        getJSON<Record<string, unknown>>('/api/optimized-params', { noStore: true }),
      ]);

      setOptimizationRunning(Boolean(statusPayload.running));
      if (statusPayload.running) {
        setOptimizationPhase('running');
        setOptimizationMessage('이미 실행 중인 최적화 작업을 추적 중입니다.');
      }
      if (paramsPayload.status === 'ok') {
        setOptimizedParams(paramsPayload);
      }
    } catch {
      push('warning', '상태 새로고침 중 일부 정보를 가져오지 못했습니다.', '최적화 상태와 최신 파라미터는 다시 시도해 주세요.', 'refresh');
    }

    push('info', '화면 상태만 새로고침했습니다.', '마지막 실행 결과 카드는 그대로 유지합니다.', 'refresh');
    pushToast({
      tone: 'info',
      title: '상태만 새로고침했습니다.',
      description: '마지막 실행 결과는 다시 계산하지 않았습니다.',
    });
  }, [onRefresh, push, pushToast]);

  const handleRunBacktest = useCallback(async () => {
    if (backtestPhase === 'requesting' || backtestPhase === 'running' || backtestPhase === 'finalizing') return;
    if (validationStore.unsaved) {
      push('warning', '저장된 설정만 실행할 수 있습니다.', '먼저 설정 저장을 눌러 실행 기준을 확정해 주세요.', 'backtest');
      pushToast({ tone: 'warning', title: '먼저 설정 저장', description: '실행 결과와 초안을 섞지 않도록 저장된 설정만 실행합니다.' });
      return;
    }

    const executedQuery = validationStore.savedQuery;
    const executedSettings = validationStore.savedSettings;
    const historyId = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    updateRunHistory([
      {
        id: historyId,
        at: nowIso(),
        market: executedQuery.market_scope,
        lookbackDays: executedQuery.lookback_days,
        status: '실행 중',
        totalReturnPct: null,
      },
      ...runHistory,
    ].slice(0, 30));

    setRunStartedAt(nowIso());
    setRunFinishedAt('');
    setBacktestPhase('requesting');
    setBacktestMessage('저장된 설정으로 백테스트 요청을 전송했습니다.');
    push('info', '백테스트 실행을 시작했습니다.', `시장 ${executedQuery.market_scope === 'kospi' ? 'KOSPI' : executedQuery.market_scope === 'nasdaq' ? 'NASDAQ' : 'KOSPI+NASDAQ'}, 기간 ${executedQuery.lookback_days}일`, 'backtest');
    pushToast({ tone: 'info', title: '백테스트 실행 시작', description: '저장된 설정 기준으로 결과를 고정합니다.' });

    await Promise.resolve();
    setBacktestPhase('running');
    setBacktestMessage('서버에서 성과 계산과 검증 요약을 생성하고 있습니다.');

    const result = await run(executedQuery);
    const validationPayload = result.ok ? await refreshValidationResult(executedQuery, executedSettings) : null;
    setBacktestPhase('finalizing');
    setBacktestMessage('결과를 정리 중입니다.');
    await new Promise((resolve) => window.setTimeout(resolve, 180));

    const finishedAt = nowIso();
    setRunFinishedAt(finishedAt);

    if (result.ok && result.payload && validationPayload) {
      const nextExecutedRun: ExecutedRunState = {
        executedAt: finishedAt,
        query: executedQuery,
        settings: executedSettings,
        backtest: result.payload,
        validation: validationPayload,
      };
      setExecutedRun(nextExecutedRun);
      writeJson(EXECUTED_RUN_KEY, nextExecutedRun);
      setBacktestPhase('success');
      setBacktestMessage('백테스트가 완료되었습니다. 결과 카드는 마지막 명시적 실행 기준으로 고정됩니다.');
      updateRunHistory(updateHistoryItem([
        {
          id: historyId,
          at: finishedAt,
          market: executedQuery.market_scope,
          lookbackDays: executedQuery.lookback_days,
          status: '완료',
          totalReturnPct: metricNumber(result.payload.metrics as Record<string, unknown> | undefined, 'total_return_pct'),
        },
        ...runHistory,
      ].slice(0, 30), historyId, {
        status: '완료',
        totalReturnPct: metricNumber(result.payload.metrics as Record<string, unknown> | undefined, 'total_return_pct'),
      }));
      push('success', '백테스트가 완료되었습니다.', '마지막 실행 결과 카드와 최근 실행 이력이 갱신되었습니다.', 'backtest');
      pushToast({ tone: 'success', title: '백테스트 완료', description: '결과 카드를 마지막 실행 기준으로 고정했습니다.' });
      return;
    }

    setBacktestPhase('error');
    setBacktestMessage(result.error || '백테스트 실행 중 오류가 발생했습니다.');
    updateRunHistory(updateHistoryItem([
      {
        id: historyId,
        at: finishedAt,
        market: executedQuery.market_scope,
        lookbackDays: executedQuery.lookback_days,
        status: '실패',
        totalReturnPct: null,
      },
      ...runHistory,
    ].slice(0, 30), historyId, { status: '실패', totalReturnPct: null }));
    push('error', '백테스트 실행이 실패했습니다.', result.error || '상단 로그 보기에서 상세 원인을 확인하세요.', 'backtest');
    pushToast({ tone: 'error', title: '백테스트 실패', description: result.error || '로그와 서버 상태를 확인해 주세요.' });
  }, [backtestPhase, push, pushToast, refreshValidationResult, run, runHistory, updateRunHistory, validationStore.savedQuery, validationStore.savedSettings, validationStore.unsaved]);

  const handleRunOptimization = useCallback(async () => {
    if (optimizationRunning || optimizationPhase === 'requesting') return;
    if (validationStore.unsaved) {
      push('warning', '저장된 설정을 먼저 확정해 주세요.', '초안 상태에서는 최적화를 시작하지 않습니다.', 'optimization');
      pushToast({ tone: 'warning', title: '먼저 설정 저장', description: '최적화도 저장된 설정 기준으로만 시작합니다.' });
      return;
    }

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
  }, [optimizationHistory, optimizationPhase, optimizationRunning, push, pushToast, updateOptimizationHistory, validationStore.unsaved]);

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
    push('success', '검증 설정을 저장했습니다.', `${validationStore.draftQuery.market_scope === 'kospi' ? 'KOSPI' : validationStore.draftQuery.market_scope === 'nasdaq' ? 'NASDAQ' : 'KOSPI+NASDAQ'} · ${validationStore.draftQuery.lookback_days}일`, 'settings');
    pushToast({ tone: 'success', title: '설정 저장 완료', description: '실행 패널 요약과 저장 필요 배지가 즉시 갱신되었습니다.' });
    setSettingsSaving(false);
  }, [push, pushToast, saveHistory, settingsSaving, updateSaveHistory, validationStore]);

  const handleResetSettings = useCallback(() => {
    validationStore.resetDraft();
    setBacktestMessage('설정 초안을 기본값으로 되돌렸습니다. 저장 후 실행할 수 있습니다.');
    push('warning', '검증 설정 초안을 기본값으로 되돌렸습니다.', '저장 전까지는 저장 필요 상태가 유지됩니다.', 'settings');
    pushToast({ tone: 'warning', title: '설정 초안 초기화', description: '기본값으로 되돌렸습니다. 저장하면 실행 패널에 반영됩니다.' });
  }, [push, pushToast, validationStore]);

  const updateDraftQueryNumber = useCallback((key: keyof BacktestQuery, fallback: number, min?: number) => (event: ChangeEvent<HTMLInputElement>) => {
    const raw = Number(event.target.value);
    const nextValue = Number.isFinite(raw) ? raw : fallback;
    validationStore.setDraftQuery((prev) => ({
      ...prev,
      [key]: typeof min === 'number' ? Math.max(min, nextValue) : nextValue,
    }));
  }, [validationStore]);

  const updateDraftQueryNullableNumber = useCallback((key: keyof BacktestQuery, min?: number) => (event: ChangeEvent<HTMLInputElement>) => {
    const { value } = event.target;
    validationStore.setDraftQuery((prev) => {
      if (value.trim() === '') {
        return { ...prev, [key]: null };
      }
      const raw = Number(value);
      const nextValue = Number.isFinite(raw) ? raw : null;
      return {
        ...prev,
        [key]: nextValue === null ? null : (typeof min === 'number' ? Math.max(min, nextValue) : nextValue),
      };
    });
  }, [validationStore]);

  const settingsPanel = (
    <div className="settings-panel-grid">
      <SettingsSection title="기본 설정" description="시장, 기간, 검증 기준을 여기서 관리합니다.">
        <FieldBlock label="시장" help="백테스트 대상 시장을 선택합니다.">
          <select
            className="backtest-input-wrap"
            style={{ padding: '0 12px' }}
            value={validationStore.draftQuery.market_scope}
            onChange={(event) => validationStore.setDraftQuery((prev) => ({ ...prev, market_scope: event.target.value as BacktestQuery['market_scope'] }))}
          >
            <option value="kospi">KOSPI</option>
            <option value="nasdaq">NASDAQ</option>
            <option value="all">KOSPI+NASDAQ</option>
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
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" min={180} step={30} value={validationStore.draftQuery.lookback_days} onChange={updateDraftQueryNumber('lookback_days', 180, 180)} />
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
      </SettingsSection>

      <SettingsSection title="고급 전략 설정" description="실제 진입·청산 파라미터를 바로 조정합니다.">
        <FieldBlock label="초기 자금" help="시장 기본 통화 기준입니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" min={1} step={1} value={validationStore.draftQuery.initial_cash} onChange={updateDraftQueryNumber('initial_cash', validationStore.draftQuery.initial_cash, 1)} />
        </FieldBlock>
        <FieldBlock label="최대 보유 종목 수" help="동시 보유 가능한 포지션 수입니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" min={1} step={1} value={validationStore.draftQuery.max_positions} onChange={updateDraftQueryNumber('max_positions', validationStore.draftQuery.max_positions, 1)} />
        </FieldBlock>
        <FieldBlock label="최대 보유 일수" help="포지션 강제 정리 기준입니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" min={1} step={1} value={validationStore.draftQuery.max_holding_days} onChange={updateDraftQueryNumber('max_holding_days', validationStore.draftQuery.max_holding_days, 1)} />
        </FieldBlock>
        <FieldBlock label="RSI 최소" help="진입 허용 하한선입니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" step={1} value={validationStore.draftQuery.rsi_min} onChange={updateDraftQueryNumber('rsi_min', validationStore.draftQuery.rsi_min)} />
        </FieldBlock>
        <FieldBlock label="RSI 최대" help="진입 허용 상한선입니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" step={1} value={validationStore.draftQuery.rsi_max} onChange={updateDraftQueryNumber('rsi_max', validationStore.draftQuery.rsi_max)} />
        </FieldBlock>
        <FieldBlock label="거래량 배수 최소" help="평균 대비 거래량 필터입니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" min={0} step={0.1} value={validationStore.draftQuery.volume_ratio_min} onChange={updateDraftQueryNumber('volume_ratio_min', validationStore.draftQuery.volume_ratio_min, 0)} />
        </FieldBlock>
        <FieldBlock label="손절 폭(%)" help="비우면 손절 조건을 끕니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" min={0} step={0.1} value={validationStore.draftQuery.stop_loss_pct ?? ''} onChange={updateDraftQueryNullableNumber('stop_loss_pct', 0)} placeholder="예: 5" />
        </FieldBlock>
        <FieldBlock label="익절 폭(%)" help="비우면 익절 조건을 끕니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" min={0} step={0.1} value={validationStore.draftQuery.take_profit_pct ?? ''} onChange={updateDraftQueryNullableNumber('take_profit_pct', 0)} placeholder="예: 12" />
        </FieldBlock>
        <FieldBlock label="ADX 최소" help="추세 강도 필터입니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" min={0} step={0.1} value={validationStore.draftQuery.adx_min ?? ''} onChange={updateDraftQueryNullableNumber('adx_min', 0)} />
        </FieldBlock>
        <FieldBlock label="MFI 최소" help="자금 유입 하한선입니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" step={0.1} value={validationStore.draftQuery.mfi_min ?? ''} onChange={updateDraftQueryNullableNumber('mfi_min')} />
        </FieldBlock>
        <FieldBlock label="MFI 최대" help="과열 차단 상한선입니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" step={0.1} value={validationStore.draftQuery.mfi_max ?? ''} onChange={updateDraftQueryNullableNumber('mfi_max')} />
        </FieldBlock>
        <FieldBlock label="BB 위치 최소" help="볼린저 밴드 위치 하한선입니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" min={0} max={1} step={0.01} value={validationStore.draftQuery.bb_pct_min ?? ''} onChange={updateDraftQueryNullableNumber('bb_pct_min', 0)} />
        </FieldBlock>
        <FieldBlock label="BB 위치 최대" help="볼린저 밴드 위치 상한선입니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" min={0} max={1} step={0.01} value={validationStore.draftQuery.bb_pct_max ?? ''} onChange={updateDraftQueryNullableNumber('bb_pct_max', 0)} />
        </FieldBlock>
        <FieldBlock label="Stoch K 최소" help="모멘텀 하한선입니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" step={0.1} value={validationStore.draftQuery.stoch_k_min ?? ''} onChange={updateDraftQueryNullableNumber('stoch_k_min')} />
        </FieldBlock>
        <FieldBlock label="Stoch K 최대" help="모멘텀 상한선입니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" step={0.1} value={validationStore.draftQuery.stoch_k_max ?? ''} onChange={updateDraftQueryNullableNumber('stoch_k_max')} />
        </FieldBlock>
      </SettingsSection>

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
                    detail={`신뢰도 ${viewModel.reliability || '-'} · 윈도우 ${formatCount(validationResult.summary?.windows, '개')}`}
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

              <div className="page-section" style={{ padding: 16 }}>
                <div className="section-head-row">
                  <div>
                    <div className="section-title">전략 점수카드</div>
                    <div className="section-copy">점수 하나로 끝내지 않고, 왜 채택/보류해야 하는지와 손실 꼬리를 같이 봅니다.</div>
                  </div>
                  <div className={`inline-badge ${scoreDecision.tone === 'good' ? 'is-success' : scoreDecision.tone === 'bad' ? 'is-danger' : 'is-warning'}`}>
                    {primaryScoreSource}
                  </div>
                </div>

                {primaryScorecard ? (
                  <>
                    <div className="summary-metric-grid" style={{ marginTop: 12 }}>
                      <SummaryMetricCard
                        label="복합 점수"
                        value={primaryScorecard.compositeScore === null ? '-' : `${formatNumber(primaryScorecard.compositeScore, 1)}점`}
                        detail={`${scoreDecision.label} · ${scoreDecision.detail}`}
                        tone={scoreDecision.tone}
                      />
                      <SummaryMetricCard
                        label="점수 끌어올린 항목"
                        value={bestComponents.map((item) => item.label).join(' · ') || '-'}
                        detail={bestComponents.length > 0 ? bestComponents.map((item) => `${item.label} ${formatNumber(item.value, 1)}점`).join(' / ') : '상승 기여 항목이 아직 없습니다.'}
                        tone="good"
                      />
                      <SummaryMetricCard
                        label="먼저 눌러야 할 리스크"
                        value={tailHeadline.label}
                        detail={weakComponents.length > 0 ? `${weakComponents.map((item) => item.label).join(' · ')} · ${tailHeadline.detail}` : tailHeadline.detail}
                        tone={tailHeadline.tone}
                      />
                    </div>

                    <div className="scorecard-detail-grid" style={{ marginTop: 12 }}>
                      <div className="scorecard-panel">
                        <div className="section-subtitle">점수 구성</div>
                        <div className="scorecard-component-list">
                          {scoreComponentRows.map((row) => (
                            <div key={row.key} className={`scorecard-component-row is-${row.tone}`}>
                              <div>
                                <div className="scorecard-component-label">{row.label}</div>
                                <div className="scorecard-component-copy">총점에 주는 기여도</div>
                              </div>
                              <div className="scorecard-component-value">{row.value >= 0 ? '+' : ''}{formatNumber(row.value, 1)}점</div>
                            </div>
                          ))}
                        </div>
                      </div>

                      <div className="scorecard-panel">
                        <div className="section-subtitle">테일 리스크 가드레일</div>
                        <div className="scorecard-tail-grid">
                          {tailRows.map((row) => (
                            <div key={row.key} className={`scorecard-tail-card is-${row.tone}`}>
                              <div className="scorecard-tail-label">{row.label}</div>
                              <div className="scorecard-tail-value">{row.key === 'loss_rate_pct' ? formatPercent(row.value, 1) : formatPercent(row.value, 1)}</div>
                              <div className="scorecard-tail-copy">
                                {row.key === 'loss_rate_pct'
                                  ? '손실 거래 비중'
                                  : row.key === 'expected_shortfall_5_pct'
                                    ? '하위 5% 평균 손실'
                                    : row.key === 'return_p05_pct'
                                      ? '하위 5% 경계값'
                                      : '관측 최악 손실'}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="empty-inline" style={{ marginTop: 12 }}>
                    점수카드 데이터가 아직 없습니다. 백테스트를 다시 실행하거나 최적화 결과를 생성하면 이 영역에 채택 판단 근거가 표시됩니다.
                  </div>
                )}
              </div>

              <div className="validation-report-grid">
                <div className="page-section" style={{ padding: 16 }}>
                  <div className="section-title">구간 성과</div>
                  <div className="detail-list">
                    <div>전략: {executedRun?.settings.strategy || validationStore.savedSettings.strategy}</div>
                    <div>시장: {(executedRun?.query.market_scope || validationStore.savedQuery.market_scope) === 'kospi' ? 'KOSPI' : (executedRun?.query.market_scope || validationStore.savedQuery.market_scope) === 'nasdaq' ? 'NASDAQ' : 'KOSPI+NASDAQ'}</div>
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
                    <div className="section-copy">초안, 저장됨, 마지막 실행 결과를 분리해서 보여줍니다.</div>
                  </div>
                  <div className={`inline-badge ${validationStore.unsaved ? 'is-warning' : 'is-success'}`}>
                    {validationStore.unsaved ? '초안 변경 있음' : '저장된 설정과 동일'}
                  </div>
                </div>

                <div className="summary-rail is-compact">
                  <div className="summary-rail-item"><strong>초안</strong> · {settingsSummaryLines[0]}</div>
                  <div className="summary-rail-item">{settingsSummaryLines[1]}</div>
                  <div className="summary-rail-item">{settingsSummaryLines[2]}</div>
                </div>

                <div className="summary-rail is-compact" style={{ marginTop: 8 }}>
                  <div className="summary-rail-item"><strong>저장됨</strong> · {savedSettingsSummaryLines[0]}</div>
                  <div className="summary-rail-item">{savedSettingsSummaryLines[1]}</div>
                  <div className="summary-rail-item">{savedSettingsSummaryLines[2]}</div>
                </div>

                {executedRun && (
                  <div className="summary-rail is-compact" style={{ marginTop: 8 }}>
                    <div className="summary-rail-item"><strong>마지막 실행</strong> · {executedSettingsSummaryLines[0]}</div>
                    <div className="summary-rail-item">{executedSettingsSummaryLines[1]}</div>
                    <div className="summary-rail-item">{executedSettingsSummaryLines[2]}</div>
                  </div>
                )}

                {validationStore.unsaved && (
                  <div className="inline-warning-card">초안이 저장된 설정과 다릅니다. 실행은 저장된 설정으로만 진행합니다.</div>
                )}

                <div className="execution-button-row is-split">
                  <button
                    className="console-action-button is-primary"
                    onClick={() => { void handleRunBacktest(); }}
                    disabled={backtestPhase === 'requesting' || backtestPhase === 'running' || backtestPhase === 'finalizing'}
                  >
                    {backtestPhase === 'requesting' || backtestPhase === 'running' || backtestPhase === 'finalizing'
                      ? <span className="button-content"><span className="button-spinner" aria-hidden="true" />백테스트 진행 중...</span>
                      : '저장된 설정으로 백테스트 실행'}
                  </button>
                  <button
                    className="console-action-button"
                    onClick={() => { void handleRunOptimization(); }}
                    disabled={optimizationRunning || optimizationPhase === 'requesting'}
                  >
                    {optimizationRunning || optimizationPhase === 'requesting'
                      ? <span className="button-content"><span className="button-spinner" aria-hidden="true" />최적화 진행 중...</span>
                      : '저장된 설정으로 최적화 실행'}
                  </button>
                </div>

                <div className="validation-inline-status">
                  <div>백테스트: {backtestPhaseLabel(backtestPhase)} · {backtestMessage}</div>
                  <div>최적화: {optimizationPhaseLabel(optimizationPhase)} · {optimizationMessage}</div>
                  <div>마지막 실행 시각: {executedRun?.executedAt ? formatDateTime(executedRun.executedAt) : runFinishedAt ? formatDateTime(runFinishedAt) : '없음'}</div>
                  <div>화면 새로고침은 상태만 다시 불러오고, 결과 카드는 다시 계산하지 않습니다.</div>
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
          '기본 설정과 고급 전략 설정 초안이 모두 기본값으로 되돌아갑니다.',
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
