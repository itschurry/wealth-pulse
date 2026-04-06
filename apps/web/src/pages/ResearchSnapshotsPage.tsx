import { useEffect, useState } from 'react';
import { fetchResearchSnapshotLatest, fetchResearchSnapshots } from '../api/domain';
import { ConsoleActionBar } from '../components/ConsoleActionBar';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import type { ConsoleSnapshot } from '../types/consoleView';
import type { ResearchSnapshotItem } from '../types/domain';
import { formatDateTime, formatNumber, formatSymbol } from '../utils/format';

interface ResearchSnapshotsPageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
}

const MARKET_OPTIONS = [
  { value: 'KOSPI', label: 'KOSPI' },
  { value: 'KOSDAQ', label: 'KOSDAQ' },
  { value: 'NASDAQ', label: 'NASDAQ' },
  { value: 'NYSE', label: 'NYSE' },
];

function ScoreBar({ value, max = 100, label }: { value: number; max?: number; label: string }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  const tone = pct >= 70 ? 'var(--success)' : pct >= 40 ? 'var(--warn, #e6a817)' : 'var(--danger, #d94f4f)';
  return (
    <div style={{ marginBottom: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 3 }}>
        <span style={{ color: 'var(--text-3)' }}>{label}</span>
        <span style={{ fontWeight: 600 }}>{formatNumber(value, 1)}</span>
      </div>
      <div style={{ height: 4, background: 'var(--border)', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: tone, borderRadius: 2 }} />
      </div>
    </div>
  );
}

