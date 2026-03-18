import { useMemo, useState } from 'react';
import { useInvestmentAssistant } from '../hooks/useInvestmentAssistant';
import type { AutoRecommendedItem, RecommendedWatchlistItem } from '../types';

interface Props {
  onRefresh: () => void;
}

const signalColor: Record<string, string> = {
  '강력추천': '#22c55e',
  '추천': 'var(--up)',
  '중립': '#f59e0b',
  '회피': 'var(--down)',
};

const riskColor: Record<string, string> = {
  '높음': 'var(--down)',
  '중간': '#f59e0b',
  '낮음': '#22c55e',
};

function WatchlistCard({ item }: { item: RecommendedWatchlistItem }) {
  return (
    <div style={{ background: 'var(--card-bg)', border: `1px solid ${signalColor[item.signal] || 'var(--border)'}`, borderRadius: 12, padding: '14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-1)' }}>{item.name}</div>
          <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>{item.code} • {item.market}</div>
        </div>
        <span style={{ fontSize: 11, fontWeight: 700, borderRadius: 6, padding: '4px 8px', color: signalColor[item.signal], border: `1px solid ${signalColor[item.signal]}`, background: `${signalColor[item.signal]}20`, whiteSpace: 'nowrap' }}>
          {item.signal}
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 24, fontWeight: 700, color: '#3b82f6' }}>{item.score}</span>
          <span style={{ fontSize: 12, color: 'var(--text-3)' }}>/ 100</span>
        </div>
        {item.price && (
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 12, color: 'var(--text-3)' }}>현재가</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-1)' }}>{item.price.toLocaleString('ko-KR')}</div>
          </div>
        )}
      </div>

      {item.change_pct !== undefined && (
        <div style={{ fontSize: 13, color: item.change_pct >= 0 ? 'var(--up)' : 'var(--down)', fontWeight: 600 }}>
          {item.change_pct >= 0 ? '📈' : '📉'} {item.change_pct > 0 ? '+' : ''}{item.change_pct.toFixed(2)}%
        </div>
      )}

      <div>
        <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 4 }}>신뢰도 {item.confidence}%</div>
        <div style={{ height: 6, borderRadius: 99, background: 'var(--surface-alt)', overflow: 'hidden' }}>
          <div style={{ width: `${Math.min(item.confidence, 100)}%`, height: '100%', background: item.confidence >= 80 ? '#22c55e' : item.confidence >= 60 ? '#f59e0b' : '#ef4444' }} />
        </div>
      </div>

      {item.evidence[0] && (
        <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.6, padding: '10px 12px', borderRadius: 10, background: 'rgba(255,255,255,.03)' }}>
          {item.evidence[0]}
        </div>
      )}

      <div style={{ fontSize: 12, color: 'var(--text-3)', lineHeight: 1.6 }}>
        {item.reasons.slice(0, 2).map((reason, index) => (
          <div key={index}>• {reason}</div>
        ))}
      </div>

      <div style={{ fontSize: 11, display: 'flex', alignItems: 'center', gap: 6, padding: '6px 8px', borderRadius: 6, background: 'var(--surface-alt)' }}>
        <span style={{ color: 'var(--text-3)' }}>위험도:</span>
        <span style={{ fontWeight: 600, color: riskColor[item.riskLevel] }}>{item.riskLevel}</span>
      </div>
    </div>
  );
}

function AutoRecommendCard({
  item,
  canAdd,
  isAdding,
  isAdded,
  onAdd,
}: {
  item: AutoRecommendedItem;
  canAdd: boolean;
  isAdding: boolean;
  isAdded: boolean;
  onAdd: () => void;
}) {
  const detailLabel = [item.code, item.market].filter(Boolean).join(' • ') || '분석 데이터 기반';
  const sourceLabel = item.source === 'search' ? '실시간 검증' : '사전 매칭';

  return (
    <div style={{ background: 'var(--card-bg)', border: `1px solid ${signalColor[item.signal] || 'var(--border)'}`, borderRadius: 12, padding: '14px', display: 'flex', flexDirection: 'column', gap: 10, opacity: 0.9 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-1)' }}>{item.name}</div>
          <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>{detailLabel}</div>
        </div>
        <span style={{ fontSize: 11, fontWeight: 700, borderRadius: 6, padding: '4px 8px', color: signalColor[item.signal], border: `1px solid ${signalColor[item.signal]}`, background: `${signalColor[item.signal]}20`, whiteSpace: 'nowrap' }}>
          {item.signal}
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ fontSize: 24, fontWeight: 700, color: '#3b82f6' }}>{item.score}</span>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>/ 100</span>
        <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-3)', border: '1px solid var(--border)', borderRadius: 999, padding: '2px 8px' }}>{sourceLabel}</span>
      </div>

      <div>
        <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 4 }}>신뢰도 {item.confidence}%</div>
        <div style={{ height: 6, borderRadius: 99, background: 'var(--surface-alt)', overflow: 'hidden' }}>
          <div style={{ width: `${Math.min(item.confidence, 100)}%`, height: '100%', background: item.confidence >= 80 ? '#22c55e' : item.confidence >= 60 ? '#f59e0b' : '#ef4444' }} />
        </div>
      </div>

      {item.evidence.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {item.evidence.map((evidence, index) => (
            <div key={index} style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.6, padding: '10px 12px', borderRadius: 10, background: 'rgba(255,255,255,.03)' }}>
              {evidence}
            </div>
          ))}
        </div>
      )}

      <div style={{ fontSize: 12, color: 'var(--text-3)', lineHeight: 1.6 }}>
        {item.reasons.slice(0, 3).map((reason, index) => (
          <div key={index}>• {reason}</div>
        ))}
      </div>

      <button
        onClick={onAdd}
        disabled={!canAdd || isAdding || isAdded}
        style={{
          marginTop: 4,
          background: isAdded ? 'rgba(34,197,94,.12)' : canAdd ? 'rgba(59,130,246,.12)' : 'var(--surface-alt)',
          border: `1px solid ${isAdded ? 'rgba(34,197,94,.3)' : canAdd ? 'rgba(59,130,246,.3)' : 'var(--border)'}`,
          borderRadius: 8,
          color: isAdded ? '#4ade80' : canAdd ? '#93c5fd' : 'var(--text-4)',
          cursor: !canAdd || isAdded ? 'default' : 'pointer',
          fontSize: 13,
          fontWeight: 600,
          padding: '8px 10px',
        }}
      >
        {isAdded ? '관심종목에 추가됨' : isAdding ? '추가 중...' : canAdd ? '관심종목에 추가' : '추가 불가'}
      </button>
    </div>
  );
}

