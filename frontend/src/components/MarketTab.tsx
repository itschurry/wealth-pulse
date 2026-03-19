import { useMarketDashboard } from '../hooks/useMarketDashboard';
import { MarketTile } from './MarketTile';
import type { MacroItem } from '../types';

function formatContextValue(value?: string) {
  if (!value) return '데이터 없음';

  const normalized = value.trim().toLowerCase();
  const labels: Record<string, string> = {
    risk_on: '위험 선호',
    risk_off: '위험 회피',
    neutral: '중립',
    bullish: '상승 우위',
    bearish: '하락 우위',
    positive: '긍정',
    negative: '부정',
    cautious: '신중',
  };

  return labels[normalized] || value;
}

function sectionTitle(text: string) {
  return (
    <div style={{ marginTop: 22, marginBottom: 12 }}>
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-4)' }}>
        {text}
      </div>
    </div>
  );
}

function infoCard(title: string, value: string, detail: string, tone: 'neutral' | 'up' | 'down' = 'neutral') {
  const borderColor = tone === 'up' ? 'rgba(34,197,94,.24)' : tone === 'down' ? 'rgba(239,68,68,.24)' : 'var(--border)';
  return (
    <div style={{ background: 'var(--card-bg)', border: `1px solid ${borderColor}`, borderRadius: 14, padding: 14 }}>
      <div style={{ fontSize: 12, color: 'var(--text-3)' }}>{title}</div>
      <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-1)', marginTop: 8 }}>{value}</div>
      <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 6, lineHeight: 1.5 }}>{detail}</div>
    </div>
  );
}

const FEATURED_US_MACRO_KEYS = ['fed_funds', 'us10y', 'us2y', 'dxy', 'unemployment', 'nfp_change'];
const FEATURED_KR_MACRO_KEYS = ['kr_base_rate', 'kr_unemployment', 'kr_cpi', 'kr_ppi'];

function pickMacroItems(items: MacroItem[], keys: string[]) {
  const map = new Map(items.map((item) => [item.key, item]));
  return keys.map((key) => map.get(key)).filter((item): item is MacroItem => Boolean(item));
}

