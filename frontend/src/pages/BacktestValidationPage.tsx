import { useEffect, useState } from 'react';
import { fetchValidationBacktest, fetchValidationWalkForward } from '../api/domain';
import type { ValidationResponse } from '../types/domain';

export function BacktestValidationPage({ onBack }: { onBack: () => void }) {
  const [backtest, setBacktest] = useState<ValidationResponse>({});
  const [walkForward, setWalkForward] = useState<ValidationResponse>({});
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('loading');

  async function refresh() {
    setStatus('loading');
    try {
      const [backtestPayload, walkForwardPayload] = await Promise.all([
        fetchValidationBacktest(),
        fetchValidationWalkForward(),
      ]);
      setBacktest(backtestPayload);
      setWalkForward(walkForwardPayload);
      setStatus('idle');
    } catch {
      setStatus('error');
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const oos = walkForward.segments?.oos || {};

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell" style={{ display: 'grid', gap: 16 }}>
          <div className="page-section" style={{ padding: 18, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: 22, fontWeight: 800 }}>Backtest / Validation</div>
              <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 6 }}>
                OOS reliability {walkForward.summary?.oos_reliability || '-'}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="ghost-button" onClick={() => void refresh()}>Refresh</button>
              <button className="ghost-button" onClick={onBack}>Back</button>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
            <div className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>Backtest Return</div>
              <div style={{ marginTop: 8, fontSize: 20, fontWeight: 800 }}>
                {String((backtest.metrics || {})['total_return_pct'] ?? '-')}%
              </div>
            </div>
            <div className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>Backtest Profit Factor</div>
              <div style={{ marginTop: 8, fontSize: 20, fontWeight: 800 }}>
                {String((backtest.metrics || {})['profit_factor'] ?? '-')}
              </div>
            </div>
            <div className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>OOS Return</div>
              <div style={{ marginTop: 8, fontSize: 20, fontWeight: 800 }}>
                {String(oos.total_return_pct ?? '-')}%
              </div>
            </div>
            <div className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>OOS Profit Factor</div>
              <div style={{ marginTop: 8, fontSize: 20, fontWeight: 800 }}>
                {String(oos.profit_factor ?? '-')}
              </div>
            </div>
          </div>

          {status === 'error' && <div style={{ color: 'var(--down)', fontSize: 12 }}>failed to load validation data</div>}
        </div>
      </div>
    </div>
  );
}
