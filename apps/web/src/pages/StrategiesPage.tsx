import { useCallback, useMemo, useState } from 'react';
import { ConsoleActionBar } from '../components/ConsoleActionBar';
import { toggleStrategyEnabled } from '../api/domain';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import type { ConsoleSnapshot } from '../types/consoleView';
import { formatDateTime, formatPercent } from '../utils/format';

interface StrategiesPageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
}

export function StrategiesPage({ snapshot, loading, errorMessage, onRefresh }: StrategiesPageProps) {
  const { entries, push, clear } = useConsoleLogs();
  const [pendingId, setPendingId] = useState('');
  const items = snapshot.strategies.items || [];
  const summary = snapshot.strategies.summary || {};

  const statusItems = useMemo(() => ([
    { label: '전체 전략', value: `${summary.total || items.length}개`, tone: 'neutral' as const },
    { label: '활성 전략', value: `${summary.enabled || 0}개`, tone: (summary.enabled || 0) > 0 ? 'good' as const : 'neutral' as const },
    { label: '승인됨', value: `${summary.counts?.approved || 0}개`, tone: 'good' as const },
    { label: '중지/대기', value: `${(summary.counts?.paused || 0) + (summary.counts?.testing || 0)}개`, tone: 'bad' as const },
  ]), [items.length, summary]);

  const handleRefresh = useCallback(() => {
    onRefresh();
    push('info', '전략 레지스트리를 다시 불러왔습니다.', undefined, 'engine');
  }, [onRefresh, push]);

  const handleToggle = useCallback(async (strategyId: string, enabled: boolean) => {
    setPendingId(strategyId);
    try {
      const response = await toggleStrategyEnabled(strategyId, enabled);
      if (!response.ok) {
        push('error', '전략 상태를 변경하지 못했습니다.', '', 'engine');
        return;
      }
      push('success', `전략 ${strategyId} 상태를 ${enabled ? '활성' : '비활성'}로 변경했습니다.`, undefined, 'engine');
      onRefresh();
    } finally {
      setPendingId('');
    }
  }, [onRefresh, push]);

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell strategies-shell" style={{ display: 'grid', gap: 16 }}>
          <ConsoleActionBar
            title="전략 관리"
            subtitle="실시간 엔진은 승인된 Strategy Registry만 읽습니다. approval status, enable 상태, universe rule, scan cycle을 여기서 분리해서 관리합니다."
            lastUpdated={snapshot.fetchedAt}
            loading={loading}
            errorMessage={errorMessage}
            statusItems={statusItems}
            onRefresh={handleRefresh}
            logs={entries}
            onClearLogs={clear}
            settingsPanel={(
              <div style={{ display: 'grid', gap: 8, fontSize: 12, color: 'var(--text-3)' }}>
                <div>실시간 경로는 backtest/validation 결과 파일을 직접 읽지 않습니다.</div>
                <div>승인 상태가 `approved`이고 `enabled=true`인 전략만 라이브 스캐너에 진입합니다.</div>
                <div>토글 변경은 다음 스캔 사이클부터 즉시 반영됩니다.</div>
              </div>
            )}
          />

          <div className="page-section strategies-registry-shell" style={{ padding: 0 }}>
            <div className="responsive-table-desktop" style={{ overflow: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1100 }}>
                <thead>
                  <tr style={{ background: 'var(--bg-soft)', textAlign: 'left' }}>
                    <th style={{ padding: 12, fontSize: 12 }}>전략</th>
                    <th style={{ padding: 12, fontSize: 12 }}>상태</th>
                    <th style={{ padding: 12, fontSize: 12 }}>시장</th>
                    <th style={{ padding: 12, fontSize: 12 }}>유니버스</th>
                    <th style={{ padding: 12, fontSize: 12 }}>스캔 주기</th>
                    <th style={{ padding: 12, fontSize: 12 }}>연구 성과</th>
                    <th style={{ padding: 12, fontSize: 12 }}>최근 승인</th>
                    <th style={{ padding: 12, fontSize: 12 }}>액션</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => {
                    const research = item.research_summary || {};
                    const strategyId = String(item.strategy_id || '');
                    const enabled = Boolean(item.enabled);
                    return (
                      <tr key={strategyId} style={{ borderTop: '1px solid var(--border)' }}>
                        <td style={{ padding: 12, verticalAlign: 'top' }}>
                          <div style={{ fontWeight: 700 }}>{item.name || strategyId}</div>
                          <div className="signal-cell-copy">{strategyId} · v{item.version || 1}</div>
                        </td>
                        <td style={{ padding: 12, verticalAlign: 'top' }}>
                          <div>{item.approval_status || '-'}</div>
                          <div className={`inline-badge ${enabled ? 'is-success' : 'is-danger'}`} style={{ marginTop: 6 }}>{enabled ? 'enabled' : 'disabled'}</div>
                        </td>
                        <td style={{ padding: 12, verticalAlign: 'top' }}>{item.market || '-'}</td>
                        <td style={{ padding: 12, verticalAlign: 'top' }}>{item.universe_rule || '-'}</td>
                        <td style={{ padding: 12, verticalAlign: 'top' }}>{item.scan_cycle || '-'}</td>
                        <td style={{ padding: 12, verticalAlign: 'top' }}>
                          <div>수익률 {formatPercent(research.backtest_return_pct, 1, true)}</div>
                          <div className="signal-cell-copy">WF {formatPercent(research.walk_forward_return_pct, 1, true)} · Sharpe {research.sharpe ?? '-'}</div>
                        </td>
                        <td style={{ padding: 12, verticalAlign: 'top' }}>{formatDateTime(item.approved_at)}</td>
                        <td style={{ padding: 12, verticalAlign: 'top' }}>
                          <button
                            className="ghost-button"
                            onClick={() => handleToggle(strategyId, !enabled)}
                            disabled={!strategyId || pendingId === strategyId}
                          >
                            {pendingId === strategyId ? '처리 중...' : enabled ? '비활성화' : '활성화'}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                  {items.length === 0 && (
                    <tr>
                      <td colSpan={8} style={{ padding: 14, fontSize: 12, color: 'var(--text-4)' }}>표시할 전략이 없습니다.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="responsive-card-list">
              {items.map((item) => {
                const research = item.research_summary || {};
                const strategyId = String(item.strategy_id || '');
                const enabled = Boolean(item.enabled);
                return (
                  <article key={`${strategyId}-card`} className="responsive-card">
                    <div className="responsive-card-head">
                      <div>
                        <div className="responsive-card-title">{item.name || strategyId}</div>
                        <div className="signal-cell-copy">{strategyId} · v{item.version || 1}</div>
                      </div>
                      <div className={`inline-badge ${enabled ? 'is-success' : 'is-danger'}`}>{enabled ? 'enabled' : 'disabled'}</div>
                    </div>
                    <div className="responsive-card-grid">
                      <div><div className="responsive-card-label">상태</div><div className="responsive-card-value">{item.approval_status || '-'}</div></div>
                      <div><div className="responsive-card-label">시장</div><div className="responsive-card-value">{item.market || '-'}</div></div>
                      <div><div className="responsive-card-label">유니버스</div><div className="responsive-card-value">{item.universe_rule || '-'}</div></div>
                      <div><div className="responsive-card-label">스캔 주기</div><div className="responsive-card-value">{item.scan_cycle || '-'}</div></div>
                      <div><div className="responsive-card-label">연구 성과</div><div className="responsive-card-value">수익률 {formatPercent(research.backtest_return_pct, 1, true)} · WF {formatPercent(research.walk_forward_return_pct, 1, true)}</div></div>
                      <div><div className="responsive-card-label">최근 승인</div><div className="responsive-card-value">{formatDateTime(item.approved_at)}</div></div>
                    </div>
                    <button
                      className="ghost-button"
                      onClick={() => handleToggle(strategyId, !enabled)}
                      disabled={!strategyId || pendingId === strategyId}
                    >
                      {pendingId === strategyId ? '처리 중...' : enabled ? '비활성화' : '활성화'}
                    </button>
                  </article>
                );
              })}
              {items.length === 0 && <div style={{ padding: 14, fontSize: 12, color: 'var(--text-4)' }}>표시할 전략이 없습니다.</div>}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
