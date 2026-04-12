import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchResearchSnapshotLatest, fetchResearchSnapshots } from '../api/domain';
import { ConsoleActionBar } from '../components/ConsoleActionBar';
import { SymbolIdentity } from '../components/SymbolIdentity';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import type { ConsoleSnapshot } from '../types/consoleView';
import type { ResearchSnapshotItem } from '../types/domain';
import { formatDateTime, formatDateTimeWithAge, formatNumber } from '../utils/format';

interface ResearchSnapshotsPageProps {
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

function snapshotGrade(item: ResearchSnapshotItem): string {
  return String(item.validation?.grade || '').toUpperCase() || '-';
}

function scoreDisplay(item: ResearchSnapshotItem): string {
  if (snapshotGrade(item) === 'D') return '—';
  return item.research_score != null ? formatNumber(item.research_score, 1) : '점수 대기';
}

function freshnessBadge(item: ResearchSnapshotItem): { label: string; tone: string } {
  const freshness = String(item.freshness || item.freshness_detail?.status || '').toLowerCase();
  if (freshness === 'fresh') return { label: 'fresh', tone: 'inline-badge is-success' };
  if (freshness === 'stale') return { label: 'stale', tone: 'inline-badge is-danger' };
  if (freshness === 'invalid') return { label: 'invalid', tone: 'inline-badge is-danger' };
  if (freshness === 'missing') return { label: 'missing', tone: 'inline-badge' };
  return { label: 'unknown', tone: 'inline-badge' };
}

function gradeBadge(item: ResearchSnapshotItem): { label: string; tone: string } {
  const grade = snapshotGrade(item);
  if (grade === 'A') return { label: 'Grade A', tone: 'inline-badge is-success' };
  if (grade === 'B') return { label: 'Grade B', tone: 'inline-badge' };
  if (grade === 'C') return { label: 'Grade C', tone: 'inline-badge is-danger' };
  if (grade === 'D') return { label: 'Grade D', tone: 'inline-badge is-danger' };
  return { label: 'Grade -', tone: 'inline-badge' };
}

function snapshotStatus(item: ResearchSnapshotItem): { label: string; tone: string } {
  const grade = snapshotGrade(item);
  if (grade === 'D') return { label: '검증 제외', tone: 'inline-badge is-danger' };
  if (String(item.freshness || '').toLowerCase() === 'stale') return { label: 'stale research', tone: 'inline-badge is-danger' };
  const score = Number(item.research_score);
  if (!Number.isFinite(score)) return { label: '점수 대기', tone: 'inline-badge' };
  if (score >= 0.8) return { label: '우선 검토', tone: 'inline-badge is-success' };
  if (score >= 0.6) return { label: '리서치 후보', tone: 'inline-badge' };
  return { label: '관찰 유지', tone: 'inline-badge is-danger' };
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

function SnapshotCard({ item }: { item: ResearchSnapshotItem }) {
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
          <div style={{ fontSize: 24, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
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
          {warnings.map((warning, index) => <span key={`w-${index}`} className="inline-badge is-danger">{warning}</span>)}
          {tags.map((tag, index) => <span key={`t-${index}`} className="inline-badge">{tag}</span>)}
        </div>
      )}
    </div>
  );
}

export function ResearchSnapshotsPage({ loading, errorMessage, onRefresh }: ResearchSnapshotsPageProps) {
  const { entries, push, clear } = useConsoleLogs();

  const [symbol, setSymbol] = useState('');
  const [market, setMarket] = useState('KOSPI');
  const [latestSnapshot, setLatestSnapshot] = useState<ResearchSnapshotItem | null>(null);
  const [history, setHistory] = useState<ResearchSnapshotItem[]>([]);
  const [recentSnapshots, setRecentSnapshots] = useState<ResearchSnapshotItem[]>([]);
  const [recentMarket, setRecentMarket] = useState<SnapshotMarketView>('ALL');
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [queryLoading, setQueryLoading] = useState(false);
  const [recentLoading, setRecentLoading] = useState(false);
  const [queried, setQueried] = useState(false);
  const queryRequestIdRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    async function loadRecent() {
      setRecentLoading(true);
      try {
        const response = await fetchResearchSnapshots({ limit: 30, descending: true });
        if (!cancelled && response?.ok !== false && Array.isArray(response?.snapshots)) {
          setRecentSnapshots(response.snapshots);
        } else if (!cancelled) {
          setRecentSnapshots([]);
        }
      } catch {
        if (!cancelled) setRecentSnapshots([]);
      } finally {
        if (!cancelled) setRecentLoading(false);
      }
    }
    void loadRecent();
    return () => {
      cancelled = true;
    };
  }, []);

  const runQuery = useCallback(async (targetSymbol: string, targetMarket: string) => {
    const normalizedSymbol = targetSymbol.trim().toUpperCase();
    if (!normalizedSymbol) {
      push('warning', '종목 코드를 입력하세요', undefined, 'research');
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
        fetchResearchSnapshotLatest({ symbol: normalizedSymbol, market: targetMarket }),
        fetchResearchSnapshots({ symbol: normalizedSymbol, market: targetMarket, limit: 50, descending: true }),
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

  const recentMarketCounts = useMemo(() => {
    const counts: Record<SnapshotMarketView, number> = { ALL: recentSnapshots.length, KOSPI: 0, NASDAQ: 0 };
    recentSnapshots.forEach((item) => {
      counts[normalizeSnapshotMarket(item.market)] += 1;
    });
    return counts;
  }, [recentSnapshots]);

  const displayedRecentSnapshots = useMemo(() => {
    if (recentMarket === 'ALL') return recentSnapshots;
    return recentSnapshots.filter((item) => normalizeSnapshotMarket(item.market) === recentMarket);
  }, [recentMarket, recentSnapshots]);

  const topReviewCount = useMemo(
    () => displayedRecentSnapshots.filter((item) => Number(item.research_score) >= 0.8).length,
    [displayedRecentSnapshots],
  );
  const lowScoreCount = useMemo(
    () => displayedRecentSnapshots.filter((item) => Number.isFinite(Number(item.research_score)) && Number(item.research_score) < 0.6).length,
    [displayedRecentSnapshots],
  );

  const statusItems = [
    { label: '최근 스냅샷', value: `${displayedRecentSnapshots.length}개`, tone: displayedRecentSnapshots.length > 0 ? 'good' as const : 'neutral' as const },
    { label: '우선 검토', value: `${topReviewCount}개`, tone: topReviewCount > 0 ? 'good' as const : 'neutral' as const },
    { label: '조회 이력', value: `${history.length}개`, tone: history.length > 0 ? 'good' as const : 'neutral' as const },
  ];

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell workspace-grid">
          <ConsoleActionBar
            title="리서치 스냅샷"
            subtitle="리서치가 쌓이는지, 점수가 어느 구간에 몰리는지, 특정 종목 근거가 있는지 한 흐름으로 보여줍니다."
            lastUpdated={latestSnapshot?.generated_at || latestSnapshot?.bucket_ts || ''}
            loading={loading}
            errorMessage={errorMessage}
            statusItems={statusItems}
            onRefresh={onRefresh}
            logs={entries}
            onClearLogs={clear}
            actions={[]}
          />

          <section className="page-section workspace-two-column">
            <div className="workspace-card-block">
              <div className="workspace-card-head">
                <div>
                  <div className="section-title">종목 조회</div>
                  <div className="section-copy">코드와 시장을 넣으면 최신 스냅샷과 이력을 같이 가져옵니다.</div>
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
                    style={{ width: '100%', padding: '10px 12px', fontSize: 13 }}
                  />
                </div>
                <div>
                  <div className="workspace-field-label">시장</div>
                  <select
                    className="input-field"
                    value={market}
                    onChange={(e) => setMarket(e.target.value)}
                    style={{ width: '100%', padding: '10px 12px', fontSize: 13 }}
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
                  style={{ alignSelf: 'end', padding: '10px 18px', fontSize: 13 }}
                >
                  {queryLoading ? '조회 중...' : '조회'}
                </button>
              </div>
            </div>

            <div className="workspace-card-block">
              <div className="workspace-card-head">
                <div>
                  <div className="section-title">리서치 상태 요약</div>
                  <div className="section-copy">지금 저장소가 단순 적재인지, 실제로 읽을만한 후보가 있는지 구분해줍니다.</div>
                </div>
              </div>
              <div className="workspace-mini-metrics">
                <div className="workspace-mini-metric"><span>우선 검토</span><strong>{topReviewCount}개</strong></div>
                <div className="workspace-mini-metric"><span>저점수</span><strong>{lowScoreCount}개</strong></div>
                <div className="workspace-mini-metric"><span>최근 선택</span><strong>{latestSnapshot?.symbol || '-'}</strong></div>
                <div className="workspace-mini-metric"><span>최근 생성</span><strong>{latestSnapshot ? formatDateTime(latestSnapshot.generated_at || latestSnapshot.bucket_ts) : '대기'}</strong></div>
              </div>
            </div>
          </section>

          <section className="page-section workspace-table-section">
              <div className="workspace-card-head">
                <div>
                  <div className="section-title">최신 스냅샷 목록</div>
                  <div className="section-copy">한국장과 미국장을 분리해서 보면 어떤 시장의 리서치가 비는지 훨씬 빨리 읽힙니다.</div>
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                  {(['ALL', 'KOSPI', 'NASDAQ'] as const).map((view) => (
                    <button
                      key={view}
                      type="button"
                      className={recentMarket === view ? 'ghost-button is-active' : 'ghost-button'}
                      onClick={() => setRecentMarket(view)}
                    >
                      {view === 'ALL' ? `전체 ${recentMarketCounts.ALL}개` : `${view} ${recentMarketCounts[view]}개`}
                    </button>
                  ))}
                  <div className="inline-badge">{recentLoading ? '불러오는 중...' : `${displayedRecentSnapshots.length}개`}</div>
                </div>
              </div>
            {displayedRecentSnapshots.length === 0 ? (
              <div className="workspace-empty-state">{recentSnapshots.length === 0 ? '표시할 최신 snapshot이 없다.' : `${recentMarket} 시장 최신 snapshot이 없다.`}</div>
            ) : (
              <div style={{ overflow: 'auto' }}>
                <table className="workspace-table" style={{ minWidth: 840 }}>
                  <thead>
                    <tr>
                      <th>종목</th>
                      <th>생성 시각</th>
                      <th>점수</th>
                      <th>상태</th>
                      <th>신뢰도</th>
                      <th>요약</th>
                    </tr>
                  </thead>
                  <tbody>
                    {displayedRecentSnapshots.map((item, idx) => {
                      const status = snapshotStatus(item);
                      return (
                        <tr
                          key={`${item.market}-${item.symbol}-${item.bucket_ts || idx}`}
                          style={{ cursor: 'pointer' }}
                          onClick={() => {
                            const nextSymbol = item.symbol || '';
                            const nextMarket = item.market || 'KOSPI';
                            setSymbol(nextSymbol);
                            setMarket(nextMarket);
                            void runQuery(nextSymbol, nextMarket);
                          }}
                        >
                          <td><SymbolIdentity code={item.symbol} name={item.name} market={item.market} /></td>
                          <td>{formatDateTime(item.generated_at || item.bucket_ts)}</td>
                          <td>{scoreDisplay(item)}</td>
                          <td><span className={status.tone}>{status.label}</span></td>
                          <td>
                            <div className="workspace-chip-row">
                              <span className={freshnessBadge(item).tone}>{freshnessBadge(item).label}</span>
                              <span className={gradeBadge(item).tone}>{gradeBadge(item).label}</span>
                            </div>
                          </td>
                          <td>{item.validation?.grade === 'D' ? (item.validation?.exclusion_reason || '검증 제외') : (item.summary ? (item.summary.length > 84 ? `${item.summary.slice(0, 84)}…` : item.summary) : '요약 없음')}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {latestSnapshot && <SnapshotCard item={latestSnapshot} />}

          {queried && !latestSnapshot && !queryLoading && (
            <div className="page-section workspace-empty-state">
              {symbol.trim().toUpperCase()} ({market}) 에 대한 리서치 스냅샷이 없다.
            </div>
          )}

          {history.length > 0 && (
            <section className="page-section workspace-table-section">
              <div className="workspace-card-head">
                <div>
                  <div className="section-title">스냅샷 이력</div>
                  <div className="section-copy">클릭해서 상세 컴포넌트와 경고를 펼쳐봅니다.</div>
                </div>
                <div className="inline-badge">{history.length}개</div>
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
                        <>
                          <tr key={`${item.bucket_ts}-${idx}`} style={{ cursor: 'pointer' }} onClick={() => setExpandedIdx(isExpanded ? null : idx)}>
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
                            <td>{warnings.length > 0 ? warnings.join(', ') : '경고 없음'}</td>
                          </tr>
                          {isExpanded && (
                            <tr>
                              <td colSpan={6}>
                                <div className="workspace-expanded-panel">
                                  <div className="workspace-chip-row" style={{ marginBottom: 12 }}>
                                    <span className={freshnessBadge(item).tone}>{freshnessBadge(item).label}</span>
                                    <span className={gradeBadge(item).tone}>{gradeBadge(item).label}</span>
                                    {item.validation?.reason ? <span className="inline-badge">{item.validation.reason}</span> : null}
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
                        </>
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
