interface Props {
  label: string;
  value?: number | string;
  pct?: number;
  badgeText?: string;
  isLive?: boolean;
  formatValue?: (v: number) => string;
}

function defaultFormat(v: number) {
  return v.toLocaleString('ko-KR', { maximumFractionDigits: 2 });
}

export function MarketTile({ label, value, pct, badgeText, isLive, formatValue }: Props) {
  const isUp = pct !== undefined && pct >= 0;
  const color = pct !== undefined ? (isUp ? 'var(--up)' : 'var(--down)') : 'var(--text-2)';
  const bgColor = pct !== undefined ? (isUp ? 'var(--up-bg)' : 'var(--down-bg)') : 'transparent';
  const borderColor = pct !== undefined ? (isUp ? 'var(--up-border)' : 'var(--down-border)') : 'var(--border)';

  const displayValue = value !== undefined
    ? (typeof value === 'number' ? (formatValue || defaultFormat)(value) : value)
    : '—';

  return (
    <div style={{
      background: 'var(--card-bg)',
      border: `1px solid ${borderColor}`,
      borderRadius: 12,
      padding: '16px',
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)', fontWeight: 500 }}>{label}</span>
        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          {isLive && (
            <span style={{
              width: 6, height: 6, borderRadius: '50%',
              background: 'var(--up)',
              boxShadow: '0 0 6px var(--up)',
              display: 'inline-block',
            }} />
          )}
          {badgeText && (
            <span style={{
              fontSize: 10, fontWeight: 600, padding: '2px 6px',
              borderRadius: 4, background: 'rgba(59,130,246,.15)',
              color: '#93c5fd', border: '1px solid rgba(59,130,246,.25)',
            }}>{badgeText}</span>
          )}
        </div>
      </div>

      <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-1)' }}>
        {displayValue}
      </div>

      {pct !== undefined && (
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: 4,
          padding: '3px 8px', borderRadius: 6,
          background: bgColor, border: `1px solid ${borderColor}`,
          fontSize: 12, fontWeight: 600, color, width: 'fit-content',
        }}>
          {isUp ? '▲' : '▼'} {Math.abs(pct).toFixed(2)}%
        </div>
      )}
    </div>
  );
}
