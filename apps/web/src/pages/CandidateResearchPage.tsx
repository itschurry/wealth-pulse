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
import { formatDateTime, formatDateTimeWithAge, formatNumber } from '../utils/format';

interface CandidateResearchPageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
}

const MARKET_OPTIONS = [
  { label: 'KOSPI', value: 'KOSPI' },
  { label: 'NASDAQ', value: 'NASDAQ' },
];

type SnapshotMarketView = 'ALL' | 'KOSPI' | 'NASDAQ';

function normalizeSnapshotMarket(value: string | undefined): Exclude<SnapshotMarketView, 'ALL'> {
  return String(value || '').toUpperCase() === 'KOSPI' ? 'KOSPI' : 'NASDAQ';
}

function buildMarketCounts(items: Array<{ market?: string }>): Record<SnapshotMarketView, number> {
  const counts: Record<SnapshotMarketView, number> = { ALL: items.length, KOSPI: 0, NASDAQ: 0 };
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
  const usOpen = Boolean(sessions.US?.is_open);
  if (usOpen && !krOpen) return 'NASDAQ';
  if (krOpen && !usOpen) return 'KOSPI';
  return 'ALL';
}

function marketSessionText(liveMarket: LiveMarketResponse | null, market: Exclude<SnapshotMarketView, 'ALL'>): string {
  const session = market === 'KOSPI' ? liveMarket?.market_sessions?.KR : liveMarket?.market_sessions?.US;
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
  if (String(item.freshness || '').toLowerCase() === 'stale') return { label: '지연 리서치', tone: 'inline-badge is-danger' };
  const score = Number(item.research_score);
  if (!Number.isFinite(score)) return { label: '점수 대기', tone: 'inline-badge' };
  if (score >= 0.8) return { label: '우선 검토', tone: 'inline-badge is-success' };
  if (score >= 0.6) return { label: '리서치 후보', tone: 'inline-badge' };
  return { label: '관찰 유지', tone: 'inline-badge is-danger' };
}

function candidateStatusBadge(item: CandidateMonitorSlot): { label: string; tone: string } {
  if (!item.snapshot_exists) return { label: '리서치 없음', tone: 'inline-badge' };
  if (item.snapshot_fresh) return { label: '최신', tone: 'inline-badge is-success' };
  return { label: '지연', tone: 'inline-badge is-danger' };
}

function pendingCandidateBadge(item: CandidateMonitorSlot): { label: string; tone: string } {
  if (!item.snapshot_exists) return { label: '신규 리서치', tone: 'inline-badge' };
  return { label: '지연 리서치', tone: 'inline-badge is-danger' };
}

