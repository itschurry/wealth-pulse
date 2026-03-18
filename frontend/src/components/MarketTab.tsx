import { useMarket } from '../hooks/useMarket';
import { useMacro } from '../hooks/useMacro';
import { useMarketContext } from '../hooks/useMarketContext';
import { MarketTile } from './MarketTile';

export function MarketTab() {
  const { data, status, updatedAt, refresh } = useMarket();
  const { data: macroData, status: macroStatus, refresh: refreshMacro } = useMacro();
  const { data: contextData, status: contextStatus, refresh: refreshContext } = useMarketContext();

  const combinedStatus: 'loading' | 'ok' | 'error' =
    status === 'error' || macroStatus === 'error' || contextStatus === 'error'
      ? 'error'
      : status === 'loading' || macroStatus === 'loading' || contextStatus === 'loading'
        ? 'loading'
        : 'ok';

  function handleRefresh() {
    refresh();
    refreshMacro();
    refreshContext();
  }

  const macroItems = macroData.items && macroData.items.length > 0 ? macroData.items : [];
  const usMacroItems = macroItems.filter((item) => !item.key.startsWith('kr_'));
  const krMacroItems = macroItems.filter((item) => item.key.startsWith('kr_'));

  const sectionTitle = (text: string) => (
    <div style={{
      fontSize: 11, fontWeight: 700, letterSpacing: '0.1em',
      textTransform: 'uppercase', color: 'var(--text-4)',
      marginTop: 20, marginBottom: 12,
    }}>{text}</div>
  );

  return (
    <div>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4,
      }}>
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
              : updatedAt ? `갱신: ${updatedAt}` : '실시간'}
          </span>
        </div>
        <button onClick={handleRefresh} style={{
          background: 'rgba(59,130,246,.12)', border: '1px solid rgba(59,130,246,.3)',
          borderRadius: 8, color: '#93c5fd', cursor: 'pointer', fontSize: 16, padding: '4px 10px',
        }} title="새로고침">↻</button>
      </div>

      <div style={{
        marginBottom: 12,
        fontSize: 12,
        color: 'var(--text-4)',
        border: '1px solid var(--border-light)',
        borderRadius: 8,
        padding: '8px 10px',
        background: 'rgba(255,255,255,.02)',
      }}>
        실시간 참고용 화면입니다. 투자 판단은 오늘 리포트 탭 기준으로 확인하세요.
      </div>

      {sectionTitle('국내 지수')}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
        <MarketTile label="KOSPI" value={data.kospi} pct={data.kospi_pct} isLive badgeText="KRX" />
        <MarketTile label="KOSDAQ" value={data.kosdaq} pct={data.kosdaq_pct} isLive badgeText="KRX" />
      </div>

      {sectionTitle('미국 지수')}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
        <MarketTile label="S&P 100" value={data.sp100} pct={data.sp100_pct} badgeText="NYSE" />
        <MarketTile label="NASDAQ" value={data.nasdaq} pct={data.nasdaq_pct} badgeText="NASDAQ" />
      </div>

      {sectionTitle('환율 · 원자재 · 암호화폐')}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
        gap: 12,
      }}>
        <MarketTile label="USD/KRW" value={data.usd_krw}
          formatValue={v => v.toLocaleString('ko-KR', { maximumFractionDigits: 1 })} />
        <MarketTile label="WTI 원유" value={data.wti} pct={data.wti_pct}
          formatValue={v => `$${v.toFixed(2)}`} />
        <MarketTile label="금 (Gold)" value={data.gold} pct={data.gold_pct}
          formatValue={v => `$${v.toLocaleString('en-US', { maximumFractionDigits: 0 })}`} />
        <MarketTile label="비트코인" value={data.btc} pct={data.btc_pct}
          formatValue={v => `$${v.toLocaleString('en-US', { maximumFractionDigits: 0 })}`} />
      </div>

      {sectionTitle('시장 컨텍스트')}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))',
        gap: 12,
      }}>
        <MarketTile label="시장 국면" value={contextData.context?.regime || '데이터 없음'} badgeText="Context" />
        <MarketTile label="리스크 수준" value={contextData.context?.risk_level || '데이터 없음'} badgeText="Risk" />
        <MarketTile label="인플레이션" value={contextData.context?.inflation_signal || '데이터 없음'} />
        <MarketTile label="고용" value={contextData.context?.labor_signal || '데이터 없음'} />
        <MarketTile label="정책" value={contextData.context?.policy_signal || '데이터 없음'} />
        <MarketTile label="장단기금리" value={contextData.context?.yield_curve_signal || '데이터 없음'} />
        <MarketTile label="달러" value={contextData.context?.dollar_signal || '데이터 없음'} />
      </div>

      {sectionTitle('주요 거시 지표 (미국)')}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))',
        gap: 12,
      }}>
        {usMacroItems.map((item) => (
          <MarketTile
            key={item.key}
            label={item.label}
            value={item.display_value || '데이터 없음'}
            badgeText={item.source || item.as_of || undefined}
          />
        ))}
        {(usMacroItems.length === 0) && (
          <MarketTile label="거시 지표" value="데이터 없음" />
        )}
      </div>

      {sectionTitle('주요 거시 지표 (한국)')}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))',
        gap: 12,
      }}>
        {krMacroItems.map((item) => (
          <MarketTile
            key={item.key}
            label={item.label}
            value={item.display_value || '데이터 없음'}
            badgeText={item.source || 'ECOS'}
          />
        ))}
        {(krMacroItems.length === 0) && (
          <MarketTile label="한국 거시" value="데이터 없음" badgeText="ECOS" />
        )}
      </div>
    </div>
  );
}
