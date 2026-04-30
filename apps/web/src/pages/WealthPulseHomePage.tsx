import {
  getRiskGuardState,
  isRiskBlockedSignal,
  isRiskEntryAllowed,
} from '../adapters/consoleViewAdapter';
import {
  UI_TEXT,
  freshnessToKorean,
  providerSourceToKorean,
  providerStatusToKorean,
  reasonCodeToKorean,
  reliabilityToKorean,
} from '../constants/uiText';
import type { ConsoleSnapshot } from '../types/consoleView';
import type { DomainSignal } from '../types/domain';
import {
  explainSizeRecommendation,
  formatDateTime,
  formatDateTimeWithAge,
  formatKRW,
  formatNumber,
  formatPercent,
  formatSymbol,
  formatUSD,
} from '../utils/format';

interface WealthPulseHomePageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
  onGoLab: () => void;
  onGoAnalysis: () => void;
}

interface PositionView {
  key: string;
  symbol: string;
  market: string;
  quantity: number;
  marketValueKrw: number;
  unrealizedPnlKrw: number;
  unrealizedPnlPct: number | null;
}

interface BarRow {
  label: string;
  value: string;
  width: string;
  tone?: string;
}

interface FlowStep {
  layer: string;
  label: string;
  value: string;
  meta: string;
  tone: 'good' | 'bad' | 'neutral' | 'warning';
}

function toNumber(value: unknown): number {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : 0;
}

function toOptionalNumber(value: unknown): number | undefined {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : undefined;
}

function normalizePositionArray(raw: unknown): Array<Record<string, unknown>> {
  if (Array.isArray(raw)) return raw as Array<Record<string, unknown>>;
  if (raw && typeof raw === 'object') {
    return Object.values(raw as Record<string, unknown>)
      .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'));
  }
  return [];
}

function isUsMarket(raw: string): boolean {
  const market = raw.toUpperCase();
  return market === 'NASDAQ' || market === 'NYSE' || market === 'AMEX' || market === 'US';
}

function marketLabel(raw: string): 'KOSPI' | 'NASDAQ' | 'OTHER' {
  const market = raw.toUpperCase();
  if (market === 'KOSPI' || market === 'KOSDAQ') return 'KOSPI';
  if (isUsMarket(market)) return 'NASDAQ';
  return 'OTHER';
}

function ratio(value: number, total: number): number {
  if (total <= 0) return 0;
  return Math.max(0, Math.min(1, value / total));
}

function ratioPercent(value: number, total: number): string {
  return `${(ratio(value, total) * 100).toFixed(1)}%`;
}