function candidateActionBadge(item: CandidateMonitorSlot): { label: string; tone: string } {
  const action = String(item.final_action || '').trim().toLowerCase();
  if (action === 'review_for_entry') return { label: '진입 검토', tone: 'inline-badge is-success' };
  if (action === 'watch_only') return { label: '관찰', tone: 'inline-badge' };
  if (action === 'blocked') return { label: '차단', tone: 'inline-badge is-danger' };
  if (action === 'do_not_touch') return { label: '보류', tone: 'inline-badge' };
  return { label: action || '-', tone: 'inline-badge' };
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
    <div className="workspace-score-row">
      <div className="workspace-score-label">{label}</div>
      <div className="workspace-score-track">
        <div className="workspace-score-fill" style={{ width: `${width}%` }} />
      </div>
      <div className="workspace-score-value">{formatNumber(value, 2)}</div>
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

  return (
    <div className="page-section workspace-analysis-section" style={{ padding: 16 }}>
      <div className="workspace-card-head" style={{ marginBottom: 12 }}>
        <div>
          <div className="section-title"><SymbolIdentity code={item.symbol} name={item.name} market={item.market} /></div>
          <div className="section-copy">생성 {formatDateTimeWithAge(item.generated_at || item.bucket_ts)}</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 27, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
            {scoreDisplay(item)}
          </div>
          <div className="workspace-chip-row" style={{ marginTop: 6, justifyContent: 'flex-end' }}>
            <span className={status.tone}>{status.label}</span>
            <span className={freshness.tone}>{freshness.label}</span>
            <span className={grade.tone}>{grade.label}</span>
          </div>
        </div>
      </div>

      {Object.keys(components).length > 0 && (
        <div className="workspace-score-grid">
          {Object.entries(components).map(([key, value]) => (
            <ScoreBar key={key} label={key} value={typeof value === 'number' ? value : 0} />
          ))}
        </div>
      )}

      <div className="workspace-summary-card" style={{ marginTop: 12 }}>
        <div className="workspace-summary-title">요약</div>
        <div className="workspace-summary-copy">{item.validation?.grade === 'D' ? (item.validation?.exclusion_reason || '검증 불가라 점수를 표시하지 않았습니다.') : (item.summary || '요약 없음')}</div>
      </div>

      {(warnings.length > 0 || tags.length > 0) && (
        <div className="workspace-chip-row" style={{ marginTop: 12 }}>
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
            {(['ALL', 'KOSPI', 'NASDAQ'] as const).map((view) => (
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
          <div style={{ overflow: 'auto' }}>
            <table className="workspace-table" style={{ minWidth: 1100 }}>
              <thead>
                <tr>
                  <th>종목</th>
                  <th>슬롯</th>
                  <th>전략</th>
                  <th>순위</th>
                  <th>리서치 상태</th>
                  <th>최근 리서치</th>
                  <th>액션</th>
                </tr>
              </thead>
              <tbody>
                {displayedItems.map((item, idx) => {
                  const status = candidateStatusBadge(item);
                  const pending = pendingCandidateBadge(item);
                  const action = candidateActionBadge(item);
                  const slot = slotTypeBadge(item);
                  const grade = validationBadge(item);
                  const market = item.market || 'KOSPI';
                  const symbol = item.symbol || item.code || '';
                  return (
                    <tr
                      key={`${market}-${symbol}-${item.strategy_id || idx}`}
                      style={{ cursor: 'pointer' }}
                      onClick={() => symbol && onSelect(symbol, market)}
                    >
                      <td><SymbolIdentity code={symbol} name={item.name} market={item.market} /></td>
                      <td>
                        <div className="workspace-chip-row">
                          <span className={slot.tone}>{slot.label}</span>
                        </div>
                      </td>
                      <td>{item.strategy_name || item.strategy_id || '-'}</td>
                      <td>{item.candidate_rank ?? '-'}</td>
                      <td>
                        <div className="workspace-chip-row">
                          <span className={status.tone}>{status.label}</span>
                          {grade ? <span className={grade.tone}>{grade.label}</span> : null}
                          {highlightPending ? <span className={pending.tone}>{pending.label}</span> : null}
                        </div>
                      </td>
                      <td>{item.snapshot_generated_at ? formatDateTime(item.snapshot_generated_at) : '없음'}</td>
                      <td><span className={action.tone}>{action.label}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="responsive-card-list">
            {displayedItems.map((item, idx) => {
              const status = candidateStatusBadge(item);
              const pending = pendingCandidateBadge(item);
              const action = candidateActionBadge(item);
              const slot = slotTypeBadge(item);
              const grade = validationBadge(item);
              const market = item.market || 'KOSPI';
              const symbol = item.symbol || item.code || '';
              return (
                <article
                  key={`${market}-${symbol}-${item.strategy_id || idx}-card`}
                  className="responsive-card"
                  onClick={() => symbol && onSelect(symbol, market)}
                >
                  <div className="responsive-card-head">
                    <div>
                      <div className="responsive-card-title">{item.name || symbol || '-'}</div>
                      <div className="signal-cell-copy">{item.strategy_name || item.strategy_id || '-'} · 순위 {item.candidate_rank ?? '-'}</div>
                    </div>
                    <span className={action.tone}>{action.label}</span>
                  </div>
                  <div className="workspace-chip-row" style={{ marginBottom: 12 }}>
                    <span className={slot.tone}>{slot.label}</span>
                    <span className={status.tone}>{status.label}</span>
                    {grade ? <span className={grade.tone}>{grade.label}</span> : null}
                    {highlightPending ? <span className={pending.tone}>{pending.label}</span> : null}
                  </div>
                  <div className="responsive-card-grid">
                    <div>
                      <div className="responsive-card-label">시장</div>
                      <div className="responsive-card-value">{item.market || '-'}</div>
                    </div>
                    <div>
                      <div className="responsive-card-label">최근 리서치</div>
                      <div className="responsive-card-value">{item.snapshot_generated_at ? formatDateTime(item.snapshot_generated_at) : '없음'}</div>
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
    return <div className="page-section workspace-empty-state">시장별 감시 상태가 아직 없어.</div>;
  }

  return (
    <section className="page-section workspace-table-section">
      <div className="workspace-card-head section-head-row">
        <div>
          <div className="section-title">시장별 감시 상태</div>
          <div className="section-copy">KOSPI/NASDAQ 후보 풀과 핵심 감시, 승격 슬롯, 보유 추적 수를 따로 본다.</div>
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
          <div className="section-title">최근 승격/탈락 로그</div>
          <div className="section-copy">새 구조가 실제로 종목을 감시 슬롯에 넣고 빼는지 바로 확인하는 용도야.</div>
        </div>
        <div className="section-toolbar">
          <div className="inline-badge">{items.length}개</div>
        </div>
      </div>
      {items.length === 0 ? (
        <div className="workspace-empty-state">최근 승격/탈락 로그가 아직 없어.</div>
      ) : (
        <>
          <div style={{ overflow: 'auto' }}>
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
                      <td><SymbolIdentity code={item.symbol} market={item.market} /></td>
                      <td><span className={event.tone}>{event.label}</span></td>
                      <td>{promotionReasonLabel(item)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="responsive-card-list">
            {items.map((item, idx) => {
              const event = promotionEventBadge(item);
              return (
                <article key={`${item.market}-${item.symbol}-${item.created_at}-${idx}-card`} className="responsive-card" style={{ cursor: 'default' }}>
                  <div className="responsive-card-head">
                    <div>
                      <div className="responsive-card-title">{item.symbol || '-'}</div>
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
      const monitorQuery = { market: ['KOSPI', 'NASDAQ'], refresh: forceRefresh };
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

  const topStatusItems = [
    { label: '감시 슬롯', value: `${totalActiveCount || activeSlots.length}개`, tone: (totalActiveCount || activeSlots.length) > 0 ? 'good' as const : 'neutral' as const },
    { label: '지금 리서치 필요', value: `${pendingTargets.length}개`, tone: pendingTargets.length > 0 ? 'bad' as const : 'good' as const },
    { label: '저장소 상태', value: storageStatusLabel, tone: storageStatusTone as 'good' | 'neutral' | 'bad' },
  ];

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell workspace-grid">
          <ConsoleActionBar
            title="후보 리서치"
            subtitle="전체 캐시 목록보다 지금 감시 중인 핵심 슬롯과 승격 슬롯을 먼저 본다. 애매한 중복 없이 이 화면을 truth source로 쓴다."
            lastUpdated={researchStatus.last_generated_at || monitorStatus[0]?.generated_at || latestSnapshot?.generated_at || latestSnapshot?.bucket_ts || ''}
            loading={loading}
            errorMessage={errorMessage}
            statusItems={topStatusItems}
            onRefresh={handleRefresh}
            logs={entries}
            onClearLogs={clear}
            actions={[]}
          />

          <section className="page-section workspace-two-column">
            <div className="workspace-card-block">
              <div className="workspace-card-head">
                <div>
                  <div className="section-title">종목 조회</div>
                  <div className="section-copy">감시 슬롯에서 바로 눌러도 되고, 직접 코드와 시장을 넣어서 latest/history를 확인해도 돼.</div>
                </div>
              </div>
              <div className="workspace-query-grid">
                <div>
                  <div className="workspace-field-label">종목 코드</div>
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

            <div className="workspace-card-block">
              <div className="workspace-card-head">
                <div>
                  <div className="section-title">감시 운영 요약</div>
                  <div className="section-copy">핵심 감시와 승격 슬롯이 실제 리서치 우선순위를 결정해. 지금은 열린 시장을 기본으로 먼저 보여주고, 닫힌 시장은 상태만 같이 표시해.</div>
                </div>
              </div>
              <div className="workspace-chip-row" style={{ marginBottom: 12 }}>
                <span className={liveMarket?.market_sessions?.KR?.is_open ? 'inline-badge is-success' : 'inline-badge'}>
                  한국장 {liveMarket?.market_sessions?.KR?.status_label || '상태 대기'}
                </span>
                <span className={liveMarket?.market_sessions?.US?.is_open ? 'inline-badge is-success' : 'inline-badge'}>
                  미국장 {liveMarket?.market_sessions?.US?.status_label || '상태 대기'}
                </span>
              </div>
              <div className="workspace-mini-metrics">
                <div className="workspace-mini-metric"><span>후보 풀</span><strong>{totalCandidatePoolCount}개</strong></div>
                <div className="workspace-mini-metric"><span>감시 슬롯</span><strong>{totalActiveCount}개</strong></div>
                <div className="workspace-mini-metric"><span>핵심 감시</span><strong>{totalCoreCount}개</strong></div>
                <div className="workspace-mini-metric"><span>승격 슬롯</span><strong>{totalPromotionCount}개</strong></div>
                <div className="workspace-mini-metric"><span>보유 추적</span><strong>{totalHeldCount}개</strong></div>
                <div className="workspace-mini-metric"><span>저장소 fresh</span><strong>{researchStatus.fresh_symbol_count ?? 0}개</strong></div>
                <div className="workspace-mini-metric"><span>즉시 리서치 대상</span><strong>{pendingTargets.length}개</strong></div>
                <div className="workspace-mini-metric"><span>마지막 적재</span><strong>{researchStatus.last_generated_at ? formatDateTime(researchStatus.last_generated_at) : '대기'}</strong></div>
              </div>
            </div>
          </section>

          <MarketSummarySection items={monitorStatus} />

          <MonitorSlotSection
            title="지금 리서치 돌릴 감시 슬롯"
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
            emptyText={targetsLoading ? '불러오는 중...' : `${pendingMarketView} 시장에서 지금 돌릴 리서치 대상이 없어.`}
            highlightPending
          />

          <MonitorSlotSection
            title="현재 핵심 감시 / 승격 슬롯"
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
            emptyText={targetsLoading ? '불러오는 중...' : `${activeMarketView} 시장 감시 슬롯이 없어.`}
          />

          <PromotionSection items={promotionEvents} />

          {latestSnapshot && <CandidateResearchCard item={latestSnapshot} />}

          {queried && !latestSnapshot && !queryLoading && (
            <div className="page-section workspace-empty-state">
              {symbol.trim().toUpperCase()} ({market}) 에 대한 후보 리서치 이력이 없어.
            </div>
          )}

          {history.length > 0 && (
            <section className="page-section workspace-table-section">
              <div className="workspace-card-head section-head-row">
                <div>
                  <div className="section-title">스냅샷 이력</div>
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
                      <th>기준 시각</th>
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
                            <td>{item.validation?.grade === 'D' ? (item.validation?.exclusion_reason || '검증 제외') : (item.summary ? (item.summary.length > 88 ? `${item.summary.slice(0, 88)}…` : item.summary) : '요약 없음')}</td>
                            <td>{warnings.length > 0 ? warnings.map((warning) => reasonCodeToKorean(String(warning))).join(', ') : '경고 없음'}</td>
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
                                    <div className="workspace-summary-title">상세 요약</div>
                                    <div className="workspace-summary-copy">{item.summary || '요약 없음'}</div>
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
