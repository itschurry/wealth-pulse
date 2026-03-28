import { useEffect, useMemo, useState } from 'react';
import { fetchPortfolioState } from '../api/domain';
import type { PortfolioStateResponse } from '../types/domain';

export function PaperPortfolioPage() {
  const [data, setData] = useState<PortfolioStateResponse>({});
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('loading');

  async function refresh() {
    setStatus('loading');
    try {
      const payload = await fetchPortfolioState(true);
      setData(payload);
      setStatus('idle');
    } catch {
      setStatus('error');
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const positions = useMemo(() => (data.account?.positions || []) as Array<Record<string, unknown>>, [data.account?.positions]);

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell" style={{ display: 'grid', gap: 16 }}>
          <div className="page-section" style={{ padding: 18, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: 22, fontWeight: 800 }}>Paper Portfolio</div>
              <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 6 }}>
                Regime {data.regime || '-'} · Risk {data.risk_level || '-'}
              </div>
            </div>
            <button className="ghost-button" onClick={() => void refresh()}>Refresh</button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
            <div className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>Equity (KRW)</div>
              <div style={{ marginTop: 8, fontSize: 20, fontWeight: 800 }}>{data.account?.equity_krw ?? '-'}</div>
            </div>
            <div className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>Risk Guard</div>
              <div style={{ marginTop: 8, fontSize: 20, fontWeight: 800, color: data.risk_guard_state?.entry_allowed ? 'var(--up)' : 'var(--down)' }}>
                {data.risk_guard_state?.entry_allowed ? 'ACTIVE' : 'BLOCKED'}
              </div>
              <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-4)' }}>
                {data.risk_guard_state?.reasons?.join(', ') || 'none'}
              </div>
            </div>
          </div>

          <div className="page-section" style={{ padding: 16 }}>
            <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 10 }}>Positions</div>
            <div style={{ display: 'grid', gap: 8 }}>
              {positions.length === 0 && <div style={{ fontSize: 12, color: 'var(--text-4)' }}>No positions</div>}
              {positions.map((position) => (
                <div
                  key={`${String(position.market || '')}:${String(position.code || '')}`}
                  style={{ border: '1px solid var(--border)', borderRadius: 12, padding: 10, fontSize: 12 }}
                >
                  <div style={{ fontWeight: 700 }}>{String(position.name || position.code || '-')}</div>
                  <div style={{ color: 'var(--text-4)', marginTop: 4 }}>
                    {String(position.market || '-')} · qty {String(position.quantity || 0)} · stop {String(position.stop_loss_pct || '-')}% · take {String(position.take_profit_pct || '-')}%
                  </div>
                </div>
              ))}
            </div>
          </div>

          {status === 'error' && <div style={{ color: 'var(--down)', fontSize: 12 }}>failed to load portfolio</div>}
        </div>
      </div>
    </div>
  );
}
