import { useMemo } from 'react';
import { useMarket } from '../hooks/useMarket';
import { useInvestmentAssistant } from '../hooks/useInvestmentAssistant';

function cardStyle(borderColor = 'var(--border)') {
  return {
    background: 'var(--card-bg)',
    border: `1px solid ${borderColor}`,
    borderRadius: 16,
    padding: '16px',
  } as const;
}

export function AssistantTab() {
  const { data: market, refresh: refreshMarket } = useMarket();
  const {
    analysisData,
    watchlistRecommendations,
    autoRecommendations,
    autoLoading,
    riskSignals,
    refreshAll,
  } = useInvestmentAssistant();

  const watchlistFocus = useMemo(() => [...watchlistRecommendations].sort((a, b) => b.score - a.score).slice(0, 3), [watchlistRecommendations]);
  const topIdeas = useMemo(() => autoRecommendations.slice(0, 3), [autoRecommendations]);
  const actionItems = useMemo(() => {
    const items: string[] = [];
    if (topIdeas[0]) items.push(`${topIdeas[0].name} 근거 문장을 확인하고 관심종목 편입 여부를 판단하세요.`);
    if (watchlistFocus.some((item) => item.signal === '회피')) items.push('관심종목 중 약한 문맥이 나온 종목은 보류 또는 제외 메모를 남기세요.');
    if (riskSignals.length > 0) items.push(`${riskSignals[0].title} 관련 일정과 노출 종목을 점검하세요.`);
    return items.slice(0, 3);
  }, [topIdeas, watchlistFocus, riskSignals]);

  function handleRefresh() {
    refreshMarket();
    refreshAll();
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ ...cardStyle('rgba(59,130,246,.22)'), background: 'linear-gradient(135deg, rgba(14,27,53,.96) 0%, rgba(18,32,64,.96) 60%, rgba(14,27,53,.96) 100%)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
          <div>
            <div style={{ fontSize: 12, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-4)', marginBottom: 8 }}>Today Brief</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--text-1)', marginBottom: 8 }}>오늘의 투자 행동 보드</div>
            <div style={{ fontSize: 14, color: 'var(--text-2)', lineHeight: 1.6 }}>
              {analysisData.summary_lines?.[0] || '오늘의 시장 요약이 아직 준비되지 않았습니다.'}
            </div>
          </div>
          <button onClick={handleRefresh} style={{ background: 'rgba(59,130,246,.12)', border: '1px solid rgba(59,130,246,.3)', borderRadius: 10, color: '#93c5fd', cursor: 'pointer', fontSize: 14, padding: '8px 12px', whiteSpace: 'nowrap' }}>
            전체 새로고침
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, marginTop: 16 }}>
          <div style={cardStyle('rgba(34,197,94,.18)')}>
            <div style={{ fontSize: 12, color: 'var(--text-3)' }}>시장 온도</div>
            <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-1)', marginTop: 8 }}>{market.kospi_pct !== undefined && market.kospi_pct >= 0 ? '위험 선호' : '방어 모드'}</div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 8 }}>KOSPI {market.kospi_pct !== undefined ? `${market.kospi_pct > 0 ? '+' : ''}${market.kospi_pct.toFixed(2)}%` : '—'}</div>
          </div>
          <div style={cardStyle('rgba(59,130,246,.18)')}>
            <div style={{ fontSize: 12, color: 'var(--text-3)' }}>오늘의 상위 아이디어</div>
            <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-1)', marginTop: 8 }}>{topIdeas[0]?.name || '대기 중'}</div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 8 }}>{topIdeas[0] ? `${topIdeas[0].signal} · ${topIdeas[0].score}점` : '추천 후보를 분석 중입니다.'}</div>
          </div>
          <div style={cardStyle('rgba(245,158,11,.18)')}>
            <div style={{ fontSize: 12, color: 'var(--text-3)' }}>관심종목 경고</div>
            <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-1)', marginTop: 8 }}>{watchlistFocus.filter((item) => item.signal === '회피').length}개</div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 8 }}>약한 문맥 또는 하락 신호가 감지된 종목 수</div>
          </div>
          <div style={cardStyle('rgba(239,68,68,.18)')}>
            <div style={{ fontSize: 12, color: 'var(--text-3)' }}>핵심 리스크</div>
            <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-1)', marginTop: 8 }}>{riskSignals[0]?.title || '특이 리스크 없음'}</div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 8 }}>{riskSignals[0]?.level === 'high' ? '즉시 점검 필요' : '관찰 필요'}</div>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
        <div style={{ ...cardStyle(), display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-1)' }}>지금 해야 할 일</div>
            <div style={{ fontSize: 12, color: 'var(--text-4)' }}>Action Queue</div>
          </div>
          {actionItems.length === 0 ? (
            <div style={{ fontSize: 13, color: 'var(--text-3)' }}>새로운 행동 항목이 아직 없습니다.</div>
          ) : actionItems.map((item, index) => (
            <div key={index} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', padding: '10px 12px', borderRadius: 12, background: 'rgba(255,255,255,.03)' }}>
              <span style={{ width: 22, height: 22, borderRadius: '50%', background: 'rgba(59,130,246,.16)', color: '#93c5fd', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 700 }}>{index + 1}</span>
              <span style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.6 }}>{item}</span>
            </div>
          ))}
        </div>

        <div style={{ ...cardStyle(), display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-1)' }}>리스크 레이더</div>
          {riskSignals.length === 0 ? (
            <div style={{ fontSize: 13, color: 'var(--text-3)' }}>감지된 주요 리스크가 없습니다.</div>
          ) : riskSignals.map((risk) => (
            <div key={risk.title} style={{ padding: '12px', borderRadius: 12, background: risk.level === 'high' ? 'rgba(239,68,68,.08)' : 'rgba(245,158,11,.08)', border: `1px solid ${risk.level === 'high' ? 'rgba(239,68,68,.2)' : 'rgba(245,158,11,.2)'}` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-1)' }}>{risk.title}</div>
                <div style={{ fontSize: 11, color: risk.level === 'high' ? '#f87171' : '#fbbf24' }}>{risk.level === 'high' ? 'High' : 'Medium'}</div>
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-3)', lineHeight: 1.6, marginTop: 6 }}>{risk.detail}</div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
        <div style={{ ...cardStyle(), display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-1)' }}>상위 자동 추천</div>
            <div style={{ fontSize: 12, color: 'var(--text-4)' }}>{autoLoading ? '분석 중...' : `${topIdeas.length}개`}</div>
          </div>
          {topIdeas.length === 0 ? (
            <div style={{ fontSize: 13, color: 'var(--text-3)' }}>추천 종목을 아직 찾지 못했습니다.</div>
          ) : topIdeas.map((item) => (
            <div key={item.name} style={{ padding: '12px', borderRadius: 12, background: 'rgba(255,255,255,.03)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'baseline' }}>
                <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-1)' }}>{item.name}</div>
                <div style={{ fontSize: 12, color: 'var(--text-3)' }}>{item.score}점</div>
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>{[item.code, item.market].filter(Boolean).join(' • ')}</div>
              <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.6, marginTop: 8 }}>{item.evidence[0] || item.reasons[0]}</div>
            </div>
          ))}
        </div>

        <div style={{ ...cardStyle(), display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-1)' }}>관심종목 집중 점검</div>
            <div style={{ fontSize: 12, color: 'var(--text-4)' }}>{watchlistFocus.length}개</div>
          </div>
          {watchlistFocus.length === 0 ? (
            <div style={{ fontSize: 13, color: 'var(--text-3)' }}>관심종목이 아직 없습니다.</div>
          ) : watchlistFocus.map((item) => (
            <div key={item.code} style={{ padding: '12px', borderRadius: 12, background: 'rgba(255,255,255,.03)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'baseline' }}>
                <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-1)' }}>{item.name}</div>
                <div style={{ fontSize: 12, color: item.signal === '회피' ? '#f87171' : item.signal === '강력추천' ? '#4ade80' : '#93c5fd' }}>{item.signal}</div>
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>{item.code} • {item.market}</div>
              <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.6, marginTop: 8 }}>{item.evidence[0] || item.reasons[0]}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
