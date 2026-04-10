import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchWatchlist, fetchWatchlistActions, saveWatchlist, searchStocks } from '../api/domain';
import { ConsoleActionBar } from '../components/ConsoleActionBar';
import { SymbolIdentity } from '../components/SymbolIdentity';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import type { ConsoleSnapshot } from '../types/consoleView';
import type { StockSearchResult, WatchlistAction, WatchlistActionItem, WatchlistItem } from '../types/domain';
import { formatDateTime, formatKRW, formatNumber } from '../utils/format';

interface WatchlistPageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
}

function isKospi(market: string): boolean {
  return market.toUpperCase() === 'KOSPI' || market.toUpperCase() === 'KOSDAQ';
}

function normalizeItems(items: WatchlistItem[]) {
  return [...items]
    .map((item) => ({
      code: item.code,
      name: item.name,
      market: item.market,
    }))
    .sort((left, right) => `${left.market}:${left.code}`.localeCompare(`${right.market}:${right.code}`));
}

function displayMetric(value: number | undefined, kind: 'price' | 'pct' | 'analysis' | 'volume', market?: string) {
  if (value == null || Number.isNaN(Number(value))) {
    if (kind === 'price') return '시세 대기';
    if (kind === 'analysis') return '분석 전';
    if (kind === 'volume') return '집계 대기';
    return '변동 대기';
  }
  if (kind === 'price') return isKospi(String(market || '')) ? formatKRW(value) : `$${formatNumber(value, 2)}`;
  if (kind === 'pct') return `${value >= 0 ? '▲' : '▼'}${Math.abs(value).toFixed(2)}%`;
  if (kind === 'analysis') return formatNumber(value, 1);
  return formatNumber(value, 2);
}

function actionTone(action?: string) {
  const value = String(action || '').toLowerCase();
  if (value === 'buy') return 'inline-badge is-success';
  if (value === 'sell') return 'inline-badge is-danger';
  return 'inline-badge';
}

function clearAnalysisState(setActionItems: (items: WatchlistActionItem[]) => void, setActions: (actions: WatchlistAction[]) => void, setActionsGeneratedAt: (value: string) => void) {
  setActionItems([]);
  setActions([]);
  setActionsGeneratedAt('');
}

