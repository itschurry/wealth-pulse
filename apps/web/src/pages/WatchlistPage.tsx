import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchWatchlist, fetchWatchlistActions, saveWatchlist, searchStocks } from '../api/domain';
import { ConsoleActionBar } from '../components/ConsoleActionBar';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import type { ConsoleSnapshot } from '../types/consoleView';
import type { StockSearchResult, WatchlistAction, WatchlistActionItem, WatchlistItem } from '../types/domain';
import { formatDateTime, formatKRW, formatNumber, formatSymbol } from '../utils/format';

interface WatchlistPageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
}

function isKospi(market: string): boolean {
  return market.toUpperCase() === 'KOSPI' || market.toUpperCase() === 'KOSDAQ';
}

export function WatchlistPage({ loading, errorMessage, onRefresh }: WatchlistPageProps) {
  const { entries, push, clear } = useConsoleLogs();

  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [actionItems, setActionItems] = useState<WatchlistActionItem[]>([]);
  const [actions, setActions] = useState<WatchlistAction[]>([]);
  const [actionsGeneratedAt, setActionsGeneratedAt] = useState('');

  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<StockSearchResult[]>([]);
  const [searchOpen, setSearchOpen] = useState(false);

  const [pageLoading, setPageLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [saveLoading, setSaveLoading] = useState(false);

  const searchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const searchContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setPageLoading(true);
    fetchWatchlist()
      .then((res) => setItems(res.items || []))
      .catch(() => push('error', '관심 종목 불러오기 실패', undefined, 'watchlist'))
      .finally(() => setPageLoading(false));
  }, []);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (searchContainerRef.current && !searchContainerRef.current.contains(event.target as Node)) {
        setSearchOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSearchChange = useCallback((query: string) => {
    setSearchQuery(query);
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    if (!query.trim()) {
      setSearchResults([]);
      setSearchOpen(false);
      return;
    }
    searchDebounceRef.current = setTimeout(async () => {
      try {
        const res = await searchStocks(query);
        setSearchResults(res.results || []);
        setSearchOpen(true);
      } catch {
        setSearchResults([]);
      }
    }, 300);
  }, []);

  const handleAddItem = useCallback((result: StockSearchResult) => {
    setItems((prev) => {
      if (prev.some((item) => item.code === result.code && item.market === result.market)) return prev;
      return [...prev, { code: result.code, name: result.name, market: result.market }];
    });
    setSearchQuery('');
    setSearchResults([]);
    setSearchOpen(false);
    push('success', `${result.name}(${result.code}) 추가됨`, undefined, 'watchlist');
  }, [push]);

  const handleRemove = useCallback((code: string, market: string) => {
    setItems((prev) => prev.filter((item) => !(item.code === code && item.market === market)));
  }, []);

  const handleSave = useCallback(async () => {
    setSaveLoading(true);
    try {
      await saveWatchlist(items);
      push('success', '관심 종목 저장 완료', undefined, 'watchlist');
    } catch {
      push('error', '저장 실패', undefined, 'watchlist');
    } finally {
      setSaveLoading(false);
    }
  }, [items, push]);

  const handleAnalyze = useCallback(async () => {
    if (items.length === 0) {
      push('warning', '관심 종목이 없습니다', undefined, 'watchlist');
      return;
    }
    setActionLoading(true);
    try {
      const res = await fetchWatchlistActions(items);
      setActionItems(res.data.items || []);
      setActions(res.data.actions || []);
      setActionsGeneratedAt(new Date().toISOString());
      push('success', `분석 완료 — ${(res.data.actions || []).length}개 액션`, undefined, 'watchlist');
    } catch {
      push('error', '분석 실패', undefined, 'watchlist');
    } finally {
      setActionLoading(false);
    }
  }, [items, push]);

  const statusItems = [
    { label: '관심 종목', value: `${items.length}개`, tone: 'neutral' as const },
    { label: '분석 액션', value: `${actions.length}개`, tone: actions.length > 0 ? 'good' as const : 'neutral' as const },
  ];

  const enrichedMap = new Map(actionItems.map((item) => [`${item.market}:${item.code}`, item]));

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell" style={{ display: 'grid', gap: 16 }}>
          <ConsoleActionBar
            title="관심 종목"
            subtitle="종목을 추가하고 기술적 분석과 수급 데이터를 조회합니다. 저장 버튼을 눌러야 목록이 서버에 반영됩니다."
            lastUpdated={actionsGeneratedAt}
            loading={loading || pageLoading}
            errorMessage={errorMessage}
            statusItems={statusItems}
            onRefresh={onRefresh}
            logs={entries}
            onClearLogs={clear}
            actions={[
              {
                label: '분석 실행',
                onClick: handleAnalyze,
                tone: 'primary' as const,
                busy: actionLoading,
                busyLabel: '분석 중...',
                disabled: items.length === 0,
              },
              {
                label: '저장',
                onClick: handleSave,
                busy: saveLoading,
                busyLabel: '저장 중...',
              },
            ]}
          />

          <section className="page-section" style={{ padding: 16 }}>
            <div className="section-title" style={{ marginBottom: 10 }}>종목 검색</div>
            <div ref={searchContainerRef} style={{ position: 'relative', maxWidth: 400 }}>
              <input
                type="text"
                className="input-field"
                placeholder="종목명 또는 코드 검색..."
                value={searchQuery}
                onChange={(e) => handleSearchChange(e.target.value)}
                onFocus={() => searchResults.length > 0 && setSearchOpen(true)}
                style={{ width: '100%', padding: '8px 12px', fontSize: 13 }}
              />
              {searchOpen && searchResults.length > 0 && (
                <div style={{
                  position: 'absolute',
                  top: '100%',
                  left: 0,
                  right: 0,
                  background: 'var(--bg)',
                  border: '1px solid var(--border)',
                  borderRadius: 6,
                  zIndex: 100,
                  maxHeight: 240,
                  overflowY: 'auto',
                }}>
                  {searchResults.map((result) => (
                    <button
                      key={`${result.market}:${result.code}`}
                      type="button"
                      className="ghost-button"
                      style={{ width: '100%', textAlign: 'left', padding: '8px 12px', borderRadius: 0, borderBottom: '1px solid var(--border)' }}
                      onClick={() => handleAddItem(result)}
                    >
                      <span style={{ fontWeight: 600 }}>{result.name}</span>
                      <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--text-3)' }}>{result.code} · {result.market}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </section>

          <section className="page-section" style={{ padding: 16 }}>
            <div className="section-head-row" style={{ marginBottom: 10 }}>
              <div className="section-title">관심 종목 목록</div>
              <div className="inline-badge">{items.length}개</div>
            </div>
            {items.length === 0 ? (
              <div style={{ fontSize: 12, color: 'var(--text-4)', padding: '12px 0' }}>관심 종목이 없습니다. 위에서 검색하여 추가하세요.</div>
            ) : (
              <div style={{ overflow: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 600 }}>
                  <thead>
                    <tr style={{ background: 'var(--bg-soft)', textAlign: 'left' }}>
                      <th style={{ padding: 10, fontSize: 12 }}>종목</th>
                      <th style={{ padding: 10, fontSize: 12 }}>시장</th>
                      <th style={{ padding: 10, fontSize: 12 }}>현재가</th>
                      <th style={{ padding: 10, fontSize: 12 }}>등락률</th>
                      <th style={{ padding: 10, fontSize: 12 }}>RSI</th>
                      <th style={{ padding: 10, fontSize: 12 }}>거래량비</th>
                      <th style={{ padding: 10, fontSize: 12 }}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((item) => {
                      const enriched = enrichedMap.get(`${item.market}:${item.code}`);
                      const technicals = enriched?.technicals || {};
                      const changePct = item.change_pct ?? (technicals.change_pct as number | undefined);
                      const price = item.price ?? (technicals.current_price as number | undefined);
                      const rsi = technicals.rsi14 as number | undefined;
                      const volRatio = technicals.volume_ratio as number | undefined;
                      return (
                        <tr key={`${item.market}:${item.code}`} style={{ borderTop: '1px solid var(--border)' }}>
                          <td style={{ padding: 10, fontSize: 12 }}>
                            <div style={{ fontWeight: 600 }}>{formatSymbol(item.code, item.name)}</div>
                          </td>
                          <td style={{ padding: 10, fontSize: 12 }}>{item.market}</td>
                          <td style={{ padding: 10, fontSize: 12 }}>
                            {price != null ? (isKospi(item.market) ? formatKRW(price) : `$${formatNumber(price, 2)}`) : '-'}
                          </td>
                          <td style={{ padding: 10, fontSize: 12 }}>
                            {changePct != null ? (
                              <span className={changePct >= 0 ? 'is-up' : 'is-down'}>
                                {changePct >= 0 ? '▲' : '▼'}{Math.abs(changePct).toFixed(2)}%
                              </span>
                            ) : '-'}
                          </td>
                          <td style={{ padding: 10, fontSize: 12 }}>{rsi != null ? formatNumber(rsi, 1) : '-'}</td>
                          <td style={{ padding: 10, fontSize: 12 }}>{volRatio != null ? formatNumber(volRatio, 2) : '-'}</td>
                          <td style={{ padding: 10, fontSize: 12 }}>
                            <button
                              type="button"
                              className="ghost-button"
                              style={{ color: 'var(--text-3)', fontSize: 12 }}
                              onClick={() => handleRemove(item.code, item.market)}
                            >
                              삭제
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {actions.length > 0 && (
            <section className="page-section" style={{ padding: 16 }}>
              <div className="section-head-row" style={{ marginBottom: 12 }}>
                <div>
                  <div className="section-title">분석 결과</div>
                  <div className="section-copy">{formatDateTime(actionsGeneratedAt)}</div>
                </div>
                <div className="inline-badge">{actions.length}개 액션</div>
              </div>
              <div className="operator-note-grid">
                {actions.map((action, i) => (
                  <div key={`action-${i}`} className="operator-note-card">
                    <div className="operator-note-label">{action.name || action.code || '-'} {action.code ? `(${action.code})` : ''}</div>
                    <div className="operator-note-copy">{action.market || '-'}</div>
                    <div style={{ marginTop: 6 }}>
                      <span className={`inline-badge ${action.action === 'watch' ? '' : action.action === 'buy' ? 'is-success' : ''}`}>
                        {action.action || '-'}
                      </span>
                    </div>
                    {action.reason && <div className="operator-note-copy" style={{ marginTop: 6 }}>{action.reason}</div>}
                    {action.confidence && <div className="operator-note-copy" style={{ marginTop: 4 }}>신뢰도 {action.confidence}</div>}
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
