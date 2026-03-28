import { useEffect, useState } from 'react';
import { fetchReportsExplain } from '../api/domain';
import type { ReportsExplainResponse } from '../types/domain';

export function ReportsPage() {
  const [data, setData] = useState<ReportsExplainResponse>({});
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('loading');

  async function refresh() {
    setStatus('loading');
    try {
      const payload = await fetchReportsExplain();
      setData(payload);
      setStatus('idle');
    } catch {
      setStatus('error');
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell" style={{ display: 'grid', gap: 16 }}>
          <div className="page-section" style={{ padding: 18, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: 22, fontWeight: 800 }}>Explainability Reports</div>
              <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 6 }}>Generated {data.generated_at || '-'}</div>
            </div>
            <button className="ghost-button" onClick={() => void refresh()}>Refresh</button>
          </div>

          <div className="page-section" style={{ padding: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 700 }}>Market Summary</div>
            <div style={{ marginTop: 8, fontSize: 13, color: 'var(--text-2)', lineHeight: 1.7 }}>
              {(data.analysis?.summary_lines || []).map((line, idx) => (
                <div key={idx}>- {line}</div>
              ))}
              {(data.analysis?.summary_lines || []).length === 0 && <div style={{ color: 'var(--text-4)' }}>No summary lines</div>}
            </div>
          </div>

          <div className="page-section" style={{ padding: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>Signal Reasoning (Top 30)</div>
            <div style={{ display: 'grid', gap: 8 }}>
              {(data.signal_reasoning || []).map((item, idx) => (
                <div key={`${item.code || 'NA'}-${idx}`} style={{ border: '1px solid var(--border)', borderRadius: 12, padding: 10, fontSize: 12 }}>
                  <div style={{ fontWeight: 700 }}>{item.code || '-'}</div>
                  <div style={{ marginTop: 4, color: 'var(--text-4)' }}>
                    {item.strategy_type || '-'} · {item.entry_allowed ? 'allowed' : 'blocked'}
                  </div>
                  {!item.entry_allowed && (
                    <div style={{ marginTop: 4, color: 'var(--down)' }}>{(item.reason_codes || []).join(', ')}</div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {status === 'error' && <div style={{ color: 'var(--down)', fontSize: 12 }}>failed to load report explainability</div>}
        </div>
      </div>
    </div>
  );
}
