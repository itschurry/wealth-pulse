import { useEffect, useState } from 'react';
import { fetchEngineStatus } from '../api/domain';
import type { EngineStatusResponse } from '../types/domain';

export function OverviewPage() {
  const [data, setData] = useState<EngineStatusResponse>({});
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('loading');

  async function refresh() {
    setStatus('loading');
    try {
      const payload = await fetchEngineStatus();
      setData(payload);
      setStatus('idle');
    } catch {
      setStatus('error');
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const allocator = data.allocator || {};
  const running = Boolean(data.execution?.state?.running);
  const guardOk = Boolean(data.risk_guard_state?.entry_allowed);

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell" style={{ display: 'grid', gap: 16 }}>
          <div className="page-section" style={{ padding: 18, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: 22, fontWeight: 800 }}>Engine Overview</div>
              <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 6 }}>
                Regime {allocator.regime || '-'} · Risk {allocator.risk_level || '-'}
              </div>
            </div>
            <button className="ghost-button" onClick={() => void refresh()}>Refresh</button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
            <div className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>Engine Status</div>
              <div style={{ marginTop: 8, fontSize: 20, fontWeight: 800, color: running ? 'var(--up)' : 'var(--down)' }}>
                {running ? 'RUNNING' : 'STOPPED'}
              </div>
            </div>
            <div className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>Entry Allowed</div>
              <div style={{ marginTop: 8, fontSize: 20, fontWeight: 800, color: guardOk ? 'var(--up)' : 'var(--down)' }}>
                {guardOk ? 'YES' : 'NO'}
              </div>
            </div>
            <div className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>Allowed Signals</div>
              <div style={{ marginTop: 8, fontSize: 20, fontWeight: 800 }}>{allocator.entry_allowed_count ?? 0}</div>
            </div>
            <div className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>Blocked Signals</div>
              <div style={{ marginTop: 8, fontSize: 20, fontWeight: 800 }}>{allocator.blocked_count ?? 0}</div>
            </div>
          </div>

          <div className="page-section" style={{ padding: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 700 }}>Risk Guard</div>
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-3)' }}>
              Daily Loss Left: {data.risk_guard_state?.daily_loss_left ?? '-'}
            </div>
            <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-3)' }}>
              Reasons: {(data.risk_guard_state?.reasons || []).join(', ') || 'none'}
            </div>
            {status === 'error' && <div style={{ marginTop: 8, color: 'var(--down)', fontSize: 12 }}>failed to load engine data</div>}
          </div>
        </div>
      </div>
    </div>
  );
}
