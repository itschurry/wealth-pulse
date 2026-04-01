import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ChangeEvent, FocusEvent, ReactNode } from 'react';
import { getJSON, postJSON } from '../api/client';
import { fetchValidationDiagnostics, fetchValidationWalkForward } from '../api/domain';
import { ConsoleActionBar, ConsoleConfirmDialog } from '../components/ConsoleActionBar';
import { reliabilityToKorean, UI_TEXT } from '../constants/uiText';
import { useBacktest } from '../hooks/useBacktest';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import {
  formatValidationSettingsLabel,
  useValidationSettingsStore,
} from '../hooks/useValidationSettingsStore';
import { useToast } from '../hooks/useToast';
import { useQuantOpsWorkflow } from '../hooks/useQuantOpsWorkflow';
import type { BacktestData, BacktestQuery, BacktestTrade } from '../types';
import type { ActionBarStatusItem, BacktestViewModel, ConsoleSnapshot } from '../types/consoleView';
import type { ExitReasonAnalysisPayload, ExitReasonAnalysisRow, ExitReasonConcentrationVerdict, ExitReasonPersistentWeakness, ExitReasonWeaknessCluster, ExitScopeWeaknessRow, ValidationDiagnosticsResponse, ValidationResponse, ValidationWalkForwardExitReasonPayload } from '../types/domain';
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

function readExitReasonAnalysis(value: unknown): ExitReasonAnalysisPayload | null {
  if (!value || typeof value !== 'object') return null;
  return value as ExitReasonAnalysisPayload;
}

function readWalkForwardExitReasonSummary(value: unknown): ValidationWalkForwardExitReasonPayload | null {
  if (!value || typeof value !== 'object') return null;
  return value as ValidationWalkForwardExitReasonPayload;
}

function aggregateByReason(trades: BacktestTrade[]): ExitReasonAnalysisRow[] {
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
      key: reason,
      label: reason,
      count: item.count,
      avg_pnl_pct: item.count > 0 ? item.sum / item.count : 0,
    }))
    .sort((left, right) => Number(right.count || 0) - Number(left.count || 0))
    .slice(0, 8);
}

function topLossReason(analysis: ExitReasonAnalysisPayload | null | undefined): ExitReasonAnalysisRow | null {
  if (!analysis?.reasons || analysis.reasons.length === 0) return null;
  const negatives = analysis.reasons.filter((item) => Number(item.gross_loss_pct || 0) > 0);
  return negatives[0] || analysis.reasons[0] || null;
}

function reasonRowTone(row: ExitReasonAnalysisRow | null | undefined): 'neutral' | 'good' | 'bad' {
  if (!row) return 'neutral';
  if (Number(row.gross_loss_pct || 0) > 0 || Number(row.avg_pnl_pct || 0) < 0) return 'bad';
  if (Number(row.gross_profit_pct || 0) > 0 || Number(row.avg_pnl_pct || 0) > 0) return 'good';
  return 'neutral';
}

function formatExitReasonDetail(row: ExitReasonAnalysisRow): string {
  const parts = [
    `거래 ${formatCount(row.count, '건')}`,
    `평균 ${formatPercent(row.avg_pnl_pct ?? null, 2)}`,
  ];
  if (row.loss_share_pct !== undefined && row.loss_share_pct !== null && Number(row.loss_share_pct) > 0) {
    parts.push(`손실 비중 ${formatPercent(row.loss_share_pct, 1)}`);
  } else if (row.profit_share_pct !== undefined && row.profit_share_pct !== null && Number(row.profit_share_pct) > 0) {
    parts.push(`이익 기여 ${formatPercent(row.profit_share_pct, 1)}`);
  }
  if (row.avg_holding_days !== undefined && row.avg_holding_days !== null && Number(row.avg_holding_days) > 0) {
    parts.push(`평균 보유 ${formatNumber(row.avg_holding_days, 1)}일`);
  }
  return parts.join(' · ');
}

function formatScopeWeaknessDetail(row: ExitScopeWeaknessRow): string {
  const parts = [
    `손실 거래 ${formatCount(row.loss_trades ?? row.count ?? null, '건')}`,
    `누적 손실 ${formatPercent(row.gross_loss_pct ?? null, 2)}`,
  ];
  if (row.loss_share_pct !== undefined && row.loss_share_pct !== null && Number(row.loss_share_pct) > 0) {
    parts.push(`손실 비중 ${formatPercent(row.loss_share_pct, 1)}`);
  }
  if (row.top_reason_label) {
    parts.push(`${row.top_reason_label} ${formatPercent(row.top_reason_loss_share_pct ?? null, 1)}`);
  }
  if (Array.isArray(row.markets) && row.markets.length > 0) {
    parts.push(row.markets.join('/'));
  }
  return parts.join(' · ');
}

function topScopeWeakness(analysis: ExitReasonAnalysisPayload | null | undefined, scope: 'symbol' | 'sector'): ExitScopeWeaknessRow | null {
  const rows = scope === 'symbol' ? analysis?.symbol_weaknesses : analysis?.sector_weaknesses;
  if (!Array.isArray(rows) || rows.length === 0) return null;
  return rows[0] || null;
}

function concentrationTone(verdict: ExitReasonConcentrationVerdict | null | undefined): 'neutral' | 'bad' {
  if (!verdict) return 'neutral';
  if (verdict.strategy_issue_bias === 'mixed') return 'neutral';
  if (verdict.strategy_issue_bias === 'unknown') return 'neutral';
  return 'bad';
}

function formatConcentrationDetail(verdict: ExitReasonConcentrationVerdict | null | undefined): string {
  if (!verdict) return '종목/섹터 집중도 데이터가 아직 없습니다.';
  const parts = [verdict.summary || ''];
  if (verdict.symbol_distribution_label) {
    parts.push(`종목 ${verdict.symbol_distribution_label} ${formatPercent(verdict.symbol_top_share_pct ?? null, 1)}`);
  }
  if (verdict.sector_distribution_label) {
    parts.push(`섹터 ${verdict.sector_distribution_label} ${formatPercent(verdict.sector_top_share_pct ?? null, 1)}`);
  }
  return parts.filter(Boolean).join(' · ');
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

function formatMoneyInput(value: number) {
  const normalized = Math.max(1, Math.floor(Number(value) || 1));
  return new Intl.NumberFormat('en-US').format(normalized);
}

function IntegerDraftInput({
  value,
  min,
  step,
  onCommit,
  placeholder,
}: {
  value: number;
  min?: number;
  step?: number;
  onCommit: (next: number) => void;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState(() => String(value));
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (!focused) {
      setDraft(String(value));
    }
  }, [focused, value]);

  return (
    <input
      className="backtest-input-wrap"
      style={{ padding: '0 12px' }}
      type="number"
      min={min}
      step={step}
      value={draft}
      placeholder={placeholder}
      onFocus={(event) => {
        setFocused(true);
        requestAnimationFrame(() => event.currentTarget.select());
      }}
      onChange={(event) => {
        setDraft(event.target.value);
      }}
      onBlur={() => {
        const parsed = Number(draft);
        let normalized = Number.isFinite(parsed) ? Math.floor(parsed) : value;
        if (typeof min === 'number') {
          normalized = Math.max(min, normalized);
        }
        onCommit(normalized);
        setDraft(String(normalized));
        setFocused(false);
      }}
    />
  );
}

