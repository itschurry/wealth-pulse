import { useCallback, useDeferredValue, useEffect, useMemo, useState } from 'react';
import { ConsoleActionBar } from '../components/ConsoleActionBar';
import { NumericInput } from '../components/NumericInput';
import { SymbolIdentity } from '../components/SymbolIdentity';
import { getRiskGuardState, isRiskEntryAllowed } from '../adapters/consoleViewAdapter';
import { UI_TEXT, reasonCodeToKorean } from '../constants/uiText';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import { usePaperTrading } from '../hooks/usePaperTrading';
import { useToast } from '../hooks/useToast';
import type { ActionBarStatusItem, ConsoleSnapshot, PaperViewModel } from '../types/consoleView';
import { explainOrderFailureReason, formatCount, formatDateTime, formatKRW, formatLocalAmountWithKRW, formatNumber, formatPercent, formatSymbol, formatUSD } from '../utils/format';

interface PaperPortfolioPageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
}

interface PaperSettings {
  initialCashKrw: number;
  initialCashUsd: number;
  paperDays: number;
  runKospi: boolean;
  runNasdaq: boolean;
  maxPositions: number;
  dailyBuyLimit: number;
  dailySellLimit: number;
  maxOrdersPerSymbol: number;
  intervalSeconds: number;
}

const SETTINGS_KEY = 'console_paper_settings_v1';
const SETTINGS_META_KEY = 'console_paper_settings_meta_v1';

function defaultSettings(): PaperSettings {
  return {
    initialCashKrw: 10_000_000,
    initialCashUsd: 10_000,
    paperDays: 7,
    runKospi: true,
    runNasdaq: true,
    maxPositions: 5,
    dailyBuyLimit: 20,
    dailySellLimit: 20,
    maxOrdersPerSymbol: 3,
    intervalSeconds: 300,
  };
}

function readSettings(): PaperSettings {
  try {
    const raw = JSON.parse(localStorage.getItem(SETTINGS_KEY) || 'null') as Partial<PaperSettings> | null;
    if (!raw || typeof raw !== 'object') return defaultSettings();
    return {
      ...defaultSettings(),
      ...raw,
    };
  } catch {
    return defaultSettings();
  }
}

function saveSettings(settings: PaperSettings) {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  const savedAt = new Date().toISOString();
  localStorage.setItem(SETTINGS_META_KEY, JSON.stringify({ savedAt }));
  return savedAt;
}

function readSettingsSavedAt(): string {
  try {
    const raw = JSON.parse(localStorage.getItem(SETTINGS_META_KEY) || 'null') as { savedAt?: string } | null;
    return raw?.savedAt || '';
  } catch {
    return '';
  }
}

