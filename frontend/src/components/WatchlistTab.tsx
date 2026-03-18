import { useState, useRef, useEffect } from 'react';
import { useWatchlist } from '../hooks/useWatchlist';
import type { StockSearchResult } from '../types';
import { MarketTile } from './MarketTile';

export function WatchlistTab() {
  const { items, add, remove, refreshPrices } = useWatchlist();
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

  useEffect(() => {
    function onScroll() { if (dropdownPos) closeDropdown(); }
    window.addEventListener('scroll', onScroll);
    return () => window.removeEventListener('scroll', onScroll);
  }, [dropdownPos]);

  return (
    <div>
      {/* Search bar */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        <input
          ref={inputRef}
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && doSearch()}
          placeholder="종목명 또는 코드 검색 (예: 삼성전자, 005930)"
          style={{
            flex: 1,
            background: 'var(--card-bg)',
            border: '1px solid var(--border)',
            borderRadius: 10,
            color: 'var(--text-1)',
            fontSize: 14,
            padding: '10px 14px',
            outline: 'none',
            fontFamily: 'inherit',
          }}
        />
        <button
          onClick={doSearch}
          disabled={searching}
          style={{
            background: 'rgba(59,130,246,.15)',
            border: '1px solid rgba(59,130,246,.3)',
            borderRadius: 10,
            color: '#93c5fd',
            cursor: 'pointer',
            fontSize: 16,
            padding: '10px 16px',
            fontFamily: 'inherit',
          }}
        >
          {searching ? '...' : '🔍'}
        </button>
        {items.length > 0 && (
          <button
            onClick={refreshPrices}
            style={{
              background: 'rgba(34,197,94,.12)',
              border: '1px solid rgba(34,197,94,.3)',
              borderRadius: 10,
              color: '#4ade80',
              cursor: 'pointer',
              fontSize: 14,
              padding: '10px 14px',
              fontFamily: 'inherit',
            }}
          >↻</button>
        )}
      </div>

      {/* Dropdown */}
      {dropdownPos && results.length > 0 && (
        <div style={{
          position: 'fixed',
          top: dropdownPos.top,
          left: dropdownPos.left,
          width: dropdownPos.width,
          background: 'var(--card-bg)',
          border: '1px solid var(--border)',
          borderRadius: 10,
          zIndex: 200,
          maxHeight: 300,
          overflowY: 'auto',
          boxShadow: '0 8px 32px rgba(0,0,0,.4)',
        }}>
          {results.map(r => (
            <div
              key={r.code}
              onClick={() => handleAdd(r)}
              style={{
                padding: '10px 14px',
                cursor: 'pointer',
                borderBottom: '1px solid var(--border-light)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
              onMouseEnter={e => (e.currentTarget.style.background = 'var(--surface-alt)')}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
            >
              <div>
                <div style={{ fontSize: 14, color: 'var(--text-1)', fontWeight: 500 }}>{r.name}</div>
                <div style={{ fontSize: 12, color: 'var(--text-3)' }}>{r.code}</div>
              </div>
              <span style={{
                fontSize: 11, padding: '2px 6px', borderRadius: 4,
                background: 'rgba(59,130,246,.15)', color: '#93c5fd',
                border: '1px solid rgba(59,130,246,.25)',
              }}>{r.market}</span>
            </div>
          ))}
          <div
            onClick={closeDropdown}
            style={{ padding: '8px 14px', textAlign: 'center', fontSize: 12, color: 'var(--text-4)', cursor: 'pointer' }}
          >닫기</div>
        </div>
      )}

      {/* Empty state */}
      {items.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: '60px 20px',
          background: 'var(--card-bg)', borderRadius: 16,
          border: '1px solid var(--border)',
        }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>⭐</div>
          <div style={{ fontSize: 16, color: 'var(--text-2)', fontWeight: 600, marginBottom: 8 }}>
            관심 종목이 없습니다
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-4)' }}>
            위 검색창에서 종목을 검색하여 추가하세요
          </div>
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
          gap: 12,
        }}>
          {items.map(item => (
            <div key={item.code} style={{ position: 'relative' }}>
              <MarketTile
                label={item.name}
                value={item.price}
                pct={item.change_pct}
                badgeText={item.market}
                formatValue={v => v.toLocaleString('ko-KR', { maximumFractionDigits: 0 })}
              />
              <button
                onClick={() => remove(item.code)}
                style={{
                  position: 'absolute', top: 8, right: 8,
                  background: 'rgba(239,68,68,.15)', border: '1px solid rgba(239,68,68,.3)',
                  borderRadius: 4, color: '#f87171', cursor: 'pointer',
                  fontSize: 11, padding: '1px 5px', lineHeight: 1.4,
                }}
                title="제거"
              >✕</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
