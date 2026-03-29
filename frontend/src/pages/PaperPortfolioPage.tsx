import { useCallback, useMemo, useState } from 'react';
import { ConsoleActionBar } from '../components/ConsoleActionBar';
import { UI_TEXT } from '../constants/uiText';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import { usePaperTrading } from '../hooks/usePaperTrading';
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

export function PaperPortfolioPage({ snapshot, loading, errorMessage, onRefresh }: PaperPortfolioPageProps) {
  const { entries, push, clear } = useConsoleLogs();
  const [settings, setSettings] = useState<PaperSettings>(() => readSettings());
  const [pendingAction, setPendingAction] = useState<'engine-toggle' | 'reset' | null>(null);
  const {
    account,
    engineState,
    status,
    lastError,
    refresh,
    reset,
    refreshEngineStatus,
    startEngine,
    stopEngine,
  } = usePaperTrading();

  const positions = account.positions || [];
  const orders = [...(account.orders || [])].sort((a, b) => String(b.ts || '').localeCompare(String(a.ts || '')));

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

  const statusItems = useMemo<ActionBarStatusItem[]>(() => ([
    {
      label: '엔진 상태',
      value: engineState.running ? UI_TEXT.status.running : UI_TEXT.status.stopped,
      tone: engineState.running ? 'good' : 'bad',
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
  ]), [engineState.running, snapshot.portfolio.risk_guard_state?.entry_allowed, status, vm.positionCount]);

  const handleRefreshAll = useCallback(async () => {
    onRefresh();
    await Promise.all([refresh(true), refreshEngineStatus()]);
    push('info', '모의투자 데이터와 콘솔 스냅샷을 새로고침했습니다.');
  }, [onRefresh, push, refresh, refreshEngineStatus]);

  const handleStartStop = useCallback(async () => {
    setPendingAction('engine-toggle');
    try {
      if (engineState.running) {
        const result = await stopEngine();
        if (!result.ok) {
          push('error', '모의투자 엔진 중지에 실패했습니다.', result.error || '');
          return;
        }
        push('success', '모의투자 엔진을 중지했습니다.');
      } else {
        const markets: Array<'KOSPI' | 'NASDAQ'> = [];
        if (settings.runKospi) markets.push('KOSPI');
        if (settings.runNasdaq) markets.push('NASDAQ');
        if (markets.length === 0) {
          push('warning', '시장 선택이 필요합니다.', '설정에서 KOSPI 또는 NASDAQ을 최소 1개 선택하세요.');
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
          push('error', '모의투자 엔진 시작에 실패했습니다.', result.error || '');
          return;
        }
        push('success', '모의투자 엔진을 시작했습니다.', `시장: ${markets.join(', ')}`);
      }
      await Promise.all([refresh(true), refreshEngineStatus()]);
    } finally {
      setPendingAction(null);
    }
  }, [
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
    startEngine,
    stopEngine,
  ]);

  const handleReset = useCallback(async () => {
    setPendingAction('reset');
    try {
      const result = await reset({
        initial_cash_krw: settings.initialCashKrw,
        initial_cash_usd: settings.initialCashUsd,
        paper_days: settings.paperDays,
      });
      if (!result.ok) {
        push('error', '모의투자 초기화에 실패했습니다.', result.error || '');
        return;
      }
      push(
        'success',
        '모의투자 계좌를 초기화했습니다.',
        `초기자금 KRW ${formatKRW(settings.initialCashKrw, true)} / USD ${formatUSD(settings.initialCashUsd, true)}`,
      );
      await Promise.all([refresh(true), refreshEngineStatus()]);
    } finally {
      setPendingAction(null);
    }
  }, [push, refresh, refreshEngineStatus, reset, settings.initialCashKrw, settings.initialCashUsd, settings.paperDays]);

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
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>최대 포지션 수</span>
        <input
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          type="number"
          value={settings.maxPositions}
          onChange={(event) => setSettings((prev) => ({ ...prev, maxPositions: Math.max(1, Number(event.target.value) || 1) }))}
        />
      </label>
      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>일일 매수 제한</span>
        <input
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          type="number"
          value={settings.dailyBuyLimit}
          onChange={(event) => setSettings((prev) => ({ ...prev, dailyBuyLimit: Math.max(1, Number(event.target.value) || 1) }))}
        />
      </label>
      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>일일 매도 제한</span>
        <input
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          type="number"
          value={settings.dailySellLimit}
          onChange={(event) => setSettings((prev) => ({ ...prev, dailySellLimit: Math.max(1, Number(event.target.value) || 1) }))}
        />
      </label>
      <label style={{ display: 'grid', gap: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>종목당 일일 주문 제한</span>
        <input
          className="backtest-input-wrap"
          style={{ padding: '0 12px' }}
          type="number"
          value={settings.maxOrdersPerSymbol}
          onChange={(event) => setSettings((prev) => ({ ...prev, maxOrdersPerSymbol: Math.max(1, Number(event.target.value) || 1) }))}
        />
      </label>
      <button
        className="console-action-button is-primary"
        onClick={() => {
          saveSettings(settings);
          push('success', '모의투자 설정을 저장했습니다.');
        }}
      >
        설정 저장
      </button>
    </div>
  );

  const stopLossPctDefault = toNumber(engineState.config?.stop_loss_pct, NaN);
  const takeProfitPctDefault = toNumber(engineState.config?.take_profit_pct, NaN);
  const skipReasonCounts = engineState.last_summary?.skip_reason_counts || {};

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
            actions={[
              {
                label: engineState.running ? '엔진 중지' : '엔진 시작',
                onClick: () => { void handleStartStop(); },
                tone: engineState.running ? 'danger' : 'primary',
                busy: pendingAction === 'engine-toggle',
                busyLabel: engineState.running ? '중지 중...' : '시작 중...',
                confirmTitle: engineState.running ? UI_TEXT.confirm.stopEngineTitle : UI_TEXT.confirm.startEngineTitle,
                confirmMessage: engineState.running ? UI_TEXT.confirm.stopEngineMessage : UI_TEXT.confirm.startEngineMessage,
              },
              {
                label: '모의투자 초기화',
                onClick: () => { void handleReset(); },
                tone: 'danger',
                busy: pendingAction === 'reset',
                busyLabel: '초기화 중...',
                confirmTitle: UI_TEXT.confirm.resetPaperTitle,
                confirmMessage: UI_TEXT.confirm.resetPaperMessage,
              },
            ]}
            settingsPanel={settingsPanel}
          />

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 10 }}>
            <div className="page-section" style={{ padding: 14 }}>
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>총자산(원화환산)</div>
              <div style={{ marginTop: 8, fontSize: 20, fontWeight: 800 }}>{formatKRW(vm.totalEquityKrw, true)}</div>
            </div>
            <div className="page-section" style={{ padding: 14 }}>
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>원화 현금</div>
              <div style={{ marginTop: 8, fontSize: 20, fontWeight: 800 }}>{formatKRW(vm.cashKrw, true)}</div>
            </div>
            <div className="page-section" style={{ padding: 14 }}>
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>달러 현금</div>
              <div style={{ marginTop: 8, fontSize: 20, fontWeight: 800 }}>{formatUSD(vm.cashUsd, true)}</div>
            </div>
            <div className="page-section" style={{ padding: 14 }}>
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>평가손익</div>
              <div style={{ marginTop: 8, fontSize: 20, fontWeight: 800, color: vm.unrealizedPnlKrw >= 0 ? 'var(--up)' : 'var(--down)' }}>
                {formatKRW(vm.unrealizedPnlKrw, true)}
              </div>
            </div>
            <div className="page-section" style={{ padding: 14 }}>
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>실현손익</div>
              <div style={{ marginTop: 8, fontSize: 20, fontWeight: 800, color: vm.realizedPnlKrw >= 0 ? 'var(--up)' : 'var(--down)' }}>
                {formatKRW(vm.realizedPnlKrw, true)}
              </div>
            </div>
            <div className="page-section" style={{ padding: 14 }}>
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>보유 포지션 수</div>
              <div style={{ marginTop: 8, fontSize: 20, fontWeight: 800 }}>{formatCount(vm.positionCount, '종목')}</div>
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
                <div>상태: {engineState.running ? UI_TEXT.status.running : UI_TEXT.status.stopped}</div>
                <div>상태 사유: {engineState.last_error ? '최근 오류 발생' : (engineState.running ? '정상 실행 중' : '대기 중')}</div>
                <div>최근 실행 시각: {formatDateTime(engineState.last_run_at)}</div>
                <div>최근 오류: {engineState.last_error || '-'}</div>
                <div>
                  최근 실행 요약: 매수 {formatNumber(engineState.last_summary?.executed_buy_count, 0)}건 / 매도 {formatNumber(engineState.last_summary?.executed_sell_count, 0)}건
                </div>
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
                {orders.slice(0, 10).map((order) => (
                  <div key={order.order_id} style={{ border: '1px solid var(--border)', borderRadius: 10, padding: '8px 10px', fontSize: 12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                      <span>{formatSymbol(order.code, order.name)}</span>
                      <span style={{ color: order.side === 'buy' ? 'var(--up)' : 'var(--down)', fontWeight: 700 }}>
                        {order.side === 'buy' ? '매수' : '매도'}
                      </span>
                    </div>
                    <div style={{ marginTop: 4, color: 'var(--text-3)' }}>
                      수량 {formatCount(order.quantity, '주')} · 체결가 {formatNumber(order.filled_price_local, 2)} · {formatDateTime(order.ts)}
                    </div>
                  </div>
                ))}
                {orders.length === 0 && <div style={{ fontSize: 12, color: 'var(--text-4)' }}>{UI_TEXT.empty.noTrades}</div>}
              </div>
            </div>

            <div className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 14, fontWeight: 700 }}>최근 엔진 이벤트 로그</div>
              <div style={{ marginTop: 10, display: 'grid', gap: 8 }}>
                {Object.entries(skipReasonCounts).slice(0, 8).map(([reason, count]) => (
                  <div key={reason} style={{ fontSize: 12, color: 'var(--text-3)', border: '1px solid var(--border)', borderRadius: 10, padding: '8px 10px' }}>
                    {reason}: {formatCount(count, '건')}
                  </div>
                ))}
                {Object.keys(skipReasonCounts).length === 0 && (
                  <div style={{ fontSize: 12, color: 'var(--text-4)' }}>{UI_TEXT.empty.noSkipReasons}</div>
                )}
              </div>
            </div>
          </div>

          {loading && <div style={{ color: 'var(--text-3)', fontSize: 12 }}>{UI_TEXT.common.loading}</div>}
        </div>
      </div>
    </div>
  );
}
