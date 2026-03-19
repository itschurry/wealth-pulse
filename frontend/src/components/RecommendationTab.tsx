import { useCompare } from '../hooks/useCompare';
import { useTodayPicks } from '../hooks/useTodayPicks';
import type { TodayPickItem } from '../types';

interface Props {
  onRefresh: () => void;
}

const signalColor: Record<string, string> = {
  '추천': 'var(--up)',
  '중립': '#b7791f',
  '회피': 'var(--down)',
};

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

function PickCard({ item }: { item: TodayPickItem }) {
  return (
    <div className="page-section" style={{ padding: 18, borderColor: `${signalColor[item.signal] || 'var(--border)'}33`, display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-1)' }}>{item.name}</div>
          <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 5 }}>{[item.code, item.market, item.sector].filter(Boolean).join(' • ')}</div>
        </div>
        <span style={{ fontSize: 11, fontWeight: 800, borderRadius: 999, padding: '6px 10px', color: signalColor[item.signal], border: `1px solid ${signalColor[item.signal]}`, background: `${signalColor[item.signal]}15` }}>
          {item.signal}
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: 14, alignItems: 'center' }}>
        <div style={{ padding: '14px 12px', borderRadius: 18, background: 'var(--bg-soft)', border: '1px solid var(--border)' }}>
          <div style={{ fontSize: 11, color: 'var(--text-4)' }}>Composite Score</div>
          <div style={{ fontSize: 34, fontWeight: 800, color: 'var(--accent)', marginTop: 6 }}>{item.score}</div>
          <div style={{ fontSize: 11, color: 'var(--text-4)' }}>신뢰도 {item.confidence}%</div>
        </div>

        <div style={{ padding: '14px 16px', borderRadius: 18, background: 'rgba(15,76,92,.06)', border: '1px solid rgba(15,76,92,.12)' }}>
          <div style={{ fontSize: 11, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Catalyst</div>
          <div style={{ fontSize: 14, color: 'var(--text-2)', lineHeight: 1.7, marginTop: 8 }}>
            {item.catalysts[0] || item.reasons[0] || '핵심 촉매 데이터 없음'}
          </div>
        </div>
      </div>

      <div style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.7 }}>
        {item.reasons.slice(0, 3).map((reason, index) => (
          <div key={index}>• {reason}</div>
        ))}
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {item.risks.slice(0, 2).map((risk, index) => (
          <span key={index} style={{ fontSize: 11, color: 'var(--down)', background: 'rgba(196,68,45,.08)', border: '1px solid rgba(196,68,45,.18)', borderRadius: 999, padding: '5px 9px' }}>
            {risk}
          </span>
        ))}
      </div>

      {item.related_news.length > 0 && (
        <div style={{ display: 'grid', gap: 10 }}>
          {item.related_news.slice(0, 2).map((news) => (
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

export function RecommendationTab({ onRefresh }: Props) {
  const { data: todayPicks, status: picksStatus, refresh: refreshPicks } = useTodayPicks();
  const { data: compare, refresh: refreshCompare } = useCompare();

  function handleRefresh() {
    onRefresh();
    refreshPicks();
    refreshCompare();
  }

  const baseSignals = compare.signal_counts?.base || {};
  const prevSignals = compare.signal_counts?.prev || {};
  const recommendationShift = (baseSignals['추천'] || 0) - (prevSignals['추천'] || 0);
  const avoidanceShift = (baseSignals['회피'] || 0) - (prevSignals['회피'] || 0);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div className="page-section" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: 24, background: 'linear-gradient(135deg, rgba(15,76,92,0.98) 0%, rgba(24,78,119,0.96) 100%)', color: '#fffaf2' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start' }}>
            <div>
              <div style={{ fontSize: 12, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'rgba(255,250,242,.64)' }}>Today Picks</div>
              <div style={{ fontSize: 30, fontWeight: 800, marginTop: 8 }}>오늘의 추천</div>
              <div style={{ fontSize: 15, color: 'rgba(255,250,242,.82)', marginTop: 10, lineHeight: 1.7, maxWidth: 760 }}>
                최신 뉴스와 시장 맥락을 바탕으로 오늘 먼저 볼 종목을 정리합니다. 점수보다 촉매와 리스크를 함께 읽는 탭입니다.
              </div>
            </div>
            <button className="ghost-button" style={{ background: 'rgba(255,255,255,.1)', color: '#fffaf2', borderColor: 'rgba(255,255,255,.18)' }} onClick={handleRefresh}>
              추천 새로고침
            </button>
          </div>
        </div>

        <div style={{ padding: 18, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, background: 'rgba(255,253,248,0.78)' }}>
          <SummaryCard title="추천 신호" value={`${prevSignals['추천'] || 0} → ${baseSignals['추천'] || 0}`} detail="전일 대비 추천 종목 수 변화" tone={recommendationShift >= 0 ? 'up' : 'down'} />
          <SummaryCard title="회피 신호" value={`${prevSignals['회피'] || 0} → ${baseSignals['회피'] || 0}`} detail="리스크가 커질수록 회피 신호가 늘어납니다." tone={avoidanceShift > 0 ? 'down' : 'neutral'} />
          <SummaryCard title="새 리스크" value={`${compare.new_risks?.length || 0}개`} detail={(compare.new_risks && compare.new_risks[0]) || '새로 추가된 리스크 없음'} tone={(compare.new_risks?.length || 0) > 0 ? 'down' : 'neutral'} />
          <SummaryCard title="시장 톤" value={todayPicks.market_tone || '데이터 없음'} detail={todayPicks.generated_at || '생성 시각 없음'} />
        </div>
      </div>

      {compare.today_pick_changes && compare.today_pick_changes.length > 0 && (
        <div className="page-section">
          <div style={{ fontSize: 12, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: '0.12em' }}>Shift Watch</div>
          <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-1)', marginTop: 6, marginBottom: 14 }}>전일 대비 변화</div>
          <div style={{ display: 'grid', gap: 10 }}>
            {compare.today_pick_changes.slice(0, 4).map((item, index) => (
              <div key={`${item.name}-${index}`} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', padding: '12px 14px', borderRadius: 18, background: 'var(--bg-soft)', border: '1px solid var(--border)' }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-1)' }}>{item.name}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 4 }}>{item.previous_signal ? `${item.previous_signal} → ${item.current_signal}` : '신규 추천 편입'}</div>
                </div>
                <div style={{ fontSize: 13, fontWeight: 700, color: item.score_diff >= 0 ? 'var(--up)' : 'var(--down)' }}>
                  {item.score_diff >= 0 ? '+' : ''}{item.score_diff}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {picksStatus === 'error' && (
        <div className="page-section" style={{ color: 'var(--down)' }}>
          오늘의 추천 데이터를 불러올 수 없습니다.
        </div>
      )}

      {picksStatus !== 'error' && todayPicks.picks.length === 0 && (
        <div className="page-section" style={{ textAlign: 'center', padding: '48px 24px' }}>
          <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-2)' }}>오늘의 추천 종목이 아직 없습니다</div>
          <div style={{ fontSize: 13, color: 'var(--text-4)', marginTop: 8 }}>다음 리포트 생성 이후 뉴스 기반 추천이 표시됩니다.</div>
        </div>
      )}

      {todayPicks.picks.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
          {todayPicks.picks.map((item) => (
            <PickCard key={`${item.code || item.name}`} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}