export function RecommendationTab({ onRefresh }: Props) {
  const {
    watchlistRecommendations,
    autoRecommendations,
    autoLoading,
    watchlistCodes,
    addingCode,
    addRecommendation,
    refreshAll,
  } = useInvestmentAssistant();
  const [sortBy, setSortBy] = useState<'score' | 'price'>('score');

  const sortedWatchlist = useMemo(() => {
    const items = [...watchlistRecommendations];
    return sortBy === 'score'
      ? items.sort((a, b) => b.score - a.score)
      : items.sort((a, b) => (b.change_pct || 0) - (a.change_pct || 0));
  }, [watchlistRecommendations, sortBy]);

  function handleRefresh() {
    refreshAll();
    onRefresh();
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
            관심 종목 {sortedWatchlist.length}개 + AI 자동 추천 {autoRecommendations.length}개
          </span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => setSortBy('score')} style={{ fontSize: 12, padding: '4px 10px', borderRadius: 6, border: `1px solid ${sortBy === 'score' ? '#3b82f6' : 'var(--border)'}`, background: sortBy === 'score' ? 'rgba(59,130,246,.1)' : 'transparent', color: sortBy === 'score' ? '#3b82f6' : 'var(--text-3)', cursor: 'pointer' }}>점수순</button>
            <button onClick={() => setSortBy('price')} style={{ fontSize: 12, padding: '4px 10px', borderRadius: 6, border: `1px solid ${sortBy === 'price' ? '#3b82f6' : 'var(--border)'}`, background: sortBy === 'price' ? 'rgba(59,130,246,.1)' : 'transparent', color: sortBy === 'price' ? '#3b82f6' : 'var(--text-3)', cursor: 'pointer' }}>수익률순</button>
          </div>
        </div>
        <button onClick={handleRefresh} style={{ background: 'rgba(59,130,246,.12)', border: '1px solid rgba(59,130,246,.3)', borderRadius: 8, color: '#93c5fd', cursor: 'pointer', fontSize: 16, padding: '4px 10px' }} title="새로고침">↻</button>
      </div>

      {sortedWatchlist.length === 0 && autoRecommendations.length === 0 && (
        <div style={{ textAlign: 'center', padding: '48px 20px', background: 'var(--card-bg)', borderRadius: 16, border: '1px solid var(--border)' }}>
          <div style={{ fontSize: 34, marginBottom: 8 }}>🎯</div>
          <div style={{ color: 'var(--text-2)', fontWeight: 700, marginBottom: 6 }}>{autoLoading ? 'AI가 회사별 문맥을 분석하는 중입니다' : 'AI가 추천할 종목을 찾지 못했습니다'}</div>
          <div style={{ fontSize: 13, color: 'var(--text-4)' }}>{autoLoading ? '분석 문장과 시장 신호를 바탕으로 후보를 정리하고 있습니다' : '리포트 본문에 회사명과 관련 문맥이 더 많아지면 추천 품질이 올라갑니다'}</div>
        </div>
      )}

      {sortedWatchlist.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-1)', marginBottom: 12 }}>📌 관심 종목 ({sortedWatchlist.length}개)</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
            {sortedWatchlist.map((item) => (
              <WatchlistCard key={item.code} item={item} />
            ))}
          </div>
        </div>
      )}

      {autoRecommendations.length > 0 && (
        <div>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-1)', marginBottom: 12 }}>🤖 AI 자동 추천 ({autoRecommendations.length}개)</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
            {autoRecommendations.map((item) => (
              <AutoRecommendCard
                key={`auto-${item.name}`}
                item={item}
                canAdd={Boolean(item.code)}
                isAdding={addingCode === item.code}
                isAdded={Boolean(item.code && watchlistCodes.has(item.code))}
                onAdd={() => addRecommendation(item)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