function toNumber(value: unknown, fallback = 0): number {
  if (value === null || value === undefined) return fallback;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function holdingDays(entryTs: unknown): number {
  if (!entryTs) return 0;
  const date = new Date(String(entryTs));
  if (Number.isNaN(date.getTime())) return 0;
  const ms = Date.now() - date.getTime();
  return Math.max(0, Math.floor(ms / (1000 * 60 * 60 * 24)));
}

function isToday(ts: unknown): boolean {
  if (!ts) return false;
  const value = new Date(String(ts));
  if (Number.isNaN(value.getTime())) return false;
  const now = new Date();
  return value.getFullYear() === now.getFullYear()
    && value.getMonth() === now.getMonth()
    && value.getDate() === now.getDate();
}

function engineStateLabel(raw: string | undefined, running: boolean): string {
  const state = String(raw || (running ? 'running' : 'stopped'));
  if (state === 'running') return UI_TEXT.status.running;
  if (state === 'paused') return UI_TEXT.status.paused;
  if (state === 'error') return UI_TEXT.status.error;
  return UI_TEXT.status.stopped;
}

function paperSkipReasonLabel(reason: string): string {
  if (reason === 'account_unavailable') return '계좌 스냅샷 없음 · sizing 계산 불가';
  if (reason === 'size_zero') return '권장 수량 0주';
  if (reason === 'exposure_or_cash_limit') return '현금/노출 한도로 권장 수량 0주';
  if (reason === 'daily_buy_limit_reached') return '일일 매수 한도 도달';
  if (reason === 'symbol_daily_limit_reached') return '종목별 주문 한도 도달';
  return explainOrderFailureReason(reason);
}

function marketCurrency(market: unknown): 'KRW' | 'USD' {
  const normalized = String(market || '').toUpperCase();
  if (normalized === 'NASDAQ' || normalized === 'NYSE' || normalized === 'AMEX' || normalized === 'US') {
    return 'USD';
  }
  return 'KRW';
}

function formatLocalPrice(value: number | null | undefined, market: unknown): string {
  if (marketCurrency(market) === 'USD') return formatUSD(value, true);
  return formatKRW(value, true);
}

function formatLocalPriceWithKrw(localValue: number | null | undefined, krwValue: number | null | undefined, market: unknown): string {
  return formatLocalAmountWithKRW(localValue, krwValue, marketCurrency(market));
}

function normalizePortfolioMarket(value: unknown): 'KOSPI' | 'NASDAQ' {
  return marketCurrency(value) === 'USD' ? 'NASDAQ' : 'KOSPI';
}

function formatMarketWithCurrency(market: unknown): string {
  const normalized = String(market || '-');
  return `${normalized} · ${marketCurrency(market)}`;
}

type HannaState = 'healthy' | 'degraded' | 'timeout' | 'research_unavailable';

function resolveHannaState(status: unknown, researchUnavailable: unknown): HannaState {
  if (Boolean(researchUnavailable)) return 'research_unavailable';
  if (String(status || '') === 'timeout') return 'timeout';
  if (String(status || '') === 'degraded') return 'degraded';
  if (String(status || '') === 'stale_ingest') return 'degraded';
  if (String(status || '') === 'research_unavailable') return 'research_unavailable';
  return 'healthy';
}

function resolveProviderHannaState(providerStatus: string | undefined, freshness: string | undefined): HannaState {
  if (providerStatus === 'healthy') return 'healthy';
  if (providerStatus === 'degraded' || providerStatus === 'stale_ingest') return 'degraded';
  if (providerStatus === 'missing' || freshness === 'missing') return 'research_unavailable';
  if (providerStatus === 'stale') return 'degraded';
  return 'healthy';
}

function resolveHannaStateWithProvider(status: unknown, researchUnavailable: unknown, providerStatus?: string, freshness?: string): HannaState {
  const candidateState = resolveHannaState(status, researchUnavailable);
  if (candidateState === 'research_unavailable') return 'research_unavailable';
  if (candidateState === 'healthy') return 'healthy';
  if (candidateState === 'timeout' || candidateState === 'degraded') return 'degraded';
  return resolveProviderHannaState(providerStatus, freshness);
}

function hannaBadgeClass(state: HannaState) {
  if (state === 'healthy') return 'inline-badge is-success';
  if (state === 'timeout' || state === 'degraded') return 'inline-badge is-danger';
  return 'inline-badge';
}

function layerCResearchGrade(source: Record<string, unknown> | null | undefined): string {
  const validation = source?.validation;
  if (!validation || typeof validation !== 'object') return '-';
  return String((validation as { grade?: string }).grade || '').toUpperCase() || '-';
}

function layerCResearchFreshness(source: Record<string, unknown> | null | undefined): string {
  const direct = source?.freshness;
  if (typeof direct === 'string' && direct) return direct.toLowerCase();
  const detail = source?.freshness_detail;
  if (detail && typeof detail === 'object') {
    return String((detail as { status?: string }).status || '').toLowerCase() || 'missing';
  }
  return 'missing';
}

function layerCResearchScoreDisplay(source: Record<string, unknown> | null | undefined): string {
  if (layerCResearchGrade(source) === 'D') return '—';
  const raw = source?.research_score;
  const numeric = Number(raw);
  return Number.isFinite(numeric) ? formatNumber(numeric, 2) : '-';
}

function layerCResearchBadgeClass(kind: 'freshness' | 'grade', value: string): string {
  if (kind === 'freshness') {
    if (value === 'fresh') return 'inline-badge is-success';
    if (value === 'stale' || value === 'invalid') return 'inline-badge is-danger';
    return 'inline-badge';
  }
  if (value === 'A') return 'inline-badge is-success';
  if (value === 'C' || value === 'D') return 'inline-badge is-danger';
  return 'inline-badge';
}

function hannaTone(state: HannaState): 'neutral' | 'good' | 'bad' {
  if (state === 'healthy') return 'good';
  if (state === 'timeout' || state === 'degraded') return 'bad';
  return 'neutral';
}

function reasonCountRows(counts: Record<string, unknown> | undefined, maxItems = 5, translator: (reason: string) => string = (reason) => reason) {
  const rows: Array<{ reason: string; label: string; count: number }> = [];
  if (!counts || typeof counts !== 'object') return rows;
  for (const [reason, countValue] of Object.entries(counts)) {
    const numericCount = Number(countValue);
    if (!Number.isFinite(numericCount)) continue;
    const normalizedReason = String(reason || '').trim();
    if (!normalizedReason) continue;
    rows.push({ reason: normalizedReason, label: translator(normalizedReason) || normalizedReason, count: numericCount });
  }
  return rows.sort((left, right) => right.count - left.count).slice(0, maxItems);
}

function orderFailureSummaryLabel(failure: {
  latest_failure_reason?: string;
  top_reason?: string;
  top_reason_count?: number;
}) {
  const latestReason = String(failure?.latest_failure_reason || '').trim();
  const topReason = String(failure?.top_reason || '').trim();
  if (latestReason && topReason) {
    return `${reasonCodeToKorean(topReason)} (${failure.top_reason_count || 0}건), 최근 ${reasonCodeToKorean(latestReason)}`;
  }
  if (latestReason) {
    return reasonCodeToKorean(latestReason);
  }
  if (topReason) {
    return `${reasonCodeToKorean(topReason)} (${failure.top_reason_count || 0}건)`;
  }
  return '-';
}

function parseRecordTime(value: unknown): number {
  if (!value) return 0;
  const date = new Date(String(value));
  const timestamp = date.getTime();
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function orderHasExecutedAction(order: Record<string, unknown>, symbolCode: string, market: string, sinceMs: number): boolean {
  const normalizedCode = String(symbolCode || '').trim().toUpperCase();
  const normalizedMarket = String(market || '').trim().toUpperCase();
  const orderType = String(order.order_type || '').toLowerCase();
  const code = String(order.code || '').trim().toUpperCase();
  const orderMarket = String(order.market || '').trim().toUpperCase();
  const success = order.success;
  const failureReason = String(order.reason_code || order.failure_reason || '').trim();

  if (!success) return false;
  if (!code || code !== normalizedCode) return false;
  if (normalizedMarket && orderMarket && orderMarket !== normalizedMarket) return false;
  if (orderType === 'screened' || orderType === 'screen') return false;
  if (failureReason && failureReason.toLowerCase() !== 'none' && failureReason.toLowerCase() !== 'ok') return false;

  const submittedAt = parseRecordTime(order.submitted_at);
  const filledAt = parseRecordTime(order.filled_at);
  const ts = parseRecordTime(order.ts);
  const timestamp = parseRecordTime(order.timestamp);
  const eventTime = Math.max(submittedAt, filledAt, ts, timestamp);
  if (!eventTime || eventTime < sinceMs) return false;
  if (eventTime > Date.now() + 20 * 60 * 1000) return false;
  const maxGapMs = 12 * 60 * 60 * 1000;
  if (eventTime - sinceMs > maxGapMs) return false;
  return true;
}

function workflowStageBucket(stage: unknown): 'discover' | 'signal' | 'decision' | 'order' {
  const value = String(stage || '').toLowerCase();
  if (value === 'watch' || value === 'blocked') return 'discover';
  if (value === 'signal_generated') return 'signal';
  if (value === 'execution_decided' || value === 'order_ready') return 'decision';
  return 'order';
}

function workflowStageLabel(stage: unknown): string {
  const value = String(stage || '').toLowerCase();
  if (value === 'watch') return '탐색';
  if (value === 'blocked') return '탐색 차단';
  if (value === 'signal_generated') return '신호 생성';
  if (value === 'execution_decided') return '판단 완료';
  if (value === 'order_ready') return '주문 준비';
  if (value === 'order_sent') return '주문 전송';
  if (value === 'filled') return '체결';
  if (value === 'rejected') return '주문 거절';
  return value || '-';
}

function workflowStatusTone(status: unknown): 'good' | 'bad' | 'neutral' {
  const value = String(status || '').toLowerCase();
  if (['filled', 'submitted', 'ready_for_order'].includes(value)) return 'good';
  if (['rejected', 'risk_blocked', 'non_entry_signal', 'insufficient_cash', 'daily_buy_limit_reached', 'symbol_daily_limit_reached'].includes(value)) return 'bad';
  return 'neutral';
}

function workflowStatusLabel(status: unknown): string {
  const value = String(status || '').toLowerCase();
  if (!value) return '-';
  if (value === 'watch_only') return '관찰 전용';
  if (value === 'non_entry_signal') return '진입 신호 아님';
  if (value === 'risk_blocked') return '리스크 차단';
  if (value === 'ready_for_order') return '주문 가능';
  if (value === 'size_pending') return '수량 계산 대기';
  if (value === 'operator_review') return '운영자 검토';
  if (value === 'signal_detected') return '신호 감지';
  if (value === 'submitted') return '주문 전송됨';
  if (value === 'filled') return '체결 완료';
  if (value === 'exit_signal') return '청산 신호';
  return reasonCodeToKorean(value);
}

function riskDecisionLabel(value: string): string {
  return value === 'allowed' ? '허용' : value === 'blocked' ? '차단' : value || '-';
}

function riskMessageLabel(value: unknown): string {
  const normalized = String(value || '').trim();
  if (!normalized || normalized === '-') return '-';
  if (normalized === 'scan_only') return '비진입 신호라 주문 리스크 평가를 생략했습니다.';
  return reasonCodeToKorean(normalized);
}

function layerEventSnapshot<T extends Record<string, unknown>>(events: unknown, layer: string): T | undefined {
  if (!Array.isArray(events)) return undefined;
  const matched = events.find((event) => {
    if (!event || typeof event !== 'object') return false;
    return String((event as { layer?: string }).layer || '').toUpperCase() === layer.toUpperCase();
  }) as { snapshot?: T } | undefined;
  if (!matched?.snapshot || typeof matched.snapshot !== 'object') return undefined;
  return matched.snapshot;
}

export function PaperPortfolioPage({ snapshot, loading, errorMessage, onRefresh }: PaperPortfolioPageProps) {
  const { pushToast } = useToast();
  const { entries, push, clear } = useConsoleLogs();
  const [settings, setSettings] = useState<PaperSettings>(() => readSettings());
  const [savedSettings, setSavedSettings] = useState<PaperSettings>(() => readSettings());
  const [settingsSavedAt, setSettingsSavedAt] = useState(() => readSettingsSavedAt());
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [pendingAction, setPendingAction] = useState<
    'engine-toggle' | 'pause' | 'resume' | 'reset' | 'history-clear' | 'history-reset' | null
  >(null);
  const [workflowTab, setWorkflowTab] = useState<'all' | 'discover' | 'signal' | 'decision' | 'order'>('all');
  const [workflowSearch, setWorkflowSearch] = useState('');
  const [workflowOnlyBlocked, setWorkflowOnlyBlocked] = useState(false);
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);
  const [positionMarketView, setPositionMarketView] = useState<'ALL' | 'KOSPI' | 'NASDAQ'>('ALL');
  const {
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
    clearRuntimeLogs,
    reset,
    refreshEngineStatus,
    refreshRuntimeLogs,
    startEngine,
    stopEngine,
    pauseEngine,
    resumeEngine,
    clearHistory,
  } = usePaperTrading({ autoRefreshEnabled });

  const positions = account.positions || [];
  const positionMarketCounts = useMemo(() => {
    const counts = { ALL: positions.length, KOSPI: 0, NASDAQ: 0 };
    positions.forEach((position) => {
      counts[normalizePortfolioMarket(position.market)] += 1;
    });
    return counts;
  }, [positions]);
  const filteredPositions = useMemo(() => {
    if (positionMarketView === 'ALL') return positions;
    return positions.filter((position) => normalizePortfolioMarket(position.market) === positionMarketView);
  }, [positionMarketView, positions]);
  const riskGuardState = getRiskGuardState(snapshot);
  const riskGuardAllowed = isRiskEntryAllowed(snapshot);
  const deferredWorkflowSearch = useDeferredValue(workflowSearch);
  const orders = useMemo(
    () => [...(account.orders || [])].sort((a, b) => String(b.ts || '').localeCompare(String(a.ts || ''))),
    [account.orders],
  );
  const mergedOrderHistory = useMemo(
    () => orderEvents
      .slice(0, 80)
      .sort((a, b) => String((b as { timestamp?: string; ts?: string }).timestamp || (b as { ts?: string }).ts || '')
        .localeCompare(String((a as { timestamp?: string; ts?: string }).timestamp || (a as { ts?: string }).ts || ''))),
    [orderEvents],
  );
  const currentHannaState = useMemo<HannaState>(() => {
    const states = (snapshot.signals.signals || []).map((signal) => resolveHannaStateWithProvider(
      signal.research_status,
      signal.research_unavailable,
      snapshot.research.status,
      snapshot.research.freshness,
    ));
    if (states.includes('timeout')) return 'timeout';
    if (states.includes('degraded')) return 'degraded';
    if (states.includes('healthy')) return 'healthy';
    return resolveProviderHannaState(snapshot.research.status, snapshot.research.freshness);
  }, [snapshot.research.freshness, snapshot.research.status, snapshot.signals.signals]);
  const signalRiskActionLogs = useMemo(() => {
    return [...signalSnapshots]
      .sort((left, right) => String((right as { timestamp?: string; logged_at?: string }).timestamp || (right as { logged_at?: string }).logged_at || '')
        .localeCompare(String((left as { timestamp?: string; logged_at?: string }).timestamp || (left as { logged_at?: string }).logged_at || '')))
      .slice(0, 14)
      .map((row) => {
        const item = row as {
          timestamp?: string;
          logged_at?: string;
          code?: string;
          name?: string;
          market?: string;
          strategy_name?: string;
          strategy_id?: string;
          research_status?: string;
          research_unavailable?: boolean;
          reason_codes?: string[];
          final_action?: string;
          entry_allowed?: boolean;
          risk_check?: { reason_code?: string; message?: string };
          risk_reason_code?: string;
          risk_message?: string;
          layer_d?: {
            allowed?: boolean;
            blocked?: boolean;
            reason_codes?: string[];
            liquidity_state?: string;
          };
          final_action_snapshot?: {
            decision_reason?: string;
            final_action?: string;
          };
          layer_events?: Array<{
            layer?: string;
            snapshot?: Record<string, unknown>;
          }>;
        };
        const layerCSnapshot = layerEventSnapshot<Record<string, unknown>>(item.layer_events, 'C');
        const layerDSnapshot = item.layer_d || layerEventSnapshot<{
          allowed?: boolean;
          blocked?: boolean;
          reason_codes?: string[];
          liquidity_state?: string;
        }>(item.layer_events, 'D');
        const layerESnapshot = item.final_action_snapshot || layerEventSnapshot<{
          decision_reason?: string;
          final_action?: string;
        }>(item.layer_events, 'E');
        const hannaState = resolveHannaStateWithProvider(
          item.research_status,
          item.research_unavailable,
          snapshot.research.status,
          snapshot.research.freshness,
        );
        const rawReasonCodes = Array.isArray(item.reason_codes) ? item.reason_codes.map((code) => String(code)) : [];
        const layerDAllowed = layerDSnapshot?.allowed === true || layerDSnapshot?.blocked === false;
        const layerDBlocked = layerDSnapshot?.blocked === true || layerDSnapshot?.allowed === false;
        const riskDecision = layerDAllowed ? 'allowed' : layerDBlocked ? 'blocked' : (item.entry_allowed ? 'allowed' : 'blocked');
        const riskReasonCode = String(
          item.risk_reason_code
          || layerDSnapshot?.reason_codes?.[0]
          || item.risk_check?.reason_code
          || '-',
        );
        const riskMessage = String(
          item.risk_message
          || layerESnapshot?.decision_reason
          || layerDSnapshot?.liquidity_state
          || item.risk_check?.message
          || '-',
        );
        const symbolCode = String(item.code || '').trim().toUpperCase();
        const symbolName = String(item.name || '').trim();
        return {
          key: `${item.timestamp || item.logged_at || 'time'}:${item.market || 'market'}:${item.code || 'code'}`,
          timestamp: String(item.timestamp || item.logged_at || ''),
          symbolCode,
          symbolName,
          strategy: String(item.strategy_name || item.strategy_id || '-'),
          market: String(item.market || '-'),
          hannaState,
          riskDecision,
          riskReasonCode,
          riskMessage,
          researchFreshness: layerCResearchFreshness(layerCSnapshot),
          researchGrade: layerCResearchGrade(layerCSnapshot),
          researchScore: layerCResearchScoreDisplay(layerCSnapshot),
          researchReason: String(((layerCSnapshot?.validation as { reason?: string } | undefined)?.reason) || ''),
          researchExclusionReason: String(((layerCSnapshot?.validation as { exclusion_reason?: string } | undefined)?.exclusion_reason) || ''),
          finalAction: String(item.final_action || layerESnapshot?.final_action || '-'),
          translatedReasons: rawReasonCodes.map((code) => reasonCodeToKorean(code)),
          rawReasons: rawReasonCodes,
        };
      });
  }, [signalSnapshots]);
  const readinessSignals = useMemo(() => {
    const cutoffMs = Date.now() - (14 * 24 * 60 * 60 * 1000);
    return signalRiskActionLogs
      .filter((item) => item.riskDecision === 'allowed' && item.finalAction === 'review_for_entry' && !!item.symbolCode)
      .map((item) => {
        const signalTs = parseRecordTime(item.timestamp);
        return {
          ...item,
          hasOrder: signalTs > 0 && signalTs >= cutoffMs
            ? mergedOrderHistory.some((order) => orderHasExecutedAction(order as Record<string, unknown>, item.symbolCode, item.market, signalTs))
            : false,
        };
      })
      .slice(0, 8);
  }, [mergedOrderHistory, signalRiskActionLogs]);
  const readinessSignalGapCount = readinessSignals.filter((item) => !item.hasOrder).length;
  const riskGuardBlockCount = signalRiskActionLogs.filter((item) => item.riskDecision === 'blocked').length;
  const readinessSignalCount = readinessSignals.length;
  const riskActionCheck = useMemo(() => {
    if (signalRiskActionLogs.length === 0) {
      return {
        tone: 'neutral' as const,
        title: '아직 판별 로그 없음',
        detail: 'Risk/Action 로그가 쌓이지 않았습니다. 엔진을 1회 실행하고 시계열을 갱신하세요.',
        steps: [
          'Layer B 신호 수집 → Layer D risk 판단 → Layer E final action',
          '모든 단계가 비어 있으면 이번 사이클이 생성되지 않은 상태입니다.',
        ],
      };
    }
    if (readinessSignalCount > 0 && readinessSignalGapCount > 0) {
      return {
        tone: 'bad' as const,
        title: '주문으로 안 넘어가는 후보가 있습니다',
        detail: `진입 허용 + review_for_entry가 ${formatCount(readinessSignalCount, '건')}건 있었지만, 최근 주문 이벤트로 이어진 건이 ${formatCount(readinessSignalGapCount, '건')}건입니다.`,
        steps: [
          `대상 후보: ${readinessSignals.filter((item) => !item.hasOrder).map((item) => `${item.symbolCode}(${item.market})`).slice(0, 3).join(', ') || '-'}`,
          'Layer D에서 허용이 났는데도 주문 이벤트가 없다면 실시간 주문 채널/사이클 실행 상태를 확인하세요.',
        ],
      };
    }
    if (riskGuardBlockCount > 0) {
      return {
        tone: 'bad' as const,
        title: '리스크 가드가 주 원인으로 보입니다',
        detail: `Risk/Action에서 차단은 ${formatCount(riskGuardBlockCount, '건')}건입니다.`,
        steps: [
          '실제 Layer D가 차단이면 주문이 들어오지 않는 것이 정상입니다.',
          '차단 사유는 reason code와 risk_message에 적혀 있습니다.',
        ],
      };
    }
    return {
      tone: 'good' as const,
      title: '리스크/액션 경로는 주문 허용 상태',
      detail: '최근 후보가 review_for_entry 또는 allowed 상태이면 주문 이벤트가 만들어져야 합니다.',
      steps: [
        '최근 주문 실패가 계속 난다면 엔진 실행 중단/브로커 에러/잔고 상태를 점검하세요.',
        '워크플로우 단계에서 order_ready → order_sent로 넘어가는지 확인하세요.',
      ],
    };
  }, [readinessSignalCount, readinessSignalGapCount, riskGuardBlockCount, signalRiskActionLogs.length]);

  const effectiveWorkflowSummary = workflowSummary?.items?.length ? workflowSummary : engineState.workflow_summary || { counts: {}, items: [], count: 0 };
  const workflowItems = useMemo(() => {
    const items = Array.isArray(effectiveWorkflowSummary.items) ? effectiveWorkflowSummary.items : [];
    return [...items]
      .sort((left, right) => String(right.last_order_at || right.fetched_at || right.timestamp || right.logged_at || '')
        .localeCompare(String(left.last_order_at || left.fetched_at || left.timestamp || left.logged_at || '')));
  }, [effectiveWorkflowSummary]);
  const workflowCounts = useMemo(() => {
    const counts = effectiveWorkflowSummary.counts || {};
    return {
      discover: Number(counts.watch || 0) + Number(counts.blocked || 0),
      signal: Number(counts.signal_generated || 0),
      decision: Number(counts.execution_decided || 0) + Number(counts.order_ready || 0),
      order: Number(counts.order_sent || 0) + Number(counts.filled || 0) + Number(counts.rejected || 0),
      ready: Number(counts.order_ready || 0),
      filled: Number(counts.filled || 0),
      rejected: Number(counts.rejected || 0),
    };
  }, [effectiveWorkflowSummary]);
  const workflowBlockedItems = useMemo(() => workflowItems.filter((item) => {
    const status = String(item.execution_status || '').toLowerCase();
    return workflowStageBucket(item.workflow_stage) === 'discover' || workflowStatusTone(status) === 'bad';
  }), [workflowItems]);
  const workflowBlockedReasonSummary = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of workflowBlockedItems) {
      const key = String(item.blocked_reason || item.last_order_reason || item.execution_status || 'unknown');
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    return [...counts.entries()]
      .sort((left, right) => right[1] - left[1])
      .slice(0, 5)
      .map(([reason, count]) => ({
        reason,
        label: reasonCodeToKorean(reason),
        count,
      }));
  }, [workflowBlockedItems]);
  const visibleWorkflowItems = useMemo(() => {
    const keyword = deferredWorkflowSearch.trim().toLowerCase();
    const filtered = workflowItems.filter((item) => {
      if (workflowTab !== 'all' && workflowStageBucket(item.workflow_stage) !== workflowTab) return false;
      if (workflowOnlyBlocked) {
        const status = String(item.execution_status || '').toLowerCase();
        if (!(workflowStageBucket(item.workflow_stage) === 'discover' || workflowStatusTone(status) === 'bad')) return false;
      }
      if (!keyword) return true;
      return [item.code, item.name, item.market, item.strategy_name, item.strategy_id, item.execution_status, item.blocked_reason, item.last_order_reason, item.final_action]
        .map((value) => String(value || '').toLowerCase())
        .join(' ')
        .includes(keyword);
    });
    return filtered.slice(0, 16);
  }, [deferredWorkflowSearch, workflowItems, workflowOnlyBlocked, workflowTab]);

  const vm = useMemo<PaperViewModel>(() => {
    const unrealized = positions.reduce((sum, item) => sum + toNumber(item.unrealized_pnl_krw), 0);
    return {
      totalEquityKrw: toNumber(account.equity_krw),
      cashKrw: toNumber(account.cash_krw),
      cashUsd: toNumber(account.cash_usd),
      unrealizedPnlKrw: unrealized,
      realizedPnlKrw: toNumber(account.realized_pnl_krw),
      positionCount: positions.length,
    };
  }, [account.cash_krw, account.cash_usd, account.equity_krw, account.realized_pnl_krw, positions]);

  const todayOrderStats = useMemo(() => {
    const todayOrders = orders.filter((order) => isToday(order.ts));
    let todayBuyCount = 0;
    let todaySellCount = 0;
    for (const order of todayOrders) {
      if (order.side === 'buy') {
        todayBuyCount += 1;
      } else if (order.side === 'sell') {
        todaySellCount += 1;
      }
    }
    return { todayOrders, todayBuyCount, todaySellCount };
  }, [orders]);
  const { todayOrders, todayBuyCount, todaySellCount } = todayOrderStats;
  const settingsDirty = useMemo(() => JSON.stringify(settings) !== JSON.stringify(savedSettings), [savedSettings, settings]);

  const statusItems = useMemo<ActionBarStatusItem[]>(() => ([
    {
      label: '엔진 상태',
      value: engineStateLabel(engineState.engine_state, engineState.running),
      tone: engineState.engine_state === 'error' ? 'bad' : engineState.running ? 'good' : 'neutral',
    },
    {
      label: '리스크 가드',
      value: riskGuardAllowed ? UI_TEXT.status.active : UI_TEXT.status.inactive,
      tone: riskGuardAllowed ? 'good' : 'bad',
    },
    {
      label: '계좌 상태',
      value: status === 'error' ? '오류' : status === 'loading' ? '로딩' : '정상',
      tone: status === 'error' ? 'bad' : status === 'loading' ? 'neutral' : 'good',
    },
    {
      label: '보유 포지션',
      value: `${vm.positionCount}건`,
      tone: 'neutral',
    },
    {
      label: 'Hanna',
      value: currentHannaState,
      tone: hannaTone(currentHannaState),
    },
  ]), [currentHannaState, engineState.engine_state, engineState.running, riskGuardAllowed, status, vm.positionCount]);

  const handleRefreshAll = useCallback(async () => {
    onRefresh();
    await Promise.all([refresh(true), refreshEngineStatus(), refreshRuntimeLogs()]);
    push('info', '모의투자 데이터와 콘솔 스냅샷을 새로고침했습니다.', undefined, 'paper');
    pushToast({
      tone: 'info',
      title: '모의투자 화면을 새로고침했습니다.',
      description: '계좌, 엔진 상태, 런타임 로그를 다시 불러왔습니다.',
    });
  }, [onRefresh, push, pushToast, refresh, refreshEngineStatus, refreshRuntimeLogs]);

  const handleStartStop = useCallback(async () => {
    if (pendingAction) return;
    setPendingAction('engine-toggle');
    try {
      if (engineState.running || engineState.engine_state === 'paused') {
        const result = await stopEngine();
        if (!result.ok) {
          push('error', '모의투자 엔진 중지에 실패했습니다.', result.error || '', 'paper');
          pushToast({
            tone: 'error',
            title: '엔진 중지 실패',
            description: result.error || '엔진 상태와 서버 로그를 확인해 주세요.',
          });
          return;
        }
        push('success', '모의투자 엔진을 중지했습니다.', undefined, 'paper');
        pushToast({
          tone: 'success',
          title: '엔진 중지 완료',
          description: '신규 평가와 자동 실행이 멈췄습니다.',
        });
      } else {
        const markets: Array<'KOSPI' | 'NASDAQ'> = [];
        if (settings.runKospi) markets.push('KOSPI');
        if (settings.runNasdaq) markets.push('NASDAQ');
        if (markets.length === 0) {
          push('warning', '시장 선택이 필요합니다.', '설정에서 KOSPI 또는 NASDAQ을 최소 1개 선택하세요.', 'paper');
          pushToast({
            tone: 'warning',
            title: '시장 선택 필요',
            description: 'KOSPI 또는 NASDAQ을 최소 1개 선택해야 엔진을 시작할 수 있습니다.',
          });
          return;
        }
        const result = await startEngine({
          interval_seconds: settings.intervalSeconds,
          markets,
          max_positions_per_market: settings.maxPositions,
          daily_buy_limit: settings.dailyBuyLimit,
          daily_sell_limit: settings.dailySellLimit,
          max_orders_per_symbol_per_day: settings.maxOrdersPerSymbol,
        });
        if (!result.ok) {
          push('error', '모의투자 엔진 시작에 실패했습니다.', result.error || '', 'paper');
          pushToast({
            tone: 'error',
            title: '엔진 시작 실패',
            description: result.error || '설정값과 백엔드 상태를 확인해 주세요.',
          });
          return;
        }
        push('success', '모의투자 엔진을 시작했습니다.', `시장: ${markets.join(', ')}`, 'paper');
        pushToast({
          tone: 'success',
          title: '엔진 시작 완료',
          description: `시장 ${markets.join(', ')} 기준으로 자동 실행을 시작했습니다.`,
        });
      }
      await Promise.all([refresh(true), refreshEngineStatus(), refreshRuntimeLogs()]);
    } finally {
      setPendingAction(null);
    }
  }, [
    engineState.engine_state,
    engineState.running,
    push,
    refresh,
    refreshEngineStatus,
    settings.dailyBuyLimit,
    settings.dailySellLimit,
    settings.intervalSeconds,
    settings.maxOrdersPerSymbol,
    settings.maxPositions,
    settings.runKospi,
    settings.runNasdaq,
    refreshRuntimeLogs,
    startEngine,
    stopEngine,
  ]);

  const handlePause = useCallback(async () => {
    if (pendingAction) return;
    setPendingAction('pause');
    const result = await pauseEngine();
    try {
      if (!result.ok) {
        push('error', '모의투자 엔진 일시정지에 실패했습니다.', result.error || '', 'paper');
        pushToast({
          tone: 'error',
          title: '엔진 일시정지 실패',
          description: result.error || '현재 엔진 상태를 다시 확인해 주세요.',
        });
        return;
      }
      await Promise.all([refreshEngineStatus(), refreshRuntimeLogs()]);
      push('success', '모의투자 엔진을 일시정지했습니다.', undefined, 'paper');
      pushToast({
        tone: 'success',
        title: '엔진 일시정지',
        description: '현재 포지션은 유지되고 신규 자동 실행만 멈춥니다.',
      });
    } finally {
      setPendingAction(null);
    }
  }, [pauseEngine, pendingAction, push, pushToast, refreshEngineStatus, refreshRuntimeLogs]);

  const handleResume = useCallback(async () => {
    if (pendingAction) return;
    setPendingAction('resume');
    const result = await resumeEngine();
    try {
      if (!result.ok) {
        push('error', '모의투자 엔진 재개에 실패했습니다.', result.error || '', 'paper');
        pushToast({
          tone: 'error',
          title: '엔진 재개 실패',
          description: result.error || '엔진 상태와 시장 선택을 다시 확인해 주세요.',
        });
        return;
      }
      await Promise.all([refreshEngineStatus(), refreshRuntimeLogs()]);
      push('success', '모의투자 엔진을 재개했습니다.', undefined, 'paper');
      pushToast({
        tone: 'success',
        title: '엔진 재개 완료',
        description: '자동 실행 루프를 다시 시작했습니다.',
      });
    } finally {
      setPendingAction(null);
    }
  }, [pendingAction, push, pushToast, refreshEngineStatus, refreshRuntimeLogs, resumeEngine]);

  const handleReset = useCallback(async () => {
    if (pendingAction) return;
    setPendingAction('reset');
    try {
      const result = await reset({
        initial_cash_krw: settings.initialCashKrw,
        initial_cash_usd: settings.initialCashUsd,
        paper_days: settings.paperDays,
      });
      if (!result.ok) {
        push('error', '모의투자 초기화에 실패했습니다.', result.error || '', 'paper');
        pushToast({
          tone: 'error',
          title: '모의투자 초기화 실패',
          description: result.error || '초기 자금과 엔진 상태를 다시 확인해 주세요.',
        });
        return;
      }
      push(
        'success',
        '모의투자 계좌를 초기화했습니다.',
        `초기자금 KRW ${formatKRW(settings.initialCashKrw, true)} / USD ${formatUSD(settings.initialCashUsd, true)}`,
        'paper',
      );
      pushToast({
        tone: 'success',
        title: '모의투자 초기화 완료',
        description: '계좌, 포지션, 로그 기준점이 새로 초기화되었습니다.',
      });
      await Promise.all([refresh(true), refreshEngineStatus(), refreshRuntimeLogs()]);
    } finally {
      setPendingAction(null);
    }
  }, [pendingAction, push, pushToast, refresh, refreshEngineStatus, refreshRuntimeLogs, reset, settings.initialCashKrw, settings.initialCashUsd, settings.paperDays]);

  const handleClearPaperHistory = useCallback(async () => {
    if (pendingAction) return;
    setPendingAction('history-clear');
    try {
      const result = await clearHistory({ clear_all: true });
      if (!result.ok) {
        push('error', '실행 로그 초기화에 실패했습니다.', result.error || '', 'paper');
        pushToast({
          tone: 'error',
          title: '실행 로그 초기화 실패',
          description: result.error || '최근 체결 내역 및 Risk/Action 로그 정리를 다시 시도해 주세요.',
        });
        return;
      }
      clearRuntimeLogs();
      clear();
      await refreshRuntimeLogs();
      push(
        'success',
        '실행 로그를 정리했습니다.',
        `삭제 건수: 주문 ${result.clear_count?.order_events || 0}건, Signal ${result.clear_count?.signal_snapshots || 0}건, 계좌 ${result.clear_count?.account_snapshots || 0}건, 엔진 ${result.clear_count?.engine_cycles || 0}건`,
        'paper',
      );
      pushToast({
        tone: 'success',
        title: '최근 로그 정리 완료',
        description: `주문/엔진/계좌/리스크 로그가 초기화되어 화면 목록이 초기화됩니다.`,
      });
    } finally {
      setPendingAction(null);
    }
  }, [clear, clearHistory, clearRuntimeLogs, pendingAction, push, pushToast, refreshRuntimeLogs]);

  const handleClearPaperHistoryAndReset = useCallback(async () => {
    if (pendingAction) return;
    setPendingAction('history-reset');
    try {
      const result = await clearHistory({
        clear_all: true,
        reset_account: true,
        initial_cash_krw: settings.initialCashKrw,
        initial_cash_usd: settings.initialCashUsd,
        paper_days: settings.paperDays,
      });
      if (!result.ok) {
        push('error', '완전 정리 실패', result.error || '', 'paper');
        pushToast({
          tone: 'error',
          title: '모의투자 완전 정리 실패',
          description: result.error || '계좌 초기화값 기반으로 로그 및 계좌 상태를 다시 설정하지 못했습니다.',
        });
        return;
      }
      clearRuntimeLogs();
      clear();
      await Promise.all([refresh(true), refreshEngineStatus(), refreshRuntimeLogs()]);
      push(
        'success',
        '로그와 계좌 상태를 완전히 정리했습니다.',
        `삭제 건수: 주문 ${result.clear_count?.order_events || 0}건, Signal ${result.clear_count?.signal_snapshots || 0}건, 계좌 ${result.clear_count?.account_snapshots || 0}건, 엔진 ${result.clear_count?.engine_cycles || 0}건`,
        'paper',
      );
      pushToast({
        tone: 'success',
        title: '완전 정리 완료',
        description: '초기 자금 기준으로 계좌가 초기화되고, 실행 로그 히스토리가 초기 상태로 재설정됩니다.',
      });
    } finally {
      setPendingAction(null);
    }
  }, [clear, clearHistory, clearRuntimeLogs, pendingAction, refresh, refreshEngineStatus, refreshRuntimeLogs, settings.initialCashKrw, settings.initialCashUsd, settings.paperDays, push, pushToast]);

  useEffect(() => {
    if (!autoRefreshEnabled) return;
    if (!(engineState.running || engineState.engine_state === 'paused')) return;
    const timer = window.setInterval(() => {
      void refreshRuntimeLogs();
    }, 10_000);
    return () => window.clearInterval(timer);
  }, [autoRefreshEnabled, engineState.engine_state, engineState.running, refreshRuntimeLogs]);

  const settingsPanel = (
    <div style={{ display: 'grid', gap: 12 }}>
      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>초기 원화 현금</span>
        <NumericInput
          value={settings.initialCashKrw}
          style={{ padding: '0 12px' }}
          onCommit={(value) => setSettings((prev) => ({ ...prev, initialCashKrw: Number(value ?? prev.initialCashKrw) }))}
        />
      </label>
      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>초기 달러 현금</span>
        <NumericInput
          value={settings.initialCashUsd}
          style={{ padding: '0 12px' }}
          onCommit={(value) => setSettings((prev) => ({ ...prev, initialCashUsd: Number(value ?? prev.initialCashUsd) }))}
        />
      </label>
      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>모의투자 기간(일)</span>
        <NumericInput
          value={settings.paperDays}
          min={1}
          style={{ padding: '0 12px' }}
          onCommit={(value) => setSettings((prev) => ({ ...prev, paperDays: Number(value ?? prev.paperDays) }))}
        />
      </label>
      <div style={{ display: 'grid', gap: 8, fontSize: 12 }}>
        <span style={{ color: 'var(--text-3)' }}>시장 선택</span>
        <label><input type="checkbox" checked={settings.runKospi} onChange={(event) => setSettings((prev) => ({ ...prev, runKospi: event.target.checked }))} /> KOSPI</label>
        <label><input type="checkbox" checked={settings.runNasdaq} onChange={(event) => setSettings((prev) => ({ ...prev, runNasdaq: event.target.checked }))} /> NASDAQ</label>
      </div>
      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>최대 포지션 수(건)</span>
        <NumericInput
          value={settings.maxPositions}
          min={1}
          style={{ padding: '0 12px' }}
          onCommit={(value) => setSettings((prev) => ({ ...prev, maxPositions: Number(value ?? prev.maxPositions) }))}
        />
      </label>
      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>일일 매수 제한(건)</span>
        <NumericInput
          value={settings.dailyBuyLimit}
          min={1}
          style={{ padding: '0 12px' }}
          onCommit={(value) => setSettings((prev) => ({ ...prev, dailyBuyLimit: Number(value ?? prev.dailyBuyLimit) }))}
        />
      </label>
      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>일일 매도 제한(건)</span>
        <NumericInput
          value={settings.dailySellLimit}
          min={1}
          style={{ padding: '0 12px' }}
          onCommit={(value) => setSettings((prev) => ({ ...prev, dailySellLimit: Number(value ?? prev.dailySellLimit) }))}
        />
      </label>
      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>종목당 일일 주문 제한(건)</span>
        <NumericInput
          value={settings.maxOrdersPerSymbol}
          min={1}
          style={{ padding: '0 12px' }}
          onCommit={(value) => setSettings((prev) => ({ ...prev, maxOrdersPerSymbol: Number(value ?? prev.maxOrdersPerSymbol) }))}
        />
      </label>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <button
          type="button"
          className="console-action-button"
          disabled={settingsSaving || !settingsDirty}
          onClick={() => setSettings(savedSettings)}
        >
          저장값으로 되돌리기
        </button>
        <button
          type="button"
          className="console-action-button"
          disabled={settingsSaving}
          onClick={() => setSettings(defaultSettings())}
        >
          기본값 불러오기
        </button>
      </div>
      <button
        className="console-action-button is-primary"
        disabled={settingsSaving}
        onClick={async () => {
          if (settingsSaving) return;
          setSettingsSaving(true);
          await new Promise((resolve) => window.setTimeout(resolve, 120));
          const savedAt = saveSettings(settings);
          setSavedSettings(settings);
          setSettingsSavedAt(savedAt);
          push('success', '모의투자 설정을 저장했습니다.', undefined, 'paper');
          pushToast({
            tone: 'success',
            title: '모의투자 설정 저장 완료',
            description: '저장 필요 배지가 사라지고 최신 설정이 기준값으로 반영되었습니다.',
          });
          setSettingsSaving(false);
        }}
      >
        {settingsSaving ? (
          <span className="button-content">
            <span className="button-spinner" aria-hidden="true" />
            저장 중...
          </span>
        ) : '설정 저장'}
      </button>
    </div>
  );

  const stopLossPctDefault = toNumber(engineState.config?.stop_loss_pct, NaN);
  const takeProfitPctDefault = toNumber(engineState.config?.take_profit_pct, NaN);
  const skipReasonCounts = engineState.last_summary?.skip_reason_counts || {};
  const orderFailureSummary = engineState.order_failure_summary || {};
  const blockedReasonRows = reasonCountRows(
    engineState.last_summary?.blocked_reason_counts,
    6,
    reasonCodeToKorean,
  );
  const skipReasonRows = reasonCountRows(
    skipReasonCounts,
    6,
    reasonCodeToKorean,
  );
  const riskGuardReasons = Array.isArray(riskGuardState?.reasons)
    ? riskGuardState.reasons.map((item) => String(item)).filter(Boolean)
    : [];
  const riskGuardReasonRows = reasonCountRows(
    riskGuardReasons.reduce<Record<string, number>>((acc, reason) => {
      const normalized = String(reason || '').trim();
      if (!normalized) return acc;
      acc[normalized] = (acc[normalized] || 0) + 1;
      return acc;
    }, {}),
    6,
    reasonCodeToKorean,
  );
  const latestScreenedFailure = useMemo(() => {
    for (const rawOrder of mergedOrderHistory) {
      const item = rawOrder as { success?: boolean; order_type?: string };
      if (item.order_type && String(item.order_type).toLowerCase() === 'screened' && item.success === false) {
        return rawOrder;
      }
    }
    return null;
  }, [mergedOrderHistory]);
  const latestFailureOrder = useMemo(() => {
    for (const rawOrder of mergedOrderHistory) {
      const item = rawOrder as { success?: boolean };
      if (item.success === false) {
        return rawOrder;
      }
    }
    return null;
  }, [mergedOrderHistory]);
  const validationFailureHint = orderFailureSummaryLabel(orderFailureSummary as {
    latest_failure_reason?: string;
    top_reason?: string;
    top_reason_count?: number;
  });
  const repeatedCashRetries = orderFailureSummary.repeated_insufficient_cash || [];
  const entryAllowed = riskGuardAllowed;
  const todayFailCount = Number(engineState.today_order_counts?.failed || 0);
  const todayInsufficientCashFailCount = Number(orderFailureSummary.insufficient_cash_failed || 0);
  const trustScore = useMemo(() => {
    let score = 100;
    if (!engineState.running) score -= 25;
    if (engineState.engine_state === 'paused') score -= 20;
    if (engineState.last_error) score -= 25;
    score -= Math.min(30, Number(engineState.today_order_counts?.failed || 0) * 6);
    if (!entryAllowed) score -= 15;
    return Math.max(10, score);
  }, [engineState.engine_state, engineState.last_error, engineState.running, engineState.today_order_counts?.failed, entryAllowed]);

  const trustState = trustScore >= 80 ? '높음' : trustScore >= 55 ? '보통' : '낮음';
  const trustTone: 'good' | 'bad' | 'neutral' = trustState === '높음' ? 'good' : trustState === '낮음' ? 'bad' : 'neutral';
  const riskyPositions = useMemo(() => {
    return filteredPositions
      .map((position) => {
        const positionRaw = position as unknown as Record<string, unknown>;
        const entryPrice = toNumber(position.avg_price_local, 0);
        const currentPrice = toNumber(position.last_price_local, 0);
        const pnlPct = toNumber(position.unrealized_pnl_pct, NaN);
        const daysHeld = holdingDays(position.entry_ts);
        const stopLossPct = toNumber(positionRaw.stop_loss_pct, stopLossPctDefault);
        const stopLossPrice = Number.isFinite(stopLossPct) ? entryPrice * (1 - stopLossPct / 100) : NaN;
        const nearStopLoss = Number.isFinite(stopLossPrice) && currentPrice > 0 && currentPrice <= stopLossPrice * 1.02;
        const deepLoss = Number.isFinite(pnlPct) && pnlPct <= -4;
        const longHoldWeak = daysHeld >= 10 && Number.isFinite(pnlPct) && pnlPct < 0;
        const urgency = (nearStopLoss ? 3 : 0) + (deepLoss ? 2 : 0) + (longHoldWeak ? 1 : 0);
        return { position, nearStopLoss, deepLoss, longHoldWeak, urgency, pnlPct, daysHeld };
      })
      .filter((item) => item.urgency > 0)
      .sort((a, b) => b.urgency - a.urgency)
      .slice(0, 6);
  }, [filteredPositions, stopLossPctDefault]);

  const scrollToSection = useCallback((sectionId: string) => {
    document.getElementById(sectionId)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, []);

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell console-page-shell paper-ops-shell" style={{ display: 'grid', gap: 16 }}>
          <ConsoleActionBar
            title="주문/리스크"
            subtitle="계좌, 포지션, 주문 이력, 리스크 거절 사유를 한 화면에서 확인합니다. 신호가 있었는데 왜 주문이 없었는지 이 화면에서 바로 추적합니다."
            lastUpdated={snapshot.fetchedAt}
            loading={loading}
            errorMessage={errorMessage || lastError}
            statusItems={statusItems}
            onRefresh={handleRefreshAll}
            logs={entries}
            onClearLogs={clear}
            settingsDirty={settingsDirty}
            settingsSavedAt={settingsSavedAt}
            actions={[
              {
                label: '엔진 시작',
                onClick: () => { if (!engineState.running) { void handleStartStop(); } },
                tone: 'primary',
                disabled: engineState.running,
                busy: pendingAction === 'engine-toggle' && !engineState.running,
                busyLabel: '시작 중...',
                confirmTitle: UI_TEXT.confirm.startEngineTitle,
                confirmMessage: UI_TEXT.confirm.startEngineMessage,
              },
              {
                label: '일시정지',
                onClick: () => { void handlePause(); },
                tone: 'default',
                disabled: !engineState.running,
                busy: pendingAction === 'pause',
                busyLabel: '일시정지 중...',
              },
              {
                label: '재개',
                onClick: () => { void handleResume(); },
                tone: 'default',
                disabled: engineState.running || engineState.engine_state !== 'paused',
                busy: pendingAction === 'resume',
                busyLabel: '재개 중...',
              },
              {
                label: '엔진 중지',
                onClick: () => { if (engineState.running || engineState.engine_state === 'paused') { void handleStartStop(); } },
                tone: 'danger',
                disabled: !(engineState.running || engineState.engine_state === 'paused'),
                busy: pendingAction === 'engine-toggle' && (engineState.running || engineState.engine_state === 'paused'),
                busyLabel: '중지 중...',
                confirmTitle: UI_TEXT.confirm.stopEngineTitle,
                confirmMessage: UI_TEXT.confirm.stopEngineMessage,
              },
              {
                label: '강제 새로고침',
                onClick: () => { void handleRefreshAll(); },
                tone: 'default',
              },
              {
                label: '실행 로그 전부 삭제',
                onClick: () => { void handleClearPaperHistory(); },
                tone: 'danger',
                busy: pendingAction === 'history-clear',
                busyLabel: '삭제 중...',
                confirmTitle: '실행 로그를 삭제할까요?',
                confirmMessage: '최근 체결 내역/리스크-액션 로그/엔진 로그를 제거합니다.',
                confirmDetails: [
                  '삭제 대상: 주문 이벤트, signal snapshot, 계좌 스냅샷, 엔진 사이클 로그',
                  '삭제 대상: 최근 체결 내역, 엔진 사이클, Risk/Action 표시 데이터',
                  '이 작업은 되돌릴 수 없습니다.',
                ],
              },
              {
                label: '모의투자 초기화',
                onClick: () => { void handleReset(); },
                tone: 'danger',
                busy: pendingAction === 'reset',
                busyLabel: '초기화 중...',
                confirmTitle: UI_TEXT.confirm.resetPaperTitle,
                confirmMessage: UI_TEXT.confirm.resetPaperMessage,
                confirmDetails: ['계좌, 포지션, 주문/사이클 기준 데이터가 새 초기 자금으로 다시 설정됩니다.', '이 작업은 되돌릴 수 없습니다.'],
              },
              {
                label: '계좌/엔진 히스토리 완전 정리',
                onClick: () => { void handleClearPaperHistoryAndReset(); },
                tone: 'danger',
                busy: pendingAction === 'history-reset',
                busyLabel: '완전 정리 중...',
                confirmTitle: '로그/히스토리를 완전히 정리할까요?',
                confirmMessage: '로그, 계좌 스냅샷, 엔진 실행 이력까지 초기 상태로 되돌립니다.',
                confirmDetails: [
                  '삭제 대상: 주문 이벤트, signal snapshot, 계좌 스냅샷, 엔진 사이클 로그',
                  '계좌/포지션/현금은 화면 설정의 초기 자금 기준으로 초기화됩니다.',
                  '이 작업은 되돌릴 수 없습니다.',
                ],
              },
            ]}
            settingsPanel={settingsPanel}
          />

          <div className="page-section validation-decision-hero console-hero-section" style={{ padding: 18 }}>
            <div className="report-hero-topline">
              <span className="report-hero-tag">Risk First</span>
              <span className={`report-decision-chip ${entryAllowed ? 'is-good' : 'is-bad'}`}>신규 진입 {entryAllowed ? '가능' : '차단'}</span>
            </div>
            <div className="report-decision-title">운용 우선순위: {riskyPositions.length > 0 || todayFailCount > 0 ? '리스크 정리 먼저' : '정상 운영 지속'}</div>
            <div className="report-hero-copy">지금 필요한 순서만 짧게 보이도록 정리했어. 보유 포지션 확인 → 실행 워크플로우 확인 → Risk/Action 로그 확인 순서로 보면 어디서 막혔는지 훨씬 빨리 찾을 수 있어.</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
              <button type="button" className="ghost-button" onClick={() => scrollToSection('paper-positions-section')}>보유 포지션으로</button>
              <button type="button" className="ghost-button" onClick={() => scrollToSection('paper-workflow-section')}>실행 워크플로우로</button>
              <button type="button" className="ghost-button" onClick={() => scrollToSection('paper-risk-action-section')}>Risk / Action 로그로</button>
              <button type="button" className="ghost-button" onClick={() => scrollToSection('paper-engine-panel-section')}>엔진 상태로</button>
            </div>
            {repeatedCashRetries.length > 0 && (
              <div className="inline-warning-card" style={{ marginTop: 12 }}>
                <div><strong>반복 현금 부족 실패 감지</strong></div>
                <div>오늘 현금 부족 실패 {formatCount(todayInsufficientCashFailCount, '건')} · 같은 종목 재시도 {formatCount(repeatedCashRetries.length, '건')}</div>
                {repeatedCashRetries.slice(0, 3).map((item) => (
                  <div key={`${item.market || '-'}:${item.code || '-'}`}>
                    {formatSymbol(String(item.code || ''), '')} {String(item.market || '-')} · {formatCount(item.count, '회')} · 마지막 {formatDateTime(String(item.last_at || ''))}
                  </div>
                ))}
              </div>
            )}
            <div className="validation-decision-grid">
              <div className={`summary-metric-card ${riskyPositions.length > 0 ? 'is-bad' : 'is-good'}`}>
                <div className="summary-metric-label">위험 포지션</div>
                <div className="summary-metric-value">{formatCount(riskyPositions.length, '건')}</div>
                <div className="summary-metric-detail">손실 심화 또는 장기 보유 포지션 수</div>
              </div>
              <div className={`summary-metric-card ${todayFailCount > 0 ? 'is-bad' : 'is-good'}`}>
                <div className="summary-metric-label">오늘 체결 / 실패</div>
                <div className="summary-metric-value">{todayBuyCount} / {todaySellCount} / {todayFailCount}</div>
                <div className="summary-metric-detail">매수 체결 / 매도 체결 / 실패 주문</div>
              </div>
              <div className={`summary-metric-card ${trustTone === 'good' ? 'is-good' : trustTone === 'bad' ? 'is-bad' : ''}`}>
                <div className="summary-metric-label">엔진 신뢰도</div>
                <div className="summary-metric-value">{trustState} ({trustScore})</div>
                <div className="summary-metric-detail">최근 오류 {engineState.last_error ? '있음' : '없음'} · validation gate {engineState.validation_policy?.validation_gate_enabled ? '활성' : '비활성'}</div>
              </div>
            </div>
          </div>

          <div className="paper-ops-overview-grid">
            <div className="page-section" style={{ padding: 16 }}>
              <div className="section-title">리서치 입력 분리</div>
              <div className="workspace-chip-row" style={{ marginTop: 10, marginBottom: 10 }}>
                <span className={String(snapshot.research.freshness || '').toLowerCase() === 'fresh' ? 'inline-badge is-success' : String(snapshot.research.freshness || '').toLowerCase() === 'stale' ? 'inline-badge is-danger' : 'inline-badge'}>
                  {String(snapshot.research.freshness || 'missing')}
                </span>
                <span className="inline-badge">provider {String(snapshot.research.source || snapshot.research.status || '-')}</span>
                <span className={String(snapshot.research.status || '') === 'healthy' ? 'inline-badge is-success' : 'inline-badge is-danger'}>
                  status {String(snapshot.research.status || '-')}
                </span>
              </div>
              <div className="detail-list">
                <div>Layer B: 퀀트 스캐너가 진입 후보를 만든 뒤 reason code와 스냅샷을 남깁니다.</div>
                <div>Layer C: Hanna는 external research scorer일 뿐이고, buy/sell/order를 직접 내리지 못합니다.</div>
                <div>Layer C 점수는 freshness/grade를 같이 봐야 합니다. Grade D면 점수 숫자는 숨기고 사유만 봅니다.</div>
                <div>Layer D/E: Risk Gate가 최종 veto를 쥐고, 결과는 review_for_entry / watch_only / blocked / do_not_touch로만 끝냅니다.</div>
              </div>
            </div>
            <div className="page-section" style={{ padding: 16 }}>
              <div className="section-title">운용 긴급도</div>
              <div className="detail-list">
                <div>신규 진입: {entryAllowed ? '허용된 종목만 선별 진입' : '금일 신규 진입 금지'}</div>
                <div>위험 포지션: {formatCount(riskyPositions.length, '건')}</div>
                <div>오늘 실패 주문: {formatCount(todayFailCount, '건')}</div>
                <div>다음 실행 시각: {formatDateTime(engineState.next_run_at)}</div>
              </div>
            </div>
            <div className="page-section" style={{ padding: 16 }}>
              <div className="section-title">현금/자산 상태</div>
              <div className="detail-list">
                <div>총자산(원화환산): {formatKRW(vm.totalEquityKrw, true)}</div>
                <div>원화 현금: {formatKRW(vm.cashKrw, true)}</div>
                <div>달러 현금: {formatUSD(vm.cashUsd, true)}</div>
                <div>평가손익 / 실현손익: {formatKRW(vm.unrealizedPnlKrw, true)} / {formatKRW(vm.realizedPnlKrw, true)}</div>
              </div>
            </div>
            <div className="page-section" style={{ padding: 16 }}>
              <div className="section-title">오늘 실행 결과</div>
              <div className="detail-list">
                <div>오늘 체결 합계: {formatNumber(todayOrders.length, 0)}건</div>
                <div>매수 체결: {formatCount(todayBuyCount, '건')}</div>
                <div>매도 체결: {formatCount(todaySellCount, '건')}</div>
                <div>실패 주문: {formatCount(todayFailCount, '건')}</div>
                <div>순증가 포지션: {formatCount(todayBuyCount - todaySellCount, '건')}</div>
              </div>
            </div>
            <div className="page-section" style={{ padding: 16, gridColumn: '1 / -1' }}>
              <div className="section-title">동작 검증 체크리스트</div>
              <div className="section-copy">실제 주문이 안 될 때 빠르게 원인별로 판단하려면 아래를 확인한다.</div>
              <div style={{ marginTop: 12, overflowX: 'auto' }}>
                <div className="validation-decision-grid" style={{ gridTemplateColumns: 'repeat(5, minmax(220px, 1fr))', minWidth: 1160 }}>
                  <div className={`summary-metric-card ${engineState.running ? 'is-good' : 'is-bad'}`}>
                    <div className="summary-metric-label">1. 실행 루프</div>
                    <div className="summary-metric-value">{engineState.running ? '가동중' : '정지'}</div>
                    <div className="summary-metric-detail">최근 {formatDateTime(engineState.last_run_at)} · 다음 {formatDateTime(engineState.next_run_at)}</div>
                  </div>
                  <div className={`summary-metric-card ${entryAllowed ? 'is-good' : 'is-bad'}`}>
                    <div className="summary-metric-label">2. 리스크 가드</div>
                    <div className="summary-metric-value">{entryAllowed ? '통과' : '차단'}</div>
                    <div className="summary-metric-detail">
                      {riskGuardReasonRows.length > 0 ? riskGuardReasonRows.slice(0, 2).map((item) => `${item.label}(${formatCount(item.count, '건')})`).join(' · ') : '해제'}
                    </div>
                  </div>
                  <div className={`summary-metric-card ${orderFailureSummary?.today_failed ? 'is-bad' : 'is-good'}`}>
                    <div className="summary-metric-label">3. 당일 실패</div>
                    <div className="summary-metric-value">{formatCount(todayFailCount, '건')}</div>
                    <div className="summary-metric-detail">{validationFailureHint}</div>
                  </div>
                  <div className={`summary-metric-card ${blockedReasonRows.length > 0 ? 'is-bad' : 'is-good'}`}>
                    <div className="summary-metric-label">4. 진입 거부 사유</div>
                    <div className="summary-metric-value">{formatCount(blockedReasonRows.length, '개')}</div>
                    <div className="summary-metric-detail">
                      {blockedReasonRows.slice(0, 2).map((item) => `${item.label} ${formatCount(item.count, '건')}`).join(' · ') || '기록 없음'}
                    </div>
                  </div>
                  <div className={`summary-metric-card ${skipReasonRows.length > 0 ? 'is-bad' : 'is-good'}`}>
                    <div className="summary-metric-label">5. 스크리닝/필터</div>
                    <div className="summary-metric-value">{formatCount(skipReasonRows.length, '개')}</div>
                    <div className="summary-metric-detail">
                      {skipReasonRows.slice(0, 2).map((item) => `${item.label} ${formatCount(item.count, '건')}`).join(' · ') || '기록 없음'}
                    </div>
                  </div>
                </div>
              </div>
              <div style={{ marginTop: 12 }}>
                <div
                  className="detail-list"
                  style={{
                    fontSize: 12,
                    color: 'var(--text-3)',
                    display: 'flex',
                    flexDirection: 'row',
                    flexWrap: 'wrap',
                    gap: 12,
                    alignItems: 'center',
                  }}
                >
                  <div>
                    최근 실패 주문: {latestFailureOrder ? (
                      <strong style={{ color: 'var(--text-1)' }}>
                        <SymbolIdentity
                          code={(latestFailureOrder as { code?: string }).code}
                          name={(latestFailureOrder as { name?: string }).name}
                          market={(latestFailureOrder as { market?: string }).market}
                          compact
                        />
                      </strong>
                    ) : '없음'} · {latestFailureOrder ? explainOrderFailureReason(String((latestFailureOrder as { failure_reason?: string; reason_code?: string }).failure_reason || (latestFailureOrder as { reason_code?: string }).reason_code || '-')) : '원인 미기록'}
                  </div>
                  <div>
                    최근 스크리닝 차단: {latestScreenedFailure ? (
                      <strong style={{ color: 'var(--text-1)' }}>
                        <SymbolIdentity
                          code={(latestScreenedFailure as { code?: string }).code}
                          name={(latestScreenedFailure as { name?: string }).name}
                          market={(latestScreenedFailure as { market?: string }).market}
                          compact
                        />
                      </strong>
                    ) : '없음'} · {
                      String((latestScreenedFailure as { failure_reason?: string; reason_code?: string } | null)?.failure_reason || (latestScreenedFailure as { reason_code?: string } | null)?.reason_code || '-')
                    }
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="page-section" style={{ padding: 16 }}>
            <div className="section-head-row">
              <div>
                <div className="section-title">우선 확인할 위험 포지션</div>
                <div className="section-copy">손실 심화 또는 오래 묶인 포지션을 위로 올렸습니다.</div>
              </div>
            </div>
            <div className="history-list">
              {riskyPositions.slice(0, 6).map(({ position, pnlPct, daysHeld }) => (
                <div key={`risk-${position.market}-${position.code}`} className="history-item is-danger">
                  <div>{formatSymbol(position.code, position.name)} · {String(position.market || '-')}</div>
                  <div className="history-item-copy">손익 {formatPercent(pnlPct, 2)} · 보유 {formatCount(daysHeld, '일')} · 평가손익 {formatKRW(position.unrealized_pnl_krw, true)}</div>
                </div>
              ))}
              {riskyPositions.length === 0 && <div className="empty-inline">즉시 정리할 위험 포지션은 없습니다.</div>}
            </div>
          </div>

          <div id="paper-positions-section" className="page-section" style={{ padding: 0 }}>
            <div style={{ padding: '14px 16px 0', display: 'grid', gap: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
                <div style={{ fontSize: 12, color: 'var(--text-4)' }}>보유 종목은 시장별로 나눠서 보는 쪽이 훨씬 덜 헷갈려. 미국장은 달러 가격 뒤에 원화 환산을 같이 붙였어.</div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {(['ALL', 'KOSPI', 'NASDAQ'] as const).map((view) => (
                    <button
                      key={view}
                      type="button"
                      className={positionMarketView === view ? 'ghost-button is-active' : 'ghost-button'}
                      onClick={() => setPositionMarketView(view)}
                    >
                      {view === 'ALL' ? `전체 ${positionMarketCounts.ALL}건` : `${view} ${positionMarketCounts[view]}건`}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div className="responsive-table-desktop" style={{ overflow: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1040 }}>
                <thead>
                  <tr style={{ background: 'var(--bg-soft)', textAlign: 'left' }}>
                    <th style={{ padding: 12, fontSize: 12 }}>종목</th>
                    <th style={{ padding: 12, fontSize: 12 }}>시장 / 통화</th>
                    <th style={{ padding: 12, fontSize: 12 }}>수량</th>
                    <th style={{ padding: 12, fontSize: 12 }}>진입가(현지)</th>
                    <th style={{ padding: 12, fontSize: 12 }}>현재가(현지)</th>
                    <th style={{ padding: 12, fontSize: 12 }}>평가손익(KRW)</th>
                    <th style={{ padding: 12, fontSize: 12 }}>수익률</th>
                    <th style={{ padding: 12, fontSize: 12 }}>보유기간</th>
                    <th style={{ padding: 12, fontSize: 12 }}>손절가 / 손절률</th>
                    <th style={{ padding: 12, fontSize: 12 }}>익절가 / 익절률</th>
                    <th style={{ padding: 12, fontSize: 12 }}>전략 태그</th>
                    <th style={{ padding: 12, fontSize: 12 }}>상태</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredPositions.map((position) => {
                    const positionRaw = position as unknown as Record<string, unknown>;
                    const code = String(position.code || '');
                    const name = String(position.name || '');
                    const entryPrice = toNumber(position.avg_price_local, 0);
                    const currentPrice = toNumber(position.last_price_local, 0);
                    const pnlKrw = toNumber(position.unrealized_pnl_krw, 0);
                    const pnlPct = toNumber(position.unrealized_pnl_pct, NaN);
                    const stopLossPct = toNumber(positionRaw.stop_loss_pct, stopLossPctDefault);
                    const takeProfitPct = toNumber(positionRaw.take_profit_pct, takeProfitPctDefault);
                    const stopLossPrice = Number.isFinite(stopLossPct) ? entryPrice * (1 - stopLossPct / 100) : NaN;
                    const takeProfitPrice = Number.isFinite(takeProfitPct) ? entryPrice * (1 + takeProfitPct / 100) : NaN;
                    const strategyTag = String(positionRaw.strategy_type || positionRaw.strategy || '-');
                    return (
                      <tr key={`${position.market}:${code}`} style={{ borderTop: '1px solid var(--border)' }}>
                        <td style={{ padding: 12, fontSize: 12 }}>{formatSymbol(code, name)}</td>
                        <td style={{ padding: 12, fontSize: 12 }}>{formatMarketWithCurrency(position.market)}</td>
                        <td style={{ padding: 12, fontSize: 12 }}>{formatCount(position.quantity, '주')}</td>
                        <td style={{ padding: 12, fontSize: 12 }}>{formatLocalPriceWithKrw(entryPrice, toNumber(position.avg_price_krw, entryPrice), position.market)}</td>
                        <td style={{ padding: 12, fontSize: 12 }}>{formatLocalPriceWithKrw(currentPrice, toNumber(position.last_price_krw, currentPrice), position.market)}</td>
                        <td style={{ padding: 12, fontSize: 12, color: pnlKrw >= 0 ? 'var(--up)' : 'var(--down)' }}>{formatKRW(pnlKrw, true)}</td>
                        <td style={{ padding: 12, fontSize: 12, color: pnlPct >= 0 ? 'var(--up)' : 'var(--down)' }}>
                          {formatPercent(pnlPct, 2)}
                        </td>
                        <td style={{ padding: 12, fontSize: 12 }}>{formatNumber(holdingDays(position.entry_ts), 0)}일</td>
                        <td style={{ padding: 12, fontSize: 12 }}>
                          {Number.isFinite(stopLossPrice) ? formatLocalPrice(stopLossPrice, position.market) : '-'} / {formatPercent(stopLossPct, 2)}
                        </td>
                        <td style={{ padding: 12, fontSize: 12 }}>
                          {Number.isFinite(takeProfitPrice) ? formatLocalPrice(takeProfitPrice, position.market) : '-'} / {formatPercent(takeProfitPct, 2)}
                        </td>
                        <td style={{ padding: 12, fontSize: 12 }}>{strategyTag}</td>
                        <td style={{ padding: 12, fontSize: 12, fontWeight: 700 }}>보유</td>
                      </tr>
                    );
                  })}
                  {filteredPositions.length === 0 && (
                    <tr>
                      <td colSpan={12} style={{ padding: 16, fontSize: 12, color: 'var(--text-4)' }}>{positionMarketView === 'ALL' ? UI_TEXT.empty.noPositions : `${positionMarketView} 보유 종목이 없습니다.`}</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="responsive-card-list">
              {filteredPositions.map((position) => {
                const positionRaw = position as unknown as Record<string, unknown>;
                const code = String(position.code || '');
                const name = String(position.name || '');
                const entryPrice = toNumber(position.avg_price_local, 0);
                const currentPrice = toNumber(position.last_price_local, 0);
                const pnlKrw = toNumber(position.unrealized_pnl_krw, 0);
                const pnlPct = toNumber(position.unrealized_pnl_pct, NaN);
                const stopLossPct = toNumber(positionRaw.stop_loss_pct, stopLossPctDefault);
                const takeProfitPct = toNumber(positionRaw.take_profit_pct, takeProfitPctDefault);
                const stopLossPrice = Number.isFinite(stopLossPct) ? entryPrice * (1 - stopLossPct / 100) : NaN;
                const takeProfitPrice = Number.isFinite(takeProfitPct) ? entryPrice * (1 + takeProfitPct / 100) : NaN;
                const strategyTag = String(positionRaw.strategy_type || positionRaw.strategy || '-');
                return (
                  <article key={`${position.market}:${code}-card`} className="responsive-card">
                    <div className="responsive-card-head">
                      <div>
                        <div className="responsive-card-title">{formatSymbol(code, name)}</div>
                        <div className="signal-cell-copy">{formatMarketWithCurrency(position.market)}</div>
                      </div>
                      <div className="inline-badge">보유</div>
                    </div>
                    <div className="responsive-card-grid">
                      <div><div className="responsive-card-label">수량</div><div className="responsive-card-value">{formatCount(position.quantity, '주')}</div></div>
                      <div><div className="responsive-card-label">수익률</div><div className="responsive-card-value" style={{ color: pnlPct >= 0 ? 'var(--up)' : 'var(--down)' }}>{formatPercent(pnlPct, 2)}</div></div>
                      <div><div className="responsive-card-label">평가손익</div><div className="responsive-card-value" style={{ color: pnlKrw >= 0 ? 'var(--up)' : 'var(--down)' }}>{formatKRW(pnlKrw, true)}</div></div>
                      <div><div className="responsive-card-label">보유기간</div><div className="responsive-card-value">{formatNumber(holdingDays(position.entry_ts), 0)}일</div></div>
                      <div><div className="responsive-card-label">진입가 / 현재가</div><div className="responsive-card-value">{formatLocalPriceWithKrw(entryPrice, toNumber(position.avg_price_krw, entryPrice), position.market)} / {formatLocalPriceWithKrw(currentPrice, toNumber(position.last_price_krw, currentPrice), position.market)}</div></div>
                      <div><div className="responsive-card-label">손절 / 익절</div><div className="responsive-card-value">{Number.isFinite(stopLossPrice) ? formatLocalPrice(stopLossPrice, position.market) : '-'} / {Number.isFinite(takeProfitPrice) ? formatLocalPrice(takeProfitPrice, position.market) : '-'}</div></div>
                      <div><div className="responsive-card-label">전략 태그</div><div className="responsive-card-value">{strategyTag}</div></div>
                      <div><div className="responsive-card-label">손절률 / 익절률</div><div className="responsive-card-value">{formatPercent(stopLossPct, 2)} / {formatPercent(takeProfitPct, 2)}</div></div>
                    </div>
                  </article>
                );
              })}
              {filteredPositions.length === 0 && <div style={{ padding: 16, fontSize: 12, color: 'var(--text-4)' }}>{positionMarketView === 'ALL' ? UI_TEXT.empty.noPositions : `${positionMarketView} 보유 종목이 없습니다.`}</div>}
            </div>
          </div>

          <div className="paper-ops-summary-grid">
            <div id="paper-engine-panel-section" className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 14, fontWeight: 700 }}>엔진 상태 패널</div>
              <div style={{ marginTop: 10, display: 'grid', gap: 6, fontSize: 12, color: 'var(--text-3)' }}>
                <div>상태: {engineStateLabel(engineState.engine_state, engineState.running)}</div>
                <div>상태 사유: {engineState.last_error ? '최근 오류 발생' : (engineState.running ? '정상 실행 중' : engineState.engine_state === 'paused' ? '일시정지' : '대기 중')}</div>
                <div>최근 실행 시각: {formatDateTime(engineState.last_run_at)}</div>
                <div>다음 실행 시각: {formatDateTime(engineState.next_run_at)}</div>
                <div>최근 오류: {engineState.last_error || '-'}</div>
                <div>
                  최근 실행 요약: 매수 {formatNumber(engineState.last_summary?.executed_buy_count, 0)}건 / 매도 {formatNumber(engineState.last_summary?.executed_sell_count, 0)}건
                </div>
                <div>today 체결(B/S) / 실패: {formatNumber(engineState.today_order_counts?.buy, 0)} / {formatNumber(engineState.today_order_counts?.sell, 0)} / {formatNumber(engineState.today_order_counts?.failed, 0)}</div>
                <div>today 실현손익: {formatKRW(engineState.today_realized_pnl, true)}</div>
                <div>validation gate: {engineState.validation_policy?.validation_gate_enabled ? '활성' : '비활성'}</div>
              </div>
            </div>

            <div className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 14, fontWeight: 700 }}>오늘 포지션 변화 요약</div>
              <div style={{ marginTop: 10, display: 'grid', gap: 6, fontSize: 12, color: 'var(--text-3)' }}>
                <div>오늘 체결 합계: {formatNumber(todayOrders.length, 0)}건</div>
                <div>매수 체결: {formatCount(todayBuyCount, '건')}</div>
                <div>매도 체결: {formatCount(todaySellCount, '건')}</div>
                <div>실패 주문: {formatCount(todayFailCount, '건')}</div>
                <div>순증가 포지션: {formatCount(todayBuyCount - todaySellCount, '건')}</div>
              </div>
            </div>
          </div>

          <div className="paper-ops-log-grid">
            <div className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 14, fontWeight: 700 }}>최근 체결 내역</div>
              <div style={{ marginTop: 10, display: 'grid', gap: 8 }}>
                {mergedOrderHistory.slice(0, 12).map((order, index) => {
                  const item = order as {
                    order_id?: string;
                    timestamp?: string;
                    ts?: string;
                    code?: string;
                    name?: string;
                    market?: string;
                    side?: string;
                    strategy_name?: string;
                    quantity?: number;
                    filled_price_local?: number;
                    success?: boolean;
                    failure_reason?: string;
                    reason_code?: string;
                    message?: string;
                  };
                  const isSuccess = item.success !== false;
                  return (
                    <div key={item.order_id || `${item.code || 'order'}-${index}`} style={{ border: '1px solid var(--border)', borderRadius: 10, padding: '8px 10px', fontSize: 12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                      <div>
                        <SymbolIdentity code={item.code} name={item.name} market={item.market} compact />
                      </div>
                      <span style={{ color: isSuccess ? (item.side === 'buy' ? 'var(--up)' : 'var(--down)') : 'var(--down)', fontWeight: 700 }}>
                        {isSuccess ? (item.side === 'buy' ? '매수' : '매도') : '실패'}
                      </span>
                    </div>
                    <div style={{ marginTop: 4, color: 'var(--text-3)' }}>
                      {item.market ? `${formatMarketWithCurrency(item.market)} · ` : ''}수량 {formatCount(item.quantity, '주')} · 체결가 {formatLocalPrice(item.filled_price_local, item.market)} · {formatDateTime(item.timestamp || item.ts)}
                    </div>
                    {!!item.strategy_name && (
                      <div className="signal-cell-copy" style={{ marginTop: 4 }}>전략: {item.strategy_name}</div>
                    )}
                    {!isSuccess && (
                      <div style={{ marginTop: 4, color: 'var(--down)', display: 'grid', gap: 4 }}>
                        <div>reason code: {item.reason_code || item.failure_reason || '-'}</div>
                        <div>상세: {item.message || explainOrderFailureReason(item.failure_reason)}</div>
                      </div>
                    )}
                    </div>
                  );
                })}
                {mergedOrderHistory.length === 0 && <div style={{ fontSize: 12, color: 'var(--text-4)' }}>{UI_TEXT.empty.noTrades}</div>}
              </div>
            </div>

            <div className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 14, fontWeight: 700 }}>최근 엔진 이벤트 로그</div>
              <div style={{ marginTop: 10, display: 'grid', gap: 8 }}>
                {Object.entries(skipReasonCounts).slice(0, 6).map(([reason, count]) => (
                  <div key={reason} style={{ fontSize: 12, color: 'var(--text-3)', border: '1px solid var(--border)', borderRadius: 10, padding: '8px 10px' }}>
                    {paperSkipReasonLabel(reason)}: {formatCount(count, '건')}
                  </div>
                ))}
                {cycles.slice(0, 4).map((cycle, idx) => {
                  const item = cycle as {
                    cycle_id?: string;
                    started_at?: string;
                    finished_at?: string;
                    executed_buy_count?: number;
                    executed_sell_count?: number;
                    error?: string;
                  };
                  return (
                    <div key={item.cycle_id || `cycle-${idx}`} style={{ fontSize: 12, color: 'var(--text-3)', border: '1px solid var(--border)', borderRadius: 10, padding: '8px 10px' }}>
                      <div>cycle: {item.cycle_id || '-'}</div>
                      <div>시각: {formatDateTime(item.finished_at || item.started_at)}</div>
                      <div>매수 {formatNumber(item.executed_buy_count, 0)} / 매도 {formatNumber(item.executed_sell_count, 0)}</div>
                      {!!item.error && <div style={{ color: 'var(--down)' }}>오류: {item.error}</div>}
                    </div>
                  );
                })}
                {Object.keys(skipReasonCounts).length === 0 && (
                  <div style={{ fontSize: 12, color: 'var(--text-4)' }}>{UI_TEXT.empty.noSkipReasons}</div>
                )}
              </div>
            </div>
          </div>


          <div id="paper-workflow-section" className="page-section" style={{ padding: 16 }}>
            <div className="section-head-row">
              <div>
                <div className="section-title">실행 워크플로우</div>
                <div className="section-copy">탐색 → 신호 → 판단 → 주문으로 끊어서 본다. 어디서 막혔는지, 주문 직전까지 갔는지, 체결됐는지 한 번에 보이게 정리했다.</div>
              </div>
              <div className={`inline-badge ${workflowCounts.ready > 0 ? 'is-success' : ''}`}>주문 준비 {formatCount(workflowCounts.ready, '건')}</div>
            </div>

            <div className="validation-decision-grid" style={{ marginTop: 12 }}>
              {[
                { key: 'discover', label: '탐색', value: workflowCounts.discover, detail: 'watch + blocked', tone: workflowTab === 'discover' ? 'is-good' : '' },
                { key: 'signal', label: '신호', value: workflowCounts.signal, detail: 'signal_generated', tone: workflowTab === 'signal' ? 'is-good' : '' },
                { key: 'decision', label: '판단', value: workflowCounts.decision, detail: 'execution_decided + order_ready', tone: workflowTab === 'decision' ? 'is-good' : '' },
                { key: 'order', label: '주문', value: workflowCounts.order, detail: `체결 ${workflowCounts.filled} · 거절 ${workflowCounts.rejected}`, tone: workflowTab === 'order' ? (workflowCounts.rejected > workflowCounts.filled ? 'is-bad' : 'is-good') : '' },
              ].map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className={`summary-metric-card ${item.tone}`}
                  style={{ textAlign: 'left', cursor: 'pointer' }}
                  onClick={() => setWorkflowTab((prev) => (prev === item.key ? 'all' : item.key as 'discover' | 'signal' | 'decision' | 'order'))}
                >
                  <div className="summary-metric-label">{item.label}</div>
                  <div className="summary-metric-value">{formatCount(item.value, '건')}</div>
                  <div className="summary-metric-detail">{item.detail}</div>
                </button>
              ))}
            </div>

            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 12 }}>
              {[
                { key: 'all', label: '전체' },
                { key: 'discover', label: '탐색' },
                { key: 'signal', label: '신호' },
                { key: 'decision', label: '판단' },
                { key: 'order', label: '주문' },
              ].map((tab) => (
                <button
                  key={tab.key}
                  type="button"
                  className={workflowTab === tab.key ? 'inline-badge is-success' : 'inline-badge'}
                  onClick={() => setWorkflowTab(tab.key as 'all' | 'discover' | 'signal' | 'decision' | 'order')}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <div style={{ display: 'grid', gap: 10, marginTop: 12 }}>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <input
                  className="backtest-input-wrap"
                  style={{ padding: '0 12px', minWidth: 220 }}
                  type="text"
                  placeholder="종목/전략/차단 사유 검색"
                  value={workflowSearch}
                  onChange={(event) => setWorkflowSearch(event.target.value)}
                />
                <label className="inline-badge" style={{ cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={workflowOnlyBlocked}
                    onChange={(event) => setWorkflowOnlyBlocked(event.target.checked)}
                    style={{ marginRight: 6 }}
                  />
                  막힌 건만 보기
                </label>
                <label className={autoRefreshEnabled ? 'inline-badge is-success' : 'inline-badge'} style={{ cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={autoRefreshEnabled}
                    onChange={(event) => setAutoRefreshEnabled(event.target.checked)}
                    style={{ marginRight: 6 }}
                  />
                  10초 자동 갱신
                </label>
                {(workflowSearch || workflowOnlyBlocked || workflowTab !== 'all') && (
                  <button
                    type="button"
                    className="console-action-button"
                    onClick={() => {
                      setWorkflowSearch('');
                      setWorkflowOnlyBlocked(false);
                      setWorkflowTab('all');
                    }}
                  >
                    필터 초기화
                  </button>
                )}
              </div>
              {workflowBlockedReasonSummary.length > 0 && (
                <div className="detail-list" style={{ gap: 8 }}>
                  <div style={{ fontWeight: 700, color: 'var(--text-2)' }}>지금 제일 많이 막는 이유</div>
                  {workflowBlockedReasonSummary.map((item) => (
                    <div key={item.reason}>{item.label} · {formatCount(item.count, '건')}</div>
                  ))}
                </div>
              )}
            </div>

            <div className="responsive-card-list" style={{ marginTop: 12 }}>
              {visibleWorkflowItems.map((item) => {
                const tone = workflowStatusTone(item.execution_status);
                const workflowSymbolCode = String(item.code || '').trim().toUpperCase();
                const workflowSymbolName = String(item.name || '').trim();
                const statusLabel = reasonCodeToKorean(String(item.blocked_reason || item.last_order_reason || item.execution_status || '-'));
                const quoteGrade = String(item.quote_validation?.grade || '-');
                const quoteFreshness = String(item.quote_freshness || 'missing');
                return (
                  <article key={`${item.signal_key || workflowSymbolCode || item.last_order_at || item.timestamp || item.logged_at || ''}`} className="responsive-card">
                    <div className="responsive-card-head">
                      <div>
                        <div className="responsive-card-title">
                          <SymbolIdentity code={workflowSymbolCode} name={workflowSymbolName} compact />
                        </div>
                        <div className="signal-cell-copy">{String(item.market || '-')} · {String(item.strategy_name || item.strategy_id || '-')}</div>
                      </div>
                      <div className={tone === 'good' ? 'inline-badge is-success' : tone === 'bad' ? 'inline-badge is-danger' : 'inline-badge'}>{workflowStageLabel(item.workflow_stage)}</div>
                    </div>
                    <div className="responsive-card-grid">
                      <div><div className="responsive-card-label">실행 상태</div><div className="responsive-card-value">{workflowStatusLabel(item.execution_status)}</div></div>
                      <div><div className="responsive-card-label">주문 가능</div><div className="responsive-card-value">{item.orderable ? `예 · ${formatCount(item.order_quantity || 0, '주')}` : '아니오'}</div></div>
                      <div><div className="responsive-card-label">최종 액션</div><div className="responsive-card-value">{reasonCodeToKorean(String(item.final_action || '-'))}</div></div>
                      <div><div className="responsive-card-label">마지막 시각</div><div className="responsive-card-value">{formatDateTime(item.last_order_at || item.fetched_at || item.timestamp || item.logged_at || '')}</div></div>
                      <div><div className="responsive-card-label">키</div><div className="responsive-card-value">{String(item.signal_key || '-')}</div></div>
                      <div><div className="responsive-card-label">주문 결과</div><div className="responsive-card-value">{item.last_order_success === undefined ? '-' : item.last_order_success ? '성공' : '실패'}</div></div>
                      <div><div className="responsive-card-label">Quote</div><div className="responsive-card-value">{quoteFreshness} · Grade {quoteGrade}</div></div>
                      <div><div className="responsive-card-label">Quote source</div><div className="responsive-card-value">{String(item.quote_source || '-')}</div></div>
                      <div style={{ gridColumn: '1 / -1' }}><div className="responsive-card-label">설명</div><div className="responsive-card-value">{statusLabel}</div></div>
                      {item.quote_validation?.exclusion_reason ? <div style={{ gridColumn: '1 / -1' }}><div className="responsive-card-label">Quote note</div><div className="responsive-card-value">{String(item.quote_validation.exclusion_reason)}</div></div> : null}
                    </div>
                  </article>
                );
              })}
              {visibleWorkflowItems.length === 0 && <div style={{ padding: 16, fontSize: 12, color: 'var(--text-4)' }}>아직 워크플로우 이벤트가 없다. 엔진을 한 번 돌리면 탐색부터 주문까지 누적된다.</div>}
            </div>
          </div>

          <div id="paper-risk-action-section" className="page-section" style={{ padding: 16 }}>
            <div className="section-head-row">
              <div>
                <div className="section-title">Risk / Action 로그</div>
                <div className="section-copy">Layer D risk 결과와 Layer E final action을 분리해서 보여줍니다. Hanna 상태는 참고 정보이고 주문 허용 여부는 risk veto 기준으로 읽으면 됩니다.</div>
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <div className={hannaBadgeClass(currentHannaState)}>Hanna {currentHannaState}</div>
                <div className={layerCResearchBadgeClass('freshness', String(snapshot.research.freshness || 'missing').toLowerCase())}>{String(snapshot.research.freshness || 'missing')}</div>
              </div>
            </div>
            <div style={{ marginTop: 12 }}>
              <div className={`inline-badge ${riskActionCheck.tone === 'good' ? 'is-success' : riskActionCheck.tone === 'bad' ? 'is-danger' : ''}`}>{riskActionCheck.title}</div>
              <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-3)' }}>{riskActionCheck.detail}</div>
              <div className="detail-list" style={{ marginTop: 8, gap: 4 }}>
                {riskActionCheck.steps.map((step) => (
                  <div key={step} style={{ color: 'var(--text-3)' }}>{step}</div>
                ))}
              </div>
            </div>
            <div className="responsive-table-desktop" style={{ overflow: 'auto', marginTop: 12 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 980 }}>
                <thead>
                  <tr style={{ background: 'var(--bg-soft)', textAlign: 'left' }}>
                    <th style={{ padding: 12, fontSize: 12 }}>시각</th>
                    <th style={{ padding: 12, fontSize: 12 }}>종목</th>
                    <th style={{ padding: 12, fontSize: 12 }}>전략</th>
                    <th style={{ padding: 12, fontSize: 12 }}>Hanna</th>
                    <th style={{ padding: 12, fontSize: 12 }}>Layer C</th>
                    <th style={{ padding: 12, fontSize: 12 }}>Layer D</th>
                    <th style={{ padding: 12, fontSize: 12 }}>Layer E</th>
                    <th style={{ padding: 12, fontSize: 12 }}>reason code</th>
                  </tr>
                </thead>
                <tbody>
                  {signalRiskActionLogs.map((item) => (
                    <tr key={item.key} style={{ borderTop: '1px solid var(--border)' }}>
                      <td style={{ padding: 12, fontSize: 12 }}>{formatDateTime(item.timestamp)}</td>
                      <td style={{ padding: 12, fontSize: 12 }}>
                        <SymbolIdentity code={item.symbolCode} name={item.symbolName} compact />
                      </td>
                      <td style={{ padding: 12, fontSize: 12 }}>{item.strategy}</td>
                      <td style={{ padding: 12, fontSize: 12 }}>
                        <div className={hannaBadgeClass(item.hannaState)}>{item.hannaState}</div>
                      </td>
                      <td style={{ padding: 12, fontSize: 12 }}>
                        <div className="workspace-chip-row">
                          <span className={layerCResearchBadgeClass('freshness', String(item.researchFreshness || 'missing'))}>{String(item.researchFreshness || 'missing')}</span>
                          <span className={layerCResearchBadgeClass('grade', String(item.researchGrade || '-'))}>Grade {String(item.researchGrade || '-')}</span>
                        </div>
                        <div className="signal-cell-copy" style={{ marginTop: 6 }}>score {String(item.researchScore || '-')}</div>
                      </td>
                      <td style={{ padding: 12, fontSize: 12 }}>
                        <div className={item.riskDecision === 'allowed' ? 'inline-badge is-success' : 'inline-badge is-danger'}>
                          {riskDecisionLabel(item.riskDecision)}
                        </div>
                      </td>

                      <td style={{ padding: 12, fontSize: 12 }}>
                        <div className={item.finalAction === 'review_for_entry' ? 'inline-badge is-success' : item.finalAction === 'blocked' ? 'inline-badge is-danger' : 'inline-badge'}>
                          {reasonCodeToKorean(item.finalAction)}
                        </div>
                        <div className="signal-cell-copy" style={{ marginTop: 6 }}>{riskMessageLabel(item.riskMessage)}</div>
                      </td>
                      <td style={{ padding: 12, fontSize: 12 }}>
                        <div>{item.translatedReasons.join(', ') || '-'}</div>
                        <div className="signal-cell-copy" style={{ marginTop: 6 }}>{item.rawReasons.join(', ') || '-'}</div>
                      </td>
                    </tr>
                  ))}
                  {signalRiskActionLogs.length === 0 && (
                    <tr>
                      <td colSpan={8} style={{ padding: 16, fontSize: 12, color: 'var(--text-4)' }}>
                        아직 기록된 signal snapshot이 없습니다. 엔진을 한 번 실행하면 Layer D/E 로그가 여기에 누적됩니다.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="responsive-card-list" style={{ marginTop: 12 }}>
              {signalRiskActionLogs.map((item) => (
                <article key={`${item.key}-card`} className="responsive-card">
                  <div className="responsive-card-head">
                    <div>
                      <div className="responsive-card-title">
                        <SymbolIdentity code={item.symbolCode} name={item.symbolName} />
                      </div>
                      <div className="signal-cell-copy">{item.market} · {item.strategy}</div>
                    </div>
                    <div className={hannaBadgeClass(item.hannaState)}>{item.hannaState}</div>
                  </div>
                  <div className="responsive-card-grid">
                    <div><div className="responsive-card-label">시각</div><div className="responsive-card-value">{formatDateTime(item.timestamp)}</div></div>
                    <div><div className="responsive-card-label">Layer C</div><div className="responsive-card-value">{String(item.researchFreshness || 'missing')} · Grade {String(item.researchGrade || '-')} · {String(item.researchScore || '-')}</div></div>
                    <div><div className="responsive-card-label">Layer D</div><div className="responsive-card-value">{riskDecisionLabel(item.riskDecision)} · {reasonCodeToKorean(item.riskReasonCode)}</div></div>
                    <div><div className="responsive-card-label">Layer E</div><div className="responsive-card-value">{reasonCodeToKorean(item.finalAction)}</div></div>
                    <div><div className="responsive-card-label">상세</div><div className="responsive-card-value">{item.researchGrade === 'D' ? (item.researchExclusionReason || riskMessageLabel(item.riskMessage)) : riskMessageLabel(item.riskMessage)}</div></div>
                    <div style={{ gridColumn: '1 / -1' }}><div className="responsive-card-label">reason code</div><div className="responsive-card-value">{item.translatedReasons.join(', ') || '-'}</div><div className="signal-cell-copy">{item.rawReasons.join(', ') || '-'}</div></div>
                  </div>
                </article>
              ))}
              {signalRiskActionLogs.length === 0 && <div style={{ padding: 16, fontSize: 12, color: 'var(--text-4)' }}>아직 기록된 signal snapshot이 없습니다. 엔진을 한 번 실행하면 Layer D/E 로그가 여기에 누적됩니다.</div>}
            </div>
          </div>

          <div className="page-section" style={{ padding: 16 }}>
            <div style={{ fontSize: 14, fontWeight: 700 }}>운영 로그 스냅샷</div>
            <div style={{ marginTop: 10, display: 'grid', gap: 6, fontSize: 12, color: 'var(--text-3)' }}>
              <div>cycle 로그: {formatCount(cycles.length, '건')}</div>
              <div>주문 이벤트 로그: {formatCount(orderEvents.length, '건')}</div>
              <div>계좌 스냅샷: {formatCount(accountHistory.length, '건')}</div>
              <div>signal snapshot: {formatCount(signalSnapshots.length, '건')}</div>
            </div>
          </div>

          {loading && <div style={{ color: 'var(--text-3)', fontSize: 12 }}>{UI_TEXT.common.loading}</div>}
        </div>
      </div>
    </div>
  );
}
