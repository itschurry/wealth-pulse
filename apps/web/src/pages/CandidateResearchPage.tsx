import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  fetchCandidateMonitorPromotions,
  fetchCandidateMonitorStatus,
  fetchCandidateMonitorWatchlist,
  fetchCandidateResearchHistory,
  fetchCandidateResearchLatest,
  fetchLiveMarket,
  fetchResearchStatus,
} from '../api/domain';
import { ConsoleActionBar } from '../components/ConsoleActionBar';
import { SymbolIdentity } from '../components/SymbolIdentity';
import { freshnessToKorean, gradeToKorean, providerStatusToKorean, reasonCodeToKorean } from '../constants/uiText';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import type { ConsoleSnapshot } from '../types/consoleView';
import type {
  CandidateMonitorMarketWatchlist,
  CandidateMonitorPromotionEvent,
  CandidateMonitorSlot,
  CandidateMonitorStatusItem,
  CandidateResearchSnapshot,
  LiveMarketResponse,
} from '../types/domain';
import { formatDateTime, formatDateTimeWithAge, formatKRW, formatNumber, formatPercent } from '../utils/format';

interface CandidateResearchPageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
}

const MARKET_OPTIONS = [
  { label: 'KOSPI', value: 'KOSPI' },
];

type SnapshotMarketView = 'ALL' | 'KOSPI';

function normalizeSnapshotMarket(_value: string | undefined): Exclude<SnapshotMarketView, 'ALL'> {
  return 'KOSPI';
}

function buildMarketCounts(items: Array<{ market?: string }>): Record<SnapshotMarketView, number> {
  const counts: Record<SnapshotMarketView, number> = { ALL: items.length, KOSPI: 0 };
  items.forEach((item) => {
    counts[normalizeSnapshotMarket(item.market)] += 1;
  });
  return counts;
}

function filterByMarket<T extends { market?: string }>(items: T[], marketView: SnapshotMarketView): T[] {
  if (marketView === 'ALL') return items;
  return items.filter((item) => normalizeSnapshotMarket(item.market) === marketView);
}

function preferredMarketView(liveMarket: LiveMarketResponse | null): SnapshotMarketView {
  const sessions = liveMarket?.market_sessions || {};
  const krOpen = Boolean(sessions.KR?.is_open);
  if (krOpen) return 'KOSPI';
  return 'ALL';
}

function marketSessionText(liveMarket: LiveMarketResponse | null, _market: Exclude<SnapshotMarketView, 'ALL'>): string {
  const session = liveMarket?.market_sessions?.KR;
  if (!session) return '';
  return session.status_label || session.status || '';
}

function snapshotGrade(item: CandidateResearchSnapshot): string {
  return String(item.validation?.grade || '').toUpperCase() || '-';
}

function scoreDisplay(item: CandidateResearchSnapshot): string {
  if (snapshotGrade(item) === 'D') return '—';
  return item.research_score != null ? formatNumber(item.research_score, 1) : '점수 대기';
}

function freshnessBadge(item: CandidateResearchSnapshot): { label: string; tone: string } {
  const freshness = String(item.freshness || item.freshness_detail?.status || '').toLowerCase();
  if (freshness === 'fresh') return { label: freshnessToKorean(freshness), tone: 'inline-badge is-success' };
  if (freshness === 'stale') return { label: freshnessToKorean(freshness), tone: 'inline-badge is-danger' };
  if (freshness === 'invalid') return { label: freshnessToKorean(freshness), tone: 'inline-badge is-danger' };
  if (freshness === 'missing') return { label: freshnessToKorean(freshness), tone: 'inline-badge' };
  return { label: freshnessToKorean(freshness), tone: 'inline-badge' };
}

function gradeBadge(item: CandidateResearchSnapshot): { label: string; tone: string } {
  const grade = snapshotGrade(item);
  if (grade === 'A') return { label: gradeToKorean(grade), tone: 'inline-badge is-success' };
  if (grade === 'B') return { label: gradeToKorean(grade), tone: 'inline-badge' };
  if (grade === 'C') return { label: gradeToKorean(grade), tone: 'inline-badge is-danger' };
  if (grade === 'D') return { label: gradeToKorean(grade), tone: 'inline-badge is-danger' };
  return { label: gradeToKorean(grade), tone: 'inline-badge' };
}

function snapshotStatus(item: CandidateResearchSnapshot): { label: string; tone: string } {
  const grade = snapshotGrade(item);
  if (grade === 'D') return { label: '검증 제외', tone: 'inline-badge is-danger' };
  if (String(item.freshness || '').toLowerCase() === 'stale') return { label: '지연', tone: 'inline-badge is-danger' };
  const score = Number(item.research_score);
  if (!Number.isFinite(score)) return { label: '점수 대기', tone: 'inline-badge' };
  if (score >= 0.8) return { label: '우선 검토', tone: 'inline-badge is-success' };
  if (score >= 0.6) return { label: '후보', tone: 'inline-badge' };
  return { label: '관찰 유지', tone: 'inline-badge is-danger' };
}

function outcomeValue(value: number | null | undefined): string {
  return typeof value === 'number' && Number.isFinite(value) ? formatPercent(value, 2) : '-';
}

function percentBarWidth(value: number | null | undefined): number {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 0;
  return Math.max(4, Math.min(100, Math.abs(numeric) * 12));
}

function numericTone(value: number | null | undefined, goodAtZero = true): string {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric === 0) return goodAtZero ? 'is-neutral' : 'is-down';
  return numeric > 0 ? 'is-up' : 'is-down';
}

function ratioPercentValue(value: number | null | undefined): string {
  return value == null ? '-' : formatPercent(value, 0, true);
}

function candidateStatusBadge(item: CandidateMonitorSlot): { label: string; tone: string } {
  const status = String(item.research_status || '').toLowerCase();
  if (status === 'fresh' || status === 'healthy' || status === 'derived') return { label: '최신', tone: 'inline-badge is-success' };
  if (status === 'stale' || status === 'stale_ingest' || status === 'invalid') return { label: '지연', tone: 'inline-badge is-danger' };
  if (status === 'missing') return { label: '없음', tone: 'inline-badge' };
  if (!item.snapshot_exists) return { label: '없음', tone: 'inline-badge' };
  if (item.snapshot_fresh) return { label: '최신', tone: 'inline-badge is-success' };
  return { label: '지연', tone: 'inline-badge is-danger' };
}

