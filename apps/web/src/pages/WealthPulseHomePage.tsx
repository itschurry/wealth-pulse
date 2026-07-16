import { useState } from 'react';
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
import type { DailyPerformanceJournal } from '../types/domain';
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

function formatHoldingTime(seconds: number | null | undefined): string {
  const total = Math.max(0, Number(seconds) || 0);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (hours > 0) return `${hours}시간 ${minutes}분`;
  return `${minutes}분`;
}

function exitReasonLabel(reason: string | undefined): string {
  const normalized = String(reason || '');
  if (normalized.includes('trailing_profit_stop')) return '트레일링 익절';
  if (normalized.includes('break_even_stop')) return '본전 보호';
  if (normalized.includes('take_profit')) return '목표 익절';
  if (normalized.includes('stop_loss')) return '손절';
  return normalized || '-';
}

const SKIP_REASON_LABELS: Record<string, string> = {
  entry_price_chased: '추격 진입 차단',
  stop_loss_too_wide: '손절폭 과다',
  stop_loss_too_tight_for_volatility: '변동성 대비 손절폭 부족',
  market_closed: '장 마감',
  daily_buy_limit_reached: '일일 매수 한도',
  symbol_daily_limit_reached: '종목별 일일 한도',
};

function DailyPerformanceJournalPanel({ journals }: { journals: DailyPerformanceJournal[] }) {
  const [selectedDate, setSelectedDate] = useState('');
  const selected = journals.find((journal) => journal.date === selectedDate) || journals[0];

  if (!selected) {
    return (
      <section className="wealth-surface-panel wealth-journal-section">
        <div className="wealth-section-heading">
          <div>
            <div className="wealth-panel-kicker">DAILY JOURNAL</div>
            <div className="section-title">일별 성과 기록</div>
          </div>
        </div>
        <div className="wealth-empty-line">아직 장 마감 기록이 없어.</div>
      </section>
    );
  }

  const account = selected.account || {};
  const market = selected.market || {};
  const trading = selected.trading || {};
  const diagnostics = selected.diagnostics || {};
  const trades = Array.isArray(trading.trades) ? trading.trades : [];
  const strategy = selected.strategy_config || {};
  const skipReasons = Object.entries(diagnostics.skip_reason_counts || {})
    .filter(([reason]) => reason !== 'market_closed')
    .sort((left, right) => right[1] - left[1]);

  return (
    <section className="wealth-surface-panel wealth-journal-section">
      <div className="wealth-section-heading">
        <div>
          <div className="wealth-panel-kicker">DAILY JOURNAL</div>
          <div className="section-title">일별 성과 기록</div>
        </div>
        <span className="inline-badge">{formatNumber(journals.length, 0)}거래일</span>
      </div>

      <div className="wealth-journal-layout">
        <div className="wealth-journal-date-list" role="list" aria-label="일별 성과 날짜">
          {journals.map((journal) => {
            const pnl = toNumber(journal.account?.net_pnl_krw);
            return (
              <button
                key={journal.date}
                type="button"
                className={`wealth-journal-date-row ${journal.date === selected.date ? 'is-selected' : ''}`}
                aria-pressed={journal.date === selected.date}
                onClick={() => setSelectedDate(journal.date || '')}
              >
                <span>
                  <strong>{journal.date || '-'}</strong>
                  <em>KOSPI {safePct(journal.market?.kospi_return_pct)}</em>
                </span>
                <span className={toneForNumber(pnl)}>
                  <strong>{formatSignedKRWExact(pnl)}</strong>
                  <em>{safePct(journal.account?.daily_return_pct)}</em>
                </span>
              </button>
            );
          })}
        </div>

        <div className="wealth-journal-detail">
          <div className="wealth-journal-summary-grid">
            <div className={toneForNumber(account.net_pnl_krw)}><span>일손익</span><strong>{formatSignedKRWExact(toNumber(account.net_pnl_krw))}</strong><em>{safePct(account.daily_return_pct)}</em></div>
            <div className={toneForNumber(market.excess_return_pct_points)}><span>시장 대비</span><strong>{safePct(market.excess_return_pct_points)}</strong><em>KOSPI {safePct(market.kospi_return_pct)}</em></div>
            <div><span>승패</span><strong>{formatNumber(trading.win_count, 0)}승 {formatNumber(trading.loss_count, 0)}패</strong><em>승률 {trading.win_rate_pct == null ? '-' : formatPercent(trading.win_rate_pct, 0)}</em></div>
            <div><span>손익비</span><strong>{trading.profit_factor == null ? '-' : formatNumber(trading.profit_factor, 2)}</strong><em>수수료 {formatKRWExact(toNumber(account.fees_krw))}</em></div>
          </div>

          <div className="wealth-journal-trades">
            <div className="wealth-journal-trade-row is-head"><span>종목</span><span>진입 → 청산</span><span>보유</span><span>손익</span><span>청산</span></div>
            {trades.map((trade, index) => (
              <div key={`${trade.code || '-'}:${trade.entry_at || index}`} className="wealth-journal-trade-row">
                <span className="is-symbol"><strong>{trade.name || trade.code || '-'}</strong><em>{trade.code || '-'} · {formatNumber(trade.quantity, 0)}주</em></span>
                <span className="is-prices"><strong>{formatKRWExact(toNumber(trade.entry_price_krw))} → {formatKRWExact(toNumber(trade.exit_price_krw))}</strong><em>{trade.entry_at ? formatDateTime(trade.entry_at) : '-'} → {trade.exit_at ? formatDateTime(trade.exit_at) : '-'}</em></span>
                <span className="is-holding">보유 {formatHoldingTime(trade.holding_seconds)}</span>
                <span className={`is-pnl ${toneForNumber(trade.realized_pnl_krw)}`}><strong>{formatSignedKRWExact(toNumber(trade.realized_pnl_krw))}</strong><em>{safePct(trade.return_pct ?? undefined)}</em></span>
                <span className="is-exit">청산 {exitReasonLabel(trade.exit_reason)}</span>
              </div>
            ))}
            {trades.length === 0 && <div className="wealth-empty-line">완료된 거래가 없어.</div>}
          </div>

          <div className="wealth-journal-foot">
            <div><span>진입 제한</span><strong>{skipReasons.length > 0 ? skipReasons.map(([reason, count]) => `${SKIP_REASON_LABELS[reason] || reasonCodeToKorean(reason)} ${count}`).join(' · ') : '없음'}</strong></div>
            <div><span>전략</span><strong>{formatNumber(toNumber(strategy.interval_seconds), 0)}초 · 일매수 {formatNumber(toNumber(strategy.daily_buy_limit), 0)} · 손실한도 {formatPercent(toNumber(strategy.daily_loss_limit_pct), 1)}</strong></div>
            <div><span>마감 자산</span><strong>{formatKRWExact(toNumber(account.ending_equity_krw))} · 누적 {safePct(account.cumulative_return_pct ?? undefined)}</strong></div>
          </div>
        </div>
      </div>
    </section>
  );
}

