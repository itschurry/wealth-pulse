import { useMemo } from 'react';
import { useMarket } from '../hooks/useMarket';
import { useInvestmentAssistant } from '../hooks/useInvestmentAssistant';
import { useUnifiedScores } from '../hooks/useUnifiedScores';
import { renderTextWithLinks } from '../utils/linkify';
import { getQuantSignalLabel } from '../utils/quantLabels';

function cardStyle(borderColor = 'var(--border)', background = 'var(--card-bg)') {
  return {
    background,
    border: `1px solid ${borderColor}`,
    borderRadius: 22,
    padding: '18px',
  } as const;
}

export function AssistantTab() {
  const { data: market, refresh: refreshMarket } = useMarket();
  const {
    analysisData,
    watchlist,
    watchlistRecommendations,
    autoRecommendations,
    autoLoading,
    riskSignals,
    refreshAll,
  } = useInvestmentAssistant();
  const { getUnifiedScore, watchlistActions, refresh: refreshUnifiedScores } = useUnifiedScores(watchlist);

  const watchlistActionMap = useMemo(
    () => new Map((watchlistActions.data.actions || []).map((item) => [item.code, item])),
    [watchlistActions.data.actions],
  );
  const watchlistFocus = useMemo(() => (
    watchlistRecommendations
      .map((item) => {
        const unified = getUnifiedScore(item);
        const actionItem = watchlistActionMap.get(item.code);
        const actionEvidence = actionItem?.related_news?.map((news) => news.title)?.slice(0, 2);
        return {
          ...item,
          score: unified?.score ?? item.score,
          signal: actionItem?.signal || unified?.signal || item.signal,
          reasons: actionItem?.reasons || item.reasons,
          evidence: actionEvidence && actionEvidence.length > 0 ? actionEvidence : item.evidence,
        };
      })
      .sort((a, b) => b.score - a.score)
      .slice(0, 3)
  ), [watchlistRecommendations, getUnifiedScore, watchlistActionMap]);
  const topIdeas = useMemo(() => (
    autoRecommendations
      .map((item) => {
        const unified = getUnifiedScore(item);
        return {
          ...item,
          score: unified?.score ?? item.score,
          signal: unified?.signal || item.signal,
        };
      })
      .sort((a, b) => b.score - a.score)
      .slice(0, 3)
  ), [autoRecommendations, getUnifiedScore]);
  const actionItems = useMemo(() => {
    const items: string[] = [];
    if (topIdeas[0]) items.push(`${topIdeas[0].name}의 근거 뉴스와 리스크를 먼저 확인하세요.`);
    if (watchlistFocus.some((item) => item.signal === '회피')) items.push('관심종목 중 기대값 낮음 판정이 나온 종목은 비중 축소 또는 보류 판단을 남기세요.');
    if (riskSignals.length > 0) items.push(`${riskSignals[0].title} 관련 일정과 노출 종목을 점검하세요.`);
    return items.slice(0, 3);
  }, [topIdeas, watchlistFocus, riskSignals]);

  function handleRefresh() {
    refreshMarket();
    refreshAll();
    refreshUnifiedScores();
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div className="page-section" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: 24, background: 'linear-gradient(135deg, rgba(23,35,52,0.98) 0%, rgba(15,76,92,0.96) 100%)', color: '#fffaf2' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: 12, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'rgba(255,250,242,.62)' }}>Action Board</div>
              <div style={{ fontSize: 30, fontWeight: 800, marginTop: 8 }}>오늘 바로 판단할 것</div>
              <div style={{ fontSize: 15, color: 'rgba(255,250,242,.82)', marginTop: 10, lineHeight: 1.7, maxWidth: 760 }}>
                {renderTextWithLinks(analysisData.summary_lines?.[0] || '오늘의 핵심 요약이 아직 준비되지 않았습니다.')}
              </div>
            </div>
            <button className="ghost-button" style={{ background: 'rgba(255,255,255,.1)', color: '#fffaf2', borderColor: 'rgba(255,255,255,.18)' }} onClick={handleRefresh}>
              전체 새로고침
            </button>
          </div>
        </div>

        <div style={{ padding: 18, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, background: 'rgba(255,253,248,0.78)' }}>
          <div style={cardStyle('rgba(24,121,78,.18)', 'rgba(255,255,255,.72)')}>
            <div style={{ fontSize: 12, color: 'var(--text-3)' }}>시장 온도</div>
            <div style={{ fontSize: 26, fontWeight: 800, color: 'var(--text-1)', marginTop: 8 }}>{market.kospi_pct !== undefined && market.kospi_pct >= 0 ? '위험 선호' : '방어 모드'}</div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 8 }}>KOSPI {market.kospi_pct !== undefined ? `${market.kospi_pct > 0 ? '+' : ''}${market.kospi_pct.toFixed(2)}%` : '—'}</div>
          </div>
          <div style={cardStyle('rgba(15,76,92,.18)', 'rgba(255,255,255,.72)')}>
            <div style={{ fontSize: 12, color: 'var(--text-3)' }}>오늘의 상위 아이디어</div>
            <div style={{ fontSize: 26, fontWeight: 800, color: 'var(--text-1)', marginTop: 8 }}>{topIdeas[0]?.name || '대기 중'}</div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 8 }}>{topIdeas[0] ? `${getQuantSignalLabel(topIdeas[0].signal)} · 종합 ${topIdeas[0].score}점` : '추천 후보를 분석 중입니다.'}</div>
          </div>
          <div style={cardStyle('rgba(196,68,45,.16)', 'rgba(255,255,255,.72)')}>
            <div style={{ fontSize: 12, color: 'var(--text-3)' }}>관심종목 경고</div>
            <div style={{ fontSize: 26, fontWeight: 800, color: 'var(--text-1)', marginTop: 8 }}>{watchlistFocus.filter((item) => item.signal === '회피').length}개</div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 8 }}>약한 문맥 또는 하락 신호</div>
          </div>
          <div style={cardStyle('rgba(183,121,31,.18)', 'rgba(255,255,255,.72)')}>
            <div style={{ fontSize: 12, color: 'var(--text-3)' }}>핵심 리스크</div>
            <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-1)', marginTop: 8 }}>{riskSignals[0]?.title || '특이 리스크 없음'}</div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 8 }}>{riskSignals[0]?.level === 'high' ? '즉시 점검 필요' : '관찰 필요'}</div>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 18 }}>
        <div className="page-section">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <div>
              <div style={{ fontSize: 12, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: '0.12em' }}>Action Queue</div>
              <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-1)', marginTop: 6 }}>지금 해야 할 일</div>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {actionItems.length === 0 ? (
              <div style={{ fontSize: 14, color: 'var(--text-3)' }}>새로운 행동 항목이 아직 없습니다.</div>
            ) : actionItems.map((item, index) => (
              <div key={index} style={{ display: 'flex', gap: 12, alignItems: 'flex-start', padding: '14px 16px', borderRadius: 18, background: 'var(--bg-soft)', border: '1px solid var(--border)' }}>
                <span style={{ width: 28, height: 28, borderRadius: '50%', background: 'var(--accent-soft)', color: 'var(--accent)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 800, flexShrink: 0 }}>{index + 1}</span>
                <span style={{ fontSize: 14, color: 'var(--text-2)', lineHeight: 1.7 }}>{item}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="page-section">
          <div style={{ fontSize: 12, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: '0.12em' }}>Risk Radar</div>
          <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-1)', marginTop: 6, marginBottom: 14 }}>리스크 레이더</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {riskSignals.length === 0 ? (
              <div style={{ fontSize: 14, color: 'var(--text-3)' }}>감지된 주요 리스크가 없습니다.</div>
            ) : riskSignals.map((risk) => (
              <div key={risk.title} style={{ padding: '14px 16px', borderRadius: 18, background: risk.level === 'high' ? 'rgba(196,68,45,.08)' : 'rgba(183,121,31,.08)', border: `1px solid ${risk.level === 'high' ? 'rgba(196,68,45,.18)' : 'rgba(183,121,31,.18)'}` }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                  <div style={{ fontSize: 14, fontWeight: 800, color: 'var(--text-1)' }}>{risk.title}</div>
                  <div style={{ fontSize: 11, color: risk.level === 'high' ? 'var(--down)' : '#b7791f' }}>{risk.level === 'high' ? 'High' : 'Medium'}</div>
                </div>
                <div style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.65, marginTop: 8 }}>{risk.detail}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 18 }}>
        <div className="page-section">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-1)' }}>상위 자동 추천</div>
            <div style={{ fontSize: 12, color: 'var(--text-4)' }}>{autoLoading ? '분석 중...' : `${topIdeas.length}개`}</div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {topIdeas.length === 0 ? (
              <div style={{ fontSize: 14, color: 'var(--text-3)' }}>추천 종목을 아직 찾지 못했습니다.</div>
            ) : topIdeas.map((item) => (
              <div key={item.name} style={{ padding: '14px 16px', borderRadius: 18, background: 'var(--bg-soft)', border: '1px solid var(--border)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'baseline' }}>
                  <div style={{ fontSize: 15, fontWeight: 800, color: 'var(--text-1)' }}>{item.name}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-3)' }}>종합 {item.score}점</div>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 5 }}>{[item.code, item.market].filter(Boolean).join(' • ')}</div>
                <div style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.7, marginTop: 8 }}>{item.evidence[0] || item.reasons[0]}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="page-section">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-1)' }}>관심종목 집중 점검</div>
            <div style={{ fontSize: 12, color: 'var(--text-4)' }}>{watchlistFocus.length}개</div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {watchlistFocus.length === 0 ? (
              <div style={{ fontSize: 14, color: 'var(--text-3)' }}>관심종목이 아직 없습니다.</div>
            ) : watchlistFocus.map((item) => (
              <div key={item.code} style={{ padding: '14px 16px', borderRadius: 18, background: 'var(--bg-soft)', border: '1px solid var(--border)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'baseline' }}>
                  <div style={{ fontSize: 15, fontWeight: 800, color: 'var(--text-1)' }}>{item.name}</div>
                  <div style={{ fontSize: 12, color: item.signal === '회피' ? 'var(--down)' : item.signal === '강력추천' ? 'var(--up)' : 'var(--accent)' }}>{getQuantSignalLabel(item.signal)}</div>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 5 }}>{item.code} • {item.market}</div>
                <div style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.7, marginTop: 8 }}>{item.evidence[0] || item.reasons[0]}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