function pendingCandidateBadge(item: CandidateMonitorSlot): { label: string; tone: string } {
  if (!item.snapshot_exists) return { label: '신규', tone: 'inline-badge' };
  return { label: '지연', tone: 'inline-badge is-danger' };
}

function candidateActionBadge(item: CandidateMonitorSlot): { label: string; tone: string } {
  const action = String(item.final_action || item.snapshot_action || '').trim().toLowerCase();
  if (action === 'review_for_entry') return { label: '진입 검토', tone: 'inline-badge is-success' };
  if (action === 'buy') return { label: '매수', tone: 'inline-badge is-success' };
  if (action === 'buy_watch') return { label: '매수 관찰', tone: 'inline-badge is-success' };
  if (action === 'watch_only') return { label: '관찰', tone: 'inline-badge' };
  if (action === 'hold') return { label: '보류', tone: 'inline-badge' };
  if (action === 'blocked') return { label: '차단', tone: 'inline-badge is-danger' };
  if (action === 'do_not_touch') return { label: '보류', tone: 'inline-badge' };
  return { label: action || '-', tone: 'inline-badge' };
}

function bluechipBadge(item: CandidateMonitorSlot): { label: string; tone: string } | null {
  if (!item.bluechip) return null;
  return { label: '우량주', tone: 'inline-badge is-success' };
}

function slotTypeBadge(item: CandidateMonitorSlot): { label: string; tone: string } {
  const slotType = String(item.slot_type || '').toLowerCase();
  if (slotType === 'held') return { label: '보유 추적', tone: 'inline-badge is-success' };
  if (slotType === 'core') return { label: '핵심 감시', tone: 'inline-badge' };
  if (slotType === 'promotion') return { label: '승격 슬롯', tone: 'inline-badge is-danger' };
  return { label: slotType || '-', tone: 'inline-badge' };
}

function validationBadge(item: CandidateMonitorSlot): { label: string; tone: string } | null {
  const grade = String(item.validation_grade || '').toUpperCase();
  if (!grade) return null;
  if (grade === 'A') return { label: gradeToKorean(grade), tone: 'inline-badge is-success' };
  if (grade === 'B') return { label: gradeToKorean(grade), tone: 'inline-badge' };
  return { label: gradeToKorean(grade), tone: 'inline-badge is-danger' };
}

function candidateRankDisplay(value: number | null | undefined): string {
  if (value === null || value === undefined) return '-';
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0 || numeric >= 999999) return '-';
  return formatNumber(numeric, 0);
}

function candidatePrice(item: CandidateMonitorSlot): number | null {
  const technical = item.technical_snapshot || {};
  const value = Number(technical.current_price ?? technical.close);
  return Number.isFinite(value) && value > 0 ? value : null;
}

function candidateChangePct(item: CandidateMonitorSlot): number | null {
  const value = Number(item.technical_snapshot?.change_pct);
  return Number.isFinite(value) ? value : null;
}

function candidateTradingValue(item: CandidateMonitorSlot): number | null {
  const value = Number(item.technical_snapshot?.trading_value);
  return Number.isFinite(value) && value >= 0 ? value : null;
}

function formatCompactKRW(value: number | null): string {
  if (value == null) return '-';
  if (value >= 1_000_000_000_000) return `${formatNumber(value / 1_000_000_000_000, 1)}조`;
  if (value >= 100_000_000) return `${formatNumber(value / 100_000_000, 0)}억`;
  return formatKRW(value, true);
}

function changeTone(value: number | null): string {
  if (value == null || value === 0) return 'is-neutral';
  return value > 0 ? 'is-up' : 'is-down';
}

function researchScoreDisplay(item: CandidateMonitorSlot): string {
  const value = Number(item.snapshot_research_score);
  return Number.isFinite(value) ? formatNumber(value, 2) : '-';
}

function candidateReasonDisplay(item: CandidateMonitorSlot): string {
  const sources = Array.isArray(item.candidate_sources) && item.candidate_sources.length > 0
    ? item.candidate_sources
    : item.reason_codes;
  const reason = item.selection_reason || item.reason || (Array.isArray(sources) ? sources[0] : '');
  return reasonCodeToKorean(String(reason || '-'));
}

function promotionEventBadge(item: CandidateMonitorPromotionEvent): { label: string; tone: string } {
  const eventType = String(item.event_type || '').toLowerCase();
  if (eventType === 'entered_watch') return { label: '감시 편입', tone: 'inline-badge is-success' };
  if (eventType === 'left_watch') return { label: '감시 제외', tone: 'inline-badge is-danger' };
  return { label: eventType || '-', tone: 'inline-badge' };
}

function promotionReasonLabel(item: CandidateMonitorPromotionEvent): string {
  const reason = String(item.reason || '').toLowerCase();
  if (reason === 'held') return '보유 추적';
  if (reason === 'core') return '핵심 감시';
  if (reason === 'promotion') return '승격 슬롯';
  if (reason === 'watch') return '감시 슬롯';
  return reason || '-';
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  const width = Math.max(0, Math.min(100, value * 100));
  return (
    <div className="workspace-score-row research-score-row">
      <div className="workspace-score-label">{label}</div>
      <div className="workspace-score-track">
        <div className="workspace-score-fill" style={{ width: `${width}%` }} />
      </div>
      <div className="workspace-score-value">{formatNumber(value, 2)}</div>
    </div>
  );
}

function MetricTile({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="research-metric-tile">
      <span>{label}</span>
      <strong className={tone || ''}>{value}</strong>
    </div>
  );
}

function ReturnBar({ label, value }: { label: string; value: number | null | undefined }) {
  const numeric = Number(value);
  const width = percentBarWidth(value);
  const tone = numericTone(value);
  return (
    <div className="research-return-row">
      <span>{label}</span>
      <div className="research-return-track">
        {Number.isFinite(numeric) ? (
          <div className={numeric >= 0 ? 'research-return-fill is-up' : 'research-return-fill is-down'} style={{ width: `${width}%` }} />
        ) : null}
      </div>
      <strong className={tone}>{outcomeValue(value)}</strong>
    </div>
  );
}

