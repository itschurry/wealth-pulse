import { useState, useRef, useEffect, useMemo } from 'react';
import { useWatchlist } from '../hooks/useWatchlist';
import { useWatchlistActions } from '../hooks/useWatchlistActions';
import { COMPANY_CATALOG } from '../data/companyCatalog';
import type { StockSearchResult, WatchlistActionItem } from '../types';
import { getMarketBucket, getMarketSectionCaption, getMarketSectionLabel, getMarketSessions, getPreferredMarketOrder, type MarketBucket, type MarketSessionInfo } from '../utils/marketSession';
import { getQuantSignalLabel } from '../utils/quantLabels';

const actionLabel: Record<WatchlistActionItem['action'], string> = {
  buy: '롱 진입 검토',
  hold: '보유 유지',
  sell: '익절/축소 검토',
  watch: '관찰 유지',
};

const actionColor: Record<WatchlistActionItem['action'], string> = {
  buy: 'var(--up)',
  hold: 'var(--accent)',
  sell: 'var(--down)',
  watch: '#b7791f',
};

function MarketStatusPill({ session }: { session: MarketSessionInfo }) {
  const color = session.isOpen ? 'var(--up)' : 'var(--text-3)';
  const background = session.isOpen ? 'rgba(24,121,78,.12)' : 'rgba(69,81,96,.08)';
  const border = session.isOpen ? 'rgba(24,121,78,.2)' : 'var(--border)';

  return (
    <div style={{ padding: '12px 14px', borderRadius: 16, border: `1px solid ${border}`, background, display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
        <div style={{ fontSize: 13, fontWeight: 800, color: 'var(--text-1)' }}>{session.label}</div>
        <span style={{ fontSize: 11, fontWeight: 800, color, padding: '5px 8px', borderRadius: 999, border: `1px solid ${border}`, background: '#fff' }}>
          {session.statusLabel}
        </span>
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-4)' }}>{session.marketsLabel} · {session.scheduleLabel}</div>
    </div>
  );
}

function normalizeText(value: string) {
  return value.trim().toLowerCase();
}

function resolveListing(code: string, name: string, market: string) {
  const normalizedName = normalizeText(name);
  const normalizedCode = code.trim().toUpperCase();
  const normalizedMarket = market.trim().toUpperCase();

  if (normalizedCode && /^\d+$/.test(normalizedCode)) {
    return { code: normalizedCode, market: normalizedMarket };
  }

  const exactMarketMatch = COMPANY_CATALOG.find((entry) => {
    if (!entry.code) return false;
    if ((entry.market || '').toUpperCase() !== normalizedMarket) return false;
    if (normalizeText(entry.name) === normalizedName) return true;
    return entry.aliases.some((alias) => normalizeText(alias) === normalizedName);
  });

  if (exactMarketMatch?.code) {
    return {
      code: exactMarketMatch.code,
      market: (exactMarketMatch.market || normalizedMarket).toUpperCase(),
    };
  }

  const nameMatch = COMPANY_CATALOG.find((entry) => {
    if (!entry.code) return false;
    if (normalizeText(entry.name) === normalizedName) return true;
    return entry.aliases.some((alias) => normalizeText(alias) === normalizedName);
  });

  if (nameMatch?.code) {
    return {
      code: nameMatch.code,
      market: (nameMatch.market || normalizedMarket).toUpperCase(),
    };
  }

  return { code: normalizedCode, market: normalizedMarket };
}

function getNaverFinanceUrl(code: string, name: string, market: string) {
  const listing = resolveListing(code, name, market);
  const normalizedCode = listing.code.trim().toUpperCase();
  const normalizedMarket = listing.market.trim().toUpperCase();

  if (/^\d+$/.test(normalizedCode)) {
    return `https://finance.naver.com/item/main.naver?code=${normalizedCode}`;
  }

  if (normalizedMarket === 'NASDAQ') {
    const symbol = normalizedCode.includes('.') ? normalizedCode : `${normalizedCode}.O`;
    return `https://stock.naver.com/worldstock/stock/${symbol}/price`;
  }

  if (normalizedMarket === 'NYSE') {
    return `https://stock.naver.com/worldstock/stock/${normalizedCode}/price`;
  }

  return null;
}

function formatNumber(value?: number | null, digits = 1) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '—';
  return value.toLocaleString('ko-KR', { maximumFractionDigits: digits });
}

function formatSigned(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '—';
  return `${value > 0 ? '+' : ''}${value.toLocaleString('ko-KR')}`;
}