export function MarketTab() {
  const { data: dashboard, status: combinedStatus, refresh } = useMarketDashboard();
  const data = dashboard.market || {};
  const macroData = dashboard.macro || {};
  const contextData = dashboard.context || {};

  function handleRefresh() {
    refresh(true);
  }

  const macroItems = macroData.items && macroData.items.length > 0 ? macroData.items : [];

  // USD/KRW는 live-market가 더 실시간성이 높으므로 거시 섹션에서는 숨긴다.
  const dedupedMacroItems = macroItems.filter((item) => !(item.key === 'kr_usdkrw' && data.usd_krw !== undefined));
  const usMacroItems = pickMacroItems(dedupedMacroItems.filter((item) => !item.key.startsWith('kr_')), FEATURED_US_MACRO_KEYS);
  const krMacroItems = pickMacroItems(dedupedMacroItems.filter((item) => item.key.startsWith('kr_')), FEATURED_KR_MACRO_KEYS);

  const marketPulse = data.kospi_pct !== undefined && data.nasdaq_pct !== undefined
    ? data.kospi_pct >= 0 && data.nasdaq_pct >= 0
      ? '위험 선호'
      : data.kospi_pct < 0 && data.nasdaq_pct < 0
        ? '위험 회피'
        : '혼조'
    : '데이터 확인 중';

  const pulseTone = marketPulse === '위험 선호' ? 'up' : marketPulse === '위험 회피' ? 'down' : 'neutral';
  const contextSummary = contextData.context?.summary || '시장 컨텍스트 데이터 없음';
  const contextRegime = formatContextValue(contextData.context?.regime);
  const contextDollar = formatContextValue(contextData.context?.dollar_signal);
  const contextPolicy = formatContextValue(contextData.context?.policy_signal);
  const contextYieldCurve = formatContextValue(contextData.context?.yield_curve_signal);
  const contextInflation = formatContextValue(contextData.context?.inflation_signal);
  const contextLabor = formatContextValue(contextData.context?.labor_signal);
  const contextRiskLevel = formatContextValue(contextData.context?.risk_level);
  const liveSummary = [
    data.kospi_pct !== undefined ? `KOSPI ${data.kospi_pct > 0 ? '+' : ''}${data.kospi_pct.toFixed(2)}%` : null,
    data.nasdaq_pct !== undefined ? `NASDAQ ${data.nasdaq_pct > 0 ? '+' : ''}${data.nasdaq_pct.toFixed(2)}%` : null,
    data.usd_krw !== undefined ? `USD/KRW ${data.usd_krw.toLocaleString('ko-KR', { maximumFractionDigits: 1 })}` : null,
  ].filter(Boolean).join(' · ');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {combinedStatus === 'loading' && (
            <span style={{
              width: 8, height: 8, borderRadius: '50%',
              border: '2px solid #3b82f6', borderTopColor: 'transparent',
              display: 'inline-block', animation: 'spin .8s linear infinite',
            }} />
          )}
          {combinedStatus === 'ok' && (
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--up)', boxShadow: '0 0 6px var(--up)', display: 'inline-block' }} />
          )}
          {combinedStatus === 'error' && (
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--down)', display: 'inline-block' }} />
          )}
          <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
            {combinedStatus === 'loading' ? '불러오는 중...'
              : combinedStatus === 'error' ? '일부 데이터 오류'
              : data.updated_at ? `실시간 갱신: ${data.updated_at}` : '실시간'}
          </span>
        </div>
        <button onClick={handleRefresh} style={{
          background: 'rgba(59,130,246,.12)', border: '1px solid rgba(59,130,246,.3)',
          borderRadius: 8, color: '#93c5fd', cursor: 'pointer', fontSize: 16, padding: '4px 10px',
        }} title="새로고침">↻</button>
      </div>

      <div style={{
        background: 'linear-gradient(135deg, rgba(14,27,53,.96) 0%, rgba(18,32,64,.96) 65%, rgba(14,27,53,.96) 100%)',
        border: '1px solid rgba(59,130,246,.16)',
        borderRadius: 16,
        padding: 18,
      }}>
        <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--text-1)' }}>실시간 참고</div>
        <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 10 }}>{liveSummary || '실시간 요약 데이터 없음'}</div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
        {infoCard('시장 온도', marketPulse, contextData.context?.risk_level ? `리스크 수준 ${contextRiskLevel}` : '시장 리스크 데이터 확인 중', pulseTone)}
        {infoCard('달러 환경', contextDollar, data.usd_krw !== undefined ? `실시간 USD/KRW ${data.usd_krw.toLocaleString('ko-KR', { maximumFractionDigits: 1 })}` : '실시간 환율 데이터 없음')}
        {infoCard('정책/금리', contextPolicy, contextData.context?.yield_curve_signal ? `장단기금리 ${contextYieldCurve}` : '금리 신호 데이터 없음')}
        {infoCard('거시 요약', contextRegime, contextSummary, 'neutral')}
      </div>

      {sectionTitle('핵심 시장 지표')}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 12 }}>
        <MarketTile label="KOSPI" value={data.kospi} pct={data.kospi_pct} isLive badgeText="KRX" />
        <MarketTile label="KOSDAQ" value={data.kosdaq} pct={data.kosdaq_pct} isLive badgeText="KRX" />
        <MarketTile label="NASDAQ" value={data.nasdaq} pct={data.nasdaq_pct} badgeText="NASDAQ" />
        <MarketTile label="S&P 100" value={data.sp100} pct={data.sp100_pct} badgeText="NYSE" />
        <MarketTile
          label="USD/KRW"
          value={data.usd_krw}
          isLive
          badgeText="Live"
          formatValue={(v) => v.toLocaleString('ko-KR', { maximumFractionDigits: 1 })}
        />
        <MarketTile label="WTI 원유" value={data.wti} pct={data.wti_pct} isLive badgeText="Live" formatValue={(v) => `$${v.toFixed(2)}`} />
      </div>

      {sectionTitle('시장 컨텍스트')}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 12 }}>
        <MarketTile label="시장 국면" value={contextRegime} badgeText="Context" metaText={contextData.context?.summary} />
        <MarketTile label="리스크 수준" value={contextRiskLevel} badgeText="Risk" />
        <MarketTile label="인플레이션" value={contextInflation} />
        <MarketTile label="고용" value={contextLabor} />
        <MarketTile label="정책" value={contextPolicy} />
        <MarketTile label="장단기금리" value={contextYieldCurve} />
        <MarketTile label="달러" value={contextDollar} />
      </div>

      {sectionTitle('주요 거시 지표')}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16 }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-2)', marginBottom: 10 }}>미국</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 12 }}>
            {usMacroItems.map((item) => (
              <MarketTile
                key={item.key}
                label={item.label}
                value={item.display_value || '데이터 없음'}
                badgeText={item.source || undefined}
                metaText={item.as_of ? `기준일 ${item.as_of}` : item.summary}
              />
            ))}
            {usMacroItems.length === 0 && <MarketTile label="미국 거시" value="데이터 없음" />}
          </div>
        </div>

        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-2)', marginBottom: 10 }}>한국</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 12 }}>
            {krMacroItems.map((item) => (
              <MarketTile
                key={item.key}
                label={item.label}
                value={item.display_value || '데이터 없음'}
                badgeText={item.source || 'ECOS'}
                metaText={item.summary}
              />
            ))}
            {krMacroItems.length === 0 && <MarketTile label="한국 거시" value="데이터 없음" badgeText="ECOS" />}
          </div>
        </div>
      </div>
    </div>
  );
}
