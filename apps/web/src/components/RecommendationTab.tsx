import { useMemo } from 'react';
import { useWatchlist } from '../hooks/useWatchlist';
import { useCompare } from '../hooks/useCompare';
import { useUnifiedScores } from '../hooks/useUnifiedScores';
import type { TodayPickItem } from '../types';
import { getMarketBucket, getMarketSectionCaption, getMarketSectionLabel, getMarketSessions, getPreferredMarketOrder, type MarketBucket, type MarketSessionInfo } from '../utils/marketSession';
import { getQuantGateLabel, getQuantSignalLabel, getSetupQualityLabel } from '../utils/quantLabels';

interface Props {
  onRefresh: () => void;
}

const signalColor: Record<string, string> = {
  '추천': 'var(--up)',
  '중립': '#b7791f',
  '회피': 'var(--down)',
};

const gateTone: Record<string, { label: string; color: string; background: string; border: string }> = {
  passed: {
    label: '필터 통과',
    color: 'var(--up)',
    background: 'rgba(24,121,78,.12)',
    border: 'rgba(24,121,78,.2)',
  },
  caution: {
    label: '주의',
    color: '#b7791f',
    background: 'rgba(183,121,31,.12)',
    border: 'rgba(183,121,31,.2)',
  },
  blocked: {
    label: '제외',
    color: 'var(--down)',
    background: 'rgba(196,68,45,.10)',
    border: 'rgba(196,68,45,.2)',
  },
};

function formatHorizon(value?: 'short_term' | 'mid_term') {
  if (value === 'mid_term') return '중기';
  return '단타';
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

function MarketSection({ bucket, items, session }: { bucket: MarketBucket; items: TodayPickItem[]; session?: MarketSessionInfo }) {
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
          <PickCard key={`${item.code || item.name}`} item={item} />
        ))}
      </div>
    </div>
  );
}