function ActionCard({ item, onRemove }: { item: WatchlistActionItem; onRemove: (code: string) => void }) {
  const hasPrice = typeof item.price === 'number' && Number.isFinite(item.price);
  const newsItems = Array.isArray(item.related_news) ? item.related_news : [];
  const reasons = Array.isArray(item.reasons) ? item.reasons : [];
  const risks = Array.isArray(item.risks) ? item.risks : [];
  const naverFinanceUrl = getNaverFinanceUrl(item.code, item.name, item.market);
  const technicals = item.technicals || null;
  const flow = item.investor_flow || null;

  return (
    <div className="page-section" style={{ padding: 18, borderColor: `${actionColor[item.action]}33`, display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-1)' }}>{item.name}</div>
          <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 5 }}>{item.code} • {item.market}</div>
          {naverFinanceUrl && (
            <a
              href={naverFinanceUrl}
              target="_blank"
              rel="noreferrer"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                marginTop: 10,
                textDecoration: 'none',
                background: 'rgba(15,76,92,.08)',
                border: '1px solid rgba(15,76,92,.18)',
                borderRadius: 999,
                color: 'var(--accent)',
                fontSize: 12,
                fontWeight: 700,
                padding: '7px 12px',
              }}
              title="네이버 증권에서 보기"
            >
              네이버 증권 열기
            </a>
          )}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 8 }}>
          <span style={{ fontSize: 11, fontWeight: 800, borderRadius: 999, padding: '6px 10px', color: actionColor[item.action], border: `1px solid ${actionColor[item.action]}`, background: `${actionColor[item.action]}15` }}>
            {actionLabel[item.action]}
          </span>
          <button
            onClick={() => onRemove(item.code)}
            style={{ background: 'rgba(196,68,45,.08)', border: '1px solid rgba(196,68,45,.18)', borderRadius: 999, color: 'var(--down)', cursor: 'pointer', fontSize: 11, padding: '4px 9px' }}
            title="제거"
          >
            종목 제거
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: 14, alignItems: 'center' }}>
        <div style={{ padding: '14px 12px', borderRadius: 18, background: 'var(--bg-soft)', border: '1px solid var(--border)' }}>
          <div style={{ fontSize: 11, color: 'var(--text-4)' }}>종합점수</div>
          <div style={{ fontSize: 34, fontWeight: 800, color: actionColor[item.action], marginTop: 6 }}>{item.score}</div>
          <div style={{ fontSize: 11, color: 'var(--text-4)' }}>신뢰도 {item.confidence}%</div>
        </div>

        <div style={{ padding: '14px 16px', borderRadius: 18, background: 'var(--bg-soft)', border: '1px solid var(--border)' }}>
          <div style={{ fontSize: 11, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Position View</div>
          <div style={{ fontSize: 14, color: 'var(--text-2)', lineHeight: 1.7, marginTop: 8 }}>
            {reasons[0] || '오늘 기준 포지션 변화 요인을 정리하는 중입니다.'}
          </div>
          {hasPrice && (
            <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 8 }}>
              현재가 {item.price!.toLocaleString('ko-KR')}
              {typeof item.change_pct === 'number' ? ` · ${item.change_pct > 0 ? '+' : ''}${item.change_pct.toFixed(2)}%` : ''}
            </div>
          )}
        </div>
      </div>

      {item.changed_from_yesterday && (
        <div style={{ fontSize: 12, color: 'var(--text-2)', padding: '10px 12px', borderRadius: 16, background: 'rgba(15,76,92,.05)', border: '1px solid rgba(15,76,92,.12)' }}>
          전일 대비 {item.changed_from_yesterday.previous_signal ? getQuantSignalLabel(item.changed_from_yesterday.previous_signal) : '데이터 없음'} → {getQuantSignalLabel(item.signal)}
          {' · '}
          <span style={{ color: (item.changed_from_yesterday.score_diff || 0) >= 0 ? 'var(--up)' : 'var(--down)', fontWeight: 700 }}>
            {(item.changed_from_yesterday.score_diff || 0) >= 0 ? '+' : ''}{item.changed_from_yesterday.score_diff || 0}
          </span>
        </div>
      )}

      <div style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.7 }}>
        {reasons.slice(0, 3).map((reason, index) => (
          <div key={index}>• {reason}</div>
        ))}
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {risks.slice(0, 2).map((risk, index) => (
          <span key={index} style={{ fontSize: 11, color: 'var(--down)', background: 'rgba(196,68,45,.08)', border: '1px solid rgba(196,68,45,.18)', borderRadius: 999, padding: '5px 9px' }}>
            {risk}
          </span>
        ))}
      </div>

      {technicals && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 10 }}>
          <div style={{ padding: '12px 13px', borderRadius: 16, background: 'var(--bg-soft)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: 11, color: 'var(--text-4)' }}>RSI(14)</div>
            <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-1)', marginTop: 6 }}>{formatNumber(technicals.rsi14, 1)}</div>
          </div>
          <div style={{ padding: '12px 13px', borderRadius: 16, background: 'var(--bg-soft)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: 11, color: 'var(--text-4)' }}>MACD</div>
            <div style={{ fontSize: 18, fontWeight: 800, color: (technicals.macd_hist || 0) >= 0 ? 'var(--up)' : 'var(--down)', marginTop: 6 }}>{formatNumber(technicals.macd_hist, 3)}</div>
            <div style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 4 }}>히스토그램</div>
          </div>
          <div style={{ padding: '12px 13px', borderRadius: 16, background: 'var(--bg-soft)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: 11, color: 'var(--text-4)' }}>거래량 배수</div>
            <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-1)', marginTop: 6 }}>{technicals.volume_ratio ? `${formatNumber(technicals.volume_ratio, 2)}x` : '—'}</div>
            <div style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 4 }}>20일 평균 대비</div>
          </div>
          <div style={{ padding: '12px 13px', borderRadius: 16, background: 'var(--bg-soft)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: 11, color: 'var(--text-4)' }}>이동평균</div>
            <div style={{ fontSize: 16, fontWeight: 800, color: 'var(--text-1)', marginTop: 6 }}>
              {formatNumber(technicals.sma20, 0)} / {formatNumber(technicals.sma60, 0)}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 4 }}>20일선 / 60일선</div>
          </div>
          <div style={{ padding: '12px 13px', borderRadius: 16, background: 'var(--bg-soft)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: 11, color: 'var(--text-4)' }}>ATR(14)</div>
            <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-1)', marginTop: 6 }}>{formatNumber(technicals.atr14, 2)}</div>
            <div style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 4 }}>{technicals.atr14_pct ? `${formatNumber(technicals.atr14_pct, 2)}%` : '변동성 정보 없음'}</div>
          </div>
          <div style={{ padding: '12px 13px', borderRadius: 16, background: 'var(--bg-soft)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: 11, color: 'var(--text-4)' }}>20일 돌파</div>
            <div style={{ fontSize: 18, fontWeight: 800, color: technicals.breakout_20d ? 'var(--up)' : 'var(--text-1)', marginTop: 6 }}>
              {technicals.breakout_20d ? '돌파' : '미확인'}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 4 }}>
              기준 고점 {formatNumber(technicals.breakout_20d_high, 2)}
            </div>
          </div>
        </div>
      )}

      {flow && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10 }}>
          <div style={{ padding: '12px 13px', borderRadius: 16, background: 'var(--bg-soft)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: 11, color: 'var(--text-4)' }}>외국인 수급</div>
            <div style={{ fontSize: 16, fontWeight: 800, color: (flow.foreign_net_5d || 0) >= 0 ? 'var(--up)' : 'var(--down)', marginTop: 6 }}>
              {formatSigned(flow.foreign_net_5d)}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 4 }}>5일 누적 · 1일 {formatSigned(flow.foreign_net_1d)}</div>
          </div>
          <div style={{ padding: '12px 13px', borderRadius: 16, background: 'var(--bg-soft)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: 11, color: 'var(--text-4)' }}>기관 수급</div>
            <div style={{ fontSize: 16, fontWeight: 800, color: (flow.institution_net_5d || 0) >= 0 ? 'var(--up)' : 'var(--down)', marginTop: 6 }}>
              {formatSigned(flow.institution_net_5d)}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 4 }}>5일 누적 · 1일 {formatSigned(flow.institution_net_1d)}</div>
          </div>
        </div>
      )}

      {newsItems.length > 0 && (
        <div style={{ display: 'grid', gap: 10 }}>
          {newsItems.slice(0, 2).map((news) => (
            <a
              key={news.url}
              href={news.url}
              target="_blank"
              rel="noreferrer"
              style={{ textDecoration: 'none', color: 'inherit', padding: '12px 14px', borderRadius: 16, border: '1px solid var(--border)', background: 'var(--bg-soft)' }}
            >
              <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-1)', lineHeight: 1.6 }}>{news.title}</div>
              <div style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 6 }}>{news.source} · {news.published}</div>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

function SummaryCard({ title, value, detail, tone = 'neutral' }: { title: string; value: string; detail: string; tone?: 'up' | 'down' | 'neutral' }) {
  const borderColor = tone === 'up' ? 'rgba(24,121,78,.2)' : tone === 'down' ? 'rgba(196,68,45,.2)' : 'var(--border)';
  return (
    <div style={{ background: 'var(--bg-soft)', border: `1px solid ${borderColor}`, borderRadius: 18, padding: 16 }}>
      <div style={{ fontSize: 12, color: 'var(--text-3)' }}>{title}</div>
      <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--text-1)', marginTop: 8 }}>{value}</div>
      <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 6, lineHeight: 1.6 }}>{detail}</div>
    </div>
  );
}

