import { useCallback, useEffect, useMemo, useState } from 'react';
import { ConsoleActionBar } from '../components/ConsoleActionBar';
import { UI_TEXT } from '../constants/uiText';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import { usePaperTrading } from '../hooks/usePaperTrading';
import { useToast } from '../hooks/useToast';
import type { ActionBarStatusItem, ConsoleSnapshot, PaperViewModel } from '../types/consoleView';
import { formatCount, formatDateTime, formatKRW, formatNumber, formatPercent, formatSymbol, formatUSD } from '../utils/format';

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
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function parseGroupedNumberInput(raw: string): number {
  const digits = raw.replace(/[^\d]/g, '');
  if (!digits) return 0;
  return Number(digits);
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

export function PaperPortfolioPage({ snapshot, loading, errorMessage, onRefresh }: PaperPortfolioPageProps) {
  const { pushToast } = useToast();
  const { entries, push, clear } = useConsoleLogs();
  const [settings, setSettings] = useState<PaperSettings>(() => readSettings());
  const [savedSettings, setSavedSettings] = useState<PaperSettings>(() => readSettings());
  const [settingsSavedAt, setSettingsSavedAt] = useState(() => readSettingsSavedAt());
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [pendingAction, setPendingAction] = useState<'engine-toggle' | 'pause' | 'resume' | 'reset' | null>(null);
  const {
    account,
    engineState,
    cycles,
    orderEvents,
    accountHistory,
    signalSnapshots,
    status,
    lastError,
    refresh,
    reset,
    refreshEngineStatus,
    refreshRuntimeLogs,
    startEngine,
    stopEngine,
    pauseEngine,
    resumeEngine,
  } = usePaperTrading();

  const positions = account.positions || [];
  const orders = [...(account.orders || [])].sort((a, b) => String(b.ts || '').localeCompare(String(a.ts || '')));
  const mergedOrderHistory = (orderEvents.length > 0 ? orderEvents : orders as unknown as Record<string, unknown>[])
    .slice(0, 80)
    .sort((a, b) => String((b as { timestamp?: string; ts?: string }).timestamp || (b as { ts?: string }).ts || '')
      .localeCompare(String((a as { timestamp?: string; ts?: string }).timestamp || (a as { ts?: string }).ts || '')));

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

  const todayOrders = orders.filter((order) => isToday(order.ts));
  const todayBuyCount = todayOrders.filter((order) => order.side === 'buy').length;
  const todaySellCount = todayOrders.filter((order) => order.side === 'sell').length;
  const settingsDirty = useMemo(() => JSON.stringify(settings) !== JSON.stringify(savedSettings), [savedSettings, settings]);

  const statusItems = useMemo<ActionBarStatusItem[]>(() => ([
    {
      label: '엔진 상태',
      value: engineStateLabel(engineState.engine_state, engineState.running),
      tone: engineState.engine_state === 'error' ? 'bad' : engineState.running ? 'good' : 'neutral',
    },
    {
      label: '리스크 가드',
      value: snapshot.portfolio.risk_guard_state?.entry_allowed ? UI_TEXT.status.active : UI_TEXT.status.inactive,
      tone: snapshot.portfolio.risk_guard_state?.entry_allowed ? 'good' : 'bad',
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
  ]), [engineState.engine_state, engineState.running, snapshot.portfolio.risk_guard_state?.entry_allowed, status, vm.positionCount]);

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

  useEffect(() => {
    if (!(engineState.running || engineState.engine_state === 'paused')) return;
    const timer = window.setInterval(() => {
      void refreshRuntimeLogs();
    }, 10_000);
    return () => window.clearInterval(timer);
  }, [engineState.engine_state, engineState.running, refreshRuntimeLogs]);

  const settingsPanel = (
    <div style={{ display: 'grid', gap: 12 }}>
      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>초기 원화 현금</span>
        <input
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          type="text"
          inputMode="numeric"
          value={formatNumber(settings.initialCashKrw, 0)}
          onChange={(event) => setSettings((prev) => ({ ...prev, initialCashKrw: parseGroupedNumberInput(event.target.value) }))}
        />
      </label>
      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>초기 달러 현금</span>
        <input
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          type="text"
          inputMode="numeric"
          value={formatNumber(settings.initialCashUsd, 0)}
          onChange={(event) => setSettings((prev) => ({ ...prev, initialCashUsd: parseGroupedNumberInput(event.target.value) }))}
        />
      </label>
      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>모의투자 기간(일)</span>
        <input
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          type="number"
          value={settings.paperDays}
          onChange={(event) => setSettings((prev) => ({ ...prev, paperDays: Math.max(1, Number(event.target.value) || 1) }))}
        />
      </label>
      <div style={{ display: 'grid', gap: 8, fontSize: 12 }}>
        <span style={{ color: 'var(--text-3)' }}>시장 선택</span>
        <label><input type="checkbox" checked={settings.runKospi} onChange={(event) => setSettings((prev) => ({ ...prev, runKospi: event.target.checked }))} /> KOSPI</label>
        <label><input type="checkbox" checked={settings.runNasdaq} onChange={(event) => setSettings((prev) => ({ ...prev, runNasdaq: event.target.checked }))} /> NASDAQ</label>
      </div>
      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>최대 포지션 수(건)</span>
        <input
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          type="number"
          min={1}
          value={settings.maxPositions}
          onChange={(event) => setSettings((prev) => ({ ...prev, maxPositions: Math.max(1, Number(event.target.value) || 1) }))}
        />
      </label>
      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>일일 매수 제한(건)</span>
        <input
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          type="number"
          min={1}
          value={settings.dailyBuyLimit}
          onChange={(event) => setSettings((prev) => ({ ...prev, dailyBuyLimit: Math.max(1, Number(event.target.value) || 1) }))}
        />
      </label>
      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>일일 매도 제한(건)</span>
        <input
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          type="number"
          min={1}
          value={settings.dailySellLimit}
          onChange={(event) => setSettings((prev) => ({ ...prev, dailySellLimit: Math.max(1, Number(event.target.value) || 1) }))}
        />
      </label>
      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>종목당 일일 주문 제한(건)</span>
        <input
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          type="number"
          min={1}
          value={settings.maxOrdersPerSymbol}
          onChange={(event) => setSettings((prev) => ({ ...prev, maxOrdersPerSymbol: Math.max(1, Number(event.target.value) || 1) }))}
        />
      </label>
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
  const entryAllowed = Boolean(snapshot.portfolio.risk_guard_state?.entry_allowed);
  const todayFailCount = Number(engineState.today_order_counts?.failed || 0);
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
    return positions
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
  }, [positions, stopLossPctDefault]);

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell" style={{ display: 'grid', gap: 16 }}>
          <ConsoleActionBar
            title="모의투자 운용"
            subtitle="계좌/포지션/엔진 상태를 확인하고 엔진 시작·중지·초기화를 직접 수행합니다."
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
                label: '모의투자 초기화',
                onClick: () => { void handleReset(); },
                tone: 'danger',
                busy: pendingAction === 'reset',
                busyLabel: '초기화 중...',
                confirmTitle: UI_TEXT.confirm.resetPaperTitle,
                confirmMessage: UI_TEXT.confirm.resetPaperMessage,
                confirmDetails: ['계좌, 포지션, 주문/사이클 기준 데이터가 새 초기 자금으로 다시 설정됩니다.', '이 작업은 되돌릴 수 없습니다.'],
              },
            ]}
            settingsPanel={settingsPanel}
          />

          <div className="page-section validation-decision-hero" style={{ padding: 18 }}>
            <div className="report-hero-topline">
              <span className="report-hero-tag">Risk First</span>
              <span className={`report-decision-chip ${entryAllowed ? 'is-good' : 'is-bad'}`}>신규 진입 {entryAllowed ? '가능' : '차단'}</span>
            </div>
            <div className="report-decision-title">운용 우선순위: {riskyPositions.length > 0 || todayFailCount > 0 ? '리스크 정리 먼저' : '정상 운영 지속'}</div>
            <div className="report-hero-copy">보유 포지션보다 먼저 위험 포지션, 오늘 체결/실패, 엔진 신뢰도, 신규 진입 허용 여부를 확인하는 화면으로 재정렬했습니다.</div>
            <div className="validation-decision-grid">
              <div className={`summary-metric-card ${riskyPositions.length > 0 ? 'is-bad' : 'is-good'}`}>
                <div className="summary-metric-label">위험 포지션</div>
                <div className="summary-metric-value">{formatCount(riskyPositions.length, '건')}</div>
                <div className="summary-metric-detail">손실 심화 또는 장기 보유 포지션 수</div>
              </div>
              <div className={`summary-metric-card ${todayFailCount > 0 ? 'is-bad' : 'is-good'}`}>
                <div className="summary-metric-label">오늘 주문</div>
                <div className="summary-metric-value">{todayBuyCount} / {todaySellCount} / {todayFailCount}</div>
                <div className="summary-metric-detail">매수 / 매도 / 실패</div>
              </div>
              <div className={`summary-metric-card ${trustTone === 'good' ? 'is-good' : trustTone === 'bad' ? 'is-bad' : ''}`}>
                <div className="summary-metric-label">엔진 신뢰도</div>
                <div className="summary-metric-value">{trustState} ({trustScore})</div>
                <div className="summary-metric-detail">최근 오류 {engineState.last_error ? '있음' : '없음'} · validation gate {engineState.validation_policy?.validation_gate_enabled ? '활성' : '비활성'}</div>
              </div>
            </div>
          </div>

          <div className="validation-report-grid">
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
              <div className="section-title">오늘 집행 결과</div>
              <div className="detail-list">
                <div>오늘 체결: {formatNumber(todayOrders.length, 0)}건</div>
                <div>매수 체결: {formatCount(todayBuyCount, '건')}</div>
                <div>매도 체결: {formatCount(todaySellCount, '건')}</div>
                <div>순증가 포지션: {formatCount(todayBuyCount - todaySellCount, '건')}</div>
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

          <div className="page-section" style={{ padding: 0, overflow: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1180 }}>
              <thead>
                <tr style={{ background: 'var(--bg-soft)', textAlign: 'left' }}>
                  <th style={{ padding: 12, fontSize: 12 }}>종목</th>
                  <th style={{ padding: 12, fontSize: 12 }}>시장</th>
                  <th style={{ padding: 12, fontSize: 12 }}>수량</th>
                  <th style={{ padding: 12, fontSize: 12 }}>진입가</th>
                  <th style={{ padding: 12, fontSize: 12 }}>현재가</th>
                  <th style={{ padding: 12, fontSize: 12 }}>평가손익</th>
                  <th style={{ padding: 12, fontSize: 12 }}>수익률</th>
                  <th style={{ padding: 12, fontSize: 12 }}>보유기간</th>
                  <th style={{ padding: 12, fontSize: 12 }}>손절가/손절률</th>
                  <th style={{ padding: 12, fontSize: 12 }}>익절가/익절률</th>
                  <th style={{ padding: 12, fontSize: 12 }}>전략 태그</th>
                  <th style={{ padding: 12, fontSize: 12 }}>상태</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((position) => {
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
                      <td style={{ padding: 12, fontSize: 12 }}>{String(position.market || '-')}</td>
                      <td style={{ padding: 12, fontSize: 12 }}>{formatCount(position.quantity, '주')}</td>
                      <td style={{ padding: 12, fontSize: 12 }}>{formatNumber(entryPrice, 2)}</td>
                      <td style={{ padding: 12, fontSize: 12 }}>{formatNumber(currentPrice, 2)}</td>
                      <td style={{ padding: 12, fontSize: 12, color: pnlKrw >= 0 ? 'var(--up)' : 'var(--down)' }}>{formatKRW(pnlKrw, true)}</td>
                      <td style={{ padding: 12, fontSize: 12, color: pnlPct >= 0 ? 'var(--up)' : 'var(--down)' }}>
                        {formatPercent(pnlPct, 2)}
                      </td>
                      <td style={{ padding: 12, fontSize: 12 }}>{formatNumber(holdingDays(position.entry_ts), 0)}일</td>
                      <td style={{ padding: 12, fontSize: 12 }}>
                        {Number.isFinite(stopLossPrice) ? formatNumber(stopLossPrice, 2) : '-'} / {formatPercent(stopLossPct, 2)}
                      </td>
                      <td style={{ padding: 12, fontSize: 12 }}>
                        {Number.isFinite(takeProfitPrice) ? formatNumber(takeProfitPrice, 2) : '-'} / {formatPercent(takeProfitPct, 2)}
                      </td>
                      <td style={{ padding: 12, fontSize: 12 }}>{strategyTag}</td>
                      <td style={{ padding: 12, fontSize: 12, fontWeight: 700 }}>보유</td>
                    </tr>
                  );
                })}
                {positions.length === 0 && (
                  <tr>
                    <td colSpan={12} style={{ padding: 16, fontSize: 12, color: 'var(--text-4)' }}>{UI_TEXT.empty.noPositions}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
            <div className="page-section" style={{ padding: 16 }}>
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
                <div>today 주문(B/S/F): {formatNumber(engineState.today_order_counts?.buy, 0)} / {formatNumber(engineState.today_order_counts?.sell, 0)} / {formatNumber(engineState.today_order_counts?.failed, 0)}</div>
                <div>today 실현손익: {formatKRW(engineState.today_realized_pnl, true)}</div>
                <div>validation gate: {engineState.validation_policy?.validation_gate_enabled ? '활성' : '비활성'}</div>
              </div>
            </div>

            <div className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 14, fontWeight: 700 }}>오늘 포지션 변화 요약</div>
              <div style={{ marginTop: 10, display: 'grid', gap: 6, fontSize: 12, color: 'var(--text-3)' }}>
                <div>오늘 체결: {formatNumber(todayOrders.length, 0)}건</div>
                <div>매수 체결: {formatCount(todayBuyCount, '건')}</div>
                <div>매도 체결: {formatCount(todaySellCount, '건')}</div>
                <div>순증가 포지션: {formatCount(todayBuyCount - todaySellCount, '건')}</div>
              </div>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 12 }}>
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
                    side?: string;
                    quantity?: number;
                    filled_price_local?: number;
                    success?: boolean;
                    failure_reason?: string;
                  };
                  const isSuccess = item.success !== false;
                  return (
                  <div key={item.order_id || `${item.code || 'order'}-${index}`} style={{ border: '1px solid var(--border)', borderRadius: 10, padding: '8px 10px', fontSize: 12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                      <span>{formatSymbol(item.code, item.name)}</span>
                      <span style={{ color: isSuccess ? (item.side === 'buy' ? 'var(--up)' : 'var(--down)') : 'var(--down)', fontWeight: 700 }}>
                        {isSuccess ? (item.side === 'buy' ? '매수' : '매도') : '실패'}
                      </span>
                    </div>
                    <div style={{ marginTop: 4, color: 'var(--text-3)' }}>
                      수량 {formatCount(item.quantity, '주')} · 체결가 {formatNumber(item.filled_price_local, 2)} · {formatDateTime(item.timestamp || item.ts)}
                    </div>
                    {!isSuccess && (
                      <div style={{ marginTop: 4, color: 'var(--down)' }}>실패 사유: {item.failure_reason || '-'}</div>
                    )}
                  </div>
                );})}
                {mergedOrderHistory.length === 0 && <div style={{ fontSize: 12, color: 'var(--text-4)' }}>{UI_TEXT.empty.noTrades}</div>}
              </div>
            </div>

            <div className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 14, fontWeight: 700 }}>최근 엔진 이벤트 로그</div>
              <div style={{ marginTop: 10, display: 'grid', gap: 8 }}>
                {Object.entries(skipReasonCounts).slice(0, 6).map(([reason, count]) => (
                  <div key={reason} style={{ fontSize: 12, color: 'var(--text-3)', border: '1px solid var(--border)', borderRadius: 10, padding: '8px 10px' }}>
                    {reason}: {formatCount(count, '건')}
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