function CandidateResearchCard({ item }: { item: CandidateResearchSnapshot }) {
  const components = item.components && typeof item.components === 'object' ? item.components as Record<string, number> : {};
  const warnings = Array.isArray(item.warnings) ? item.warnings : [];
  const tags = Array.isArray(item.tags) ? item.tags : [];
  const status = snapshotStatus(item);
  const freshness = freshnessBadge(item);
  const grade = gradeBadge(item);
  const quality = item.research_quality || {};
  const outcomes = item.outcomes || {};
  const newsInputs = Array.isArray(item.news_inputs) ? item.news_inputs.slice(0, 3) : [];
  const evidence = Array.isArray(item.evidence) ? item.evidence.slice(0, 3) : [];
  const outcomeRows = [
    { label: '1D', value: outcomes.return_1d },
    { label: '3D', value: outcomes.return_3d },
    { label: '5D', value: outcomes.return_5d },
    { label: '20D', value: outcomes.return_20d },
    { label: 'MDD', value: outcomes.max_drawdown_20d },
  ];

  return (
    <div className="page-section workspace-analysis-section research-snapshot-panel">
      <div className="research-snapshot-head">
        <div>
          <div className="section-title"><SymbolIdentity code={item.symbol} name={item.name} market={item.market} /></div>
          <div className="research-snapshot-meta">{formatDateTimeWithAge(item.generated_at || item.bucket_ts)}</div>
        </div>
        <div className="research-score-hero">
          <span>RESEARCH</span>
          <strong>
            {scoreDisplay(item)}
          </strong>
          <div className="workspace-chip-row">
            <span className={status.tone}>{status.label}</span>
            <span className={freshness.tone}>{freshness.label}</span>
            <span className={grade.tone}>{grade.label}</span>
          </div>
        </div>
      </div>

      <div className="research-kpi-strip">
        <MetricTile label="출처" value={formatNumber(quality.source_quality_score, 2)} tone={Number(quality.source_quality_score || 0) >= 0.65 ? 'is-up' : 'is-down'} />
        <MetricTile label="신뢰 뉴스" value={formatNumber(quality.trusted_news_count ?? 0, 0)} />
        <MetricTile label="Fresh" value={formatNumber(quality.fresh_news_count ?? 0, 0)} />
        <MetricTile label="공식" value={formatNumber(quality.official_source_count ?? 0, 0)} />
        <MetricTile label="비허용" value={formatNumber(quality.untrusted_source_count ?? 0, 0)} tone={Number(quality.untrusted_source_count || 0) > 0 ? 'is-down' : 'is-neutral'} />
        <MetricTile label="Hit" value={outcomes.hit == null ? '-' : outcomes.hit ? 'Y' : 'N'} tone={outcomes.hit ? 'is-up' : outcomes.hit === false ? 'is-down' : 'is-neutral'} />
      </div>

      <div className="research-visual-grid">
        <div className="research-visual-panel">
          <div className="research-visual-title">성과</div>
          <div className="research-return-list">
            {outcomeRows.map((row) => (
              <ReturnBar key={row.label} label={row.label} value={row.value} />
            ))}
          </div>
        </div>
        {Object.keys(components).length > 0 ? (
          <div className="research-visual-panel">
            <div className="research-visual-title">컴포넌트</div>
            <div className="workspace-score-grid">
              {Object.entries(components).map(([key, value]) => (
                <ScoreBar key={key} label={key} value={typeof value === 'number' ? value : 0} />
              ))}
            </div>
          </div>
        ) : null}
      </div>

      {quality.blocked_reason ? <div className="research-alert-line">{reasonCodeToKorean(quality.blocked_reason)}</div> : null}

      {(newsInputs.length > 0 || evidence.length > 0) && (
        <div className="workspace-table-wrap research-evidence-table">
          <table className="workspace-table compact">
            <thead>
              <tr>
                <th>구분</th>
                <th>출처</th>
                <th>시각</th>
                <th>제목</th>
              </tr>
            </thead>
            <tbody>
              {newsInputs.map((news, index) => (
                <tr key={`news-${index}`}>
                  <td>뉴스</td>
                  <td>{news.source || '-'}</td>
                  <td>{formatDateTime(news.published_at)}</td>
                  <td>{news.url ? <a href={news.url} target="_blank" rel="noreferrer">{news.title || news.summary || news.url}</a> : (news.title || news.summary || '-')}</td>
                </tr>
              ))}
              {evidence.map((row, index) => (
                <tr key={`ev-${index}`}>
                  <td>근거</td>
                  <td>{row.source || row.type || '-'}</td>
                  <td>-</td>
                  <td>{row.url ? <a href={row.url} target="_blank" rel="noreferrer">{row.title || row.detail || row.summary || row.url}</a> : (row.title || row.detail || row.summary || '-')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {(warnings.length > 0 || tags.length > 0) && (
        <div className="workspace-chip-row research-warning-row">
          {warnings.map((warning, index) => <span key={`w-${index}`} className="inline-badge is-danger">{reasonCodeToKorean(String(warning))}</span>)}
          {tags.map((tag, index) => <span key={`t-${index}`} className="inline-badge">{reasonCodeToKorean(String(tag))}</span>)}
        </div>
      )}
    </div>
  );
}

interface MonitorSlotSectionProps {
  title: string;
  copy: string;
  items: CandidateMonitorSlot[];
  loading: boolean;
  marketView: SnapshotMarketView;
  liveMarket: LiveMarketResponse | null;
  onChangeMarketView: (view: SnapshotMarketView) => void;
  onSelect: (symbol: string, market: string) => void;
  emptyText: string;
  highlightPending?: boolean;
}

function MonitorSlotSection({
  title,
  copy,
  items,
  loading,
  marketView,
  liveMarket,
  onChangeMarketView,
  onSelect,
  emptyText,
  highlightPending = false,
}: MonitorSlotSectionProps) {
  const marketCounts = useMemo(() => buildMarketCounts(items), [items]);
  const displayedItems = useMemo(() => filterByMarket(items, marketView), [items, marketView]);

  return (
    <section className="page-section workspace-table-section">
      <div className="workspace-card-head section-head-row">
        <div>
          <div className="section-title">{title}</div>
          <div className="section-copy">{copy}</div>
        </div>
        <div className="section-toolbar">
          <div className="section-filter-row">
            {(['ALL', 'KOSPI'] as const).map((view) => (
              <button
                key={view}
                type="button"
                className={marketView === view ? 'ghost-button is-active' : 'ghost-button'}
                onClick={() => onChangeMarketView(view)}
              >
                {view === 'ALL'
                  ? `전체 ${marketCounts.ALL}개`
                  : `${view} ${marketCounts[view]}개${marketSessionText(liveMarket, view) ? ` · ${marketSessionText(liveMarket, view)}` : ''}`}
              </button>
            ))}
          </div>
          <div className="inline-badge">{loading ? '불러오는 중...' : `${displayedItems.length}개`}</div>
        </div>
      </div>

      {displayedItems.length === 0 ? (
        <div className="workspace-empty-state">{loading ? '불러오는 중...' : emptyText}</div>
      ) : (
        <>
          <div className="workspace-table-scroll is-ten-rows">
            <table className="workspace-table research-watch-table" style={{ minWidth: 1040 }}>
              <thead>
                <tr>
                  <th>종목</th>
                  <th>가격</th>
                  <th>슬롯</th>
                  <th>순위</th>
                  <th>리서치</th>
                  <th>액션</th>
                  <th>최근</th>
                  <th>근거</th>
                </tr>
              </thead>
              <tbody>
                {displayedItems.map((item, idx) => {
                  const status = candidateStatusBadge(item);
                  const pending = pendingCandidateBadge(item);
                  const action = candidateActionBadge(item);
                  const slot = slotTypeBadge(item);
                  const grade = validationBadge(item);
                  const bluechip = bluechipBadge(item);
                  const market = item.market || 'KOSPI';
                  const symbol = item.symbol || item.code || '';
                  const price = candidatePrice(item);
                  const changePct = candidateChangePct(item);
                  const tradingValue = candidateTradingValue(item);
                  return (
                    <tr
                      key={`${market}-${symbol}-${item.strategy_id || idx}`}
                      style={{ cursor: 'pointer' }}
                      onClick={() => symbol && onSelect(symbol, market)}
                    >
                      <td><SymbolIdentity code={symbol} name={item.name} market={item.market} /></td>
                      <td>
                        <div className="research-price-stack">
                          <strong>{formatCompactKRW(price)}</strong>
                          <span className={`research-change ${changeTone(changePct)}`}>{changePct == null ? '-' : formatPercent(changePct, 2)}</span>
                        </div>
                      </td>
                      <td>
                        <div className="workspace-chip-row">
                          <span className={slot.tone}>{slot.label}</span>
                        </div>
                      </td>
                      <td>{candidateRankDisplay(item.candidate_rank)}</td>
                      <td>
                        <div className="research-score-stack">
                          <strong>{researchScoreDisplay(item)}</strong>
                          <div className="workspace-chip-row">
                            <span className={status.tone}>{status.label}</span>
                            {grade ? <span className={grade.tone}>{grade.label}</span> : null}
                            {bluechip ? <span className={bluechip.tone}>{bluechip.label}</span> : null}
                            {highlightPending ? <span className={pending.tone}>{pending.label}</span> : null}
                          </div>
                        </div>
                      </td>
                      <td><span className={action.tone}>{action.label}</span></td>
                      <td>{item.snapshot_generated_at ? formatDateTimeWithAge(item.snapshot_generated_at) : '없음'}</td>
                      <td>
                        <div className="signal-cell-copy">{candidateReasonDisplay(item)}</div>
                        <div className="signal-cell-copy">거래대금 {formatCompactKRW(tradingValue)}</div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="responsive-card-list is-scroll-ten">
            {displayedItems.map((item, idx) => {
              const status = candidateStatusBadge(item);
              const pending = pendingCandidateBadge(item);
              const action = candidateActionBadge(item);
              const slot = slotTypeBadge(item);
              const grade = validationBadge(item);
              const bluechip = bluechipBadge(item);
              const market = item.market || 'KOSPI';
              const symbol = item.symbol || item.code || '';
              const price = candidatePrice(item);
              const changePct = candidateChangePct(item);
              const tradingValue = candidateTradingValue(item);
              return (
                <article
                  key={`${market}-${symbol}-${item.strategy_id || idx}-card`}
                  className="responsive-card"
                  onClick={() => symbol && onSelect(symbol, market)}
                >
                  <div className="responsive-card-head">
                    <div>
                      <div className="responsive-card-title">
                        <SymbolIdentity code={symbol} name={item.name} market={item.market} compact />
                      </div>
                      <div className="signal-cell-copy">순위 {candidateRankDisplay(item.candidate_rank)} · {candidateReasonDisplay(item)}</div>
                    </div>
                    <span className={action.tone}>{action.label}</span>
                  </div>
                  <div className="workspace-chip-row" style={{ marginBottom: 12 }}>
                    <span className={slot.tone}>{slot.label}</span>
                    <span className={status.tone}>{status.label}</span>
                    {grade ? <span className={grade.tone}>{grade.label}</span> : null}
                    {bluechip ? <span className={bluechip.tone}>{bluechip.label}</span> : null}
                    {highlightPending ? <span className={pending.tone}>{pending.label}</span> : null}
                  </div>
                  <div className="responsive-card-grid">
                    <div>
                      <div className="responsive-card-label">가격</div>
                      <div className="responsive-card-value">{formatCompactKRW(price)} · <span className={`research-change ${changeTone(changePct)}`}>{changePct == null ? '-' : formatPercent(changePct, 2)}</span></div>
                    </div>
                    <div>
                      <div className="responsive-card-label">리서치</div>
                      <div className="responsive-card-value">{researchScoreDisplay(item)} · {status.label}</div>
                    </div>
                    <div>
                      <div className="responsive-card-label">최근</div>
                      <div className="responsive-card-value">{item.snapshot_generated_at ? formatDateTimeWithAge(item.snapshot_generated_at) : '없음'}</div>
                    </div>
                    <div>
                      <div className="responsive-card-label">거래대금</div>
                      <div className="responsive-card-value">{formatCompactKRW(tradingValue)}</div>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        </>
      )}
    </section>
  );
}

function MarketSummarySection({ items }: { items: CandidateMonitorStatusItem[] }) {
  if (!items.length) {
    return <div className="page-section workspace-empty-state">없음</div>;
  }

  return (
    <section className="page-section workspace-table-section">
      <div className="workspace-card-head section-head-row">
        <div>
          <div className="section-title">시장</div>
          <div className="section-copy">KOSPI 후보 풀과 핵심 감시, 승격 슬롯, 보유 추적 수를 따로 본다.</div>
        </div>
      </div>
      <div className="responsive-card-list">
        {items.map((item) => (
          <article key={item.market || 'market'} className="responsive-card" style={{ cursor: 'default' }}>
            <div className="responsive-card-head">
              <div>
                <div className="responsive-card-title">{item.market || '-'}</div>
                <div className="signal-cell-copy">생성 {item.generated_at ? formatDateTimeWithAge(item.generated_at) : '대기'}</div>
              </div>
              <span className="inline-badge">세션 {item.session_date || '-'}</span>
            </div>
            <div className="responsive-card-grid">
              <div>
                <div className="responsive-card-label">후보 풀</div>
                <div className="responsive-card-value">{item.candidate_pool_count ?? 0}개</div>
              </div>
              <div>
                <div className="responsive-card-label">감시 슬롯</div>
                <div className="responsive-card-value">{item.active_count ?? 0}개</div>
              </div>
              <div>
                <div className="responsive-card-label">핵심 감시</div>
                <div className="responsive-card-value">{item.core_count ?? 0}개</div>
              </div>
              <div>
                <div className="responsive-card-label">승격 슬롯</div>
                <div className="responsive-card-value">{item.promotion_count ?? 0}개</div>
              </div>
              <div>
                <div className="responsive-card-label">보유 추적</div>
                <div className="responsive-card-value">{item.held_count ?? 0}개</div>
              </div>
              <div>
                <div className="responsive-card-label">소스</div>
                <div className="responsive-card-value">{item.source || '-'}</div>
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function PromotionSection({ items }: { items: CandidateMonitorPromotionEvent[] }) {
  return (
    <section className="page-section workspace-table-section">
      <div className="workspace-card-head section-head-row">
        <div>
          <div className="section-title">승격/탈락</div>
          <div className="section-copy">새 구조가 실제로 종목을 감시 슬롯에 넣고 빼는지 바로 확인하는 용도야.</div>
        </div>
        <div className="section-toolbar">
          <div className="inline-badge">{items.length}개</div>
        </div>
      </div>
      {items.length === 0 ? (
        <div className="workspace-empty-state">없음</div>
      ) : (
        <>
          <div className="workspace-table-scroll is-ten-rows">
            <table className="workspace-table" style={{ minWidth: 760 }}>
              <thead>
                <tr>
                  <th>시각</th>
                  <th>시장</th>
                  <th>종목</th>
                  <th>이벤트</th>
                  <th>슬롯</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item, idx) => {
                  const event = promotionEventBadge(item);
                  return (
                    <tr key={`${item.market}-${item.symbol}-${item.created_at}-${idx}`}>
                      <td>{item.created_at ? formatDateTime(item.created_at) : '-'}</td>
                      <td>{item.market || '-'}</td>
                      <td><SymbolIdentity code={item.symbol} name={item.name} market={item.market} /></td>
                      <td><span className={event.tone}>{event.label}</span></td>
                      <td>{promotionReasonLabel(item)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="responsive-card-list is-scroll-ten">
            {items.map((item, idx) => {
              const event = promotionEventBadge(item);
              return (
                <article key={`${item.market}-${item.symbol}-${item.created_at}-${idx}-card`} className="responsive-card" style={{ cursor: 'default' }}>
                  <div className="responsive-card-head">
                    <div>
                      <div className="responsive-card-title"><SymbolIdentity code={item.symbol} name={item.name} market={item.market} compact /></div>
                      <div className="signal-cell-copy">{item.market || '-'} · {item.created_at ? formatDateTime(item.created_at) : '-'}</div>
                    </div>
                    <span className={event.tone}>{event.label}</span>
                  </div>
                  <div className="responsive-card-grid">
                    <div>
                      <div className="responsive-card-label">슬롯</div>
                      <div className="responsive-card-value">{promotionReasonLabel(item)}</div>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        </>
      )}
    </section>
  );
}

export function CandidateResearchPage({ snapshot, loading, errorMessage, onRefresh }: CandidateResearchPageProps) {
  const { entries, push, clear } = useConsoleLogs();

  const [symbol, setSymbol] = useState('');
  const [market, setMarket] = useState('KOSPI');
  const [latestSnapshot, setLatestSnapshot] = useState<CandidateResearchSnapshot | null>(null);
  const [history, setHistory] = useState<CandidateResearchSnapshot[]>([]);
  const [localResearchStatus, setLocalResearchStatus] = useState(snapshot.research || {});
  const [liveMarket, setLiveMarket] = useState<LiveMarketResponse | null>(null);
  const [monitorStatus, setMonitorStatus] = useState<CandidateMonitorStatusItem[]>([]);
  const [watchlists, setWatchlists] = useState<CandidateMonitorMarketWatchlist[]>([]);
  const [pendingTargets, setPendingTargets] = useState<CandidateMonitorSlot[]>([]);
  const [promotionEvents, setPromotionEvents] = useState<CandidateMonitorPromotionEvent[]>([]);
  const [pendingMarketView, setPendingMarketView] = useState<SnapshotMarketView>('ALL');
  const [activeMarketView, setActiveMarketView] = useState<SnapshotMarketView>('ALL');
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [targetsLoading, setTargetsLoading] = useState(false);
  const [queryLoading, setQueryLoading] = useState(false);
  const [queried, setQueried] = useState(false);
  const queryRequestIdRef = useRef(0);
  const pendingFilterTouchedRef = useRef(false);
  const activeFilterTouchedRef = useRef(false);

  const activeSlots = useMemo(
    () => watchlists.flatMap((item) => (Array.isArray(item.active_slots) ? item.active_slots : [])),
    [watchlists],
  );

  const totalCandidatePoolCount = useMemo(
    () => monitorStatus.reduce((sum, item) => sum + Number(item.candidate_pool_count || 0), 0),
    [monitorStatus],
  );
  const totalActiveCount = useMemo(
    () => monitorStatus.reduce((sum, item) => sum + Number(item.active_count || 0), 0),
    [monitorStatus],
  );
  const totalCoreCount = useMemo(
    () => monitorStatus.reduce((sum, item) => sum + Number(item.core_count || 0), 0),
    [monitorStatus],
  );
  const totalPromotionCount = useMemo(
    () => monitorStatus.reduce((sum, item) => sum + Number(item.promotion_count || 0), 0),
    [monitorStatus],
  );
  const totalHeldCount = useMemo(
    () => monitorStatus.reduce((sum, item) => sum + Number(item.held_count || 0), 0),
    [monitorStatus],
  );

  const loadCandidateBoards = useCallback(async (forceRefresh = false, silent = false) => {
    setTargetsLoading(true);
    try {
      const monitorQuery = { market: ['KOSPI'], refresh: forceRefresh };
      const [researchStatusPayload, liveMarketPayload, monitorStatusPayload, monitorWatchlistPayload, monitorPromotionsPayload] = await Promise.all([
        fetchResearchStatus(),
        fetchLiveMarket(),
        fetchCandidateMonitorStatus(monitorQuery),
        fetchCandidateMonitorWatchlist({ ...monitorQuery, limit: 60, mode: 'missing_or_stale' }),
        fetchCandidateMonitorPromotions({ ...monitorQuery, limit: 20 }),
      ]);

      setLocalResearchStatus(researchStatusPayload?.ok !== false ? researchStatusPayload : {});
      setLiveMarket(liveMarketPayload || null);
      setMonitorStatus(monitorStatusPayload?.ok !== false && Array.isArray(monitorStatusPayload?.items) ? monitorStatusPayload.items : []);
      setWatchlists(monitorWatchlistPayload?.ok !== false && Array.isArray(monitorWatchlistPayload?.items) ? monitorWatchlistPayload.items : []);
      setPendingTargets(monitorWatchlistPayload?.ok !== false && Array.isArray(monitorWatchlistPayload?.pending_items) ? monitorWatchlistPayload.pending_items : []);
      setPromotionEvents(monitorPromotionsPayload?.ok !== false && Array.isArray(monitorPromotionsPayload?.items) ? monitorPromotionsPayload.items : []);

      if (!silent && (researchStatusPayload?.ok === false || monitorStatusPayload?.ok === false || monitorWatchlistPayload?.ok === false || monitorPromotionsPayload?.ok === false)) {
        push(
          'warning',
          '감시 상태 일부만 불러왔어',
          researchStatusPayload?.error || monitorStatusPayload?.error || monitorWatchlistPayload?.error || monitorPromotionsPayload?.error,
          'research',
        );
      }
    } catch {
      setLocalResearchStatus({});
      setLiveMarket(null);
      setMonitorStatus([]);
      setWatchlists([]);
      setPendingTargets([]);
      setPromotionEvents([]);
      if (!silent) push('error', '감시 상태를 불러오지 못했어', undefined, 'research');
    } finally {
      setTargetsLoading(false);
    }
  }, [push]);

  useEffect(() => {
    void loadCandidateBoards(false, true);
  }, [loadCandidateBoards]);

  useEffect(() => {
    const preferred = preferredMarketView(liveMarket);
    if (!pendingFilterTouchedRef.current) {
      setPendingMarketView(preferred);
    }
    if (!activeFilterTouchedRef.current) {
      setActiveMarketView(preferred);
    }
  }, [liveMarket]);

  const runQuery = useCallback(async (targetSymbol: string, targetMarket: string) => {
    const normalizedSymbol = targetSymbol.trim().toUpperCase();
    if (!normalizedSymbol) {
      push('warning', '종목 코드를 입력해줘', undefined, 'research');
      return;
    }
    const requestId = queryRequestIdRef.current + 1;
    queryRequestIdRef.current = requestId;
    setQueryLoading(true);
    setQueried(false);
    setLatestSnapshot(null);
    setHistory([]);
    setExpandedIdx(null);

    try {
      const [latestRes, histRes] = await Promise.allSettled([
        fetchCandidateResearchLatest({ symbol: normalizedSymbol, market: targetMarket }),
        fetchCandidateResearchHistory({ symbol: normalizedSymbol, market: targetMarket, limit: 50, descending: true }),
      ]);
      if (queryRequestIdRef.current !== requestId) return;

      const latestPayload = latestRes.status === 'fulfilled' ? latestRes.value : null;
      const historyPayload = histRes.status === 'fulfilled' ? histRes.value : null;
      const latestFailed = latestRes.status === 'rejected' || latestPayload?.ok === false;
      const historyFailed = histRes.status === 'rejected' || historyPayload?.ok === false;

      if (!latestFailed && latestPayload?.snapshot) {
        setLatestSnapshot(latestPayload.snapshot);
      }
      if (!historyFailed && Array.isArray(historyPayload?.snapshots)) {
        setHistory(historyPayload.snapshots);
      }

      if (latestFailed && historyFailed) {
        push('error', '조회 실패', latestPayload?.error || historyPayload?.error, 'research');
      } else {
        push('success', `${normalizedSymbol} 조회 완료`, undefined, 'research');
        setQueried(true);
      }
    } catch {
      if (queryRequestIdRef.current !== requestId) return;
      push('error', '조회 실패', undefined, 'research');
    } finally {
      if (queryRequestIdRef.current === requestId) {
        setQueryLoading(false);
      }
    }
  }, [push]);

  const handleQuery = useCallback(() => runQuery(symbol, market), [market, runQuery, symbol]);

  const handleSelectTarget = useCallback((targetSymbol: string, targetMarket: string) => {
    setSymbol(targetSymbol);
    setMarket(targetMarket);
    void runQuery(targetSymbol, targetMarket);
  }, [runQuery]);

  const handleRefresh = useCallback(() => {
    onRefresh();
    void loadCandidateBoards(true);
  }, [loadCandidateBoards, onRefresh]);

  const researchStatus = localResearchStatus;
  const storageStatusLabel = providerStatusToKorean(researchStatus.status);
  const storageStatusTone = researchStatus.status === 'healthy'
    ? 'good'
    : researchStatus.status === 'missing'
      ? 'neutral'
      : 'bad';
  const runStatusTone = researchStatus.partial_failure || researchStatus.last_run_status === 'failed'
    ? 'bad'
    : researchStatus.last_run_status === 'success'
      ? 'good'
      : 'neutral';

  const topStatusItems = [
    { label: '감시 슬롯', value: `${totalActiveCount || activeSlots.length}개`, tone: (totalActiveCount || activeSlots.length) > 0 ? 'good' as const : 'neutral' as const },
    { label: '필요', value: `${pendingTargets.length}개`, tone: pendingTargets.length > 0 ? 'bad' as const : 'good' as const },
    { label: '저장소', value: storageStatusLabel, tone: storageStatusTone as 'good' | 'neutral' | 'bad' },
    { label: '실행', value: researchStatus.last_run_status || '대기', tone: runStatusTone as 'good' | 'neutral' | 'bad' },
    { label: '출처', value: formatNumber(researchStatus.avg_source_quality_score, 2), tone: Number(researchStatus.avg_source_quality_score || 0) >= 0.65 ? 'good' as const : 'bad' as const },
  ];
  const researchHeadline = researchStatus.partial_failure
    ? '리서치 일부 실패'
    : pendingTargets.length > 0
      ? '분석 대기 있음'
      : researchStatus.status === 'healthy'
        ? '리서치 정상'
        : '리서치 확인 필요';
  const researchHeadlineTone = researchStatus.partial_failure || researchStatus.status === 'stale' || researchStatus.status === 'invalid'
    ? 'bad'
    : pendingTargets.length > 0
      ? 'warn'
      : 'good';
  const recentErrorText = researchStatus.partial_failure && Array.isArray(researchStatus.recent_errors) && researchStatus.recent_errors.length > 0
    ? researchStatus.recent_errors.slice(0, 2).map((item) => `${item.market || '-'}:${item.symbol || '-'} ${item.error || ''}`).join(' / ')
    : '';

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell workspace-grid">
          <ConsoleActionBar
            title="리서치"
            subtitle=""
            lastUpdated={researchStatus.last_generated_at || monitorStatus[0]?.generated_at || latestSnapshot?.generated_at || latestSnapshot?.bucket_ts || ''}
            loading={loading}
            errorMessage={errorMessage}
            statusItems={topStatusItems}
            onRefresh={handleRefresh}
            logs={entries}
            onClearLogs={clear}
            actions={[]}
          />

          <section className={`research-command-center is-${researchHeadlineTone} is-compact`}>
            <div>
              <div className="ops-eyebrow">상태</div>
              <div className="ops-command-title">{researchHeadline}</div>
              {recentErrorText ? <div className="research-error-line research-error-text">{recentErrorText}</div> : null}
            </div>
            <div className="research-command-metrics">
              <div><span>감시 슬롯</span><strong>{totalActiveCount || activeSlots.length}</strong></div>
              <div><span>필요</span><strong>{pendingTargets.length}</strong></div>
              <div><span>성공/실패</span><strong>{researchStatus.success_count ?? 0}/{researchStatus.failure_count ?? 0}</strong></div>
              <div><span>차단</span><strong>{researchStatus.quality_gate_rejected_count ?? 0}</strong></div>
              <div><span>출처</span><strong>{formatNumber(researchStatus.avg_source_quality_score, 2)}</strong></div>
              <div><span>1D hit</span><strong>{ratioPercentValue(researchStatus.outcome_1d_hit_rate)}</strong></div>
              <div><span>3D hit</span><strong>{ratioPercentValue(researchStatus.outcome_3d_hit_rate)}</strong></div>
              <div><span>5D hit</span><strong>{ratioPercentValue(researchStatus.outcome_5d_hit_rate)}</strong></div>
              <div><span>20D hit</span><strong>{ratioPercentValue(researchStatus.outcome_20d_hit_rate)}</strong></div>
            </div>
          </section>

          <section className="page-section workspace-two-column is-research-compact">
            <div className="workspace-card-block research-query-panel">
              <div className="workspace-card-head">
                <div>
                  <div className="section-title">조회</div>
                </div>
              </div>
              <div className="workspace-query-grid">
                <div>
                  <div className="workspace-field-label">종목</div>
                  <input
                    type="text"
                    className="input-field"
                    placeholder="예: 005930, AAPL"
                    value={symbol}
                    onChange={(e) => setSymbol(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && void handleQuery()}
                    style={{ width: '100%', padding: '10px 12px', fontSize: 16 }}
                  />
                </div>
                <div>
                  <div className="workspace-field-label">시장</div>
                  <select
                    className="input-field"
                    value={market}
                    onChange={(e) => setMarket(e.target.value)}
                    style={{ width: '100%', padding: '10px 12px', fontSize: 16 }}
                  >
                    {MARKET_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                </div>
                <button
                  type="button"
                  className="action-button is-primary"
                  onClick={() => void handleQuery()}
                  disabled={queryLoading}
                  style={{ alignSelf: 'end', padding: '10px 18px', fontSize: 16 }}
                >
                  {queryLoading ? '조회 중...' : '조회'}
                </button>
              </div>
            </div>

            <div className="workspace-card-block research-monitor-panel">
              <div className="workspace-card-head">
                <div>
                  <div className="section-title">감시</div>
                </div>
              </div>
              <div className="workspace-chip-row" style={{ marginBottom: 12 }}>
                <span className={liveMarket?.market_sessions?.KR?.is_open ? 'inline-badge is-success' : 'inline-badge'}>
                  KR {liveMarket?.market_sessions?.KR?.status_label || '대기'}
                </span>
                <span className={liveMarket?.market_sessions?.US?.is_open ? 'inline-badge is-success' : 'inline-badge'}>
                  US {liveMarket?.market_sessions?.US?.status_label || '대기'}
                </span>
              </div>
              <div className="workspace-mini-metrics">
                <div className="workspace-mini-metric"><span>후보</span><strong>{totalCandidatePoolCount}개</strong></div>
                <div className="workspace-mini-metric"><span>감시</span><strong>{totalActiveCount}개</strong></div>
                <div className="workspace-mini-metric"><span>핵심</span><strong>{totalCoreCount}개</strong></div>
                <div className="workspace-mini-metric"><span>승격</span><strong>{totalPromotionCount}개</strong></div>
                <div className="workspace-mini-metric"><span>보유</span><strong>{totalHeldCount}개</strong></div>
                <div className="workspace-mini-metric"><span>대상</span><strong>{pendingTargets.length}개</strong></div>
                <div className="workspace-mini-metric"><span>성공/실패</span><strong>{researchStatus.success_count ?? 0}/{researchStatus.failure_count ?? 0}</strong></div>
                <div className="workspace-mini-metric"><span>부분</span><strong>{researchStatus.partial_failure ? '있음' : '없음'}</strong></div>
              </div>
              {researchStatus.partial_failure && Array.isArray(researchStatus.recent_errors) && researchStatus.recent_errors.length > 0 ? (
                <div className="workspace-summary-card" style={{ marginTop: 12 }}>
                  <div className="workspace-summary-title">실패</div>
                  <div className="workspace-summary-copy research-error-text">
                    {researchStatus.recent_errors.slice(0, 3).map((item) => `${item.market || '-'}:${item.symbol || '-'} ${item.error || ''}`).join(' / ')}
                  </div>
                </div>
              ) : null}
            </div>
          </section>

          <MarketSummarySection items={monitorStatus} />

          <MonitorSlotSection
            title="대상"
            copy="감시 슬롯 중에서 snapshot이 없거나 stale인 대상만 먼저 돌린다. 핵심 감시와 승격 슬롯 위주라서 더 이상 전체 후보 목록에 끌려가지 않아."
            items={pendingTargets}
            loading={targetsLoading}
            marketView={pendingMarketView}
            liveMarket={liveMarket}
            onChangeMarketView={(view) => {
              pendingFilterTouchedRef.current = true;
              setPendingMarketView(view);
            }}
            onSelect={handleSelectTarget}
            emptyText={targetsLoading ? '불러오는 중...' : '없음'}
            highlightPending
          />

          <MonitorSlotSection
            title="감시"
            copy="여기가 후보 리서치의 기준 목록이야. 보유 추적, 핵심 감시, 승격 슬롯만 남기고 애매한 중간 후보는 걷어냈어."
            items={activeSlots}
            loading={targetsLoading}
            marketView={activeMarketView}
            liveMarket={liveMarket}
            onChangeMarketView={(view) => {
              activeFilterTouchedRef.current = true;
              setActiveMarketView(view);
            }}
            onSelect={handleSelectTarget}
            emptyText={targetsLoading ? '불러오는 중...' : '없음'}
          />

          <PromotionSection items={promotionEvents} />

          {latestSnapshot && <CandidateResearchCard item={latestSnapshot} />}

          {queried && !latestSnapshot && !queryLoading && (
            <div className="page-section workspace-empty-state">
              없음
            </div>
          )}

          {history.length > 0 && (
            <section className="page-section workspace-table-section">
              <div className="workspace-card-head section-head-row">
                <div>
                  <div className="section-title">이력</div>
                  <div className="section-copy">감시 슬롯에서 선택한 종목이나 직접 조회한 종목의 저장된 리서치 이력을 본다.</div>
                </div>
                <div className="section-toolbar">
                  <div className="section-table-meta">선택 종목 {symbol.trim().toUpperCase() || '-'} · 시장 {market}</div>
                  <div className="inline-badge">{history.length}개</div>
                </div>
              </div>
              <div style={{ overflow: 'auto' }}>
                <table className="workspace-table" style={{ minWidth: 760 }}>
                  <thead>
                    <tr>
                      <th>시각</th>
                      <th>점수</th>
                      <th>상태</th>
                      <th>신뢰도</th>
                      <th>요약</th>
                      <th>경고</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((item, idx) => {
                      const warnings = Array.isArray(item.warnings) ? item.warnings : [];
                      const components = item.components && typeof item.components === 'object' ? item.components as Record<string, number> : {};
                      const isExpanded = expandedIdx === idx;
                      const status = snapshotStatus(item);
                      return (
                        <Fragment key={`${item.bucket_ts}-${idx}`}>
                          <tr style={{ cursor: 'pointer' }} onClick={() => setExpandedIdx(isExpanded ? null : idx)}>
                            <td>{formatDateTime(item.bucket_ts)}</td>
                            <td>{scoreDisplay(item)}</td>
                            <td><span className={status.tone}>{status.label}</span></td>
                            <td>
                              <div className="workspace-chip-row">
                                <span className={freshnessBadge(item).tone}>{freshnessBadge(item).label}</span>
                                <span className={gradeBadge(item).tone}>{gradeBadge(item).label}</span>
                              </div>
                            </td>
                            <td>{item.validation?.grade === 'D' ? (item.validation?.exclusion_reason || '제외') : (item.summary ? (item.summary.length > 48 ? `${item.summary.slice(0, 48)}…` : item.summary) : '-')}</td>
                            <td>{warnings.length > 0 ? warnings.map((warning) => reasonCodeToKorean(String(warning))).join(', ') : '-'}</td>
                          </tr>
                          {isExpanded && (
                            <tr>
                              <td colSpan={6}>
                                <div className="workspace-expanded-panel">
                                  <div className="workspace-chip-row" style={{ marginBottom: 12 }}>
                                    <span className={freshnessBadge(item).tone}>{freshnessBadge(item).label}</span>
                                    <span className={gradeBadge(item).tone}>{gradeBadge(item).label}</span>
                                    {item.validation?.reason ? <span className="inline-badge">{reasonCodeToKorean(String(item.validation.reason))}</span> : null}
                                  </div>
                                  {Object.keys(components).length > 0 && (
                                    <div className="workspace-score-grid" style={{ marginBottom: 12 }}>
                                      {Object.entries(components).map(([key, value]) => (
                                        <ScoreBar key={key} label={key} value={typeof value === 'number' ? value : 0} />
                                      ))}
                                    </div>
                                  )}
                                  <div className="workspace-summary-card">
                                    <div className="workspace-summary-title">요약</div>
                                    <div className="workspace-summary-copy">{item.summary || '-'}</div>
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