function MoneyValueInput({
  value,
  min = 1,
  onChange,
  placeholder,
}: {
  value: number;
  min?: number;
  onChange: (next: number) => void;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState(() => formatMoneyInput(value));
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (!focused) {
      setDraft(formatMoneyInput(value));
    }
  }, [focused, value]);

  return (
    <input
      className="backtest-input-wrap"
      style={{ padding: '0 12px' }}
      type="text"
      inputMode="numeric"
      value={draft}
      placeholder={placeholder}
      onFocus={(event) => {
        setFocused(true);
        setDraft(String(Math.max(min, Math.floor(Number(value) || min))));
        requestAnimationFrame(() => event.currentTarget.select());
      }}
      onChange={(event) => {
        const digitsOnly = event.target.value.replace(/[^\d]/g, '');
        setDraft(digitsOnly);
        if (digitsOnly.trim() === '') return;
        const parsed = Number(digitsOnly);
        if (!Number.isFinite(parsed)) return;
        onChange(Math.max(min, Math.floor(parsed)));
      }}
      onBlur={() => {
        const parsed = Number(draft.replace(/[^\d]/g, ''));
        const normalized = Number.isFinite(parsed) ? Math.max(min, Math.floor(parsed)) : min;
        onChange(normalized);
        setDraft(formatMoneyInput(normalized));
        setFocused(false);
      }}
    />
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

function reliabilityMetricLabel(metric: string | undefined): string {
  if (metric === 'trade_count') return '학습 거래 수';
  if (metric === 'validation_signals') return '검증 신호 수';
  if (metric === 'validation_sharpe') return '검증 Sharpe';
  if (metric === 'max_drawdown_pct') return '최대 낙폭(%)';
  return metric || '-';
}

function quantStageLabel(status: string | undefined): string {
  if (status === 'ready') return '후보 있음';
  if (status === 'adopt') return '통과';
  if (status === 'hold') return '보류';
  if (status === 'reject') return '거절';
  if (status === 'saved') return '저장됨';
  if (status === 'applied') return '반영됨';
  return '대기';
}

function quantDecisionTone(status: string | undefined): 'neutral' | 'good' | 'bad' {
  if (status === 'adopt') return 'good';
  if (status === 'reject') return 'bad';
  return 'neutral';
}

function quantGuardrailReasonLabel(reason: string): string {
  if (reason === 'validation_min_trades_not_met') return '거래 표본 수 부족';
  if (reason === 'oos_reliability_low') return 'OOS 신뢰도 낮음';
  if (reason === 'profit_factor_too_low') return 'Profit factor 부족';
  if (reason === 'oos_return_negative') return 'OOS 수익률 음수';
  if (reason === 'max_drawdown_too_large') return '최대 낙폭 과다';
  if (reason === 'tail_risk_too_large') return '테일 리스크 과다';
  if (reason === 'optimizer_search_stale') return 'optimizer 탐색 결과가 오래됨';
  if (reason === 'optimizer_search_version_changed') return '탐색 버전이 바뀌어 재검증이 무효화됨';
  if (reason === 'symbol_candidate_missing') return '종목 재검증 후보가 없음';
  if (reason === 'symbol_validation_failed') return '종목 재검증 실패';
  if (reason === 'symbol_validation_guardrail_blocked') return '종목 재검증 가드레일 차단';
  if (reason === 'operator_approval_required') return '운영자 승인 필요';
  if (reason === 'operator_approval_stale') return '승인 대상 후보가 최신이 아님';
  if (reason === 'symbol_overlay_patch_missing') return '종목 overlay 파라미터 없음';
  return reason || '-';
}

function symbolApprovalTone(status: string | undefined): 'good' | 'bad' | 'neutral' {
  if (status === 'approved') return 'good';
  if (status === 'rejected') return 'bad';
  return 'neutral';
}

function symbolApprovalLabel(status: string | undefined): string {
  if (status === 'approved') return '승인';
  if (status === 'rejected') return '거절';
  return '보류';
}

function quantWorkflowCardTitle(status: string | undefined, fallback: string): string {
  const label = quantStageLabel(status);
  return label === '대기' ? fallback : `${fallback} · ${label}`;
}

function quantCandidateStateReasonLabel(reason: string): string {
  if (reason === 'candidate_missing') return '후보가 아직 없습니다.';
  if (reason === 'validation_settings_changed') return '현재 baseline 설정이 바뀌어 기존 후보를 그대로 쓰면 안 됩니다.';
  if (reason === 'optimizer_search_missing') return 'optimizer search 결과가 없습니다.';
  if (reason === 'optimizer_search_version_changed') return 'latest/search 버전이 달라 다시 재검증해야 합니다.';
  if (reason === 'saved_candidate_missing') return '저장된 후보가 없어 runtime 적용본과 비교할 기준이 없습니다.';
  if (reason === 'runtime_candidate_mismatch') return '현재 runtime 적용본이 최신 저장 후보와 다릅니다.';
  return reason || '-';
}

function quantRuntimeSourceLabel(source: string | undefined): string {
  if (source === 'runtime') return 'runtime applied file';
  if (source === 'search') return 'search result file';
  if (source === 'missing') return '미적용';
  return source || '-';
}

function runtimeCandidateSourceModeLabel(mode: string | undefined): string {
  if (mode === 'research_only') return 'research_only';
  if (mode === 'hybrid') return 'hybrid';
  return 'quant_only';
}

function runtimeCandidateSourceModeDescription(mode: string | undefined): string {
  if (mode === 'research_only') return '리서치 경로만 사용해 today picks / recommendations 후보만 runtime 후보 풀로 씁니다. 퀀트 검증 후보는 실행 소스에서 제외합니다.';
  if (mode === 'hybrid') return '퀀트와 리서치 경로를 섞어 평가하지 않고 분리해 수집한 뒤, runtime 후보 풀에서 합집합으로 병합합니다.';
  return '퀀트 검증 경로만 사용해 저장된 validation/runtime overlay 후보만 runtime 후보 풀로 씁니다. 기본값이자 안전 모드입니다.';
}

export function BacktestValidationPage({ snapshot, loading, errorMessage, onRefresh }: BacktestValidationPageProps) {
  const { pushToast } = useToast();
  const { entries, push, clear } = useConsoleLogs();
  const validationStore = useValidationSettingsStore();
  const quantWorkflow = useQuantOpsWorkflow();
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
  const [backtestMessage, setBacktestMessage] = useState('현재 저장된 quant 설정 요약을 확인한 뒤 실행하면 됩니다.');
  const [optimizationMessage, setOptimizationMessage] = useState('quant 최적화는 백그라운드 작업으로 분리되어 실행됩니다.');
  const [optimizationRunning, setOptimizationRunning] = useState(false);
  const [optimizedParams, setOptimizedParams] = useState<Record<string, unknown> | null>(null);
  const [diagnosticsResult, setDiagnosticsResult] = useState<ValidationDiagnosticsResponse | null>(null);
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false);
  const [executedRun, setExecutedRun] = useState<ExecutedRunState | null>(() => readJson<ExecutedRunState>(EXECUTED_RUN_KEY));
  const settingsLoading = validationStore.syncStatus === 'loading';
  const settingsSaving = validationStore.syncStatus === 'saving';
  const settingsResetting = validationStore.syncStatus === 'resetting';
  const settingsSyncBusy = settingsLoading || settingsSaving || settingsResetting;

  const activeBacktest = executedRun?.backtest || null;
  const validationResult = executedRun?.validation || snapshot.validation;
  const metrics = activeBacktest?.metrics as Record<string, unknown> | undefined;
  const oos = validationResult.segments?.oos;
  const exitReasonSummary = useMemo(
    () => readWalkForwardExitReasonSummary(validationResult.summary?.exit_reason_analysis),
    [validationResult.summary?.exit_reason_analysis],
  );
  const backtestExitReasonAnalysis = useMemo(
    () => readExitReasonAnalysis(metrics?.exit_reason_analysis),
    [metrics?.exit_reason_analysis],
  );
  const validationExitReasonAnalysis = useMemo(
    () => exitReasonSummary?.validation || readExitReasonAnalysis(validationResult.segments?.validation?.exit_reason_analysis),
    [exitReasonSummary?.validation, validationResult.segments?.validation?.exit_reason_analysis],
  );
  const oosExitReasonAnalysis = useMemo(
    () => exitReasonSummary?.oos || readExitReasonAnalysis(validationResult.segments?.oos?.exit_reason_analysis) || backtestExitReasonAnalysis,
    [backtestExitReasonAnalysis, exitReasonSummary?.oos, validationResult.segments?.oos?.exit_reason_analysis],
  );
  const overallExitReasonAnalysis = useMemo(
    () => exitReasonSummary?.overall || backtestExitReasonAnalysis,
    [backtestExitReasonAnalysis, exitReasonSummary?.overall],
  );
  const exitWeaknessClusters = useMemo<ExitReasonWeaknessCluster[]>(
    () => (Array.isArray(exitReasonSummary?.weakness_clusters) ? exitReasonSummary.weakness_clusters : []),
    [exitReasonSummary?.weakness_clusters],
  );
  const persistentExitReasons = useMemo<ExitReasonPersistentWeakness[]>(
    () => (Array.isArray(exitReasonSummary?.persistent_negative_reasons) ? exitReasonSummary.persistent_negative_reasons : []),
    [exitReasonSummary?.persistent_negative_reasons],
  );
  const reasonRows = useMemo(
    () => {
      if (Array.isArray(oosExitReasonAnalysis?.reasons) && oosExitReasonAnalysis.reasons.length > 0) return oosExitReasonAnalysis.reasons.slice(0, 6);
      if (Array.isArray(validationExitReasonAnalysis?.reasons) && validationExitReasonAnalysis.reasons.length > 0) return validationExitReasonAnalysis.reasons.slice(0, 6);
      if (Array.isArray(overallExitReasonAnalysis?.reasons) && overallExitReasonAnalysis.reasons.length > 0) return overallExitReasonAnalysis.reasons.slice(0, 6);
      return aggregateByReason(activeBacktest?.trades || []);
    },
    [activeBacktest?.trades, oosExitReasonAnalysis?.reasons, overallExitReasonAnalysis?.reasons, validationExitReasonAnalysis?.reasons],
  );
  const oosTopLossReason = useMemo(() => topLossReason(oosExitReasonAnalysis), [oosExitReasonAnalysis]);
  const persistentTopReason = persistentExitReasons[0] || null;
  const exitHeadlines = useMemo(
    () => {
      if (Array.isArray(exitReasonSummary?.headlines) && exitReasonSummary.headlines.length > 0) return exitReasonSummary.headlines;
      return [
        ...(oosExitReasonAnalysis?.summary_lines || []),
        ...(validationExitReasonAnalysis?.summary_lines || []),
      ].slice(0, 4);
    },
    [exitReasonSummary?.headlines, oosExitReasonAnalysis?.summary_lines, validationExitReasonAnalysis?.summary_lines],
  );
  const oosSymbolWeakness = useMemo(() => topScopeWeakness(oosExitReasonAnalysis, 'symbol'), [oosExitReasonAnalysis]);
  const validationSymbolWeakness = useMemo(() => topScopeWeakness(validationExitReasonAnalysis, 'symbol'), [validationExitReasonAnalysis]);
  const overallSymbolWeakness = useMemo(() => topScopeWeakness(overallExitReasonAnalysis, 'symbol'), [overallExitReasonAnalysis]);
  const oosSectorWeakness = useMemo(() => topScopeWeakness(oosExitReasonAnalysis, 'sector'), [oosExitReasonAnalysis]);
  const validationSectorWeakness = useMemo(() => topScopeWeakness(validationExitReasonAnalysis, 'sector'), [validationExitReasonAnalysis]);
  const overallSectorWeakness = useMemo(() => topScopeWeakness(overallExitReasonAnalysis, 'sector'), [overallExitReasonAnalysis]);
  const primarySymbolWeakness = oosSymbolWeakness || validationSymbolWeakness || overallSymbolWeakness || null;
  const primarySectorWeakness = oosSectorWeakness || validationSectorWeakness || overallSectorWeakness || null;
  const oosConcentrationVerdict = useMemo<ExitReasonConcentrationVerdict | null>(
    () => (Array.isArray(oosExitReasonAnalysis?.concentration_verdicts) ? oosExitReasonAnalysis.concentration_verdicts[0] || null : null),
    [oosExitReasonAnalysis?.concentration_verdicts],
  );
  const validationConcentrationVerdict = useMemo<ExitReasonConcentrationVerdict | null>(
    () => (Array.isArray(validationExitReasonAnalysis?.concentration_verdicts) ? validationExitReasonAnalysis.concentration_verdicts[0] || null : null),
    [validationExitReasonAnalysis?.concentration_verdicts],
  );
  const overallConcentrationVerdict = useMemo<ExitReasonConcentrationVerdict | null>(
    () => (Array.isArray(overallExitReasonAnalysis?.concentration_verdicts) ? overallExitReasonAnalysis.concentration_verdicts[0] || null : null),
    [overallExitReasonAnalysis?.concentration_verdicts],
  );
  const primaryConcentrationVerdict = oosConcentrationVerdict || validationConcentrationVerdict || overallConcentrationVerdict || null;

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
  const reliabilityDiagnostic = validationResult.summary?.reliability_diagnostic || validationResult.reliability_diagnostic;
  const diagnosticBlockers = useMemo(
    () => (Array.isArray(reliabilityDiagnostic?.blocking_factors) ? reliabilityDiagnostic.blocking_factors : []),
    [reliabilityDiagnostic?.blocking_factors],
  );
  const diagnosticRecommended = reliabilityDiagnostic?.uplift_search?.recommended_path;

  const workflowPayload = quantWorkflow.workflow;
  const searchResult = workflowPayload?.search_result || null;
  const searchHandoff = workflowPayload?.search_handoff || null;
  const latestValidatedCandidate = workflowPayload?.latest_candidate || null;
  const latestCandidateState = workflowPayload?.latest_candidate_state || null;
  const savedValidatedCandidate = workflowPayload?.saved_candidate || null;
  const savedCandidateState = workflowPayload?.saved_candidate_state || null;
  const symbolCandidates = workflowPayload?.symbol_candidates || [];
  const runtimeApplyState = workflowPayload?.runtime_apply || null;
  const latestCandidateMatchesSearch = Boolean(
    searchResult?.available
    && latestValidatedCandidate?.search_version
    && latestValidatedCandidate.search_version === searchResult?.version,
  );
  const searchContextLabel = useMemo(() => {
    const context = searchResult?.context;
    if (!context) return '';
    const parts = [
      context.market ? `시장 ${String(context.market).toUpperCase()}` : '',
      context.lookback_days ? `학습 ${formatCount(context.lookback_days, '일')}` : '',
      context.validation_days ? `검증 ${formatCount(context.validation_days, '일')}` : '',
      context.top_n ? `상위 ${formatCount(context.top_n, '종목')}` : '',
    ].filter(Boolean);
    return parts.join(' · ');
  }, [searchResult?.context]);
  const latestCandidateStateReasons = (latestCandidateState?.reasons || []).map((reason) => quantCandidateStateReasonLabel(reason));
  const savedCandidateStateReasons = (savedCandidateState?.reasons || []).map((reason) => quantCandidateStateReasonLabel(reason));
  const runtimeApplyReasons = (runtimeApplyState?.reasons || []).map((reason) => quantCandidateStateReasonLabel(reason));
  const handoffWarnings = [
    !latestCandidateMatchesSearch && searchResult?.available ? '최신 search 결과와 현재 latest candidate가 아직 연결되지 않았습니다. 재검증 또는 handoff 상태를 먼저 확인하세요.' : '',
    ...latestCandidateStateReasons,
    ...savedCandidateStateReasons,
    ...runtimeApplyReasons,
  ].filter(Boolean);
  const [selectedSymbol, setSelectedSymbol] = useState('');
  const selectedSymbolWorkflow = useMemo(
    () => symbolCandidates.find((item) => String(item.symbol || '') === selectedSymbol) || symbolCandidates[0] || null,
    [selectedSymbol, symbolCandidates],
  );

  useEffect(() => {
    if (symbolCandidates.length === 0) {
      if (selectedSymbol) setSelectedSymbol('');
      return;
    }
    const exists = symbolCandidates.some((item) => String(item.symbol || '') === selectedSymbol);
    if (!exists) {
      setSelectedSymbol(String(symbolCandidates[0]?.symbol || ''));
    }
  }, [selectedSymbol, symbolCandidates]);

  useEffect(() => {
    void validationStore.loadSavedFromServer().catch(() => {
      push('warning', '서버 저장된 quant 설정을 불러오지 못했습니다.', '로컬 초안은 유지하고 계속 작업할 수 있습니다.', 'settings');
      pushToast({ tone: 'warning', title: '서버 저장값 로드 실패', description: '현재 브라우저 초안으로 계속 작업합니다.' });
    });
  }, []);

  const diagnosisLines = diagnosticsResult?.diagnosis?.summary_lines || [];
  const diagnosisBlockers = diagnosticsResult?.diagnosis?.blockers || [];
  const diagnosisSuggestions = diagnosticsResult?.research?.suggestions || [];
  const workflowStages = useMemo(() => ([
    {
      key: 'baseline',
      title: '1. Baseline',
      label: activeBacktest ? '완료' : '대기',
      tone: activeBacktest ? 'good' as const : 'neutral' as const,
      detail: activeBacktest ? `마지막 실행 ${formatDateTime(executedRun?.executedAt || runFinishedAt || '')}` : '저장된 설정으로 백테스트를 먼저 실행하세요.',
    },
    {
      key: 'diagnosis',
      title: '2. Diagnosis',
      label: diagnosticsResult?.ok ? '완료' : activeBacktest ? '실행 가능' : '대기',
      tone: diagnosticsResult?.ok ? 'good' as const : 'neutral' as const,
      detail: diagnosticsResult?.ok ? (diagnosisLines[0] || '차단 요인과 개선 경로를 계산했습니다.') : 'baseline 결과를 진단해서 차단 요인을 구조적으로 확인합니다.',
    },
    {
      key: 'candidate_search',
      title: '3. Candidate Search',
      label: searchResult?.available ? (searchResult?.is_stale ? '후보 있음(오래됨)' : '후보 있음') : '대기',
      tone: searchResult?.available ? 'good' as const : 'neutral' as const,
      detail: searchResult?.available ? `optimizer ${String(searchResult.version || '-')} · reliable ${formatCount(searchResult.n_reliable, '건')}` : '먼저 optimizer를 실행해 탐색 결과를 만드세요.',
    },
    {
      key: 'revalidation',
      title: '4. Re-validation',
      label: latestValidatedCandidate?.decision?.label || '대기',
      tone: quantDecisionTone(latestValidatedCandidate?.decision?.status),
      detail: latestValidatedCandidate?.decision?.summary || '탐색 후보를 현재 기준으로 다시 검증합니다.',
    },
    {
      key: 'save',
      title: '5. Save',
      label: savedValidatedCandidate?.saved_at ? '저장됨' : '대기',
      tone: savedValidatedCandidate?.saved_at ? 'good' as const : 'neutral' as const,
      detail: savedValidatedCandidate?.saved_at ? `저장 시각 ${formatDateTime(savedValidatedCandidate.saved_at)}` : '재검증 통과 후보만 저장됩니다.',
    },
    {
      key: 'runtime_apply',
      title: '6. Runtime Apply',
      label: runtimeApplyState?.status === 'applied' ? '반영됨' : '대기',
      tone: runtimeApplyState?.status === 'applied' ? 'good' as const : 'neutral' as const,
      detail: runtimeApplyState?.status === 'applied' ? `${formatDateTime(runtimeApplyState.applied_at)} · 엔진 ${runtimeApplyState.engine_state || '-'}` : '저장된 후보만 paper/runtime 설정으로 반영됩니다.',
    },
  ]), [
    activeBacktest,
    diagnosisLines,
    diagnosticsResult?.ok,
    executedRun?.executedAt,
    latestValidatedCandidate?.decision?.label,
    latestValidatedCandidate?.decision?.status,
    latestValidatedCandidate?.decision?.summary,
    runFinishedAt,
    runtimeApplyState?.applied_at,
    runtimeApplyState?.engine_state,
    runtimeApplyState?.status,
    savedValidatedCandidate?.saved_at,
    searchResult?.available,
    searchResult?.is_stale,
    searchResult?.n_reliable,
    searchResult?.version,
  ]);

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
      label: '운영 후보',
      value: latestValidatedCandidate?.decision?.label || '미검증',
      tone: quantDecisionTone(latestValidatedCandidate?.decision?.status),
    },
    {
      label: '종목 승인',
      value: formatCount(workflowPayload?.symbol_summary?.approved_count, '건'),
      tone: (workflowPayload?.symbol_summary?.approved_count || 0) > 0 ? 'good' : 'neutral',
    },
    {
      label: 'Runtime',
      value: runtimeApplyState?.status === 'applied' ? '반영됨' : '미반영',
      tone: runtimeApplyState?.status === 'applied' ? 'good' : 'neutral',
    },
    {
      label: 'OOS 신뢰도',
      value: viewModel.reliability || '-',
      tone: viewModel.reliability === '낮음' ? 'bad' : 'neutral',
    },
  ]), [backtestPhase, latestValidatedCandidate?.decision?.label, latestValidatedCandidate?.decision?.status, optimizationPhase, runtimeApplyState?.status, validationStore.unsaved, viewModel.reliability, workflowPayload?.symbol_summary?.approved_count]);

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

  const adoptionDecisionPanel = (
    <div className={`page-section validation-report-card decision-state-card is-${adoptionDecision.tone}`}>
      <div className="section-kicker">Adoption Decision</div>
      <div className="section-head-row">
        <div>
          <div className="section-title">퀀트 전략 채택 상태: {adoptionDecision.label}</div>
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
  );

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
        if (paramsPayload.status === 'ok') setOptimizedParams(paramsPayload);
        const workflowResult = await quantWorkflow.refresh();
        const handoffMatched = Boolean(
          workflowResult?.search_result?.version
          && workflowResult?.latest_candidate?.search_version
          && workflowResult.search_result.version === workflowResult.latest_candidate.search_version,
        );
        const handoffLabel = workflowResult?.latest_candidate?.decision?.label || '후보 미갱신';
        setOptimizationMessage(
          handoffMatched
            ? `최적화와 후보 handoff가 완료되었습니다. ${handoffLabel}`
            : '최적화가 완료되었습니다. 최신 탐색 결과를 확인하세요.',
        );
        push(
          'success',
          handoffMatched ? '최적화와 후보 handoff가 완료되었습니다.' : '최적화가 완료되었습니다.',
          handoffMatched ? `${handoffLabel} · 저장 가능 여부를 바로 확인하세요.` : '결과 카드가 갱신되었습니다.',
          'optimization',
        );
        pushToast({
          tone: 'success',
          title: handoffMatched ? '최적화 + 후보 갱신 완료' : '최적화 완료',
          description: handoffMatched ? `${handoffLabel} 상태로 latest candidate를 갱신했습니다.` : '최신 파라미터와 상태 카드가 갱신되었습니다.',
        });
        const historyItem: OptimizationHistoryItem = {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          at: nowIso(),
          status: '완료',
          message: handoffMatched ? '백그라운드 최적화 완료 · 후보 handoff 완료' : '백그라운드 최적화 완료',
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
  }, [optimizationHistory, optimizationRunning, push, pushToast, quantWorkflow, updateOptimizationHistory]);

  const refreshValidationResult = useCallback(async (query: BacktestQuery, settings: ValidationStoreSnapshot['savedSettings']) => {
    try {
      return await fetchValidationWalkForward(query, settings);
    } catch {
      push('warning', '검증 요약을 다시 계산하지 못했습니다.', '백엔드 validation 응답을 확인하세요.', 'backtest');
      return null;
    }
  }, [push]);

  const handleRunDiagnosis = useCallback(async () => {
    if (validationStore.unsaved) {
      push('warning', '저장된 설정 기준으로만 진단합니다.', '초안과 baseline 기준이 섞이지 않도록 먼저 설정 저장이 필요합니다.', 'diagnosis');
      pushToast({ tone: 'warning', title: '먼저 설정 저장', description: '진단도 저장된 설정 기준으로만 계산합니다.' });
      return;
    }
    try {
      const payload = await fetchValidationDiagnostics(validationStore.savedQuery, validationStore.savedSettings);
      setDiagnosticsResult(payload);
      if (payload.ok) {
        push('success', 'baseline 진단을 다시 계산했습니다.', (payload.diagnosis?.summary_lines || []).join(' · ') || '차단 요인과 개선 경로를 갱신했습니다.', 'diagnosis');
        pushToast({ tone: 'success', title: '진단 완료', description: '차단 요인과 개선 경로를 최신 기준으로 갱신했습니다.' });
        return;
      }
      push('error', '진단 계산이 실패했습니다.', payload.error || 'validation diagnostics 응답을 확인하세요.', 'diagnosis');
      pushToast({ tone: 'error', title: '진단 실패', description: payload.error || 'validation diagnostics 응답을 확인하세요.' });
    } catch {
      push('error', '진단 계산 요청에 실패했습니다.', '네트워크 또는 서버 상태를 확인하세요.', 'diagnosis');
      pushToast({ tone: 'error', title: '진단 요청 실패', description: '네트워크 또는 서버 상태를 확인하세요.' });
    }
  }, [push, pushToast, validationStore.savedQuery, validationStore.savedSettings, validationStore.unsaved]);

  const handleRevalidateCandidate = useCallback(async () => {
    if (validationStore.unsaved) {
      push('warning', '저장된 설정 기준으로만 후보 재검증을 실행합니다.', '초안은 먼저 저장해 주세요.', 'quant-workflow');
      pushToast({ tone: 'warning', title: '먼저 설정 저장', description: '후보 재검증도 저장된 설정 기준으로만 실행합니다.' });
      return;
    }
    const payload = await quantWorkflow.revalidate(validationStore.savedQuery, validationStore.savedSettings);
    if (payload?.ok) {
      push('success', 'optimizer 후보 재검증이 완료되었습니다.', payload.candidate?.decision?.summary || '최신 후보와 저장 가능 여부를 갱신했습니다.', 'quant-workflow');
      pushToast({ tone: 'success', title: '재검증 완료', description: payload.candidate?.decision?.label || '운영 후보 상태를 갱신했습니다.' });
      return;
    }
    push('error', 'optimizer 후보 재검증이 실패했습니다.', payload?.error || quantWorkflow.lastError || 'workflow 상태를 확인하세요.', 'quant-workflow');
    pushToast({ tone: 'error', title: '재검증 실패', description: payload?.error || quantWorkflow.lastError || 'workflow 상태를 확인하세요.' });
  }, [push, pushToast, quantWorkflow, validationStore.savedQuery, validationStore.savedSettings, validationStore.unsaved]);

  const handleSaveValidatedCandidate = useCallback(async () => {
    const payload = await quantWorkflow.saveCandidate(latestValidatedCandidate?.id);
    if (payload?.ok) {
      push('success', '재검증 통과 후보를 저장했습니다.', payload.candidate?.save_note || payload.candidate?.decision?.summary || 'runtime apply 전 단계 스냅샷을 보존했습니다.', 'quant-workflow');
      pushToast({ tone: 'success', title: '후보 저장 완료', description: '저장된 후보와 runtime apply 가드가 갱신되었습니다.' });
      return;
    }
    push('error', '후보 저장이 차단되었습니다.', payload?.error || quantWorkflow.lastError || 'guardrail 사유를 확인하세요.', 'quant-workflow');
    pushToast({ tone: 'error', title: '후보 저장 차단', description: payload?.error || quantWorkflow.lastError || 'guardrail 사유를 확인하세요.' });
  }, [latestValidatedCandidate?.id, push, pushToast, quantWorkflow]);

  const handleRevalidateSymbolCandidate = useCallback(async (symbol: string) => {
    if (validationStore.unsaved) {
      push('warning', '저장된 설정 기준으로만 종목 후보 재검증을 실행합니다.', '초안은 먼저 저장해 주세요.', 'quant-workflow');
      pushToast({ tone: 'warning', title: '먼저 설정 저장', description: '종목 후보 재검증도 저장된 설정 기준으로만 실행합니다.' });
      return;
    }
    const payload = await quantWorkflow.revalidateSymbol(symbol, validationStore.savedQuery, validationStore.savedSettings);
    if (payload?.ok) {
      push('success', `${symbol} 종목 후보 재검증이 완료되었습니다.`, payload.candidate?.decision?.summary || '종목별 저장 가능 여부를 갱신했습니다.', 'quant-workflow');
      pushToast({ tone: 'success', title: '종목 재검증 완료', description: `${symbol} 승인/저장 가드가 갱신되었습니다.` });
      return;
    }
    push('error', `${symbol} 종목 후보 재검증이 실패했습니다.`, payload?.error || quantWorkflow.lastError || 'workflow 상태를 확인하세요.', 'quant-workflow');
    pushToast({ tone: 'error', title: '종목 재검증 실패', description: payload?.error || quantWorkflow.lastError || 'workflow 상태를 확인하세요.' });
  }, [push, pushToast, quantWorkflow, validationStore.savedQuery, validationStore.savedSettings, validationStore.unsaved]);

  const handleSetSymbolApproval = useCallback(async (symbol: string, status: 'approved' | 'rejected' | 'hold') => {
    const payload = await quantWorkflow.setSymbolApproval(symbol, status);
    if (payload?.ok) {
      push('success', `${symbol} 승인 상태를 갱신했습니다.`, `상태 ${symbolApprovalLabel(status)} · 저장 전 guardrail이 다시 계산됩니다.`, 'quant-workflow');
      pushToast({ tone: 'success', title: '종목 승인 상태 갱신', description: `${symbol} → ${symbolApprovalLabel(status)}` });
      return;
    }
    push('error', `${symbol} 승인 상태 갱신이 실패했습니다.`, payload?.error || quantWorkflow.lastError || 'workflow 상태를 확인하세요.', 'quant-workflow');
    pushToast({ tone: 'error', title: '종목 승인 상태 실패', description: payload?.error || quantWorkflow.lastError || 'workflow 상태를 확인하세요.' });
  }, [push, pushToast, quantWorkflow]);

  const handleSaveSymbolCandidate = useCallback(async (symbol: string) => {
    const payload = await quantWorkflow.saveSymbolCandidate(symbol);
    if (payload?.ok) {
      push('success', `${symbol} 종목 후보를 저장했습니다.`, payload.candidate?.decision?.summary || 'runtime apply 대상으로 승격됐습니다.', 'quant-workflow');
      pushToast({ tone: 'success', title: '종목 후보 저장 완료', description: `${symbol} 저장 상태를 갱신했습니다.` });
      return;
    }
    push('error', `${symbol} 종목 후보 저장이 차단되었습니다.`, payload?.error || quantWorkflow.lastError || 'guardrail 사유를 확인하세요.', 'quant-workflow');
    pushToast({ tone: 'error', title: '종목 후보 저장 차단', description: payload?.error || quantWorkflow.lastError || 'guardrail 사유를 확인하세요.' });
  }, [push, pushToast, quantWorkflow]);

  const handleApplyRuntimeCandidate = useCallback(async () => {
    const payload = await quantWorkflow.applyRuntime(savedValidatedCandidate?.id);
    if (payload?.ok) {
      push('success', '저장된 후보를 runtime 설정으로 반영했습니다.', `엔진 ${payload.runtime_apply?.engine_state || '-'} · 다음 실행 ${payload.runtime_apply?.applied_at ? formatDateTime(payload.runtime_apply.applied_at) : '-'}`, 'quant-workflow');
      pushToast({ tone: 'success', title: 'Runtime 반영 완료', description: '다음 paper engine cycle부터 최신 저장 후보를 사용합니다.' });
      return;
    }
    push('error', 'runtime 반영이 차단되었습니다.', payload?.error || quantWorkflow.lastError || 'saved candidate와 guardrail 상태를 확인하세요.', 'quant-workflow');
    pushToast({ tone: 'error', title: 'Runtime 반영 차단', description: payload?.error || quantWorkflow.lastError || 'saved candidate와 guardrail 상태를 확인하세요.' });
  }, [push, pushToast, quantWorkflow, savedValidatedCandidate?.id]);

  const handleRefreshAll = useCallback(async () => {
    onRefresh();

    try {
      const [statusPayload, paramsPayload] = await Promise.all([
        getJSON<{ running?: boolean }>('/api/optimization-status', { noStore: true }),
        getJSON<Record<string, unknown>>('/api/optimized-params', { noStore: true }),
        quantWorkflow.refresh(),
        validationStore.loadSavedFromServer(),
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
  }, [onRefresh, push, pushToast, quantWorkflow, validationStore]);

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
    push('info', '퀀트 백테스트 실행을 시작했습니다.', `시장 ${executedQuery.market_scope === 'kospi' ? 'KOSPI' : executedQuery.market_scope === 'nasdaq' ? 'NASDAQ' : 'KOSPI+NASDAQ'}, 기간 ${executedQuery.lookback_days}일`, 'backtest');
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
      setDiagnosticsResult(null);
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
      const response = await postJSON<{ status?: string; error?: string }>('/api/run-optimization', {
        query: validationStore.savedQuery,
        settings: validationStore.savedSettings,
      });
      const payload = response.data;

      if (payload.status === 'started' || payload.status === 'already_running') {
        const alreadyRunning = payload.status === 'already_running';
        setOptimizationRunning(true);
        setOptimizationPhase(alreadyRunning ? 'running' : 'queued');
        setOptimizationMessage(alreadyRunning ? '이미 실행 중인 최적화 작업을 추적합니다.' : '최적화가 큐에 등록되었습니다. 완료 후 latest candidate까지 자동 갱신합니다.');
        push('info', alreadyRunning ? '퀀트 최적화가 이미 실행 중입니다.' : '퀀트 최적화를 시작했습니다.', alreadyRunning ? '이미 실행 중인 작업을 계속 추적합니다.' : '완료되면 search → latest candidate handoff까지 자동으로 갱신됩니다.', 'optimization');
        pushToast({
          tone: 'info',
          title: alreadyRunning ? '최적화 작업 확인' : '최적화 시작',
          description: alreadyRunning ? '이미 실행 중인 작업을 계속 모니터링합니다.' : '완료되면 search 결과와 latest candidate가 함께 갱신됩니다.',
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
  }, [optimizationHistory, optimizationPhase, optimizationRunning, push, pushToast, updateOptimizationHistory, validationStore.savedQuery, validationStore.savedSettings, validationStore.unsaved]);

  const handleSaveSettings = useCallback(async () => {
    if (settingsSyncBusy) return;
    try {
      const savedAt = await validationStore.saveDraftToServer();
      const historyItem: SettingSaveItem = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        at: savedAt,
        market: validationStore.draftQuery.market_scope,
        lookbackDays: validationStore.draftQuery.lookback_days,
        strategy: validationStore.draftSettings.strategy,
      };
      updateSaveHistory([historyItem, ...saveHistory].slice(0, 30));
      push('success', '퀀트 검증 설정을 서버에 저장했습니다.', `${validationStore.draftQuery.market_scope === 'kospi' ? 'KOSPI' : validationStore.draftQuery.market_scope === 'nasdaq' ? 'NASDAQ' : 'KOSPI+NASDAQ'} · ${validationStore.draftQuery.lookback_days}일`, 'settings');
      pushToast({ tone: 'success', title: '서버 저장 완료', description: '이 저장값은 다른 브라우저/기기에서도 같은 기준으로 불러옵니다.' });
    } catch {
      push('error', '퀀트 검증 설정 저장이 실패했습니다.', '서버 설정 저장 API 또는 JSON 파일 상태를 확인하세요.', 'settings');
      pushToast({ tone: 'error', title: '서버 저장 실패', description: '잠시 후 다시 시도해 주세요.' });
    }
  }, [push, pushToast, saveHistory, settingsSyncBusy, updateSaveHistory, validationStore]);

  const handleLoadSavedSettings = useCallback(async () => {
    if (settingsSyncBusy) return;
    try {
      await validationStore.loadSavedFromServer({ forceDraft: true });
      setBacktestMessage('서버 저장값을 초안으로 다시 불러왔습니다. 저장된 기준으로 바로 실행할 수 있습니다.');
      push('info', '서버 저장값을 초안으로 불러왔습니다.', '다른 기기에서 저장한 값도 여기로 즉시 동기화됩니다.', 'settings');
      pushToast({ tone: 'info', title: '저장값 불러오기 완료', description: '서버 저장값으로 draft를 덮어썼습니다.' });
    } catch {
      push('error', '서버 저장값을 불러오지 못했습니다.', '네트워크 또는 백엔드 상태를 확인하세요.', 'settings');
      pushToast({ tone: 'error', title: '저장값 불러오기 실패', description: '현재 브라우저 초안은 유지했습니다.' });
    }
  }, [push, pushToast, settingsSyncBusy, validationStore]);

  const handleResetSettings = useCallback(async () => {
    if (settingsSyncBusy) return;
    try {
      await validationStore.resetSavedToServer();
      setBacktestMessage('서버 저장값을 기본 quant 값으로 초기화했습니다. 모든 기기에서 같은 기본값을 다시 읽습니다.');
      push('warning', '서버 저장된 quant 설정을 기본값으로 초기화했습니다.', '브라우저 초안도 함께 기본값으로 덮어썼습니다.', 'settings');
      pushToast({ tone: 'warning', title: '서버 저장값 초기화', description: '공유 기준이 기본값으로 재설정되었습니다.' });
    } catch {
      push('error', '서버 저장값 초기화가 실패했습니다.', '백엔드 상태 또는 저장 파일 권한을 확인하세요.', 'settings');
      pushToast({ tone: 'error', title: '서버 저장값 초기화 실패', description: '기존 초안과 저장값은 그대로 유지했습니다.' });
    }
  }, [push, pushToast, settingsSyncBusy, validationStore]);

  const selectAllOnFocus = useCallback((event: FocusEvent<HTMLInputElement>) => {
    requestAnimationFrame(() => event.currentTarget.select());
  }, []);

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
      <section className="settings-flow-card">
        <div className="settings-flow-title">전략 검증 순서</div>
        <div className="settings-flow-copy">설정 저장 후에 백테스트와 진단을 실행하면 이후 Search/Revalidate/Save/Apply 단계가 끊기지 않습니다. 퀀트 검증 경로와 리서치 후보 경로는 분리되어 있고, runtime 후보 소스 모드에서 둘을 어떻게 노출할지 결정합니다.</div>
        <div className="settings-flow-list">
          <div><strong>1)</strong> 설정 저장</div>
          <div><strong>2)</strong> 저장 기준 백테스트 실행</div>
          <div><strong>3)</strong> Baseline 진단 (필요 시)</div>
          <div><strong>4)</strong> 아래 Workflow에서 Search → Revalidate → Save → Apply</div>
        </div>
        <div className="settings-panel-actions">
          <button className="console-action-button is-primary" onClick={() => { void handleSaveSettings(); }} disabled={settingsSyncBusy}>
            {settingsSaving ? <span className="button-content"><span className="button-spinner" aria-hidden="true" />저장 중...</span> : '1) 설정 저장'}
          </button>
          <button
            className="console-action-button"
            onClick={() => { void handleRunBacktest(); }}
            disabled={backtestPhase === 'requesting' || backtestPhase === 'running' || backtestPhase === 'finalizing'}
          >
            {backtestPhase === 'requesting' || backtestPhase === 'running' || backtestPhase === 'finalizing'
              ? <span className="button-content"><span className="button-spinner" aria-hidden="true" />백테스트 실행 중...</span>
              : '2) 저장 기준 백테스트'}
          </button>
          <button className="console-action-button" onClick={() => { void handleRunDiagnosis(); }} disabled={validationStore.unsaved}>
            3) Baseline 진단
          </button>
        </div>
      </section>

      <SettingsSection title="기본 전략 설정" description="시장·기간·검증 기준을 정한 뒤 저장하면 백테스트와 재검증 기준이 확정됩니다.">
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

        <FieldBlock label="퀀트 전략 이름" help="실행 패널과 저장 이력에 함께 표시됩니다.">
          <input
            className="backtest-input-wrap"
            style={{ padding: '0 12px' }}
            value={validationStore.draftSettings.strategy}
            onChange={(event) => validationStore.setDraftSettings((prev) => ({ ...prev, strategy: event.target.value }))}
            placeholder="예: 퀀트 모멘텀 엔진"
          />
        </FieldBlock>

        <FieldBlock label="백테스트 기간(일)" help="최소 180일, 30일 단위 권장">
          <IntegerDraftInput
            value={validationStore.draftQuery.lookback_days}
            min={180}
            step={30}
            onCommit={(next) => validationStore.setDraftQuery((prev) => ({ ...prev, lookback_days: next }))}
          />
        </FieldBlock>

        <FieldBlock label="학습 기간(일)" help="최소 30일, 10일 단위">
          <IntegerDraftInput
            value={validationStore.draftSettings.trainingDays}
            min={30}
            step={10}
            onCommit={(next) => validationStore.setDraftSettings((prev) => ({ ...prev, trainingDays: next }))}
          />
        </FieldBlock>

        <FieldBlock label="검증 기간(일)" help="최소 20일, 10일 단위">
          <IntegerDraftInput
            value={validationStore.draftSettings.validationDays}
            min={20}
            step={10}
            onCommit={(next) => validationStore.setDraftSettings((prev) => ({ ...prev, validationDays: next }))}
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
          <IntegerDraftInput
            value={validationStore.draftSettings.minTrades}
            min={1}
            step={1}
            onCommit={(next) => validationStore.setDraftSettings((prev) => ({ ...prev, minTrades: next }))}
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

        <FieldBlock label="Runtime 후보 소스 모드" help="퀀트 실행 경로와 리서치 후보 경로를 어떻게 runtime 후보 풀에 노출할지 고릅니다. 기본값은 quant_only 입니다.">
          <select
            className="backtest-input-wrap"
            style={{ padding: '0 12px' }}
            value={validationStore.draftSettings.runtimeCandidateSourceMode}
            onChange={(event) => validationStore.setDraftSettings((prev) => ({ ...prev, runtimeCandidateSourceMode: event.target.value as typeof prev.runtimeCandidateSourceMode }))}
          >
            <option value="quant_only">quant_only · 퀀트 검증 후보만 사용</option>
            <option value="research_only">research_only · 리서치 후보만 사용</option>
            <option value="hybrid">hybrid · 분리 수집 후 합집합 사용</option>
          </select>
          <div className="settings-field-help" style={{ marginTop: 8 }}>
            {runtimeCandidateSourceModeDescription(validationStore.draftSettings.runtimeCandidateSourceMode)}
          </div>
        </FieldBlock>
      </SettingsSection>

      <SettingsSection title="고급 룰 파라미터" description="진입·청산 파라미터를 조정한 뒤 저장하면 백테스트와 최적화에 반영됩니다.">
        <FieldBlock label="초기 자금" help="시장 기본 통화 기준입니다.">
          <MoneyValueInput
            value={validationStore.draftQuery.initial_cash}
            onChange={(next) => validationStore.setDraftQuery((prev) => ({ ...prev, initial_cash: next }))}
            min={1}
            placeholder="예: 100,000,000"
          />
        </FieldBlock>
        <FieldBlock label="최대 보유 종목 수" help="동시 보유 가능한 포지션 수입니다.">
          <IntegerDraftInput
            value={validationStore.draftQuery.max_positions}
            min={1}
            step={1}
            onCommit={(next) => validationStore.setDraftQuery((prev) => ({ ...prev, max_positions: next }))}
          />
        </FieldBlock>
        <FieldBlock label="최대 보유 일수" help="포지션 강제 정리 기준입니다.">
          <IntegerDraftInput
            value={validationStore.draftQuery.max_holding_days}
            min={1}
            step={1}
            onCommit={(next) => validationStore.setDraftQuery((prev) => ({ ...prev, max_holding_days: next }))}
          />
        </FieldBlock>
        <FieldBlock label="RSI 최소" help="진입 허용 하한선입니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" step={1} value={validationStore.draftQuery.rsi_min} onChange={updateDraftQueryNumber('rsi_min', validationStore.draftQuery.rsi_min)} onFocus={selectAllOnFocus} />
        </FieldBlock>
        <FieldBlock label="RSI 최대" help="진입 허용 상한선입니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" step={1} value={validationStore.draftQuery.rsi_max} onChange={updateDraftQueryNumber('rsi_max', validationStore.draftQuery.rsi_max)} onFocus={selectAllOnFocus} />
        </FieldBlock>
        <FieldBlock label="거래량 배수 최소" help="평균 대비 거래량 필터입니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" min={0} step={0.1} value={validationStore.draftQuery.volume_ratio_min} onChange={updateDraftQueryNumber('volume_ratio_min', validationStore.draftQuery.volume_ratio_min, 0)} onFocus={selectAllOnFocus} />
        </FieldBlock>
        <FieldBlock label="손절 폭(%)" help="비우면 손절 조건을 끕니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" min={0} step={0.1} value={validationStore.draftQuery.stop_loss_pct ?? ''} onChange={updateDraftQueryNullableNumber('stop_loss_pct', 0)} placeholder="예: 5" onFocus={selectAllOnFocus} />
        </FieldBlock>
        <FieldBlock label="익절 폭(%)" help="비우면 익절 조건을 끕니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" min={0} step={0.1} value={validationStore.draftQuery.take_profit_pct ?? ''} onChange={updateDraftQueryNullableNumber('take_profit_pct', 0)} placeholder="예: 12" onFocus={selectAllOnFocus} />
        </FieldBlock>
        <FieldBlock label="ADX 최소" help="추세 강도 필터입니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" min={0} step={0.1} value={validationStore.draftQuery.adx_min ?? ''} onChange={updateDraftQueryNullableNumber('adx_min', 0)} onFocus={selectAllOnFocus} />
        </FieldBlock>
        <FieldBlock label="MFI 최소" help="자금 유입 하한선입니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" step={0.1} value={validationStore.draftQuery.mfi_min ?? ''} onChange={updateDraftQueryNullableNumber('mfi_min')} onFocus={selectAllOnFocus} />
        </FieldBlock>
        <FieldBlock label="MFI 최대" help="과열 차단 상한선입니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" step={0.1} value={validationStore.draftQuery.mfi_max ?? ''} onChange={updateDraftQueryNullableNumber('mfi_max')} onFocus={selectAllOnFocus} />
        </FieldBlock>
        <FieldBlock label="BB 위치 최소" help="볼린저 밴드 위치 하한선입니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" min={0} max={1} step={0.01} value={validationStore.draftQuery.bb_pct_min ?? ''} onChange={updateDraftQueryNullableNumber('bb_pct_min', 0)} onFocus={selectAllOnFocus} />
        </FieldBlock>
        <FieldBlock label="BB 위치 최대" help="볼린저 밴드 위치 상한선입니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" min={0} max={1} step={0.01} value={validationStore.draftQuery.bb_pct_max ?? ''} onChange={updateDraftQueryNullableNumber('bb_pct_max', 0)} onFocus={selectAllOnFocus} />
        </FieldBlock>
        <FieldBlock label="Stoch K 최소" help="모멘텀 하한선입니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" step={0.1} value={validationStore.draftQuery.stoch_k_min ?? ''} onChange={updateDraftQueryNullableNumber('stoch_k_min')} onFocus={selectAllOnFocus} />
        </FieldBlock>
        <FieldBlock label="Stoch K 최대" help="모멘텀 상한선입니다.">
          <input className="backtest-input-wrap" style={{ padding: '0 12px' }} type="number" step={0.1} value={validationStore.draftQuery.stoch_k_max ?? ''} onChange={updateDraftQueryNullableNumber('stoch_k_max')} onFocus={selectAllOnFocus} />
        </FieldBlock>
      </SettingsSection>

      <div className="settings-panel-actions">
        <button className="console-action-button is-primary" onClick={() => { void handleSaveSettings(); }} disabled={settingsSyncBusy}>
          {settingsSaving ? <span className="button-content"><span className="button-spinner" aria-hidden="true" />저장 중...</span> : '설정 저장'}
        </button>
        <button className="console-action-button" onClick={() => { void handleLoadSavedSettings(); }} disabled={settingsSyncBusy}>
          {settingsLoading ? <span className="button-content"><span className="button-spinner" aria-hidden="true" />불러오는 중...</span> : '저장값 다시 불러오기'}
        </button>
        <button className="console-action-button is-danger" onClick={() => setResetConfirmOpen(true)} disabled={settingsSyncBusy}>
          {settingsResetting ? <span className="button-content"><span className="button-spinner" aria-hidden="true" />초기화 중...</span> : '서버 저장 초기화'}
        </button>
      </div>
      <div className="detail-list" style={{ marginTop: 8 }}>
        <div>저장값은 서버 JSON 파일에 보관되어 브라우저/기기/세션이 달라도 같은 기준으로 불러옵니다.</div>
        <div>이 저장값은 runtime optimized params와 분리되며, baseline·진단·재검증 기준만 공유합니다. 다만 runtime 후보 소스 모드는 여기서 함께 저장되어 API/UI 전체에 같은 값으로 반영됩니다.</div>
        <div>마지막 서버 저장: {validationStore.lastSavedAt ? formatDateTime(validationStore.lastSavedAt) : '없음'}</div>
        {validationStore.syncMessage && <div>동기화 상태: {validationStore.syncMessage}</div>}
      </div>
    </div>
  );

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell" style={{ display: 'grid', gap: 16 }}>
          <ConsoleActionBar
            title="전략 검증 랩"
            subtitle="리서치와 퀀트 실행 경로를 분리한 채, quant 전략 검증과 runtime handoff를 관리하는 화면입니다. 리서치 후보는 여기서 실행 소스 모드로만 연결합니다."
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

          {adoptionDecisionPanel}

          <div className="validation-report-grid">
            <div className="page-section" style={{ padding: 16 }}>
              <div className="section-kicker">Mode 01</div>
              <div className="section-title">퀀트 전략 검증</div>
              <div className="section-copy">백테스트, walk-forward, 최적화로 전략을 채택/보류하는 전용 영역입니다. paper/live 실행 전에 통과해야 하는 게이트를 여기서 관리합니다.</div>
            </div>
            <div className="page-section" style={{ padding: 16 }}>
              <div className="section-kicker">Mode 02</div>
              <div className="section-title">AI/테마/뉴스 리서치</div>
              <div className="section-copy">투자 브리프, 관심 시나리오, paper 실행 후보 선택에서 따로 읽습니다. 퀀트 검증 경로와 직접 섞지 않고 분리 운영하며, runtime 후보 소스 모드가 hybrid일 때만 downstream 후보 풀에서 합집합으로 병합합니다.</div>
            </div>
          </div>

          <div className="validation-layout">
            <div className="validation-report-column">
              <div className="page-section" style={{ padding: 16 }}>
                <div className="section-head-row">
                  <div>
                    <div className="section-title">Validation → Runtime 실행 흐름</div>
                    <div className="section-copy">권장 순서는 설정 저장 → 백테스트 → (필요 시) Baseline 진단 → Search → Revalidate → Save → Apply 입니다. Search는 후보 풀이고, latest candidate는 같은 search 버전을 baseline 기준으로 다시 판정한 실행 후보입니다. 리서치 후보 경로는 별도이며, runtime 후보 소스 모드에서 quant_only / research_only / hybrid 중 하나로 실제 실행 노출 범위를 정합니다.</div>
                  </div>
                  <div className={`inline-badge ${quantWorkflow.busyAction ? 'is-warning' : latestCandidateMatchesSearch ? 'is-success' : 'is-warning'}`}>
                    {quantWorkflow.busyAction ? `작업 중 · ${quantWorkflow.busyAction}` : latestCandidateMatchesSearch ? '최신 handoff 완료' : '단계 확인 필요'}
                  </div>
                </div>

                <div className="quant-ops-stage-grid" style={{ marginTop: 12 }}>
                  {workflowStages.map((stage) => (
                    <div key={stage.key} className={`quant-ops-stage-card is-${stage.tone}`}>
                      <div className="quant-ops-stage-title">{stage.title}</div>
                      <div className="quant-ops-stage-status">{stage.label}</div>
                      <div className="quant-ops-stage-copy">{stage.detail}</div>
                    </div>
                  ))}
                </div>

                <div className="operator-note-grid" style={{ marginTop: 12 }}>
                  <div className={`operator-note-card ${searchResult?.available ? 'is-good' : ''}`}>
                    <div className="operator-note-label">현재 Search 결과</div>
                    <div className="operator-note-copy">버전 {String(searchResult?.version || '-')} · {searchContextLabel || 'optimizer search 결과 대기'}<br />source {String(searchResult?.source || searchResult?.global_overlay_source || '-')}</div>
                  </div>
                  <div className={`operator-note-card ${latestCandidateMatchesSearch ? 'is-good' : latestValidatedCandidate ? 'is-bad' : ''}`}>
                    <div className="operator-note-label">현재 latest candidate</div>
                    <div className="operator-note-copy">{latestValidatedCandidate?.decision?.label || '재검증 전'} · search {String(latestValidatedCandidate?.search_version || '-')}<br />{latestCandidateMatchesSearch ? '현재 search 버전과 일치합니다.' : latestCandidateStateReasons[0] || '최신 search와 아직 연결되지 않았습니다.'}</div>
                  </div>
                  <div className={`operator-note-card ${savedValidatedCandidate?.saved_at ? (savedCandidateStateReasons.length === 0 ? 'is-good' : 'is-bad') : ''}`}>
                    <div className="operator-note-label">저장 후보 스냅샷</div>
                    <div className="operator-note-copy">{savedValidatedCandidate?.saved_at ? formatDateTime(savedValidatedCandidate.saved_at) : '아직 없음'}<br />{savedCandidateStateReasons[0] || (savedValidatedCandidate?.saved_at ? 'runtime 반영 전 기준 스냅샷입니다.' : 'Save 단계 전입니다.')}</div>
                  </div>
                  <div className={`operator-note-card ${runtimeApplyState?.status === 'applied' && runtimeApplyReasons.length === 0 ? 'is-good' : runtimeApplyReasons.length > 0 ? 'is-bad' : ''}`}>
                    <div className="operator-note-label">실제 runtime 적용본</div>
                    <div className="operator-note-copy">{quantRuntimeSourceLabel(runtimeApplyState?.effective_source)} · mode {runtimeCandidateSourceModeLabel(runtimeApplyState?.runtime_candidate_source_mode || validationStore.savedSettings.runtimeCandidateSourceMode)} · candidate {String(runtimeApplyState?.candidate_id || '-')}<br />{runtimeApplyReasons[0] || runtimeCandidateSourceModeDescription(runtimeApplyState?.runtime_candidate_source_mode || validationStore.savedSettings.runtimeCandidateSourceMode)}</div>
                  </div>
                </div>

                {handoffWarnings.length > 0 && (
                  <div className="inline-warning-card" style={{ marginTop: 12 }}>
                    {handoffWarnings.slice(0, 3).map((line) => <div key={line}>{line}</div>)}
                  </div>
                )}

                <div className="detail-list" style={{ marginTop: 12 }}>
                  <div><strong>실행 순서</strong> 1) 설정 저장 2) 백테스트 3) Search 4) Revalidate 5) Save 6) Apply</div>
                  <div>Search는 optimizer로 후보 풀을 만들고, Revalidate는 같은 버전을 현재 baseline 기준으로 다시 판정합니다.</div>
                  <div>Baseline 진단은 보조 단계이며, Search 전에 막힌 이유를 빠르게 확인할 때 사용합니다.</div>
                </div>

                <div className="execution-button-row" style={{ marginTop: 12 }}>
                  <button className="console-action-button" onClick={() => { void handleRunDiagnosis(); }} disabled={validationStore.unsaved}>
                    {diagnosticsResult?.ok ? 'Baseline 진단 다시 계산' : 'Baseline 진단 실행'}
                  </button>
                </div>

                <div className="quant-ops-stage-grid" style={{ marginTop: 12 }}>
                  <div className={`quant-ops-stage-card is-${searchResult?.available ? 'good' : searchHandoff?.status === 'optimizer_failed' ? 'bad' : 'neutral'}`}>
                    <div className="quant-ops-stage-title">1. Search</div>
                    <div className="quant-ops-stage-status">{searchResult?.available ? '후보 풀 준비' : optimizationRunning ? '실행 중' : '미실행'}</div>
                    <div className="quant-ops-stage-copy">{searchContextLabel || '저장된 설정 기준으로 optimizer를 돌려 최신 후보 풀을 만듭니다.'}</div>
                    <div className="quant-ops-stage-copy">{searchHandoff?.status === 'candidate_updated' ? `자동 handoff 완료 · ${searchHandoff?.decision_label || 'latest candidate 갱신'}` : searchHandoff?.error ? `handoff 상태: ${searchHandoff.error}` : '완료 후 latest candidate를 같은 search 버전으로 자동 갱신합니다.'}</div>
                    <button
                      className="console-action-button"
                      style={{ marginTop: 12, width: '100%' }}
                      onClick={() => { void handleRunOptimization(); }}
                      disabled={optimizationRunning || optimizationPhase === 'requesting'}
                    >
                      {optimizationRunning || optimizationPhase === 'requesting'
                        ? <span className="button-content"><span className="button-spinner" aria-hidden="true" />optimizer 실행 중...</span>
                        : searchResult?.available ? '최신 Search 다시 실행' : 'Search 실행'}
                    </button>
                  </div>

                  <div className={`quant-ops-stage-card is-${latestCandidateMatchesSearch ? quantDecisionTone(latestValidatedCandidate?.decision?.status) : 'neutral'}`}>
                    <div className="quant-ops-stage-title">2. Revalidate</div>
                    <div className="quant-ops-stage-status">{latestCandidateMatchesSearch ? latestValidatedCandidate?.decision?.label || '완료' : '대기'}</div>
                    <div className="quant-ops-stage-copy">{latestCandidateMatchesSearch ? latestValidatedCandidate?.decision?.summary || '최신 search 버전 기준 후보가 갱신됐습니다.' : 'Search 결과를 현재 baseline 기준으로 다시 판정합니다.'}</div>
                    <div className="quant-ops-stage-copy">{latestCandidateMatchesSearch ? `search ${String(latestValidatedCandidate?.search_version || '-')}` : '자동 handoff가 실패했거나 수동으로 다시 돌리고 싶으면 여기서 재검증하세요.'}</div>
                    <button
                      className="console-action-button"
                      style={{ marginTop: 12, width: '100%' }}
                      onClick={() => { void handleRevalidateCandidate(); }}
                      disabled={validationStore.unsaved || quantWorkflow.busyAction === 'revalidate' || !searchResult?.available}
                    >
                      {quantWorkflow.busyAction === 'revalidate' ? <span className="button-content"><span className="button-spinner" aria-hidden="true" />재검증 중...</span> : latestCandidateMatchesSearch ? '최신 후보 다시 재검증' : 'Search 결과 재검증'}
                    </button>
                  </div>

                  <div className={`quant-ops-stage-card is-${latestValidatedCandidate?.guardrails?.can_save ? 'good' : 'neutral'}`}>
                    <div className="quant-ops-stage-title">3. Save</div>
                    <div className="quant-ops-stage-status">{savedValidatedCandidate?.saved_at ? '저장됨' : latestValidatedCandidate?.guardrails?.can_save ? '저장 가능' : '대기'}</div>
                    <div className="quant-ops-stage-copy">{savedValidatedCandidate?.saved_at ? `저장 시각 ${formatDateTime(savedValidatedCandidate.saved_at)}` : '재검증 통과 후보만 저장합니다.'}</div>
                    <div className="quant-ops-stage-copy">{latestValidatedCandidate?.guardrails?.can_save ? '현재 latest candidate를 저장해 runtime apply 전 스냅샷으로 고정합니다.' : '먼저 최신 search 버전 후보를 재검증하고 guardrail을 통과해야 합니다.'}</div>
                    <button
                      className="console-action-button"
                      style={{ marginTop: 12, width: '100%' }}
                      onClick={() => { void handleSaveValidatedCandidate(); }}
                      disabled={!latestValidatedCandidate?.guardrails?.can_save || quantWorkflow.busyAction === 'save'}
                    >
                      {quantWorkflow.busyAction === 'save' ? <span className="button-content"><span className="button-spinner" aria-hidden="true" />저장 중...</span> : '재검증 통과 후보 저장'}
                    </button>
                  </div>

                  <div className={`quant-ops-stage-card is-${savedValidatedCandidate?.guardrails?.can_apply ? 'good' : runtimeApplyState?.status === 'applied' ? 'good' : 'neutral'}`}>
                    <div className="quant-ops-stage-title">4. Apply</div>
                    <div className="quant-ops-stage-status">{runtimeApplyState?.status === 'applied' ? 'runtime 반영됨' : savedValidatedCandidate?.guardrails?.can_apply ? '반영 가능' : '대기'}</div>
                    <div className="quant-ops-stage-copy">{runtimeApplyState?.status === 'applied' ? `${formatDateTime(runtimeApplyState.applied_at)} · 엔진 ${runtimeApplyState.engine_state || '-'}` : '저장된 후보만 runtime/paper 설정으로 반영합니다.'}</div>
                    <div className="quant-ops-stage-copy">{savedValidatedCandidate?.guardrails?.can_apply ? '다음 engine cycle부터 저장 후보를 쓰게 됩니다.' : 'Save 단계가 끝나야 Apply가 열립니다.'}</div>
                    <button
                      className="console-action-button is-primary"
                      style={{ marginTop: 12, width: '100%' }}
                      onClick={() => { void handleApplyRuntimeCandidate(); }}
                      disabled={!savedValidatedCandidate?.guardrails?.can_apply || quantWorkflow.busyAction === 'apply'}
                    >
                      {quantWorkflow.busyAction === 'apply' ? <span className="button-content"><span className="button-spinner" aria-hidden="true" />반영 중...</span> : '저장 후보 runtime 반영'}
                    </button>
                  </div>
                </div>

                {(quantWorkflow.lastError || errorMessage) && (
                  <div className="inline-warning-card" style={{ marginTop: 12 }}>{quantWorkflow.lastError || errorMessage}</div>
                )}
              </div>

              <div className="validation-report-grid">
                <div className="page-section" style={{ padding: 16 }}>
                  <div className="section-head-row">
                    <div>
                      <div className="section-title">탐색 결과(Search)</div>
                      <div className="section-copy">optimizer가 만든 최신 후보 풀입니다. 여기서 끝나지 않고 같은 search 버전으로 latest candidate를 자동/수동 재검증해야 저장 단계로 넘어갑니다.</div>
                    </div>
                    <div className={`inline-badge ${searchResult?.is_stale ? 'is-warning' : searchResult?.available ? 'is-success' : ''}`}>
                      {searchResult?.available ? quantWorkflowCardTitle(workflowPayload?.stage_status?.candidate_search, String(searchResult.version || '-')) : '후보 없음'}
                    </div>
                  </div>
                  <div className="summary-metric-grid" style={{ marginTop: 12 }}>
                    <SummaryMetricCard label="검색 버전" value={String(searchResult?.version || '-')} detail={searchContextLabel || (searchResult?.optimized_at ? formatDateTime(searchResult.optimized_at) : '아직 탐색 결과가 없습니다.')} tone={searchResult?.available ? 'good' : 'neutral'} />
                    <SummaryMetricCard label="신뢰 후보" value={formatCount(searchResult?.n_reliable, '건')} detail={`medium ${formatCount(searchResult?.n_medium, '건')} · total ${formatCount(searchResult?.n_symbols_optimized, '건')}`} tone={searchResult?.available ? 'good' : 'neutral'} />
                    <SummaryMetricCard label="Optimizer source" value={String(searchResult?.global_overlay_source || '-')} detail={searchResult?.is_stale ? '결과가 오래돼서 재탐색 권장' : `파라미터 ${formatCount(searchResult?.param_count, '개')}`} tone={searchResult?.is_stale ? 'bad' : 'neutral'} />
                    <SummaryMetricCard label="Latest candidate 연결" value={searchHandoff?.decision_label || (latestCandidateMatchesSearch ? latestValidatedCandidate?.decision?.label || '완료' : '대기')} detail={searchHandoff?.error ? `handoff 실패: ${searchHandoff.error}` : latestCandidateMatchesSearch ? `같은 search 버전 ${String(latestValidatedCandidate?.search_version || '-')}` : 'latest candidate가 아직 최신 search를 따라오지 않았습니다.'} tone={latestCandidateMatchesSearch ? quantDecisionTone(latestValidatedCandidate?.decision?.status) : searchHandoff?.error ? 'bad' : 'neutral'} />
                  </div>
                  <div className="detail-list" style={{ marginTop: 12 }}>
                    {Object.entries((searchResult?.global_params || {}) as Record<string, unknown>).slice(0, 8).map(([key, value]) => (
                      <div key={`search-${key}`}>{key}: {typeof value === 'number' ? formatNumber(value, 4) : String(value)}</div>
                    ))}
                    {(!searchResult?.global_params || Object.keys(searchResult.global_params).length === 0) && <div className="empty-inline">optimizer global params가 아직 없습니다.</div>}
                  </div>
                </div>

                <div className="page-section" style={{ padding: 16 }}>
                  <div className="section-head-row">
                    <div>
                      <div className="section-title">재검증 후보(Validated Candidate)</div>
                      <div className="section-copy">현재 baseline 기준으로 다시 검증한 운영 후보입니다. 저장 가드레일은 여기 결과로만 판단합니다.</div>
                    </div>
                    <div className={`inline-badge ${quantDecisionTone(latestValidatedCandidate?.decision?.status) === 'good' ? 'is-success' : quantDecisionTone(latestValidatedCandidate?.decision?.status) === 'bad' ? 'is-danger' : 'is-warning'}`}>
                      {latestValidatedCandidate?.decision?.label || '재검증 전'}
                    </div>
                  </div>
                  <div className="summary-metric-grid" style={{ marginTop: 12 }}>
                    <SummaryMetricCard label="OOS / PF" value={`${formatPercent(latestValidatedCandidate?.metrics?.oos_return_pct ?? null, 2)} / ${formatNumber(latestValidatedCandidate?.metrics?.profit_factor ?? null, 2)}`} detail={`신뢰도 ${reliabilityToKorean(String(latestValidatedCandidate?.metrics?.reliability || '')) || '-'} · 거래 ${formatCount(latestValidatedCandidate?.metrics?.trade_count, '건')}`} tone={quantDecisionTone(latestValidatedCandidate?.decision?.status)} />
                    <SummaryMetricCard label="낙폭 / ES(5%)" value={`${formatPercent(latestValidatedCandidate?.metrics?.max_drawdown_pct ?? null, 2)} / ${formatPercent(latestValidatedCandidate?.metrics?.expected_shortfall_5_pct ?? null, 2)}`} detail={`윈도우 양수 비율 ${formatPercent(((latestValidatedCandidate?.metrics?.positive_window_ratio ?? null) !== null && (latestValidatedCandidate?.metrics?.positive_window_ratio ?? undefined) !== undefined) ? Number(latestValidatedCandidate?.metrics?.positive_window_ratio) * 100 : null, 1)}`} tone={quantDecisionTone(latestValidatedCandidate?.decision?.status)} />
                    <SummaryMetricCard label="복합 점수" value={latestValidatedCandidate?.metrics?.composite_score === undefined ? '-' : `${formatNumber(latestValidatedCandidate?.metrics?.composite_score ?? null, 1)}점`} detail={latestValidatedCandidate?.decision?.summary || '재검증을 실행하면 저장 가능 여부가 여기 표시됩니다.'} tone={quantDecisionTone(latestValidatedCandidate?.decision?.status)} />
                  </div>
                  <div className="detail-list" style={{ marginTop: 12 }}>
                    {(latestValidatedCandidate?.patch_lines || []).map((line) => <div key={line}>{line}</div>)}
                    {(!latestValidatedCandidate?.patch_lines || latestValidatedCandidate.patch_lines.length === 0) && <div className="empty-inline">아직 재검증 후보가 없습니다.</div>}
                  </div>
                  {latestValidatedCandidate && (
                    <div className="quant-ops-guardrail-list" style={{ marginTop: 12 }}>
                      {(latestValidatedCandidate.guardrails?.reasons || []).length === 0 && <div className="summary-rail-item">저장/반영 가드레일 차단 사유 없음</div>}
                      {(latestValidatedCandidate.guardrails?.reasons || []).map((reason) => (
                        <div key={reason} className="summary-rail-item">{quantGuardrailReasonLabel(reason)}</div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div className="page-section" style={{ padding: 16 }}>
                <div className="section-head-row">
                  <div>
                    <div className="section-title">Per-Symbol Candidate Approval</div>
                    <div className="section-copy">종목 후보는 재검증 후 운영자가 승인/거절/보류를 명시해야 저장할 수 있습니다. 저장된 종목 후보만 runtime apply 시 반영됩니다.</div>
                  </div>
                  <div className={`inline-badge ${(workflowPayload?.symbol_summary?.saved_count || 0) > 0 ? 'is-success' : ''}`}>
                    검색 {formatCount(workflowPayload?.symbol_summary?.search_count, '건')} · 승인 {formatCount(workflowPayload?.symbol_summary?.approved_count, '건')} · 저장 {formatCount(workflowPayload?.symbol_summary?.saved_count, '건')}
                  </div>
                </div>

                {symbolCandidates.length > 0 ? (
                  <>
                    <div className="execution-button-row is-split" style={{ marginTop: 12 }}>
                      <select
                        className="backtest-input-wrap"
                        style={{ padding: '0 12px', minWidth: 170 }}
                        value={selectedSymbolWorkflow?.symbol || ''}
                        onChange={(event) => setSelectedSymbol(event.target.value)}
                      >
                        {symbolCandidates.map((item) => (
                          <option key={String(item.symbol || '')} value={String(item.symbol || '')}>
                            {String(item.symbol || '')}
                          </option>
                        ))}
                      </select>
                      <button
                        className="console-action-button"
                        onClick={() => { if (selectedSymbolWorkflow?.symbol) void handleRevalidateSymbolCandidate(String(selectedSymbolWorkflow.symbol)); }}
                        disabled={!selectedSymbolWorkflow?.symbol || validationStore.unsaved || quantWorkflow.busyAction === 'revalidate_symbol'}
                      >
                        {quantWorkflow.busyAction === 'revalidate_symbol' ? <span className="button-content"><span className="button-spinner" aria-hidden="true" />종목 재검증 중...</span> : '선택 종목 재검증'}
                      </button>
                      <button
                        className="console-action-button"
                        onClick={() => { if (selectedSymbolWorkflow?.symbol) void handleSetSymbolApproval(String(selectedSymbolWorkflow.symbol), 'approved'); }}
                        disabled={!selectedSymbolWorkflow?.latest_candidate || quantWorkflow.busyAction === 'approve_symbol'}
                      >
                        승인
                      </button>
                      <button
                        className="console-action-button"
                        onClick={() => { if (selectedSymbolWorkflow?.symbol) void handleSetSymbolApproval(String(selectedSymbolWorkflow.symbol), 'hold'); }}
                        disabled={!selectedSymbolWorkflow?.latest_candidate || quantWorkflow.busyAction === 'approve_symbol'}
                      >
                        보류
                      </button>
                      <button
                        className="console-action-button is-danger"
                        onClick={() => { if (selectedSymbolWorkflow?.symbol) void handleSetSymbolApproval(String(selectedSymbolWorkflow.symbol), 'rejected'); }}
                        disabled={!selectedSymbolWorkflow?.latest_candidate || quantWorkflow.busyAction === 'approve_symbol'}
                      >
                        거절
                      </button>
                      <button
                        className="console-action-button is-primary"
                        onClick={() => { if (selectedSymbolWorkflow?.symbol) void handleSaveSymbolCandidate(String(selectedSymbolWorkflow.symbol)); }}
                        disabled={!selectedSymbolWorkflow?.latest_guardrails?.can_save || quantWorkflow.busyAction === 'save_symbol'}
                      >
                        {quantWorkflow.busyAction === 'save_symbol' ? <span className="button-content"><span className="button-spinner" aria-hidden="true" />종목 저장 중...</span> : '선택 종목 저장'}
                      </button>
                    </div>

                    {selectedSymbolWorkflow && (
                      <>
                        <div className="summary-metric-grid" style={{ marginTop: 12 }}>
                          <SummaryMetricCard
                            label="선택 종목"
                            value={String(selectedSymbolWorkflow.symbol || '-')}
                            detail={`승인 ${symbolApprovalLabel(selectedSymbolWorkflow.approval?.status)} · 저장 ${selectedSymbolWorkflow.saved_candidate?.saved_at ? '완료' : '대기'}`}
                            tone={symbolApprovalTone(selectedSymbolWorkflow.approval?.status)}
                          />
                          <SummaryMetricCard
                            label="재검증 상태"
                            value={selectedSymbolWorkflow.latest_candidate?.decision?.label || '미실행'}
                            detail={selectedSymbolWorkflow.latest_candidate?.decision?.summary || '재검증 후 승인/저장 단계를 진행하세요.'}
                            tone={quantDecisionTone(selectedSymbolWorkflow.latest_candidate?.decision?.status)}
                          />
                          <SummaryMetricCard
                            label="Runtime 반영"
                            value={selectedSymbolWorkflow.runtime?.applied ? '반영됨' : '미반영'}
                            detail={selectedSymbolWorkflow.runtime?.applied_at ? formatDateTime(selectedSymbolWorkflow.runtime.applied_at) : '아직 runtime apply 전'}
                            tone={selectedSymbolWorkflow.runtime?.applied ? 'good' : 'neutral'}
                          />
                        </div>

                        <div className="detail-list" style={{ marginTop: 12 }}>
                          <div><strong>종목 후보 파라미터</strong></div>
                          {(selectedSymbolWorkflow.search_candidate?.patch_lines || []).slice(0, 8).map((line) => (
                            <div key={`${selectedSymbolWorkflow.symbol}-search-${line}`}>{line}</div>
                          ))}
                          {(!selectedSymbolWorkflow.search_candidate?.patch_lines || selectedSymbolWorkflow.search_candidate.patch_lines.length === 0) && <div>optimizer per-symbol 파라미터가 없습니다.</div>}
                        </div>

                        <div className="quant-ops-guardrail-list" style={{ marginTop: 12 }}>
                          <div className="summary-rail-item"><strong>승인 상태</strong> {symbolApprovalLabel(selectedSymbolWorkflow.approval?.status)} · {selectedSymbolWorkflow.approval?.updated_at ? formatDateTime(selectedSymbolWorkflow.approval.updated_at) : '미지정'}</div>
                          {(selectedSymbolWorkflow.latest_guardrails?.reasons || []).length === 0 && <div className="summary-rail-item">저장/반영 가드레일 차단 사유 없음</div>}
                          {(selectedSymbolWorkflow.latest_guardrails?.reasons || []).map((reason) => (
                            <div key={`${selectedSymbolWorkflow.symbol}-${reason}`} className="summary-rail-item">{quantGuardrailReasonLabel(reason)}</div>
                          ))}
                        </div>
                      </>
                    )}
                  </>
                ) : (
                  <div className="empty-inline" style={{ marginTop: 12 }}>
                    optimizer per-symbol 후보가 아직 없습니다.
                  </div>
                )}
              </div>

              {(diagnosticsResult?.ok || latestValidatedCandidate || savedValidatedCandidate) && (
                <div className="validation-report-grid">
                  <div className="page-section" style={{ padding: 16 }}>
                    <div className="section-head-row">
                      <div>
                        <div className="section-title">진단 / 개선 경로</div>
                        <div className="section-copy">baseline 진단은 차단 요인을 찾는 단계고, re-validation은 실제 후보를 판정하는 단계입니다. 둘을 섞지 않습니다.</div>
                      </div>
                      <div className={`inline-badge ${diagnosticsResult?.ok ? 'is-success' : ''}`}>{diagnosticsResult?.ok ? '진단 계산됨' : '진단 대기'}</div>
                    </div>
                    <div className="detail-list" style={{ marginTop: 12 }}>
                      {diagnosisLines.slice(0, 4).map((line, index) => <div key={`diag-${index}`}>{line}</div>)}
                      {diagnosisLines.length === 0 && <div>아직 baseline 진단을 실행하지 않았습니다.</div>}
                    </div>
                    <div className="detail-list" style={{ marginTop: 12 }}>
                      <div><strong>차단 요인</strong></div>
                      {diagnosisBlockers.slice(0, 4).map((item, index) => (
                        <div key={`blocker-${index}`}>{reliabilityMetricLabel(String(item.metric || ''))}: 현재 {String(item.current ?? '-')} / 기준 {String(item.threshold ?? '-')} · {String(item.summary || '-')}</div>
                      ))}
                      {diagnosisBlockers.length === 0 && <div>차단 요인 없음</div>}
                    </div>
                    <div className="detail-list" style={{ marginTop: 12 }}>
                      <div><strong>근처 개선 후보</strong></div>
                      {diagnosisSuggestions.slice(0, 3).map((item, index) => (
                        <div key={`suggestion-${index}`}>{item.probe_label || item.label || 'probe'} · {(item.changes || []).slice(0, 2).join(' / ') || '변경 요약 없음'}</div>
                      ))}
                      {diagnosisSuggestions.length === 0 && <div>아직 개선 후보를 계산하지 않았습니다.</div>}
                    </div>
                  </div>

                  <div className="page-section" style={{ padding: 16 }}>
                    <div className="section-head-row">
                      <div>
                        <div className="section-title">저장됨 / Runtime 반영</div>
                        <div className="section-copy">저장 후보와 실제 런타임 반영 상태를 분리합니다. 저장이 안 된 후보는 runtime에 반영되지 않습니다.</div>
                      </div>
                      <div className={`inline-badge ${runtimeApplyState?.status === 'applied' ? 'is-success' : savedValidatedCandidate?.saved_at ? 'is-warning' : ''}`}>
                        {runtimeApplyState?.status === 'applied' ? 'runtime 반영됨' : savedValidatedCandidate?.saved_at ? '저장만 됨' : '저장 전'}
                      </div>
                    </div>
                    <div className="summary-metric-grid" style={{ marginTop: 12 }}>
                      <SummaryMetricCard label="저장 후보 스냅샷" value={savedValidatedCandidate?.saved_at ? formatDateTime(savedValidatedCandidate.saved_at) : '-'} detail={savedCandidateStateReasons[0] || savedValidatedCandidate?.decision?.summary || '저장된 후보가 아직 없습니다.'} tone={savedValidatedCandidate?.saved_at ? 'good' : 'neutral'} />
                      <SummaryMetricCard label="현재 runtime source" value={quantRuntimeSourceLabel(runtimeApplyState?.effective_source)} detail={runtimeApplyReasons[0] || (runtimeApplyState?.applied_at ? `반영 ${formatDateTime(runtimeApplyState.applied_at)}` : '아직 runtime apply 전')} tone={runtimeApplyState?.status === 'applied' && runtimeApplyReasons.length === 0 ? 'good' : runtimeApplyReasons.length > 0 ? 'bad' : 'neutral'} />
                      <SummaryMetricCard label="후보 소스 모드" value={runtimeCandidateSourceModeLabel(runtimeApplyState?.runtime_candidate_source_mode || validationStore.savedSettings.runtimeCandidateSourceMode)} detail={runtimeCandidateSourceModeDescription(runtimeApplyState?.runtime_candidate_source_mode || validationStore.savedSettings.runtimeCandidateSourceMode)} tone={runtimeApplyState?.runtime_candidate_source_mode === 'research_only' ? 'bad' : runtimeApplyState?.runtime_candidate_source_mode === 'hybrid' ? 'neutral' : 'good'} />
                      <SummaryMetricCard label="적용 candidate" value={String(runtimeApplyState?.candidate_id || '-')} detail={runtimeApplyState?.next_run_at ? `다음 실행 ${formatDateTime(runtimeApplyState.next_run_at)}` : '다음 cycle부터 현재 config 사용'} tone={runtimeApplyState?.status === 'applied' ? 'good' : 'neutral'} />
                    </div>
                    <div className="detail-list" style={{ marginTop: 12 }}>
                      {(savedValidatedCandidate?.patch_lines || []).slice(0, 6).map((line) => <div key={`saved-${line}`}>{line}</div>)}
                      {(!savedValidatedCandidate?.patch_lines || savedValidatedCandidate.patch_lines.length === 0) && <div>저장된 파라미터 스냅샷이 아직 없습니다.</div>}
                    </div>
                  </div>
                </div>
              )}

              <div className="page-section" style={{ padding: 16 }}>
                <div className="section-head-row">
                  <div>
                    <div className="section-title">퀀트 전략 점수카드</div>
                    <div className="section-copy">점수 하나로 끝내지 않고, 왜 채택/보류해야 하는지와 손실 꼬리를 같이 봅니다. AI 추천 점수와는 별도입니다.</div>
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

              {reliabilityDiagnostic && (
                <div className="page-section" style={{ padding: 16 }}>
                  <div className="section-head-row">
                    <div>
                      <div className="section-title">신뢰도 진단</div>
                      <div className="section-copy">낮은 등급의 차단 요인과, 최소한 어떤 지표 변화가 필요할지 보여줍니다.</div>
                    </div>
                    <div className={`inline-badge ${reliabilityDiagnostic.target_reached ? 'is-success' : 'is-warning'}`}>
                      목표 {String(reliabilityDiagnostic.target_label || 'medium')} · 현재 {String(reliabilityDiagnostic.current?.label || '-')}
                    </div>
                  </div>

                  <div className="validation-report-grid" style={{ marginTop: 10 }}>
                    <div className="detail-list">
                      <div><strong>차단 요인</strong></div>
                      {diagnosticBlockers.length === 0 && <div>차단 요인 없음</div>}
                      {diagnosticBlockers.slice(0, 4).map((item, index) => (
                        <div key={`${item.metric || 'm'}-${index}`}>
                          {reliabilityMetricLabel(String(item.metric || ''))}: 현재 {String(item.current ?? '-')} / 필요 {String(item.required ?? '-')} (gap {String(item.gap ?? '-')})
                        </div>
                      ))}
                    </div>
                    <div className="detail-list">
                      <div><strong>최소 개선 경로</strong></div>
                      {!diagnosticRecommended && <div>탐색 범위 내에서 개선 경로를 찾지 못했습니다.</div>}
                      {diagnosticRecommended && (
                        <>
                          <div>예상 결과: {String(diagnosticRecommended.label || '-')} ({String(diagnosticRecommended.reason || '-')})</div>
                          {(diagnosticRecommended.changes || []).length === 0 && <div>변경 없음</div>}
                          {(diagnosticRecommended.changes || []).slice(0, 3).map((change, index) => (
                            <div key={`${change.metric || 'c'}-${index}`}>
                              {reliabilityMetricLabel(String(change.metric || ''))}: {String(change.from ?? '-')} → {String(change.to ?? '-')} (Δ{String(change.delta ?? '-')})
                            </div>
                          ))}
                        </>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {(oosExitReasonAnalysis || validationExitReasonAnalysis || exitWeaknessClusters.length > 0) && (
                <div className="page-section" style={{ padding: 16 }}>
                  <div className="section-head-row">
                    <div>
                      <div className="section-title">청산 사유 손실 맵</div>
                      <div className="section-copy">손절·이평 이탈·MACD 약세·보유기간 만료 같은 exit가 검증/OOS에서 왜 문제인지, 그리고 특정 종목·섹터 쏠림인지 한 번에 봅니다.</div>
                    </div>
                    <div className={`inline-badge ${exitWeaknessClusters.length > 0 ? 'is-warning' : 'is-success'}`}>
                      {exitWeaknessClusters.length > 0 ? '약점 클러스터 포착' : '청산 이슈 없음'}
                    </div>
                  </div>

                  <div className="summary-metric-grid" style={{ marginTop: 12 }}>
                    <SummaryMetricCard
                      label="OOS 최대 손실 사유"
                      value={oosTopLossReason?.label || '-'}
                      detail={oosTopLossReason ? formatExitReasonDetail(oosTopLossReason) : 'OOS 청산 데이터가 없습니다.'}
                      tone={reasonRowTone(oosTopLossReason)}
                    />
                    <SummaryMetricCard
                      label="손실 집중 종목"
                      value={primarySymbolWeakness?.label || '-'}
                      detail={primarySymbolWeakness ? formatScopeWeaknessDetail(primarySymbolWeakness) : '문제 종목 데이터가 없습니다.'}
                      tone={primarySymbolWeakness ? 'bad' : 'neutral'}
                    />
                    <SummaryMetricCard
                      label="손실 집중 섹터"
                      value={primarySectorWeakness?.label || '-'}
                      detail={primarySectorWeakness ? formatScopeWeaknessDetail(primarySectorWeakness) : '문제 섹터 데이터가 없습니다.'}
                      tone={primarySectorWeakness ? 'bad' : 'neutral'}
                    />
                    <SummaryMetricCard
                      label="구조 판정"
                      value={primaryConcentrationVerdict?.strategy_issue_label || '-'}
                      detail={formatConcentrationDetail(primaryConcentrationVerdict)}
                      tone={concentrationTone(primaryConcentrationVerdict)}
                    />
                  </div>

                  <div className="validation-report-grid" style={{ marginTop: 12 }}>
                    <div className="detail-list">
                      <div><strong>OOS 상위 청산 사유</strong></div>
                      {(oosExitReasonAnalysis?.reasons || []).slice(0, 4).map((row) => (
                        <div key={`oos-${row.key || row.label}`}>
                          {row.label || row.key || '기타'} · {formatExitReasonDetail(row)}
                        </div>
                      ))}
                      {(!oosExitReasonAnalysis?.reasons || oosExitReasonAnalysis.reasons.length === 0) && <div>OOS 청산 사유가 아직 없습니다.</div>}
                    </div>
                    <div className="detail-list">
                      <div><strong>검증/OOS 해석</strong></div>
                      {exitHeadlines.slice(0, 3).map((line, index) => (
                        <div key={`exit-headline-${index}`}>{line}</div>
                      ))}
                      {primaryConcentrationVerdict?.summary && <div>{primaryConcentrationVerdict.summary}</div>}
                      {persistentTopReason && (
                        <div>
                          반복 약점 {persistentTopReason.label || '-'} · {(persistentTopReason.segments || []).join(' → ')} 반복 · 누적 손실 {formatPercent(persistentTopReason.combined_gross_loss_pct ?? null, 2)}
                        </div>
                      )}
                      {(validationExitReasonAnalysis?.reasons || []).slice(0, 2).map((row) => (
                        <div key={`validation-${row.key || row.label}`}>
                          검증 {row.label || row.key || '기타'} · {formatExitReasonDetail(row)}
                        </div>
                      ))}
                      {exitHeadlines.length === 0 && !primaryConcentrationVerdict?.summary && !persistentTopReason && (!validationExitReasonAnalysis?.reasons || validationExitReasonAnalysis.reasons.length === 0) && <div>검증/OOS 청산 인사이트가 아직 없습니다.</div>}
                    </div>
                  </div>

                  <div className="validation-report-grid" style={{ marginTop: 12 }}>
                    <div className="detail-list">
                      <div><strong>문제 종목 상위</strong></div>
                      {(oosExitReasonAnalysis?.symbol_weaknesses || validationExitReasonAnalysis?.symbol_weaknesses || overallExitReasonAnalysis?.symbol_weaknesses || []).slice(0, 4).map((row) => (
                        <div key={`symbol-${row.key || row.label}`}>
                          {row.label || row.key || '기타'} · {formatScopeWeaknessDetail(row)}
                        </div>
                      ))}
                      {(!oosExitReasonAnalysis?.symbol_weaknesses || oosExitReasonAnalysis.symbol_weaknesses.length === 0)
                        && (!validationExitReasonAnalysis?.symbol_weaknesses || validationExitReasonAnalysis.symbol_weaknesses.length === 0)
                        && (!overallExitReasonAnalysis?.symbol_weaknesses || overallExitReasonAnalysis.symbol_weaknesses.length === 0)
                        && <div>문제 종목 데이터가 아직 없습니다.</div>}
                    </div>
                    <div className="detail-list">
                      <div><strong>문제 섹터 상위</strong></div>
                      {(oosExitReasonAnalysis?.sector_weaknesses || validationExitReasonAnalysis?.sector_weaknesses || overallExitReasonAnalysis?.sector_weaknesses || []).slice(0, 4).map((row) => (
                        <div key={`sector-${row.key || row.label}`}>
                          {row.label || row.key || '기타'} · {formatScopeWeaknessDetail(row)}
                        </div>
                      ))}
                      {(!oosExitReasonAnalysis?.sector_weaknesses || oosExitReasonAnalysis.sector_weaknesses.length === 0)
                        && (!validationExitReasonAnalysis?.sector_weaknesses || validationExitReasonAnalysis.sector_weaknesses.length === 0)
                        && (!overallExitReasonAnalysis?.sector_weaknesses || overallExitReasonAnalysis.sector_weaknesses.length === 0)
                        && <div>문제 섹터 데이터가 아직 없습니다.</div>}
                    </div>
                  </div>
                </div>
              )}

              <div className="validation-report-grid">
                <div className="page-section" style={{ padding: 16 }}>
                  <div className="section-title">구간 성과</div>
                  <div className="detail-list">
                    <div>퀀트 전략: {executedRun?.settings.strategy || validationStore.savedSettings.strategy}</div>
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
                    <div className="section-title">퀀트 실행 패널</div>
                    <div className="section-copy">초안/서버 저장값/마지막 실행 결과를 분리해 보여주며, 실행은 저장된 기준으로만 진행됩니다.</div>
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
                  <div className="summary-rail-item"><strong>서버 저장됨</strong> · {savedSettingsSummaryLines[0]}</div>
                  <div className="summary-rail-item">{savedSettingsSummaryLines[1]}</div>
                  <div className="summary-rail-item">{savedSettingsSummaryLines[2]}</div>
                  <div className="summary-rail-item">마지막 서버 저장 · {validationStore.lastSavedAt ? formatDateTime(validationStore.lastSavedAt) : '없음'}</div>
                </div>

                {executedRun && (
                  <div className="summary-rail is-compact" style={{ marginTop: 8 }}>
                    <div className="summary-rail-item"><strong>마지막 실행</strong> · {executedSettingsSummaryLines[0]}</div>
                    <div className="summary-rail-item">{executedSettingsSummaryLines[1]}</div>
                    <div className="summary-rail-item">{executedSettingsSummaryLines[2]}</div>
                  </div>
                )}

                {validationStore.unsaved && (
                  <div className="inline-warning-card">초안이 서버 저장값과 다릅니다. 실행은 서버 저장값 기준으로만 진행합니다.</div>
                )}

                <div className="execution-button-row is-split">
                  <button
                    className="console-action-button is-primary"
                    onClick={() => { void handleRunBacktest(); }}
                    disabled={backtestPhase === 'requesting' || backtestPhase === 'running' || backtestPhase === 'finalizing'}
                  >
                    {backtestPhase === 'requesting' || backtestPhase === 'running' || backtestPhase === 'finalizing'
                      ? <span className="button-content"><span className="button-spinner" aria-hidden="true" />백테스트 진행 중...</span>
                      : '저장된 설정으로 퀀트 백테스트 실행'}
                  </button>
                </div>

                <div className="detail-list" style={{ marginTop: 8 }}>
                  <div>설정 패널에서 저장과 백테스트를 먼저 실행한 뒤, 위 Workflow 카드에서 Search → Revalidate → Save → Apply를 진행하세요.</div>
                </div>

                <div className="validation-inline-status">
                  <div>퀀트 백테스트: {backtestPhaseLabel(backtestPhase)} · {backtestMessage}</div>
                  <div>퀀트 최적화: {optimizationPhaseLabel(optimizationPhase)} · {optimizationMessage}</div>
                  <div>재검증 후보: {latestValidatedCandidate?.decision?.label || '없음'} · 저장 {latestValidatedCandidate?.guardrails?.can_save ? '가능' : '차단'}</div>
                  <div>종목 승인/저장: {formatCount(workflowPayload?.symbol_summary?.approved_count, '건')} / {formatCount(workflowPayload?.symbol_summary?.saved_count, '건')}</div>
                  <div>저장 후보 / runtime: {savedValidatedCandidate?.saved_at ? formatDateTime(savedValidatedCandidate.saved_at) : '없음'} / {runtimeApplyState?.status === 'applied' ? formatDateTime(runtimeApplyState.applied_at) : '미반영'}</div>
                  <div>runtime 종목 반영: {formatCount(runtimeApplyState?.applied_symbol_count, '건')} · {Array.isArray(runtimeApplyState?.applied_symbols) && runtimeApplyState?.applied_symbols?.length ? runtimeApplyState.applied_symbols.join(', ') : '없음'}</div>
                  <div>마지막 실행 시각: {executedRun?.executedAt ? formatDateTime(executedRun.executedAt) : runFinishedAt ? formatDateTime(runFinishedAt) : '없음'}</div>
                  <div>서버 저장 기준: {validationStore.lastSavedAt ? formatDateTime(validationStore.lastSavedAt) : '없음'} · runtime 최적화 반영과는 별개로 관리합니다.</div>
                  <div>화면 새로고침은 상태와 서버 저장값을 다시 불러오고, 결과 카드는 다시 계산하지 않습니다.</div>
                </div>
              </div>

              <div className="process-grid">
                <ProcessStepper
                  title="퀀트 백테스트 진행"
                  steps={['요청', '계산', '정리', backtestPhase === 'error' ? '실패' : '완료']}
                  activeIndex={buildPhaseIndex(backtestPhase)}
                  error={backtestPhase === 'error'}
                  detail={`경과 ${formatElapsed(runStartedAt)}`}
                  timestamp={runStartedAt || runFinishedAt}
                />
                <ProcessStepper
                  title="퀀트 최적화 진행"
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
                <div className="section-subtitle">OOS 청산 사유 요약</div>
                <div className="history-list">
                  {reasonRows.map((row) => (
                    <div key={row.key || row.label} className="history-item">
                      <div>{row.label || row.key || '기타'}</div>
                      <div className="history-item-copy">{formatExitReasonDetail(row)}</div>
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
          '서버에 저장된 quant 기준을 기본값으로 되돌립니다.',
          '현재 브라우저 초안도 함께 기본값으로 덮어씁니다.',
          'runtime optimized params와는 별개라서 운영 반영값은 건드리지 않습니다.',
        ]}
        tone="danger"
        onConfirm={() => {
          void handleResetSettings();
          setResetConfirmOpen(false);
        }}
        onCancel={() => setResetConfirmOpen(false)}
      />
    </div>
  );
}
