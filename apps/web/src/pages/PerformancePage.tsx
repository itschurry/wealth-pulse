import { useCallback, useMemo } from 'react';
import { ConsoleActionBar } from '../components/ConsoleActionBar';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import type { ConsoleSnapshot } from '../types/consoleView';
import { formatKRW, formatPercent } from '../utils/format';

interface PerformancePageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
}

export function PerformancePage({ snapshot, loading, errorMessage, onRefresh }: PerformancePageProps) {
  const { entries, push, clear } = useConsoleLogs();
  const research = snapshot.performance.research || [];
  const live = snapshot.performance.live || {};

  const statusItems = useMemo(() => ([
    { label: '오늘 신호', value: `${live.today_signal_count || 0}건`, tone: 'neutral' as const },
    { label: '오늘 주문', value: `${live.today_order_count || 0}건`, tone: 'good' as const },
    { label: '주문 거절', value: `${live.today_reject_count || 0}건`, tone: (live.today_reject_count || 0) > 0 ? 'bad' as const : 'neutral' as const },
    { label: '사전 차단', value: `${live.today_screened_block_count || 0}건`, tone: (live.today_screened_block_count || 0) > 0 ? 'neutral' as const : 'neutral' as const },
    { label: '실현 손익', value: formatKRW(live.realized_pnl_krw, true), tone: Number(live.realized_pnl_krw || 0) >= 0 ? 'good' as const : 'bad' as const },
  ]), [live]);

  const handleRefresh = useCallback(() => {
    onRefresh();
    push('info', '연구/운용 성과 요약을 다시 불러왔습니다.', undefined, 'refresh');
  }, [onRefresh, push]);

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell console-page-shell performance-shell" style={{ display: 'grid', gap: 16 }}>
          <ConsoleActionBar
            title="성과"
            subtitle="연구 성과와 장중 운용 성과를 같은 카드에 섞지 않고 분리해서 보여줍니다. 전략 승인 판단과 오늘 운용 상태를 구분해서 봅니다."
            lastUpdated={snapshot.fetchedAt}
            loading={loading}
            errorMessage={errorMessage}
            statusItems={statusItems}
            onRefresh={handleRefresh}
            logs={entries}
            onClearLogs={clear}
          />

          <section className="page-section console-card-section" style={{ display: 'grid', gap: 12 }}>
            <div style={{ fontSize: 14, fontWeight: 700 }}>운용 성과</div>
            <div className="console-metric-grid">
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-4)' }}>오늘 신호 수</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{live.today_signal_count || 0}건</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-4)' }}>오늘 주문 수</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{live.today_order_count || 0}건</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-4)' }}>주문 거절 수</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{live.today_reject_count || 0}건</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-4)' }}>사전 차단 수</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{live.today_screened_block_count || 0}건</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-4)' }}>실현 손익</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{formatKRW(live.realized_pnl_krw, true)}</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-4)' }}>미실현 손익</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{formatKRW(live.unrealized_pnl_krw, true)}</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-4)' }}>오픈 포지션</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{live.positions || 0}건</div>
              </div>
            </div>
          </section>

          <section className="page-section console-data-section" style={{ padding: 0 }}>
            <div style={{ padding: 16, fontSize: 14, fontWeight: 700 }}>연구 성과</div>
            <div className="responsive-table-desktop" style={{ overflow: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 900 }}>
                <thead>
                  <tr style={{ background: 'var(--bg-soft)', textAlign: 'left' }}>
                    <th style={{ padding: 12, fontSize: 12 }}>전략</th>
                    <th style={{ padding: 12, fontSize: 12 }}>상태</th>
                    <th style={{ padding: 12, fontSize: 12 }}>백테스트</th>
                    <th style={{ padding: 12, fontSize: 12 }}>워크포워드</th>
                    <th style={{ padding: 12, fontSize: 12 }}>MDD</th>
                    <th style={{ padding: 12, fontSize: 12 }}>승률</th>
                    <th style={{ padding: 12, fontSize: 12 }}>Sharpe</th>
                  </tr>
                </thead>
                <tbody>
                  {research.map((item) => (
                    <tr key={item.strategy_id} style={{ borderTop: '1px solid var(--border)' }}>
                      <td style={{ padding: 12, fontSize: 12 }}>
                        <div style={{ fontWeight: 700 }}>{item.name || item.strategy_id}</div>
                        <div className="signal-cell-copy">{item.strategy_kind || item.strategy_id}</div>
                      </td>
                      <td style={{ padding: 12, fontSize: 12 }}>{item.approval_status || '-'}</td>
                      <td style={{ padding: 12, fontSize: 12 }}>{formatPercent(item.backtest_return_pct, 1, true)}</td>
                      <td style={{ padding: 12, fontSize: 12 }}>{formatPercent(item.walk_forward_return_pct, 1, true)}</td>
                      <td style={{ padding: 12, fontSize: 12 }}>{formatPercent(item.max_drawdown_pct, 1, true)}</td>
                      <td style={{ padding: 12, fontSize: 12 }}>{formatPercent(item.win_rate_pct, 1, true)}</td>
                      <td style={{ padding: 12, fontSize: 12 }}>{item.sharpe ?? '-'}</td>
                    </tr>
                  ))}
                  {research.length === 0 && (
                    <tr>
                      <td colSpan={7} style={{ padding: 14, fontSize: 12, color: 'var(--text-4)' }}>표시할 연구 성과가 없습니다.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="responsive-card-list">
              {research.map((item) => (
                <article key={`${item.strategy_id}-card`} className="responsive-card">
                  <div className="responsive-card-head">
                    <div>
                      <div className="responsive-card-title">{item.name || item.strategy_id}</div>
                      <div className="signal-cell-copy">{item.strategy_kind || item.strategy_id}</div>
                    </div>
                    <div className="inline-badge">{item.approval_status || '-'}</div>
                  </div>
                  <div className="responsive-card-grid">
                    <div><div className="responsive-card-label">백테스트</div><div className="responsive-card-value">{formatPercent(item.backtest_return_pct, 1, true)}</div></div>
                    <div><div className="responsive-card-label">워크포워드</div><div className="responsive-card-value">{formatPercent(item.walk_forward_return_pct, 1, true)}</div></div>
                    <div><div className="responsive-card-label">MDD</div><div className="responsive-card-value">{formatPercent(item.max_drawdown_pct, 1, true)}</div></div>
                    <div><div className="responsive-card-label">승률</div><div className="responsive-card-value">{formatPercent(item.win_rate_pct, 1, true)}</div></div>
                    <div><div className="responsive-card-label">Sharpe</div><div className="responsive-card-value">{item.sharpe ?? '-'}</div></div>
                  </div>
                </article>
              ))}
              {research.length === 0 && <div style={{ padding: 14, fontSize: 12, color: 'var(--text-4)' }}>표시할 연구 성과가 없습니다.</div>}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