function MarketActionSection({ bucket, items, session, onRemove }: { bucket: MarketBucket; items: WatchlistActionItem[]; session?: MarketSessionInfo; onRemove: (code: string) => void }) {
  return (
    <div className="page-section" style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--text-1)' }}>{getMarketSectionLabel(bucket)}</div>
          <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 6 }}>{getMarketSectionCaption(bucket)} · {items.length}종목</div>
        </div>
        {session ? (
          <span style={{ fontSize: 11, fontWeight: 800, borderRadius: 999, padding: '6px 10px', color: session.isOpen ? 'var(--up)' : 'var(--text-3)', border: `1px solid ${session.isOpen ? 'rgba(24,121,78,.2)' : 'var(--border)'}`, background: session.isOpen ? 'rgba(24,121,78,.12)' : 'rgba(69,81,96,.08)' }}>
            {session.statusLabel}
          </span>
        ) : (
          <span style={{ fontSize: 11, fontWeight: 800, borderRadius: 999, padding: '6px 10px', color: 'var(--text-3)', border: '1px solid var(--border)', background: 'rgba(69,81,96,.08)' }}>
            시장 구분
          </span>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
        {items.map((item) => (
          <ActionCard key={item.code} item={item} onRemove={onRemove} />
        ))}
      </div>
    </div>
  );
}

