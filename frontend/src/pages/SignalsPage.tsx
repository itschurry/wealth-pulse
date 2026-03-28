import { useEffect, useMemo, useState } from 'react';
import { fetchSignals } from '../api/domain';
import type { DomainSignal, SignalsRankResponse } from '../types/domain';

export function SignalsPage() {
  const [data, setData] = useState<SignalsRankResponse>({});
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('loading');

  async function refresh() {
    setStatus('loading');
    try {
      const payload = await fetchSignals(120);
      setData(payload);
      setStatus('idle');
    } catch {
      setStatus('error');
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const topSignals = useMemo(() => (data.signals || []).slice(0, 40), [data.signals]);

  function formatEv(signal: DomainSignal) {
    const ev = signal.ev_metrics?.expected_value;
    return typeof ev === 'number' ? ev.toFixed(2) : '-';
  }

  function formatProb(signal: DomainSignal) {
    const prob = signal.ev_metrics?.win_probability;
    return typeof prob === 'number' ? `${(prob * 100).toFixed(1)}%` : '-';
  }

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell" style={{ display: 'grid', gap: 16 }}>
          <div className="page-section" style={{ padding: 18, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: 22, fontWeight: 800 }}>Signals (EV Rank)</div>
              <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 6 }}>
                Regime {data.regime || '-'} · Risk {data.risk_level || '-'} · Count {data.count ?? 0}
              </div>
            </div>
            <button className="ghost-button" onClick={() => void refresh()}>Refresh</button>
          </div>

          <div className="page-section" style={{ padding: 0, overflow: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: 'var(--bg-soft)', textAlign: 'left' }}>
                  <th style={{ padding: 12, fontSize: 12 }}>Code</th>
                  <th style={{ padding: 12, fontSize: 12 }}>Strategy</th>
                  <th style={{ padding: 12, fontSize: 12 }}>EV</th>
                  <th style={{ padding: 12, fontSize: 12 }}>Win%</th>
                  <th style={{ padding: 12, fontSize: 12 }}>Size</th>
                  <th style={{ padding: 12, fontSize: 12 }}>Blocked Reason</th>
                </tr>
              </thead>
              <tbody>
                {topSignals.map((signal) => (
                  <tr key={`${signal.market || ''}:${signal.code || ''}`} style={{ borderTop: '1px solid var(--border)' }}>
                    <td style={{ padding: 12, fontSize: 12 }}>{signal.code || '-'}</td>
                    <td style={{ padding: 12, fontSize: 12 }}>{signal.strategy_type || '-'}</td>
                    <td style={{ padding: 12, fontSize: 12, fontWeight: 700 }}>{formatEv(signal)}</td>
                    <td style={{ padding: 12, fontSize: 12 }}>{formatProb(signal)}</td>
                    <td style={{ padding: 12, fontSize: 12 }}>{signal.size_recommendation?.quantity ?? 0}</td>
                    <td style={{ padding: 12, fontSize: 12, color: signal.entry_allowed ? 'var(--up)' : 'var(--down)' }}>
                      {signal.entry_allowed ? 'allowed' : (signal.reason_codes || []).join(', ') || 'blocked'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {status === 'error' && <div style={{ color: 'var(--down)', fontSize: 12 }}>failed to load signals</div>}
        </div>
      </div>
    </div>
  );
}