export function WatchlistPage({ loading, errorMessage, onRefresh }: WatchlistPageProps) {
  const { entries, push, clear } = useConsoleLogs();

  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [savedItems, setSavedItems] = useState<WatchlistItem[]>([]);
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
  const searchRequestIdRef = useRef(0);
  const analysisRequestIdRef = useRef(0);
  const searchContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setPageLoading(true);
    fetchWatchlist()
      .then((res) => {
        const next = res.items || [];
        setItems(next);
        setSavedItems(next);
      })
      .catch(() => push('error', '관심 종목 불러오기 실패', undefined, 'watchlist'))
      .finally(() => setPageLoading(false));
  }, [push]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (searchContainerRef.current && !searchContainerRef.current.contains(event.target as Node)) {
        setSearchOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      if (searchDebounceRef.current) {
        clearTimeout(searchDebounceRef.current);
      }
      searchRequestIdRef.current += 1;
      analysisRequestIdRef.current += 1;
    };
  }, []);

  const dirty = useMemo(() => JSON.stringify(normalizeItems(items)) !== JSON.stringify(normalizeItems(savedItems)), [items, savedItems]);

  const handleSearchChange = useCallback((query: string) => {
    setSearchQuery(query);
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    if (!query.trim()) {
      searchRequestIdRef.current += 1;
      setSearchResults([]);
      setSearchOpen(false);
      return;
    }
    const requestId = searchRequestIdRef.current + 1;
    searchRequestIdRef.current = requestId;
    searchDebounceRef.current = setTimeout(async () => {
      try {
        const res = await searchStocks(query);
        if (searchRequestIdRef.current !== requestId) return;
        setSearchResults(res.results || []);
        setSearchOpen(true);
      } catch {
        if (searchRequestIdRef.current !== requestId) return;
        setSearchResults([]);
      }
    }, 250);
  }, []);

  const handleAddItem = useCallback((result: StockSearchResult) => {
    setItems((prev) => {
      if (prev.some((item) => item.code === result.code && item.market === result.market)) return prev;
      return [...prev, { code: result.code, name: result.name, market: result.market }];
    });
    clearAnalysisState(setActionItems, setActions, setActionsGeneratedAt);
    setSearchQuery('');
    setSearchResults([]);
    setSearchOpen(false);
    push('success', `${result.name}(${result.code}) 추가됨`, undefined, 'watchlist');
  }, [push]);

  const handleRemove = useCallback((code: string, market: string) => {
    setItems((prev) => prev.filter((item) => !(item.code === code && item.market === market)));
    clearAnalysisState(setActionItems, setActions, setActionsGeneratedAt);
  }, []);

  const handleSave = useCallback(async () => {
    setSaveLoading(true);
    try {
      const response = await saveWatchlist(items);
      if (!response.ok || response.data?.ok === false) {
        throw new Error(response.data?.error || response.error?.message || '저장 실패');
      }
      setSavedItems(items);
      clearAnalysisState(setActionItems, setActions, setActionsGeneratedAt);
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
    const requestId = analysisRequestIdRef.current + 1;
    analysisRequestIdRef.current = requestId;
    setActionLoading(true);
    try {
      const res = await fetchWatchlistActions(items);
      if (analysisRequestIdRef.current !== requestId) return;
      if (!res.ok || res.data?.error) {
        throw new Error(res.data?.error || res.error?.message || '분석 실패');
      }
      setActionItems(res.data.items || []);
      setActions(res.data.actions || []);
      setActionsGeneratedAt(new Date().toISOString());
      push('success', `분석 완료 · ${(res.data.actions || []).length}개 액션`, undefined, 'watchlist');
    } catch {
      if (analysisRequestIdRef.current !== requestId) return;
      push('error', '분석 실패', undefined, 'watchlist');
    } finally {
      if (analysisRequestIdRef.current === requestId) {
        setActionLoading(false);
      }
    }
  }, [items, push]);

  const statusItems = [
    { label: '관심 종목', value: `${items.length}개`, tone: 'neutral' as const },
    { label: '저장 상태', value: dirty ? '수정됨' : '동기화', tone: dirty ? 'bad' as const : 'good' as const },
    { label: '분석 액션', value: `${actions.length}개`, tone: actions.length > 0 ? 'good' as const : 'neutral' as const },
  ];

  const enrichedMap = new Map(actionItems.map((item) => [`${item.market}:${item.code}`, item]));
  const priceReadyCount = actionItems.filter((item) => item.price != null || item.technicals?.current_price != null).length;
  const rsiReadyCount = actionItems.filter((item) => item.technicals?.rsi14 != null).length;
  const buyActions = actions.filter((item) => String(item.action || '').toLowerCase() === 'buy').length;
  const reviewActions = actions.filter((item) => String(item.action || '').toLowerCase() === 'watch').length;

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell workspace-grid">
          <ConsoleActionBar
            title="관심 종목"
            subtitle="편집, 저장, 분석을 분리해서 보여줍니다. 저장 전 변경과 최근 분석 상태를 여기서 바로 확인합니다."
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
                disabled: !dirty,
                disabledReason: dirty ? '' : '변경 없음',
              },
            ]}
          />

          <section className="page-section workspace-two-column">
            <div className="workspace-card-block">
              <div className="workspace-card-head">
                <div>
                  <div className="section-title">종목 검색 / 추가</div>
                  <div className="section-copy">검색 결과는 아래 표를 덮지 않게 별도 패널처럼 띄웁니다.</div>
                </div>
                {dirty && <div className="inline-badge is-danger">저장되지 않은 변경 있음</div>}
              </div>
              <div ref={searchContainerRef} className="workspace-search-shell">
                <input
                  type="text"
                  className="input-field"
                  placeholder="종목명 또는 코드 검색"
                  value={searchQuery}
                  onChange={(e) => handleSearchChange(e.target.value)}
                  onFocus={() => searchResults.length > 0 && setSearchOpen(true)}
                  style={{ width: '100%', padding: '10px 12px', fontSize: 13 }}
                />
                {searchOpen && searchResults.length > 0 && (
                  <div className="workspace-search-dropdown">
                    {searchResults.map((result) => (
                      <button
                        key={`${result.market}:${result.code}`}
                        type="button"
                        className="workspace-search-result"
                        onClick={() => handleAddItem(result)}
                      >
                        <SymbolIdentity code={result.code} name={result.name} market={result.market} compact />
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div className="workspace-help-row">
                <span className="inline-badge">추가 후 저장 필요</span>
                <span className="workspace-muted-copy">목록 수정만으로 서버 반영되진 않음</span>
              </div>
            </div>

            <div className="workspace-card-block">
              <div className="workspace-card-head">
                <div>
                  <div className="section-title">편집 / 분석 상태</div>
                  <div className="section-copy">지금 페이지에서 어디까지 된 건지 숫자로 바로 봅니다.</div>
                </div>
                <div className="inline-badge">{actionsGeneratedAt ? formatDateTime(actionsGeneratedAt) : '분석 전'}</div>
              </div>
              <div className="workspace-mini-metrics">
                <div className="workspace-mini-metric"><span>서버 저장</span><strong>{savedItems.length}개</strong></div>
                <div className="workspace-mini-metric"><span>가격 준비</span><strong>{priceReadyCount}개</strong></div>
                <div className="workspace-mini-metric"><span>RSI 준비</span><strong>{rsiReadyCount}개</strong></div>
                <div className="workspace-mini-metric"><span>매수 후보</span><strong>{buyActions}개</strong></div>
                <div className="workspace-mini-metric"><span>관찰 후보</span><strong>{reviewActions}개</strong></div>
              </div>
            </div>
          </section>

          <section className="page-section workspace-table-section">
            <div className="workspace-card-head">
              <div>
                <div className="section-title">관심 종목 목록</div>
                <div className="section-copy">종목 표기는 이름 / 코드 · 시장 형식으로 통일했습니다.</div>
              </div>
              <div className="inline-badge">{items.length}개</div>
            </div>
            {items.length === 0 ? (
              <div className="workspace-empty-state">관심 종목이 없습니다. 위에서 검색해서 추가해.</div>
            ) : (
              <div style={{ overflow: 'auto' }}>
                <table className="workspace-table" style={{ minWidth: 760 }}>
                  <thead>
                    <tr>
                      <th>종목</th>
                      <th>현재가</th>
                      <th>등락률</th>
                      <th>RSI</th>
                      <th>거래량비</th>
                      <th>액션</th>
                      <th></th>
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
                      const action = actions.find((candidate) => candidate.code === item.code && candidate.market === item.market);
                      return (
                        <tr key={`${item.market}:${item.code}`}>
                          <td><SymbolIdentity code={item.code} name={item.name} market={item.market} /></td>
                          <td>{displayMetric(price, 'price', item.market)}</td>
                          <td className={changePct != null ? (changePct >= 0 ? 'is-up' : 'is-down') : ''}>{displayMetric(changePct, 'pct')}</td>
                          <td>{displayMetric(rsi, 'analysis')}</td>
                          <td>{displayMetric(volRatio, 'volume')}</td>
                          <td>
                            <span className={actionTone(action?.action)}>{action?.action || '분석 전'}</span>
                            {action?.reason && <div className="workspace-row-subcopy">{action.reason}</div>}
                          </td>
                          <td style={{ textAlign: 'right' }}>
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
            <section className="page-section workspace-analysis-section">
              <div className="workspace-card-head">
                <div>
                  <div className="section-title">최근 분석 결과</div>
                  <div className="section-copy">매수/관찰/회피 판단을 카드로 먼저 보여줍니다.</div>
                </div>
                <div className="inline-badge">{actions.length}개 액션</div>
              </div>
              <div className="operator-note-grid">
                {actions.map((action, i) => (
                  <div key={`action-${i}`} className="operator-note-card">
                    <div className="operator-note-label"><SymbolIdentity code={action.code} name={action.name} market={action.market} compact /></div>
                    <div style={{ marginTop: 6 }}>
                      <span className={actionTone(action.action)}>{action.action || '관찰'}</span>
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