function formatSignedKRWExact(value: number): string {
  const prefix = value > 0 ? '+' : '';
  return `${prefix}${formatKRWExact(value)}`;
}

function formatUSD(value: number | undefined): string {
  if (value == null || !Number.isFinite(value)) return '-';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: value >= 10 ? 2 : 4,
  }).format(value);
}

function formatCompactNumber(value: number | undefined): string {
  if (value == null || !Number.isFinite(value)) return '-';
  return new Intl.NumberFormat('ko-KR', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value);
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
  const totalBookValueKrw = Math.max(totalEquityKrw, totalMarketValueKrw + cashKrw, 1);
  const livePerformance = snapshot.performance.live || {};
  const totalReturnPct = toOptionalNumber(livePerformance.total_return_pct);
  const positionReturnPct = toOptionalNumber(livePerformance.position_return_pct);
  const startingEquityKrw = toNumber(livePerformance.starting_equity_krw);
  const performanceEquityKrw = toNumber(livePerformance.equity_krw) || totalEquityKrw;
  const totalReturnKrw = performanceEquityKrw - startingEquityKrw;
  const positionCostKrw = toNumber(livePerformance.position_cost_krw) || Math.max(0, totalMarketValueKrw - totalUnrealizedPnlKrw);
  const positionMarketValueKrw = toNumber(livePerformance.position_market_value_krw) || totalMarketValueKrw;
  const positionReturnKrw = toNumber(livePerformance.position_unrealized_pnl_krw);

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
  const openaiBilling = snapshot.openaiBilling || {};
  const openaiCost = toOptionalNumber(openaiBilling.cost?.amount);
  const openaiCurrency = String(openaiBilling.cost?.currency || 'usd').toUpperCase();
  const openaiTokens = toOptionalNumber(openaiBilling.usage?.total_tokens);
  const openaiRequests = toOptionalNumber(openaiBilling.usage?.requests);
  const openaiBillingError = String(openaiBilling.error || openaiBilling.message || '');
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
    { value: otherExposureKrw, color: 'var(--warning)' },
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
  const realizedPnlKrw = toNumber(engineState.today_realized_pnl) || toNumber(livePerformance.realized_pnl_krw);
  const todayPnlKrw = realizedPnlKrw + totalUnrealizedPnlKrw;
  const focusSignals = [...signals]
    .sort((left, right) => toNumber(right.research_score ?? right.score) - toNumber(left.research_score ?? left.score))
    .slice(0, 3);

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell wealth-home-shell">
          <section className="wealth-command-hero">
            <div className="wealth-terminal-topbar">
              <div className="wealth-terminal-brand">
                <span className={`wealth-status-dot ${engineRunning ? 'is-live' : ''}`} />
                <span>WEALTHPULSE / QUANT COMMAND</span>
                <strong>{engineStatusLabel}</strong>
              </div>
              <div className="wealth-terminal-actions">
                <div className={`wealth-openai-corner ${openaiBilling.ok === false ? 'is-error' : ''}`.trim()}>
                  <span>AI 리서치 비용</span>
                  <strong>{openaiBilling.ok === false ? '확인 실패' : formatUSD(openaiCost)}</strong>
                  <em>
                    {openaiBilling.ok === false
                      ? openaiBillingError
                      : `${openaiCurrency} · ${formatCompactNumber(openaiTokens)} tok · ${formatCompactNumber(openaiRequests)} req`}
                  </em>
                </div>
                <button className="ghost-button" onClick={onRefresh}>새로고침</button>
              </div>
            </div>

            <div className="wealth-command-grid">
              <div className="wealth-asset-card">
                <div className="wealth-panel-kicker">TOTAL EQUITY</div>
                <div className="wealth-asset-value">{formatKRWExact(totalEquityKrw)}</div>
                <div className={`wealth-today-pnl ${toneForNumber(todayPnlKrw)}`}>
                  {formatSignedKRWExact(todayPnlKrw)}
                  <span>오늘 총손익</span>
                </div>
                <div className="wealth-pnl-strip">
                  <div>
                    <span>오늘 실현손익</span>
                    <strong className={toneForNumber(realizedPnlKrw)}>{formatSignedKRWExact(realizedPnlKrw)}</strong>
                  </div>
                  <div>
                    <span>평가손익</span>
                    <strong className={toneForNumber(totalUnrealizedPnlKrw)}>{formatSignedKRWExact(totalUnrealizedPnlKrw)}</strong>
                  </div>
                  <div>
                    <span>통합 수익률</span>
                    <strong className={toneForNumber(totalReturnPct)}>{totalReturnPct == null ? '-' : formatPercent(totalReturnPct, 2)}</strong>
                  </div>
                </div>
              </div>

              <div className="wealth-allocation-card">
                <div className="wealth-card-head">
                  <div>
                    <div className="wealth-panel-kicker">ASSET ALLOCATION</div>
                    <div className="section-title">자산 배분</div>
                  </div>
                  <span className="inline-badge">{formatNumber(positions.length, 0)} 포지션</span>
                </div>
                <div className="wealth-allocation-visual">
                  <div
                    className="wealth-donut"
                    style={{ background: allocationGradient }}
                    role="img"
                    aria-label={`투자 ${ratioPercent(totalMarketValueKrw, totalBookValueKrw)}, 현금 ${ratioPercent(cashAllocationKrw, totalBookValueKrw)}`}
                  >
                    <div>
                      <strong>{ratioPercent(totalMarketValueKrw, totalBookValueKrw)}</strong>
                      <span>투자중</span>
                    </div>
                  </div>
                  <div className="wealth-allocation-legend">
                    {allocationRows.map((item) => (
                      <div key={item.label}>
                        <span className={`wealth-legend-dot ${item.tone || ''}`.trim()} />
                        <span>{item.label}</span>
                        <strong>{item.meta}</strong>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div className="wealth-system-card">
                <div className="wealth-card-head">
                  <div>
                    <div className="wealth-panel-kicker">SYSTEM STATUS</div>
                    <div className="section-title">운용 상태</div>
                  </div>
                  <span className={engineRunning ? 'inline-badge is-success' : 'inline-badge is-danger'}>{engineStatusLabel}</span>
                </div>
                <div className="wealth-status-list">
                  <div>
                    <span>리스크 게이트</span>
                    <strong className={riskGuardAllowed ? 'is-up' : 'is-down'}>{riskGuardAllowed ? '정상' : '차단'}</strong>
                  </div>
                  <div>
                    <span>AI 리서치</span>
                    <strong>{freshnessToKorean(String(snapshot.research.freshness || 'missing'))}</strong>
                  </div>
                  <div>
                    <span>리서치 최신</span>
                    <strong>{formatNumber(researchFresh, 0)} / {formatNumber(researchCoverage, 0)}</strong>
                  </div>
                  <div>
                    <span>오늘 주문</span>
                    <strong>매수 {formatNumber(buyOrders, 0)} · 매도 {formatNumber(sellOrders, 0)}</strong>
                  </div>
                </div>
                <div className="wealth-system-foot">마지막 동기화 {formatDateTimeWithAge(snapshot.fetchedAt)}</div>
              </div>
            </div>
            {!!errorMessage && <div className="wealth-home-error">{errorMessage}</div>}
          </section>

          <section className="wealth-market-strip wealth-surface-panel">
            <div className="wealth-section-heading">
              <div>
                <div className="wealth-panel-kicker">MARKET RADAR</div>
                <div className="section-title">시장 흐름</div>
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
            </div>
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

          <section className="wealth-workspace-grid">
            <div className="wealth-surface-panel wealth-holdings-panel">
              <div className="wealth-section-heading">
                <div>
                  <div className="wealth-panel-kicker">LIVE POSITIONS</div>
                  <div className="section-title">보유 포지션</div>
                </div>
                <div className="wealth-portfolio-total">
                  <span>평가금액</span>
                  <strong>{formatKRWExact(totalMarketValueKrw)}</strong>
                </div>
              </div>
              <div className="wealth-position-table">
                <div className="wealth-position-table-row is-head">
                  <span>종목</span><span>평가금액</span><span>비중</span><span>수량</span><span>평가손익</span>
                </div>
                {positions.slice(0, 8).map((position) => (
                  <div key={position.key} className="wealth-position-table-row">
                    <div>
                      <strong>{position.symbol}</strong>
                      <em>{position.market}</em>
                    </div>
                    <span>{formatKRWExact(position.marketValueKrw)}</span>
                    <span>{ratioPercent(position.marketValueKrw, totalMarketValueKrw)}</span>
                    <span>{formatNumber(position.quantity, 0)}주</span>
                    <div className={toneForNumber(position.unrealizedPnlKrw)}>
                      <strong>{formatSignedKRWExact(position.unrealizedPnlKrw)}</strong>
                      <em>{position.unrealizedPnlPct == null ? '-' : formatPercent(position.unrealizedPnlPct, 2)}</em>
                    </div>
                  </div>
                ))}
                {positions.length === 0 && <div className="wealth-empty-line">현재 보유 포지션 없음</div>}
              </div>
            </div>

            <div className="wealth-command-rail">
              <div className="wealth-surface-panel wealth-signal-panel">
                <div className="wealth-section-heading">
                  <div>
                    <div className="wealth-panel-kicker">AI SIGNALS</div>
                    <div className="section-title">핵심 후보</div>
                  </div>
                  <span className="inline-badge">{formatNumber(signals.length, 0)} 후보</span>
                </div>
                <div className="wealth-signal-list">
                  {focusSignals.map((signal, index) => {
                    const score = toOptionalNumber(signal.research_score) ?? toOptionalNumber(signal.score);
                    const action = signal.entry_allowed
                      ? '진입 검토'
                      : signal.final_action === 'blocked'
                        ? '차단'
                        : signal.final_action === 'watch_only'
                          ? '관찰'
                          : '대기';
                    return (
                      <div key={`${signal.market || '-'}:${signal.code || index}`} className="wealth-signal-row">
                        <div>
                          <strong>{formatSymbol(signal.code, signal.name)}</strong>
                          <span>{signal.market || '-'} · {action}</span>
                        </div>
                        <div className={signal.entry_allowed ? 'is-up' : signal.final_action === 'blocked' ? 'is-down' : ''}>
                          <strong>{score == null ? '-' : formatNumber(score, 0)}</strong>
                          <span>AI SCORE</span>
                        </div>
                      </div>
                    );
                  })}
                  {focusSignals.length === 0 && <div className="wealth-empty-line">현재 후보 신호 없음</div>}
                </div>
              </div>

              <div className="wealth-surface-panel wealth-order-panel">
                <div className="wealth-section-heading">
                  <div>
                    <div className="wealth-panel-kicker">TODAY ORDERS</div>
                    <div className="section-title">주문 현황</div>
                  </div>
                  <span className={failedOrders > 0 ? 'inline-badge is-danger' : 'inline-badge is-success'}>실패 {formatNumber(failedOrders, 0)}</span>
                </div>
                <div className="wealth-order-grid">
                  <div><span>매수</span><strong className="is-up">{formatNumber(buyOrders, 0)}</strong></div>
                  <div><span>매도</span><strong>{formatNumber(sellOrders, 0)}</strong></div>
                  <div><span>스킵</span><strong>{formatNumber(skippedCount, 0)}</strong></div>
                </div>
                <div className="wealth-order-note">
                  <span>진입 게이트</span>
                  <strong className={riskGuardAllowed ? 'is-up' : 'is-down'}>{riskGuardAllowed ? '정상' : '차단'}</strong>
                </div>
              </div>
            </div>
          </section>

          <section className="wealth-secondary-grid">
            <div className="wealth-surface-panel">
              <div className="wealth-section-heading">
                <div>
                  <div className="wealth-panel-kicker">PERFORMANCE</div>
                  <div className="section-title">성과 요약</div>
                </div>
                <span className="inline-badge">시작 {formatKRWExact(startingEquityKrw)}</span>
              </div>
              <div className="wealth-performance-grid">
                <div className={toneForNumber(totalReturnPct)}>
                  <span>통합 수익률</span>
                  <strong>{totalReturnPct == null ? '-' : formatPercent(totalReturnPct, 2)}</strong>
                  <em>{formatSignedKRWExact(totalReturnKrw)}</em>
                </div>
                <div className={toneForNumber(positionReturnPct)}>
                  <span>보유 수익률</span>
                  <strong>{positionReturnPct == null ? '-' : formatPercent(positionReturnPct, 2)}</strong>
                  <em>{formatSignedKRWExact(positionReturnKrw)}</em>
                </div>
                <div>
                  <span>투자 원금</span>
                  <strong>{formatKRWExact(positionCostKrw)}</strong>
                  <em>평가 {formatKRWExact(positionMarketValueKrw)}</em>
                </div>
              </div>
            </div>

            <div className="wealth-surface-panel">
              <div className="wealth-section-heading">
                <div>
                  <div className="wealth-panel-kicker">PIPELINE</div>
                  <div className="section-title">운용 흐름</div>
                </div>
                <span className="inline-badge">{engineState.last_success_at ? formatDateTime(engineState.last_success_at) : '기록 없음'}</span>
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
            </div>
          </section>

          <DailyPerformanceJournalPanel journals={snapshot.dailyPerformance.journals || []} />

          <section className="wealth-surface-panel wealth-dashboard-grid wealth-risk-section">
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