function safePct(value: number | undefined): string {
  if (value == null) return '-';
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

function toneForNumber(value: number | undefined): string {
  if (value == null || value === 0) return 'is-neutral';
  return value > 0 ? 'is-up' : 'is-down';
}

function formatKRWCompact(value: number): string {
  if (!Number.isFinite(value)) return '-';
  const sign = value < 0 ? '-' : '';
  const abs = Math.abs(value);
  if (abs >= 100_000_000) return `${sign}${formatNumber(abs / 100_000_000, 1)}억`;
  if (abs >= 10_000) return `${sign}${formatNumber(abs / 10_000, 0)}만`;
  return formatKRW(value, true);
}

function formatSignedKRW(value: number): string {
  const prefix = value > 0 ? '+' : '';
  return `${prefix}${formatKRWCompact(value)}`;
}

function sessionTone(status: string | undefined): string {
  if (status === 'open') return 'is-success';
  if (status === 'pre_open') return 'is-warning';
  if (status === 'after_close') return 'is-neutral';
  return 'is-danger';
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? value as Record<string, unknown> : {};
}

function topRecordRows(record: unknown, limit = 4): BarRow[] {
  const entries = Object.entries(asRecord(record))
    .map(([key, value]) => ({ key, count: toNumber(value) }))
    .filter((item) => item.count > 0)
    .sort((left, right) => right.count - left.count)
    .slice(0, limit);
  const max = Math.max(...entries.map((item) => item.count), 1);
  return entries.map((item) => ({
    label: reasonCodeToKorean(item.key),
    value: formatNumber(item.count, 0),
    width: ratioPercent(item.count, max),
    tone: 'is-blocked',
  }));
}

function buildConicGradient(rows: Array<{ value: number; color: string }>): string {
  const total = rows.reduce((sum, row) => sum + Math.max(0, row.value), 0);
  if (total <= 0) return 'conic-gradient(var(--border-light) 0 100%)';

  let cursor = 0;
  const stops = rows
    .filter((row) => row.value > 0)
    .map((row) => {
      const start = cursor;
      cursor += (row.value / total) * 100;
      return `${row.color} ${start.toFixed(2)}% ${cursor.toFixed(2)}%`;
    });
  return `conic-gradient(${stops.join(', ')})`;
}

function marketTicker(label: string, price: number | undefined, pct: number | undefined) {
  return { label, price, pct };
}

export function WealthPulseHomePage({
  snapshot,
  loading,
  errorMessage,
  onRefresh,
  onGoLab,
  onGoAnalysis,
}: WealthPulseHomePageProps) {
  const engineState = snapshot.engine.execution?.state || {};
  const engineAccount = snapshot.engine.execution?.account || {};
  const portfolioAccount = snapshot.portfolio.account || engineAccount || {};
  const rawPositions = normalizePositionArray(portfolioAccount.positions || engineAccount.positions);
  const positions: PositionView[] = rawPositions
    .map((raw, index) => {
      const market = String(raw.market || '-').toUpperCase();
      const quantity = toNumber(raw.quantity);
      const marketValueKrw = toNumber(raw.market_value_krw) || (toNumber(raw.last_price_krw) * quantity);
      const unrealizedPnlKrw = toNumber(raw.unrealized_pnl_krw);
      const unrealizedPnlPct = toOptionalNumber(raw.unrealized_pnl_pct) ?? null;
      const code = String(raw.code || '');
      const name = String(raw.name || '');

      return {
        key: `${market}:${code}:${index}`,
        symbol: formatSymbol(code, name),
        market,
        quantity,
        marketValueKrw,
        unrealizedPnlKrw,
        unrealizedPnlPct,
      };
    })
    .sort((left, right) => right.marketValueKrw - left.marketValueKrw);

  const totalMarketValueKrw = positions.reduce((sum, item) => sum + item.marketValueKrw, 0);
  const totalUnrealizedPnlKrw = positions.reduce((sum, item) => sum + item.unrealizedPnlKrw, 0);
  const totalEquityKrw = toNumber(portfolioAccount.equity_krw) || toNumber(engineState.current_equity) || toNumber(engineAccount.equity_krw);
  const cashKrw = toNumber(portfolioAccount.cash_krw) || toNumber(engineAccount.cash_krw);
  const cashUsd = toNumber(portfolioAccount.cash_usd) || toNumber(engineAccount.cash_usd);
  const todayRealizedPnlKrw = toNumber(engineState.today_realized_pnl);
  const totalBookValueKrw = Math.max(totalEquityKrw, totalMarketValueKrw + cashKrw, 1);

  const kospiExposureKrw = positions
    .filter((item) => marketLabel(item.market) === 'KOSPI')
    .reduce((sum, item) => sum + item.marketValueKrw, 0);
  const nasdaqExposureKrw = positions
    .filter((item) => marketLabel(item.market) === 'NASDAQ')
    .reduce((sum, item) => sum + item.marketValueKrw, 0);
  const otherExposureKrw = Math.max(0, totalMarketValueKrw - kospiExposureKrw - nasdaqExposureKrw);
  const cashAllocationKrw = Math.max(0, totalBookValueKrw - totalMarketValueKrw);

  const allocator = snapshot.engine.allocator || {};
  const signals = snapshot.signals.signals || [];
  const allowedSignals = signals.filter((item) => item.entry_allowed);
  const blockedSignals = signals.filter(isRiskBlockedSignal);
  const totalAllowedSignals = Number(allocator.entry_allowed_count ?? allowedSignals.length);
  const totalBlockedSignals = Number(allocator.blocked_count ?? blockedSignals.length);
  const totalObserveSignals = Math.max(signals.length - totalAllowedSignals - totalBlockedSignals, 0);
  const totalSignalCount = Math.max(0, totalAllowedSignals + totalBlockedSignals + totalObserveSignals);
  const riskGuard = getRiskGuardState(snapshot);
  const riskGuardAllowed = isRiskEntryAllowed(snapshot);
  const riskReasons = Array.isArray(riskGuard.reasons) ? riskGuard.reasons.map((reason) => reasonCodeToKorean(String(reason))) : [];
  const validationSummary = snapshot.validation.summary || {};
  const validationReliability = reliabilityToKorean(String(validationSummary.oos_reliability || '').toLowerCase()) || '-';
  const engineRunning = Boolean(engineState.running);
  const engineStatusLabel = engineRunning ? 'RUN' : engineState.engine_state === 'paused' ? 'PAUSE' : engineState.engine_state === 'error' ? 'ERROR' : 'STOP';
  const failedOrders = toNumber(engineState.today_order_counts?.failed);
  const buyOrders = toNumber(engineState.today_order_counts?.buy);
  const sellOrders = toNumber(engineState.today_order_counts?.sell);
  const skippedCount = toNumber((engineState.last_summary as { skipped_count?: number } | undefined)?.skipped_count);
  const lastSummary = asRecord(engineState.last_summary);
  const blockedReasonRows = topRecordRows(lastSummary.blocked_reason_counts);
  const skipReasonRows = topRecordRows(lastSummary.skip_reason_counts);
  const reportGeneratedAt = snapshot.reports.generated_at || snapshot.reports.brief?.generated_at || '';

  const liveMarket = snapshot.liveMarket || {};
  const marketCtx = snapshot.marketContext || {};
  const marketSessions = liveMarket.market_sessions || {};
  const sessionCards = [marketSessions.KR, marketSessions.US].filter(Boolean);
  const tickers = [
    marketTicker('KOSPI', liveMarket.kospi, liveMarket.kospi_pct),
    marketTicker('KOSDAQ', liveMarket.kosdaq, liveMarket.kosdaq_pct),
    marketTicker('NASDAQ', liveMarket.nasdaq, liveMarket.nasdaq_pct),
    marketTicker('S&P100', liveMarket.sp100, liveMarket.sp100_pct),
    marketTicker('WTI', liveMarket.wti, liveMarket.wti_pct),
  ];

  const allocationRows: BarRow[] = [
    { label: 'CASH', value: ratioPercent(cashAllocationKrw, totalBookValueKrw), width: ratioPercent(cashAllocationKrw, totalBookValueKrw), tone: 'is-cash' },
    { label: 'KOSPI', value: ratioPercent(kospiExposureKrw, totalBookValueKrw), width: ratioPercent(kospiExposureKrw, totalBookValueKrw), tone: 'is-kospi' },
    { label: 'NASDAQ', value: ratioPercent(nasdaqExposureKrw, totalBookValueKrw), width: ratioPercent(nasdaqExposureKrw, totalBookValueKrw), tone: 'is-nasdaq' },
    { label: 'OTHER', value: ratioPercent(otherExposureKrw, totalBookValueKrw), width: ratioPercent(otherExposureKrw, totalBookValueKrw), tone: 'is-other' },
  ];
  const signalRows: BarRow[] = [
    { label: 'ENTRY', value: formatNumber(totalAllowedSignals, 0), width: ratioPercent(totalAllowedSignals, totalSignalCount || 1), tone: 'is-allowed' },
    { label: 'BLOCK', value: formatNumber(totalBlockedSignals, 0), width: ratioPercent(totalBlockedSignals, totalSignalCount || 1), tone: 'is-blocked' },
    { label: 'WATCH', value: formatNumber(totalObserveSignals, 0), width: ratioPercent(totalObserveSignals, totalSignalCount || 1), tone: 'is-watch' },
  ];
  const allocationGradient = buildConicGradient([
    { value: cashAllocationKrw, color: 'var(--text-4)' },
    { value: kospiExposureKrw, color: 'var(--gold)' },
    { value: nasdaqExposureKrw, color: 'var(--up)' },
    { value: otherExposureKrw, color: 'var(--silver)' },
  ]);
  const signalGradient = buildConicGradient([
    { value: totalAllowedSignals, color: 'var(--up)' },
    { value: totalBlockedSignals, color: 'var(--down)' },
    { value: totalObserveSignals, color: 'var(--silver)' },
  ]);

  const universeSymbolCount = (snapshot.universe.items || []).reduce((sum, item) => sum + toNumber(item.symbol_count), 0);
  const researchCoverage = toNumber(snapshot.research.coverage_count);
  const researchFresh = toNumber(snapshot.research.fresh_symbol_count);
  const researchAcceptRatio = toOptionalNumber(snapshot.research.accept_ratio);
  const flowSteps: FlowStep[] = [
    {
      layer: 'A',
      label: 'Universe',
      value: formatNumber(universeSymbolCount || signals.length, 0),
      meta: `${formatNumber(snapshot.universe.count || 0, 0)} sets`,
      tone: universeSymbolCount > 0 ? 'good' : 'neutral',
    },
    {
      layer: 'B',
      label: 'Quant',
      value: formatNumber(signals.length, 0),
      meta: `${formatNumber(totalSignalCount, 0)} signals`,
      tone: signals.length > 0 ? 'good' : 'neutral',
    },
    {
      layer: 'C',
      label: 'Research',
      value: formatNumber(researchFresh || researchCoverage, 0),
      meta: researchAcceptRatio == null ? freshnessToKorean(String(snapshot.research.freshness || 'missing')) : `${formatPercent(researchAcceptRatio, 1, true)} accept`,
      tone: researchFresh > 0 ? 'good' : snapshot.research.freshness === 'stale' ? 'warning' : 'neutral',
    },
    {
      layer: 'D',
      label: 'Risk Gate',
      value: riskGuardAllowed ? 'OPEN' : 'LOCK',
      meta: `${formatNumber(totalAllowedSignals, 0)} in / ${formatNumber(totalBlockedSignals, 0)} out`,
      tone: riskGuardAllowed ? 'good' : 'bad',
    },
    {
      layer: 'E',
      label: 'Execution',
      value: engineStatusLabel,
      meta: `${formatNumber(buyOrders, 0)} buy / ${formatNumber(sellOrders, 0)} sell / ${formatNumber(failedOrders, 0)} fail`,
      tone: failedOrders > 0 || engineState.engine_state === 'error' ? 'bad' : engineRunning ? 'good' : 'neutral',
    },
  ];

  const topSignals = [...signals]
    .sort((left, right) => {
      const allowedGap = Number(Boolean(right.entry_allowed)) - Number(Boolean(left.entry_allowed));
      if (allowedGap !== 0) return allowedGap;
      const evGap = toNumber(right.ev_metrics?.expected_value) - toNumber(left.ev_metrics?.expected_value);
      if (evGap !== 0) return evGap;
      return toNumber(right.score) - toNumber(left.score);
    })
    .slice(0, 8);
  const topPositions = positions.slice(0, 6);
  const researchSourceLabel = providerSourceToKorean(String(snapshot.research.source || snapshot.research.source_of_truth || ''))
    || providerStatusToKorean(String(snapshot.research.status || '-'))
    || '-';

  function signalActionLabel(signal: DomainSignal): string {
    if (signal.entry_allowed) return 'ENTRY';
    if (isRiskBlockedSignal(signal)) return 'BLOCK';
    const finalAction = String(signal.final_action || signal.final_action_snapshot?.final_action || '').toLowerCase();
    if (finalAction === 'watch_only') return 'WATCH';
    if (finalAction === 'do_not_touch') return 'SKIP';
    return 'WAIT';
  }

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell wealth-home-shell">
          <section className="page-section wealth-terminal-hero">
            <div className="wealth-terminal-topbar">
              <div className="wealth-terminal-brand">
                <span className={`wealth-status-dot ${engineRunning ? 'is-live' : ''}`} />
                <span>WealthPulse</span>
                <strong>{engineStatusLabel}</strong>
              </div>
              <div className="wealth-terminal-actions">
                <button className="ghost-button" onClick={onRefresh}>Refresh</button>
                <button className="ghost-button" onClick={onGoAnalysis}>Signals</button>
                <button className="ghost-button" onClick={onGoLab}>Lab</button>
              </div>
            </div>

            <div className="wealth-hero-grid">
              <div>
                <div className="wealth-kpi-label">TOTAL EQUITY</div>
                <div className="wealth-hero-number">{formatKRWCompact(totalEquityKrw)}</div>
                <div className="wealth-hero-subline">
                  <span>Cash {formatKRWCompact(cashKrw)}</span>
                  <span>USD {formatUSD(cashUsd, true)}</span>
                  <span>{formatDateTimeWithAge(snapshot.fetchedAt)}</span>
                </div>
              </div>
              <div className="wealth-hero-metrics">
                <div>
                  <span>Today P/L</span>
                  <strong className={toneForNumber(todayRealizedPnlKrw)}>{formatSignedKRW(todayRealizedPnlKrw)}</strong>
                </div>
                <div>
                  <span>Unrealized</span>
                  <strong className={toneForNumber(totalUnrealizedPnlKrw)}>{formatSignedKRW(totalUnrealizedPnlKrw)}</strong>
                </div>
                <div>
                  <span>Risk Gate</span>
                  <strong className={riskGuardAllowed ? 'is-up' : 'is-down'}>{riskGuardAllowed ? 'OPEN' : 'LOCKED'}</strong>
                </div>
                <div>
                  <span>OOS</span>
                  <strong>{validationReliability}</strong>
                </div>
              </div>
            </div>
            {!!errorMessage && <div className="wealth-home-error">{errorMessage}</div>}
          </section>

          <section className="page-section wealth-market-strip">
            <div className="wealth-ticker-grid">
              {tickers.map((item) => (
                <div key={item.label} className="wealth-ticker">
                  <span>{item.label}</span>
                  <strong>{item.price != null ? formatNumber(item.price, 2) : '-'}</strong>
                  <em className={toneForNumber(item.pct)}>{safePct(item.pct)}</em>
                </div>
              ))}
              <div className="wealth-ticker">
                <span>USD/KRW</span>
                <strong>{liveMarket.usd_krw != null ? formatNumber(liveMarket.usd_krw, 0) : '-'}</strong>
                <em>{liveMarket.updated_at ? 'LIVE' : '-'}</em>
              </div>
            </div>
            {sessionCards.length > 0 && (
              <div className="wealth-session-row">
                {sessionCards.map((session) => (
                  <div
                    key={String(session.label || session.status || session.local_time || '-')}
                    className={`inline-badge ${sessionTone(session.status)}`}
                  >
                    {session.label || '-'} {session.status_label || '-'} {session.local_time || '-'}
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="page-section wealth-dashboard-grid">
            <div className="wealth-chart-panel">
              <div className="section-head-row">
                <div>
                  <div className="section-title">Portfolio</div>
                  <div className="section-copy">positions {formatNumber(positions.length, 0)} · market {formatKRWCompact(totalMarketValueKrw)}</div>
                </div>
              </div>
              <div className="wealth-chart-body">
                <div className="wealth-donut" style={{ background: allocationGradient }}>
                  <div>
                    <strong>{ratioPercent(totalMarketValueKrw, totalBookValueKrw)}</strong>
                    <span>Invested</span>
                  </div>
                </div>
                <div className="wealth-bars">
                  {allocationRows.map((item) => (
                    <div key={item.label} className="wealth-bar-row">
                      <div className="wealth-bar-label">{item.label}</div>
                      <div className="wealth-bar-track"><div className={`wealth-bar-fill ${item.tone || ''}`.trim()} style={{ width: item.width }} /></div>
                      <div className="wealth-bar-value">{item.value}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="wealth-chart-panel">
              <div className="section-head-row">
                <div>
                  <div className="section-title">Signals</div>
                  <div className="section-copy">regime {allocator.regime || snapshot.signals.regime || '-'} · risk {allocator.risk_level || snapshot.signals.risk_level || '-'}</div>
                </div>
              </div>
              <div className="wealth-chart-body">
                <div className="wealth-donut" style={{ background: signalGradient }}>
                  <div>
                    <strong>{formatNumber(totalSignalCount, 0)}</strong>
                    <span>Total</span>
                  </div>
                </div>
                <div className="wealth-bars">
                  {signalRows.map((item) => (
                    <div key={item.label} className="wealth-bar-row">
                      <div className="wealth-bar-label">{item.label}</div>
                      <div className="wealth-bar-track"><div className={`wealth-bar-fill ${item.tone || ''}`.trim()} style={{ width: item.width }} /></div>
                      <div className="wealth-bar-value">{item.value}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </section>

          <section className="page-section">
            <div className="section-head-row">
              <div>
                <div className="section-title">Engine Flow</div>
                <div className="section-copy">API layers A-E · latest cycle {String(engineState.latest_cycle_id || '-')}</div>
              </div>
              <div className="inline-badge">{engineState.last_success_at ? formatDateTime(engineState.last_success_at) : 'no cycle'}</div>
            </div>
            <div className="wealth-flow-grid">
              {flowSteps.map((step) => (
                <div key={step.layer} className={`wealth-flow-step is-${step.tone}`}>
                  <span>{step.layer}</span>
                  <div>{step.label}</div>
                  <strong>{step.value}</strong>
                  <em>{step.meta}</em>
                </div>
              ))}
            </div>
          </section>

          <section className="page-section wealth-dashboard-grid">
            <div className="wealth-chart-panel">
              <div className="section-head-row">
                <div>
                  <div className="section-title">Risk</div>
                  <div className="section-copy">{riskReasons.slice(0, 2).join(' · ') || 'no active guard reason'}</div>
                </div>
                <div className={riskGuardAllowed ? 'inline-badge is-success' : 'inline-badge is-danger'}>
                  {riskGuardAllowed ? 'ENTRY ON' : 'ENTRY OFF'}
                </div>
              </div>
              <div className="wealth-data-list">
                <div className={`wealth-data-row ${failedOrders > 0 ? 'is-bad' : 'is-good'}`.trim()}>
                  <div className="wealth-data-label">FAIL/SKIP</div>
                  <div className="wealth-data-main">{formatNumber(failedOrders, 0)} / {formatNumber(skippedCount, 0)}</div>
                  <div className="wealth-data-meta">{String(engineState.order_failure_summary?.top_reason || '-')}</div>
                </div>
                <div className={`wealth-data-row ${engineState.optimized_params?.is_stale ? 'is-bad' : 'is-good'}`.trim()}>
                  <div className="wealth-data-label">PARAMS</div>
                  <div className="wealth-data-main">{engineState.optimized_params?.is_stale ? 'STALE' : 'OK'}</div>
                  <div className="wealth-data-meta">{String(engineState.optimized_params?.effective_source || engineState.optimized_params?.source || '-')}</div>
                </div>
                <div className="wealth-data-row is-good">
                  <div className="wealth-data-label">RESEARCH</div>
                  <div className="wealth-data-main">{freshnessToKorean(String(snapshot.research.freshness || 'missing'))}</div>
                  <div className="wealth-data-meta">{researchSourceLabel} · fresh {formatNumber(researchFresh, 0)} / coverage {formatNumber(researchCoverage, 0)}</div>
                </div>
              </div>
            </div>

            <div className="wealth-chart-panel">
              <div className="section-head-row">
                <div>
                  <div className="section-title">Blocks</div>
                  <div className="section-copy">blocked reason distribution</div>
                </div>
              </div>
              <div className="wealth-bars wealth-reason-bars">
                {(blockedReasonRows.length > 0 ? blockedReasonRows : skipReasonRows).map((item) => (
                  <div key={item.label} className="wealth-bar-row">
                    <div className="wealth-bar-label">{item.label}</div>
                    <div className="wealth-bar-track"><div className={`wealth-bar-fill ${item.tone || ''}`.trim()} style={{ width: item.width }} /></div>
                    <div className="wealth-bar-value">{item.value}</div>
                  </div>
                ))}
                {blockedReasonRows.length === 0 && skipReasonRows.length === 0 && (
                  <div className="wealth-empty-line">no block histogram</div>
                )}
              </div>
            </div>
          </section>

          <section className="page-section">
            <div className="section-head-row">
              <div>
                <div className="section-title">Signal Board</div>
                <div className="section-copy">ranked by entry permission, EV, score</div>
              </div>
              <div className="inline-badge">{reportGeneratedAt ? formatDateTimeWithAge(reportGeneratedAt) : 'report idle'}</div>
            </div>
            <div className="wealth-table">
              <div className="wealth-table-row is-head">
                <span>Symbol</span>
                <span>Action</span>
                <span>Score</span>
                <span>EV</span>
                <span>Win</span>
                <span>Size</span>
              </div>
              {topSignals.map((signal, index) => (
                <div key={`signal-${signal.market || ''}-${signal.code || ''}-${index}`} className="wealth-table-row">
                  <span>
                    <strong>{formatSymbol(signal.code, signal.name)}</strong>
                    <em>{signal.market || '-'} · {signal.strategy_type || '-'}</em>
                  </span>
                  <span className={signal.entry_allowed ? 'is-up' : isRiskBlockedSignal(signal) ? 'is-down' : 'is-neutral'}>{signalActionLabel(signal)}</span>
                  <span>{formatNumber(signal.score ?? signal.quant_score, 1)}</span>
                  <span>{formatNumber(signal.ev_metrics?.expected_value, 2)}</span>
                  <span>{formatPercent(signal.ev_metrics?.win_probability, 1, true)}</span>
                  <span>{explainSizeRecommendation(signal.size_recommendation)}</span>
                </div>
              ))}
              {topSignals.length === 0 && <div className="wealth-empty-line">{UI_TEXT.empty.signalsNoMatches}</div>}
            </div>
          </section>

          <section className="page-section">
            <div className="section-head-row">
              <div>
                <div className="section-title">Positions</div>
                <div className="section-copy">largest live exposures</div>
              </div>
            </div>
            <div className="wealth-table is-positions">
              <div className="wealth-table-row is-head">
                <span>Symbol</span>
                <span>Market</span>
                <span>Qty</span>
                <span>Value</span>
                <span>P/L</span>
              </div>
              {topPositions.map((position) => (
                <div key={position.key} className="wealth-table-row">
                  <span><strong>{position.symbol}</strong></span>
                  <span>{position.market}</span>
                  <span>{formatNumber(position.quantity, 0)}</span>
                  <span>{formatKRWCompact(position.marketValueKrw)}</span>
                  <span className={toneForNumber(position.unrealizedPnlKrw)}>
                    {formatSignedKRW(position.unrealizedPnlKrw)}
                    {position.unrealizedPnlPct == null ? '' : ` · ${safePct(position.unrealizedPnlPct)}`}
                  </span>
                </div>
              ))}
              {topPositions.length === 0 && <div className="wealth-empty-line">no positions</div>}
            </div>
          </section>

          {(marketCtx.regime || marketCtx.risk_level || marketCtx.summary) && (
            <section className="page-section wealth-context-strip">
              <div className="wealth-context-item"><span>Regime</span><strong>{marketCtx.regime || allocator.regime || '-'}</strong></div>
              <div className="wealth-context-item"><span>Risk</span><strong>{marketCtx.risk_level || allocator.risk_level || '-'}</strong></div>
              <div className="wealth-context-item"><span>Inflation</span><strong>{marketCtx.inflation_signal || '-'}</strong></div>
              <div className="wealth-context-item"><span>Policy</span><strong>{marketCtx.policy_signal || '-'}</strong></div>
              <div className="wealth-context-item"><span>Dollar</span><strong>{marketCtx.dollar_signal || '-'}</strong></div>
            </section>
          )}

          {loading && <div className="wealth-home-muted">{UI_TEXT.common.loading}</div>}
        </div>
      </div>
    </div>
  );
}