export function WatchlistTab() {
  const { items, add, remove, refreshPrices } = useWatchlist();
  const { data: actionsData, status: actionsStatus, refresh: refreshActions } = useWatchlistActions(items);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<StockSearchResult[]>([]);
  const [dropdownPos, setDropdownPos] = useState<{ top: number; left: number; width: number } | null>(null);
  const [searching, setSearching] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function doSearch() {
    if (!query.trim()) return;
    setSearching(true);
    try {
      const res = await fetch(`/api/stock-search?q=${encodeURIComponent(query)}`);
      const d = await res.json();
      setResults(d.results || []);
      if (inputRef.current) {
        const rect = inputRef.current.getBoundingClientRect();
        setDropdownPos({ top: rect.bottom + 4, left: rect.left, width: rect.width + 60 });
      }
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  }

  function closeDropdown() {
    setResults([]);
    setDropdownPos(null);
  }

  async function handleAdd(r: StockSearchResult) {
    await add(r.code, r.name, r.market);
    setQuery('');
    closeDropdown();
  }

  async function handleRefresh() {
    await refreshPrices();
    refreshActions();
  }

  useEffect(() => {
    function onScroll() { if (dropdownPos) closeDropdown(); }
    window.addEventListener('scroll', onScroll);
    return () => window.removeEventListener('scroll', onScroll);
  }, [dropdownPos]);

  const marketSessions = getMarketSessions();
  const sortedActions = useMemo(() => (
    [...actionsData.actions].sort((a, b) => {
      const priority = { sell: 0, buy: 1, hold: 2, watch: 3 } as const;
      return priority[a.action] - priority[b.action] || b.score - a.score;
    })
  ), [actionsData.actions]);
  const groupedActions = useMemo(() => {
    const buckets: Record<MarketBucket, WatchlistActionItem[]> = {
      domestic: [],
      us: [],
      other: [],
    };

    sortedActions.forEach((item) => {
      buckets[getMarketBucket(item.market)].push(item);
    });

    return getPreferredMarketOrder().map((bucket) => ({
      bucket,
      items: buckets[bucket],
      session: bucket === 'domestic' ? marketSessions.domestic : bucket === 'us' ? marketSessions.us : undefined,
    })).filter((group) => group.items.length > 0);
  }, [marketSessions, sortedActions]);
  const buyCount = sortedActions.filter((item) => item.action === 'buy').length;
  const sellCount = sortedActions.filter((item) => item.action === 'sell').length;
  const holdCount = sortedActions.filter((item) => item.action === 'hold').length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div className="page-section" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: 24, background: 'linear-gradient(135deg, rgba(23,35,52,0.98) 0%, rgba(47,64,88,0.96) 100%)', color: '#fffaf2' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: 12, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'rgba(255,250,242,.64)' }}>Watchlist Judgement</div>
              <div style={{ fontSize: 30, fontWeight: 800, marginTop: 8 }}>관심종목 판단</div>
              <div style={{ fontSize: 15, color: 'rgba(255,250,242,.82)', marginTop: 10, lineHeight: 1.7, maxWidth: 760 }}>
                내가 담아둔 종목만 따로 모아 오늘 액션을 정리합니다. 매수·보유·매도·관망 신호를 빠르게 확인하는 영역입니다.
              </div>
            </div>
            <button className="ghost-button" style={{ background: 'rgba(255,255,255,.1)', color: '#fffaf2', borderColor: 'rgba(255,255,255,.18)' }} onClick={handleRefresh}>
              판단 새로고침
            </button>
          </div>
        </div>

        <div style={{ padding: 18, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, background: 'rgba(255,253,248,0.78)' }}>
          <SummaryCard title="관심종목 수" value={`${items.length}개`} detail={actionsData.generated_at || '생성 시각 없음'} />
          <SummaryCard title="매수 후보" value={`${buyCount}개`} detail="오늘 기준 비중 확대를 검토할 수 있는 종목" tone={buyCount > 0 ? 'up' : 'neutral'} />
          <SummaryCard title="매도 경고" value={`${sellCount}개`} detail="리스크 확대 또는 신호 악화 종목" tone={sellCount > 0 ? 'down' : 'neutral'} />
          <SummaryCard title="보유 유지" value={`${holdCount}개`} detail={actionsStatus === 'loading' ? '판단 계산 중...' : '현재 포지션 유지 신호'} />
        </div>
      </div>

      <div className="page-section">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr auto auto', gap: 10, alignItems: 'center' }}>
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && doSearch()}
            placeholder="종목명 또는 코드 검색 (KOSPI/NASDAQ, 예: 삼성전자, AAPL)"
            style={{
              width: '100%',
              background: 'var(--bg-soft)',
              border: '1px solid var(--border)',
              borderRadius: 999,
              color: 'var(--text-1)',
              fontSize: 14,
              padding: '12px 16px',
              outline: 'none',
              fontFamily: 'inherit',
            }}
          />
          <button className="ghost-button" onClick={doSearch} disabled={searching}>
            {searching ? '검색 중...' : '종목 검색'}
          </button>
          {items.length > 0 && (
            <button className="ghost-button" onClick={handleRefresh}>
              가격 갱신
            </button>
          )}
        </div>
      </div>

      <div className="page-section" style={{ padding: 18, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
        <MarketStatusPill session={marketSessions.domestic} />
        <MarketStatusPill session={marketSessions.us} />
      </div>

      {dropdownPos && results.length > 0 && (
        <div style={{ position: 'fixed', top: dropdownPos.top, left: dropdownPos.left, width: dropdownPos.width, background: 'var(--card-bg)', border: '1px solid var(--border)', borderRadius: 16, zIndex: 200, maxHeight: 320, overflowY: 'auto', boxShadow: 'var(--shadow-md)' }}>
          {results.map(r => (
            <div
              key={r.code}
              onClick={() => handleAdd(r)}
              style={{ padding: '12px 14px', cursor: 'pointer', borderBottom: '1px solid var(--border-light)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
              onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-soft)')}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
            >
              <div>
                <div style={{ fontSize: 14, color: 'var(--text-1)', fontWeight: 700 }}>{r.name}</div>
                <div style={{ fontSize: 12, color: 'var(--text-4)' }}>{r.code}</div>
              </div>
              <span style={{ fontSize: 11, padding: '4px 8px', borderRadius: 999, background: 'var(--accent-soft)', color: 'var(--accent)', border: '1px solid var(--accent-border)' }}>{r.market}</span>
            </div>
          ))}
          <div onClick={closeDropdown} style={{ padding: '10px 14px', textAlign: 'center', fontSize: 12, color: 'var(--text-4)', cursor: 'pointer' }}>닫기</div>
        </div>
      )}

      {items.length === 0 ? (
        <div className="page-section" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <div style={{ fontSize: 18, color: 'var(--text-2)', fontWeight: 800, marginBottom: 8 }}>관심 종목이 없습니다</div>
          <div style={{ fontSize: 13, color: 'var(--text-4)' }}>위 검색창에서 종목을 추가하면 판단 카드가 생성됩니다.</div>
        </div>
      ) : (
        <>
          {actionsStatus === 'error' && (
            <div className="page-section" style={{ color: 'var(--down)' }}>
              관심종목 판단 데이터를 불러오지 못했습니다.
            </div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {groupedActions.map((group) => (
              <MarketActionSection key={group.bucket} bucket={group.bucket} items={group.items} session={group.session} onRemove={remove} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