function SnapshotCard({ item }: { item: ResearchSnapshotItem }) {
  const components = item.components && typeof item.components === 'object' ? item.components as Record<string, number> : {};
  const warnings = Array.isArray(item.warnings) ? item.warnings : [];
  const tags = Array.isArray(item.tags) ? item.tags : [];

  return (
    <div className="page-section" style={{ padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
        <div>
          <div className="section-title">{formatSymbol(item.symbol, item.name)} <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{item.market}</span></div>
          <div style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 2 }}>{formatDateTime(item.generated_at || item.bucket_ts)}</div>
        </div>
        <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
          <div style={{ fontSize: 22, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
            {item.research_score != null ? formatNumber(item.research_score, 1) : '-'}
          </div>
          <div style={{ fontSize: 10, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Research Score</div>
        </div>
      </div>

      {Object.keys(components).length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Components</div>
          {Object.entries(components).map(([k, v]) => (
            <ScoreBar key={k} label={k} value={typeof v === 'number' ? v : 0} />
          ))}
        </div>
      )}

      {item.summary && (
        <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.6, marginBottom: 10 }}>{item.summary}</div>
      )}

      {warnings.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          {warnings.map((w, i) => (
            <div key={i} className="inline-badge" style={{ marginRight: 4, marginBottom: 4, background: 'var(--danger-soft, rgba(217,79,79,0.12))', color: 'var(--danger, #d94f4f)' }}>
              {w}
            </div>
          ))}
        </div>
      )}

      {tags.length > 0 && (
        <div>
          {tags.map((t, i) => (
            <span key={i} className="inline-badge" style={{ marginRight: 4, marginBottom: 4 }}>{t}</span>
          ))}
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
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [queryLoading, setQueryLoading] = useState(false);
  const [recentLoading, setRecentLoading] = useState(false);
  const [queried, setQueried] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function loadRecent() {
      setRecentLoading(true);
      try {
        const response = await fetchResearchSnapshots({ limit: 30, descending: true });
        if (!cancelled && Array.isArray(response?.snapshots)) {
          setRecentSnapshots(response.snapshots);
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

  const handleQuery = async () => {
    if (!symbol.trim()) {
      push('warning', '종목 코드를 입력하세요', undefined, 'research');
      return;
    }
    setQueryLoading(true);
    setQueried(false);
    setLatestSnapshot(null);
    setHistory([]);
    setExpandedIdx(null);

    try {
      const [latestRes, histRes] = await Promise.allSettled([
        fetchResearchSnapshotLatest({ symbol: symbol.trim().toUpperCase(), market }),
        fetchResearchSnapshots({ symbol: symbol.trim().toUpperCase(), market, limit: 50, descending: true }),
      ]);

      if (latestRes.status === 'fulfilled' && latestRes.value?.snapshot) {
        setLatestSnapshot(latestRes.value.snapshot);
      }

      if (histRes.status === 'fulfilled' && Array.isArray(histRes.value?.snapshots)) {
        setHistory(histRes.value.snapshots);
      }

      if (latestRes.status === 'rejected' && histRes.status === 'rejected') {
        push('error', '조회 실패', undefined, 'research');
      } else {
        push('success', `${symbol.trim().toUpperCase()} 조회 완료`, undefined, 'research');
        setQueried(true);
      }
    } catch {
      push('error', '조회 실패', undefined, 'research');
    } finally {
      setQueryLoading(false);
    }
  };

  const statusItems = [
    { label: '최근 스냅샷', value: `${recentSnapshots.length}개`, tone: recentSnapshots.length > 0 ? 'good' as const : 'neutral' as const },
    { label: '종목', value: latestSnapshot ? `${latestSnapshot.symbol} · ${latestSnapshot.market}` : '-', tone: 'neutral' as const },
    { label: '조회 이력', value: `${history.length}개`, tone: history.length > 0 ? 'good' as const : 'neutral' as const },
  ];

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell" style={{ display: 'grid', gap: 16 }}>
          <ConsoleActionBar
            title="리서치 스냅샷"
            subtitle="Hanna 연구 점수 이력을 종목별로 조회합니다."
            lastUpdated={latestSnapshot?.generated_at || latestSnapshot?.bucket_ts || ''}
            loading={loading}
            errorMessage={errorMessage}
            statusItems={statusItems}
            onRefresh={onRefresh}
            logs={entries}
            onClearLogs={clear}
            actions={[]}
          />

          <section className="page-section" style={{ padding: 16 }}>
            <div className="section-head-row" style={{ marginBottom: 10 }}>
              <div>
                <div className="section-title">최신 스냅샷 목록</div>
                <div className="section-copy">지금 저장소에 있는 최신 Hanna snapshot을 먼저 보여줍니다.</div>
              </div>
              <div className="inline-badge">{recentLoading ? '불러오는 중...' : `${recentSnapshots.length}개`}</div>
            </div>
            {recentSnapshots.length === 0 ? (
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>표시할 최신 snapshot이 없습니다.</div>
            ) : (
              <div style={{ overflow: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 720 }}>
                  <thead>
                    <tr style={{ background: 'var(--bg-soft)', textAlign: 'left' }}>
                      <th style={{ padding: 10, fontSize: 12 }}>종목</th>
                      <th style={{ padding: 10, fontSize: 12 }}>시장</th>
                      <th style={{ padding: 10, fontSize: 12 }}>생성 시각</th>
                      <th style={{ padding: 10, fontSize: 12 }}>점수</th>
                      <th style={{ padding: 10, fontSize: 12 }}>요약</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentSnapshots.map((item, idx) => (
                      <tr
                        key={`${item.market}-${item.symbol}-${item.bucket_ts || idx}`}
                        style={{ borderTop: '1px solid var(--border)', cursor: 'pointer' }}
                        onClick={() => {
                          setSymbol(item.symbol || '');
                          setMarket(item.market || 'KOSPI');
                          setLatestSnapshot(item);
                        }}
                      >
                        <td style={{ padding: 10, fontSize: 12, fontWeight: 600 }}>{formatSymbol(item.symbol, item.name)}</td>
                        <td style={{ padding: 10, fontSize: 12 }}>{item.market || '-'}</td>
                        <td style={{ padding: 10, fontSize: 12, whiteSpace: 'nowrap' }}>{formatDateTime(item.generated_at || item.bucket_ts)}</td>
                        <td style={{ padding: 10, fontSize: 12, fontVariantNumeric: 'tabular-nums' }}>{item.research_score != null ? formatNumber(item.research_score, 1) : '-'}</td>
                        <td style={{ padding: 10, fontSize: 12, color: 'var(--text-3)' }}>{item.summary ? (item.summary.length > 70 ? `${item.summary.slice(0, 70)}…` : item.summary) : '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="page-section" style={{ padding: 16 }}>
            <div className="section-title" style={{ marginBottom: 10 }}>종목 조회</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }}>
              <div style={{ flex: '1 1 180px' }}>
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 4 }}>종목 코드</div>
                <input
                  type="text"
                  className="input-field"
                  placeholder="예: 005930, AAPL"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && void handleQuery()}
                  style={{ width: '100%', padding: '8px 12px', fontSize: 13 }}
                />
              </div>
              <div style={{ flex: '0 0 140px' }}>
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 4 }}>시장</div>
                <select
                  className="input-field"
                  value={market}
                  onChange={(e) => setMarket(e.target.value)}
                  style={{ width: '100%', padding: '8px 12px', fontSize: 13 }}
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
                style={{ alignSelf: 'flex-end', padding: '8px 20px', fontSize: 13 }}
              >
                {queryLoading ? '조회 중...' : '조회'}
              </button>
            </div>
          </section>

          {latestSnapshot && (
            <div>
              <div className="section-title" style={{ marginBottom: 8, paddingLeft: 2 }}>최신 스냅샷</div>
              <SnapshotCard item={latestSnapshot} />
            </div>
          )}

          {queried && !latestSnapshot && !queryLoading && (
            <div className="page-section" style={{ padding: 16, fontSize: 12, color: 'var(--text-4)' }}>
              {symbol.trim().toUpperCase()} ({market}) 에 대한 리서치 스냅샷이 없습니다.
            </div>
          )}

          {history.length > 0 && (
            <section className="page-section" style={{ padding: 16 }}>
              <div className="section-head-row" style={{ marginBottom: 10 }}>
                <div className="section-title">스냅샷 이력</div>
                <div className="inline-badge">{history.length}개</div>
              </div>
              <div style={{ overflow: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 560 }}>
                  <thead>
                    <tr style={{ background: 'var(--bg-soft)', textAlign: 'left' }}>
                      <th style={{ padding: 10, fontSize: 12 }}>기준 시각</th>
                      <th style={{ padding: 10, fontSize: 12 }}>점수</th>
                      <th style={{ padding: 10, fontSize: 12 }}>요약</th>
                      <th style={{ padding: 10, fontSize: 12 }}>경고</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((item, idx) => {
                      const warnings = Array.isArray(item.warnings) ? item.warnings : [];
                      const isExpanded = expandedIdx === idx;
                      const components = item.components && typeof item.components === 'object' ? item.components as Record<string, number> : {};
                      return (
                        <>
                          <tr
                            key={`${item.bucket_ts}-${idx}`}
                            style={{ borderTop: '1px solid var(--border)', cursor: 'pointer' }}
                            onClick={() => setExpandedIdx(isExpanded ? null : idx)}
                          >
                            <td style={{ padding: 10, fontSize: 12, whiteSpace: 'nowrap' }}>{formatDateTime(item.bucket_ts)}</td>
                            <td style={{ padding: 10, fontSize: 12, fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>
                              {item.research_score != null ? formatNumber(item.research_score, 1) : '-'}
                            </td>
                            <td style={{ padding: 10, fontSize: 12, color: 'var(--text-3)', maxWidth: 320 }}>
                              {item.summary ? (item.summary.length > 80 ? `${item.summary.slice(0, 80)}…` : item.summary) : '-'}
                            </td>
                            <td style={{ padding: 10, fontSize: 12 }}>
                              {warnings.length > 0
                                ? warnings.slice(0, 2).map((w, i) => (
                                    <span key={i} className="inline-badge" style={{ marginRight: 4, background: 'var(--danger-soft, rgba(217,79,79,0.12))', color: 'var(--danger, #d94f4f)', fontSize: 10 }}>{w}</span>
                                  ))
                                : <span style={{ color: 'var(--text-4)' }}>-</span>}
                              {warnings.length > 2 && <span style={{ fontSize: 10, color: 'var(--text-4)' }}>+{warnings.length - 2}</span>}
                            </td>
                          </tr>
                          {isExpanded && (
                            <tr key={`${item.bucket_ts}-${idx}-detail`} style={{ borderTop: '1px solid var(--border)', background: 'var(--bg-soft)' }}>
                              <td colSpan={4} style={{ padding: '12px 16px' }}>
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 16 }}>
                                  {Object.keys(components).length > 0 && (
                                    <div>
                                      <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 6, textTransform: 'uppercase' }}>Components</div>
                                      {Object.entries(components).map(([k, v]) => (
                                        <ScoreBar key={k} label={k} value={typeof v === 'number' ? v : 0} />
                                      ))}
                                    </div>
                                  )}
                                  {item.summary && (
                                    <div style={{ gridColumn: 'span 2' }}>
                                      <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 4, textTransform: 'uppercase' }}>요약</div>
                                      <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.6 }}>{item.summary}</div>
                                    </div>
                                  )}
                                  {warnings.length > 0 && (
                                    <div>
                                      <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 4, textTransform: 'uppercase' }}>경고</div>
                                      {warnings.map((w, i) => (
                                        <div key={i} style={{ fontSize: 12, color: 'var(--danger, #d94f4f)', marginBottom: 2 }}>· {w}</div>
                                      ))}
                                    </div>
                                  )}
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
