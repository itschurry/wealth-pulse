import {
  getRiskGuardState,
  isRiskEntryAllowed,
} from '../adapters/consoleViewAdapter';
import {
  UI_TEXT,
  freshnessToKorean,
  providerSourceToKorean,
  providerStatusToKorean,
  reasonCodeToKorean,
} from '../constants/uiText';
import type { ConsoleSnapshot } from '../types/consoleView';
import {
  formatDateTime,
  formatDateTimeWithAge,
  formatKRW,
  formatNumber,
  formatPercent,
  formatSymbol,
} from '../utils/format';

interface WealthPulseHomePageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
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
  meta?: string;
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

interface IndexHistoryPoint {
  date?: string;
  close?: number;
  pct?: number;
}

interface IndexChartPoint extends IndexHistoryPoint {
  close: number;
  x: number;
  y: number;
  dateLabel: string;
}

interface IndexChart {
  path: string;
  points: IndexChartPoint[];
  min: number;
  max: number;
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

function marketLabel(raw: string): 'KOSPI' | 'OTHER' {
  const market = raw.toUpperCase();
  if (market === 'KOSPI' || market === 'KOSDAQ') return 'KOSPI';
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

function formatKRWExact(value: number): string {
  if (!Number.isFinite(value)) return '-';
  return formatKRW(Math.round(value), true);
}

function formatSignedKRWExact(value: number): string {
  const prefix = value > 0 ? '+' : '';
  return `${prefix}${formatKRWExact(value)}`;
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

function formatIndexDate(value: string | undefined): string {
  if (!value) return '-';
  return value.slice(5).replace('-', '/');
}

function buildIndexChart(points: IndexHistoryPoint[], width = 720, chartTop = 42, chartBottom = 112): IndexChart | null {
  const values = points
    .map((point) => ({ ...point, close: toOptionalNumber(point.close) }))
    .filter((point): point is IndexHistoryPoint & { close: number } => point.close != null);
  if (values.length < 2) return null;

  const closes = values.map((point) => point.close);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const spread = max - min || 1;
  const paddingX = 18;
  const step = (width - paddingX * 2) / Math.max(values.length - 1, 1);
  const chartHeight = chartBottom - chartTop;

  const chartPoints = values.map((point, index) => {
    const x = paddingX + index * step;
    const y = chartTop + (1 - ((point.close - min) / spread)) * chartHeight;
    return {
      ...point,
      x,
      y,
      dateLabel: formatIndexDate(point.date),
    };
  });

  return {
    path: chartPoints.map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(' '),
    points: chartPoints,
    min,
    max,
  };
}

export function WealthPulseHomePage({
  snapshot,
  loading,
  errorMessage,
  onRefresh,
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
  const todayRealizedPnlKrw = toNumber(engineState.today_realized_pnl);
  const totalBookValueKrw = Math.max(totalEquityKrw, totalMarketValueKrw + cashKrw, 1);
  const livePerformance = snapshot.performance.live || {};
  const totalReturnPct = toOptionalNumber(livePerformance.total_return_pct);
  const positionReturnPct = toOptionalNumber(livePerformance.position_return_pct);
  const positionReturnKrwPct = toOptionalNumber(livePerformance.position_return_pct_krw);
  const startingEquityKrw = toNumber(livePerformance.starting_equity_krw);
  const performanceEquityKrw = toNumber(livePerformance.equity_krw) || totalEquityKrw;
  const positionCostKrw = toNumber(livePerformance.position_cost_krw) || Math.max(0, totalMarketValueKrw - totalUnrealizedPnlKrw);
  const positionMarketValueKrw = toNumber(livePerformance.position_market_value_krw) || totalMarketValueKrw;
  const positionUnrealizedKrwOnly = toNumber(livePerformance.position_unrealized_pnl_krw_only);

  const kospiExposureKrw = positions
    .filter((item) => marketLabel(item.market) === 'KOSPI')
    .reduce((sum, item) => sum + item.marketValueKrw, 0);
  const otherExposureKrw = Math.max(0, totalMarketValueKrw - kospiExposureKrw);
  const cashAllocationKrw = Math.max(0, totalBookValueKrw - totalMarketValueKrw);

  const allocator = snapshot.engine.allocator || {};
  const signals = snapshot.signals.signals || [];
  const totalAllowedSignals = Number(allocator.entry_allowed_count ?? 0);
  const totalBlockedSignals = Number(allocator.blocked_count ?? 0);
  const totalObserveSignals = Math.max(signals.length - totalAllowedSignals - totalBlockedSignals, 0);
  const totalSignalCount = Math.max(0, totalAllowedSignals + totalBlockedSignals + totalObserveSignals);
  const riskGuard = getRiskGuardState(snapshot);
  const riskGuardAllowed = isRiskEntryAllowed(snapshot);
  const riskReasons = Array.isArray(riskGuard.reasons) ? riskGuard.reasons.map((reason) => reasonCodeToKorean(String(reason))) : [];
  const engineRunning = Boolean(engineState.running);
  const engineStatusLabel = engineRunning ? '실행' : engineState.engine_state === 'paused' ? '일시정지' : engineState.engine_state === 'error' ? '오류' : '정지';
  const failedOrders = toNumber(engineState.today_order_counts?.failed);
  const buyOrders = toNumber(engineState.today_order_counts?.buy);
  const sellOrders = toNumber(engineState.today_order_counts?.sell);
  const skippedCount = toNumber((engineState.last_summary as { skipped_count?: number } | undefined)?.skipped_count);
  const lastSummary = asRecord(engineState.last_summary);
  const blockedReasonRows = topRecordRows(lastSummary.blocked_reason_counts);
  const skipReasonRows = topRecordRows(lastSummary.skip_reason_counts);

  const liveMarket = snapshot.liveMarket || {};
  const marketCtx = snapshot.marketContext || {};
  const marketSessions = liveMarket.market_sessions || {};
  const sessionCards = [marketSessions.KR].filter(Boolean);
  const tickers = [
    marketTicker('KOSPI', liveMarket.kospi, liveMarket.kospi_pct),
    marketTicker('KOSDAQ', liveMarket.kosdaq, liveMarket.kosdaq_pct),
    marketTicker('NASDAQ', liveMarket.nasdaq, liveMarket.nasdaq_pct),
    marketTicker('S&P100', liveMarket.sp100, liveMarket.sp100_pct),
    marketTicker('WTI', liveMarket.wti, liveMarket.wti_pct),
  ];
  const kospiHistory = Array.isArray(liveMarket.kospi_history) ? liveMarket.kospi_history : [];
  const kospiChart = buildIndexChart(kospiHistory);
  const kospiFirst = kospiHistory[0]?.close;
  const kospiLast = kospiHistory[kospiHistory.length - 1]?.close;
  const kospiTrendPct = kospiFirst && kospiLast ? ((kospiLast - kospiFirst) / kospiFirst) * 100 : undefined;
  const kospiRange = kospiHistory.length > 0
    ? `${kospiHistory[0]?.date || '-'} → ${kospiHistory[kospiHistory.length - 1]?.date || '-'}`
    : '-';

  const allocationRows: BarRow[] = [
    { label: '현금', value: formatKRWExact(cashAllocationKrw), meta: ratioPercent(cashAllocationKrw, totalBookValueKrw), width: ratioPercent(cashAllocationKrw, totalBookValueKrw), tone: 'is-cash' },
    { label: 'KOSPI', value: formatKRWExact(kospiExposureKrw), meta: ratioPercent(kospiExposureKrw, totalBookValueKrw), width: ratioPercent(kospiExposureKrw, totalBookValueKrw), tone: 'is-kospi' },
    { label: '기타', value: formatKRWExact(otherExposureKrw), meta: ratioPercent(otherExposureKrw, totalBookValueKrw), width: ratioPercent(otherExposureKrw, totalBookValueKrw), tone: 'is-other' },
  ];
  const allocationGradient = buildConicGradient([
    { value: cashAllocationKrw, color: 'var(--text-4)' },
    { value: kospiExposureKrw, color: 'var(--gold)' },
    { value: otherExposureKrw, color: 'var(--silver)' },
  ]);
  const universeSymbolCount = (snapshot.universe.items || []).reduce((sum, item) => sum + toNumber(item.symbol_count), 0);
  const researchCoverage = toNumber(snapshot.research.coverage_count);
  const researchFresh = toNumber(snapshot.research.fresh_symbol_count);
  const researchAcceptRatio = toOptionalNumber(snapshot.research.accept_ratio);
  const flowSteps: FlowStep[] = [
    {
      layer: 'A',
      label: '종목군',
      value: formatNumber(universeSymbolCount || signals.length, 0),
      meta: `${formatNumber(snapshot.universe.count || 0, 0)}개`,
      tone: universeSymbolCount > 0 ? 'good' : 'neutral',
    },
    {
      layer: 'B',
      label: '퀀트',
      value: formatNumber(signals.length, 0),
      meta: `${formatNumber(totalSignalCount, 0)}건`,
      tone: signals.length > 0 ? 'good' : 'neutral',
    },
    {
      layer: 'C',
      label: '리서치',
      value: formatNumber(researchFresh || researchCoverage, 0),
      meta: researchAcceptRatio == null ? freshnessToKorean(String(snapshot.research.freshness || 'missing')) : `수락 ${formatPercent(researchAcceptRatio, 1, true)}`,
      tone: researchFresh > 0 ? 'good' : snapshot.research.freshness === 'stale' ? 'warning' : 'neutral',
    },
    {
      layer: 'D',
      label: '리스크',
      value: riskGuardAllowed ? '열림' : '잠김',
      meta: `허용 ${formatNumber(totalAllowedSignals, 0)} / 차단 ${formatNumber(totalBlockedSignals, 0)}`,
      tone: riskGuardAllowed ? 'good' : 'bad',
    },
    {
      layer: 'E',
      label: '실행',
      value: engineStatusLabel,
      meta: `매수 ${formatNumber(buyOrders, 0)} / 매도 ${formatNumber(sellOrders, 0)} / 실패 ${formatNumber(failedOrders, 0)}`,
      tone: failedOrders > 0 || engineState.engine_state === 'error' ? 'bad' : engineRunning ? 'good' : 'neutral',
    },
  ];

  const researchSourceLabel = providerSourceToKorean(String(snapshot.research.source || snapshot.research.source_of_truth || ''))
    || providerStatusToKorean(String(snapshot.research.status || '-'))
    || '-';

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
                <button className="ghost-button" onClick={onRefresh}>새로고침</button>
              </div>
            </div>

            <div className="wealth-hero-grid">
              <div>
                <div className="wealth-kpi-label">총자산</div>
                <div className="wealth-hero-number">{formatKRWExact(totalEquityKrw)}</div>
                <div className="wealth-hero-subline">
                  <span>원화 현금 {formatKRWExact(cashKrw)}</span>
                  <span>{formatDateTimeWithAge(snapshot.fetchedAt)}</span>
                </div>
              </div>
              <div className="wealth-hero-metrics">
                <div>
                  <span>오늘 손익</span>
                  <strong className={toneForNumber(todayRealizedPnlKrw)}>{formatSignedKRWExact(todayRealizedPnlKrw)}</strong>
                </div>
                <div>
                  <span>평가손익</span>
                  <strong className={toneForNumber(totalUnrealizedPnlKrw)}>{formatSignedKRWExact(totalUnrealizedPnlKrw)}</strong>
                </div>
                <div>
                  <span>리스크</span>
                  <strong className={riskGuardAllowed ? 'is-up' : 'is-down'}>{riskGuardAllowed ? '열림' : '잠김'}</strong>
                </div>
                <div>
                  <span>리서치</span>
                  <strong>{researchSourceLabel}</strong>
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
                <span>달러/원</span>
                <strong>{liveMarket.usd_krw != null ? formatNumber(liveMarket.usd_krw, 0) : '-'}</strong>
                <em>{liveMarket.updated_at ? '시장 흐름' : '-'}</em>
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
            <div className="wealth-index-sparkline">
              <div>
                <span>KOSPI 10거래일</span>
                <strong>{liveMarket.kospi != null ? formatNumber(liveMarket.kospi, 2) : '-'}</strong>
                <em className={toneForNumber(kospiTrendPct)}>
                  {kospiHistory.length > 1 ? `${safePct(kospiTrendPct)} · ${kospiRange}` : '-'}
                </em>
                {kospiChart && (
                  <small>
                    저점 {formatNumber(kospiChart.min, 2)} / 고점 {formatNumber(kospiChart.max, 2)}
                  </small>
                )}
              </div>
              <div className="wealth-index-chart-scroll">
                <svg viewBox="0 0 720 156" role="img" aria-label="KOSPI 최근 10거래일 가격 흐름">
                  <line className="wealth-index-axis" x1="18" y1="116" x2="702" y2="116" />
                  {kospiChart?.points.map((point) => (
                    <g key={`${point.date || '-'}-${point.close}`}>
                      <line className="wealth-index-day-line" x1={point.x} y1="36" x2={point.x} y2="116" />
                      <text className="wealth-index-price-label" x={point.x} y="18">{formatNumber(point.close, 0)}</text>
                      <text className={`wealth-index-pct-label ${toneForNumber(point.pct)}`.trim()} x={point.x} y="32">{safePct(point.pct)}</text>
                      <circle className={toneForNumber(point.pct)} cx={point.x} cy={point.y} r="4.2" />
                      <text className="wealth-index-date-label" x={point.x} y="145">{point.dateLabel}</text>
                    </g>
                  ))}
                  {kospiChart && <path className={toneForNumber(kospiTrendPct)} d={kospiChart.path} />}
                </svg>
              </div>
            </div>
          </section>

          <section className="page-section wealth-dashboard-grid">
            <div className="wealth-chart-panel">
              <div className="section-head-row">
                <div>
                  <div className="section-title">포트폴리오</div>
                  <div className="section-copy">보유 {formatNumber(positions.length, 0)}종목 · 평가 {formatKRWExact(totalMarketValueKrw)}</div>
                </div>
              </div>
              <div className="wealth-chart-body">
                <div className="wealth-donut" style={{ background: allocationGradient }}>
                  <div>
                    <strong>{ratioPercent(totalMarketValueKrw, totalBookValueKrw)}</strong>
                    <span>투자중</span>
                  </div>
                </div>
                <div className="wealth-bars">
                  {allocationRows.map((item) => (
                    <div key={item.label} className="wealth-bar-row">
                      <div className="wealth-bar-label">{item.label}</div>
                      <div className="wealth-bar-track"><div className={`wealth-bar-fill ${item.tone || ''}`.trim()} style={{ width: item.width }} /></div>
                      <div className="wealth-bar-value">
                        <strong>{item.value}</strong>
                        {item.meta && <span>{item.meta}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="wealth-chart-panel">
              <div className="section-head-row">
                <div>
                  <div className="section-title">성과</div>
                  <div className="section-copy">시작 {formatKRWExact(startingEquityKrw)} · 현재 {formatKRWExact(performanceEquityKrw)}</div>
                </div>
              </div>
              <div className="wealth-data-list">
                <div className={`wealth-data-row ${toneForNumber(totalReturnPct)}`.trim()}>
                  <div className="wealth-data-label">통합 수익률</div>
                  <div className="wealth-data-main">{totalReturnPct == null ? '-' : formatPercent(totalReturnPct, 2)}</div>
                  <div className="wealth-data-meta">{formatKRWExact(startingEquityKrw)} → {formatKRWExact(performanceEquityKrw)}</div>
                </div>
                <div className={`wealth-data-row ${toneForNumber(positionReturnPct)}`.trim()}>
                  <div className="wealth-data-label">보유 수익률</div>
                  <div className="wealth-data-main">{positionReturnPct == null ? '-' : formatPercent(positionReturnPct, 2)}</div>
                  <div className="wealth-data-meta">투자 {formatKRWExact(positionCostKrw)} / 평가 {formatKRWExact(positionMarketValueKrw)}</div>
                </div>
                <div className="wealth-data-row">
                  <div className="wealth-data-label">KOSPI 수익률</div>
                  <div className="wealth-data-main">{positionReturnKrwPct == null ? '-' : formatPercent(positionReturnKrwPct, 2)}</div>
                  <div className="wealth-data-meta">평가손익 {formatKRWExact(positionUnrealizedKrwOnly)}</div>
                </div>
              </div>
            </div>
          </section>

          <section className="page-section">
            <div className="section-head-row">
              <div>
                <div className="section-title">운용 흐름</div>
                <div className="section-copy">최근 사이클 {String(engineState.latest_cycle_id || '-')}</div>
              </div>
              <div className="inline-badge">{engineState.last_success_at ? formatDateTime(engineState.last_success_at) : '기록 없음'}</div>
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
                  <div className="section-title">리스크</div>
                  <div className="section-copy">{riskReasons.slice(0, 2).join(' · ') || '활성 차단 없음'}</div>
                </div>
                <div className={riskGuardAllowed ? 'inline-badge is-success' : 'inline-badge is-danger'}>
                  {riskGuardAllowed ? '진입 가능' : '진입 차단'}
                </div>
              </div>
              <div className="wealth-data-list">
                <div className={`wealth-data-row ${failedOrders > 0 ? 'is-bad' : 'is-good'}`.trim()}>
                  <div className="wealth-data-label">실패/스킵</div>
                  <div className="wealth-data-main">{formatNumber(failedOrders, 0)} / {formatNumber(skippedCount, 0)}</div>
                  <div className="wealth-data-meta">{String(engineState.order_failure_summary?.top_reason || '-')}</div>
                </div>
                <div className={`wealth-data-row ${riskGuardAllowed ? 'is-good' : 'is-bad'}`.trim()}>
                  <div className="wealth-data-label">진입 게이트</div>
                  <div className="wealth-data-main">{riskGuardAllowed ? '정상' : '차단'}</div>
                  <div className="wealth-data-meta">{riskReasons.slice(0, 1).join(' · ') || '활성 차단 없음'}</div>
                </div>
                <div className="wealth-data-row is-good">
                  <div className="wealth-data-label">리서치</div>
                  <div className="wealth-data-main">{freshnessToKorean(String(snapshot.research.freshness || 'missing'))}</div>
                  <div className="wealth-data-meta">{researchSourceLabel} · 최신 {formatNumber(researchFresh, 0)} / 전체 {formatNumber(researchCoverage, 0)}</div>
                </div>
              </div>
            </div>

            <div className="wealth-chart-panel">
              <div className="section-head-row">
                <div>
                  <div className="section-title">차단 사유</div>
                  <div className="section-copy">주요 차단 분포</div>
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
                  <div className="wealth-empty-line">차단 기록 없음</div>
                )}
              </div>
            </div>
          </section>

          {(marketCtx.regime || marketCtx.risk_level || marketCtx.summary) && (
            <section className="page-section wealth-context-strip">
              <div className="wealth-context-item"><span>장세</span><strong>{marketCtx.regime || allocator.regime || '-'}</strong></div>
              <div className="wealth-context-item"><span>위험도</span><strong>{marketCtx.risk_level || allocator.risk_level || '-'}</strong></div>
              <div className="wealth-context-item"><span>물가</span><strong>{marketCtx.inflation_signal || '-'}</strong></div>
              <div className="wealth-context-item"><span>정책</span><strong>{marketCtx.policy_signal || '-'}</strong></div>
            </section>
          )}

          {loading && <div className="wealth-home-muted">{UI_TEXT.common.loading}</div>}
        </div>
      </div>
    </div>
  );
}