function PickCard({ item }: { item: TodayPickItem }) {
  const gate = gateTone[item.gate_status || 'passed'] || gateTone.passed;
  const signalLabel = getQuantSignalLabel(item.signal);
  
  // Phase 5: 신뢰도 배지 렌더링
  const getReliabilityBadge = () => {
    if (!item.strategy_reliability && !item.reliability_reason) {
      return null;
    }
    
    const reliabilityConfig: Record<string, { label: string; color: string; bg: string; border: string }> = {
      'high': { label: '신뢰도 높음', color: 'var(--up)', bg: 'rgba(24,121,78,.12)', border: 'rgba(24,121,78,.2)' },
      'medium': { label: '신뢰도 보통', color: '#b7791f', bg: 'rgba(183,121,31,.12)', border: 'rgba(183,121,31,.2)' },
      'low': { label: '신뢰도 낮음', color: 'var(--down)', bg: 'rgba(196,68,45,.10)', border: 'rgba(196,68,45,.2)' },
      'insufficient': { label: '검증 부족', color: '#a0aec0', bg: 'rgba(160,174,192,.12)', border: 'rgba(160,174,192,.2)' },
    };
    
    const config = reliabilityConfig[item.strategy_reliability || 'insufficient'] || 
                   { label: item.reliability_reason || '신뢰도 확인', color: '#a0aec0', bg: 'rgba(160,174,192,.12)', border: 'rgba(160,174,192,.2)' };
    
    return (
      <span style={{ fontSize: 11, fontWeight: 800, borderRadius: 999, padding: '6px 10px', 
                     color: config.color, border: `1px solid ${config.border}`, background: config.bg }}>
        {config.label}
        {item.validation_trades !== undefined && ` (신호: ${item.validation_trades})`}
      </span>
    );
  };
  
  return (
    <div className="page-section" style={{ padding: 18, borderColor: `${signalColor[item.signal] || 'var(--border)'}33`, display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-1)' }}>{item.name}</div>
          <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 5 }}>{[item.code, item.market, item.sector].filter(Boolean).join(' • ')}</div>
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <span style={{ fontSize: 11, fontWeight: 800, borderRadius: 999, padding: '6px 10px', color: gate.color, border: `1px solid ${gate.border}`, background: gate.background }}>
            {getQuantGateLabel(item.gate_status)}
          </span>
          <span style={{ fontSize: 11, fontWeight: 800, borderRadius: 999, padding: '6px 10px', color: signalColor[item.signal], border: `1px solid ${signalColor[item.signal]}`, background: `${signalColor[item.signal]}15` }}>
            {signalLabel}
          </span>
          {item.setup_quality && (
            <span style={{ fontSize: 11, fontWeight: 800, borderRadius: 999, padding: '6px 10px', color: 'var(--text-2)', border: '1px solid var(--border)', background: 'var(--bg-soft)' }}>
              {getSetupQualityLabel(item.setup_quality)}
            </span>
          )}
          {getReliabilityBadge()}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: 14, alignItems: 'center' }}>
        <div style={{ padding: '14px 12px', borderRadius: 18, background: 'var(--bg-soft)', border: '1px solid var(--border)' }}>
          <div style={{ fontSize: 11, color: 'var(--text-4)' }}>종합점수</div>
          <div style={{ fontSize: 34, fontWeight: 800, color: 'var(--accent)', marginTop: 6 }}>{item.score}</div>
          <div style={{ fontSize: 11, color: 'var(--text-4)' }}>{formatHorizon(item.horizon)} · 신뢰도 {item.confidence}%</div>
        </div>

        <div style={{ padding: '14px 16px', borderRadius: 18, background: 'rgba(15,76,92,.06)', border: '1px solid rgba(15,76,92,.12)' }}>
          <div style={{ fontSize: 11, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Playbook Thesis</div>
          <div style={{ fontSize: 14, color: 'var(--text-2)', lineHeight: 1.7, marginTop: 8 }}>
            {item.ai_thesis || item.technical_view || item.catalysts[0] || item.reasons[0] || '핵심 촉매 데이터 없음'}
          </div>
          {item.technical_view && (
            <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 8 }}>
              {item.technical_view}
            </div>
          )}
        </div>
      </div>

      <div style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.7 }}>
        {item.reasons.slice(0, 3).map((reason, index) => (
          <div key={index}>• {reason}</div>
        ))}
      </div>

      {item.gate_reasons && item.gate_reasons.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {item.gate_reasons.slice(0, 2).map((reason, index) => (
            <span key={index} style={{ fontSize: 11, color: gate.color, background: gate.background, border: `1px solid ${gate.border}`, borderRadius: 999, padding: '5px 9px' }}>
              {reason}
            </span>
          ))}
        </div>
      )}

      {item.technical_snapshot && (
        <div style={{ display: 'grid', gap: 8, padding: '12px 14px', borderRadius: 16, border: '1px solid rgba(15,76,92,.16)', background: 'rgba(15,76,92,.06)' }}>
          <div style={{ fontSize: 11, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 700 }}>기술 지표</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(100px, 1fr))', gap: 8 }}>
            {item.technical_snapshot.current_price !== undefined && item.technical_snapshot.current_price !== null && (
              <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
                <div style={{ fontSize: 10, color: 'var(--text-4)', marginBottom: 2 }}>현재가</div>
                <div style={{ fontWeight: 700 }}>{item.technical_snapshot.current_price.toLocaleString()}</div>
              </div>
            )}
            {item.technical_snapshot.rsi14 !== undefined && item.technical_snapshot.rsi14 !== null && (
              <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
                <div style={{ fontSize: 10, color: 'var(--text-4)', marginBottom: 2 }}>RSI(14)</div>
                <div style={{ fontWeight: 700 }}>{item.technical_snapshot.rsi14.toFixed(1)}</div>
              </div>
            )}
            {item.technical_snapshot.adx14 !== undefined && item.technical_snapshot.adx14 !== null && (
              <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
                <div style={{ fontSize: 10, color: 'var(--text-4)', marginBottom: 2 }}>ADX(14)</div>
                <div style={{ fontWeight: 700 }}>{item.technical_snapshot.adx14.toFixed(1)}</div>
              </div>
            )}
            {item.technical_snapshot.mfi14 !== undefined && item.technical_snapshot.mfi14 !== null && (
              <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
                <div style={{ fontSize: 10, color: 'var(--text-4)', marginBottom: 2 }}>MFI(14)</div>
                <div style={{ fontWeight: 700 }}>{item.technical_snapshot.mfi14.toFixed(1)}</div>
              </div>
            )}
            {item.technical_snapshot.bb_pct !== undefined && item.technical_snapshot.bb_pct !== null && (
              <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
                <div style={{ fontSize: 10, color: 'var(--text-4)', marginBottom: 2 }}>BB %b</div>
                <div style={{ fontWeight: 700 }}>{item.technical_snapshot.bb_pct.toFixed(2)}</div>
              </div>
            )}
            {item.technical_snapshot.stoch_k !== undefined && item.technical_snapshot.stoch_k !== null && (
              <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
                <div style={{ fontSize: 10, color: 'var(--text-4)', marginBottom: 2 }}>Stoch K</div>
                <div style={{ fontWeight: 700 }}>{item.technical_snapshot.stoch_k.toFixed(1)}</div>
              </div>
            )}
            {item.technical_snapshot.volume_ratio !== undefined && item.technical_snapshot.volume_ratio !== null && (
              <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
                <div style={{ fontSize: 10, color: 'var(--text-4)', marginBottom: 2 }}>거래량배수</div>
                <div style={{ fontWeight: 700 }}>{item.technical_snapshot.volume_ratio.toFixed(2)}x</div>
              </div>
            )}
          </div>
        </div>
      )}

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
  const { items: watchlist } = useWatchlist();
  const { todayPicks, refresh: refreshUnifiedScores, applyToPick } = useUnifiedScores(watchlist);
  const { data: compare, refresh: refreshCompare } = useCompare();

  function handleRefresh() {
    onRefresh();
    refreshUnifiedScores();
    refreshCompare();
  }

  const viewPicks = useMemo(() => (
    [...(todayPicks.data.picks || [])]
      .map((item) => applyToPick(item))
      .sort((a, b) => b.score - a.score)
  ), [todayPicks.data.picks, applyToPick]);
  const marketSessions = getMarketSessions();
  const groupedPicks = useMemo(() => {
    const buckets: Record<MarketBucket, TodayPickItem[]> = {
      domestic: [],
      us: [],
      other: [],
    };

    viewPicks.forEach((item) => {
      buckets[getMarketBucket(item.market)].push(item);
    });

    return getPreferredMarketOrder().map((bucket) => ({
      bucket,
      items: buckets[bucket],
      session: bucket === 'domestic' ? marketSessions.domestic : bucket === 'us' ? marketSessions.us : undefined,
    })).filter((group) => group.items.length > 0);
  }, [marketSessions, viewPicks]);

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
                최신 뉴스와 시장 맥락을 바탕으로 오늘 먼저 볼 종목을 정리합니다. 플레이북 게이트를 통과한 아이디어와 보류 사유를 함께 읽는 탭입니다.
              </div>
            </div>
            <button className="ghost-button" style={{ background: 'rgba(255,255,255,.1)', color: '#fffaf2', borderColor: 'rgba(255,255,255,.18)' }} onClick={handleRefresh}>
              추천 새로고침
            </button>
          </div>
        </div>

        <div style={{ padding: 18, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, background: 'rgba(255,253,248,0.78)' }}>
          <SummaryCard title="롱 우위 신호" value={`${prevSignals['추천'] || 0} → ${baseSignals['추천'] || 0}`} detail="전일 대비 롱 우위 후보 수 변화" tone={recommendationShift >= 0 ? 'up' : 'down'} />
          <SummaryCard title="기대값 낮음" value={`${prevSignals['회피'] || 0} → ${baseSignals['회피'] || 0}`} detail="리스크가 커질수록 기대값 낮음 판정이 늘어납니다." tone={avoidanceShift > 0 ? 'down' : 'neutral'} />
          <SummaryCard title="새 리스크" value={`${compare.new_risks?.length || 0}개`} detail={(compare.new_risks && compare.new_risks[0]) || '새로 추가된 리스크 없음'} tone={(compare.new_risks?.length || 0) > 0 ? 'down' : 'neutral'} />
          <SummaryCard title="시장 톤" value={todayPicks.data.market_tone || '데이터 없음'} detail={todayPicks.data.generated_at || '생성 시각 없음'} />
        </div>
      </div>

      <div className="page-section" style={{ padding: 18, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
        <MarketStatusPill session={marketSessions.domestic} />
        <MarketStatusPill session={marketSessions.us} />
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
                  <div style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 4 }}>{item.previous_signal ? `${getQuantSignalLabel(item.previous_signal)} → ${getQuantSignalLabel(item.current_signal)}` : '신규 추천 편입'}</div>
                </div>
                <div style={{ fontSize: 13, fontWeight: 700, color: item.score_diff >= 0 ? 'var(--up)' : 'var(--down)' }}>
                  {item.score_diff >= 0 ? '+' : ''}{item.score_diff}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {todayPicks.status === 'error' && (
        <div className="page-section" style={{ color: 'var(--down)' }}>
          오늘의 추천 데이터를 불러올 수 없습니다.
        </div>
      )}

      {todayPicks.status !== 'error' && viewPicks.length === 0 && (
        <div className="page-section" style={{ textAlign: 'center', padding: '48px 24px' }}>
          <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-2)' }}>오늘의 추천 종목이 아직 없습니다</div>
          <div style={{ fontSize: 13, color: 'var(--text-4)', marginTop: 8 }}>다음 리포트 생성 이후 뉴스 기반 추천이 표시됩니다.</div>
        </div>
      )}

      {viewPicks.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {groupedPicks.map((group) => (
            <MarketSection key={group.bucket} bucket={group.bucket} items={group.items} session={group.session} />
          ))}
        </div>
      )}
    </div>
  );
}
