import { useCallback, useMemo } from 'react';
import { ConsoleActionBar } from '../components/ConsoleActionBar';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import type { ConsoleSnapshot } from '../types/consoleView';
import { formatDateTime, formatKRW, formatNumber, formatPercent } from '../utils/format';

interface PerformancePageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
}

export function PerformancePage({ snapshot, loading, errorMessage, onRefresh }: PerformancePageProps) {
  const { entries, push, clear } = useConsoleLogs();
  const live = snapshot.performance.live || {};
  const history = live.filled_history || [];

  const totalReturn = live.total_return_pct;
  const returnTone = totalReturn == null
    ? 'neutral' as const
    : totalReturn >= 0 ? 'good' as const : 'bad' as const;

  const statusItems = useMemo(() => ([
    { label: '오늘 신호', value: `${live.today_signal_count ?? 0}건`, tone: 'neutral' as const },
    { label: '오늘 주문', value: `${live.today_order_count ?? 0}건`, tone: 'neutral' as const },
    { label: '오늘 거절', value: `${live.today_reject_count ?? 0}건`, tone: (live.today_reject_count ?? 0) > 0 ? 'bad' as const : 'neutral' as const },
    { label: '사전 차단', value: `${live.today_screened_block_count ?? 0}건`, tone: 'neutral' as const },
    { label: '총 수익률', value: totalReturn != null ? formatPercent(totalReturn, 2, true) : '-', tone: returnTone },
  ]), [live, returnTone, totalReturn]);

  const handleRefresh = useCallback(() => {
    onRefresh();
    push('info', '운용 성과를 다시 불러왔습니다.', undefined, 'refresh');
  }, [onRefresh, push]);

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell console-page-shell performance-shell" style={{ display: 'grid', gap: 16 }}>
          <ConsoleActionBar
            title="성과"
            subtitle="페이퍼 트레이딩 체결 내역을 기반으로 한 누적 운용 성과입니다. 전략 연구 성과(백테스트)는 전략 관리 탭에서 확인하세요."
            lastUpdated={snapshot.fetchedAt}
            loading={loading}
            errorMessage={errorMessage}
            statusItems={statusItems}
            onRefresh={handleRefresh}
            logs={entries}
            onClearLogs={clear}
          />

          <section className="page-section console-card-section" style={{ display: 'grid', gap: 12 }}>
            <div style={{ fontSize: 14, fontWeight: 700 }}>오늘 운용</div>
            <div className="console-metric-grid">
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-4)' }}>신호 수</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{live.today_signal_count ?? 0}건</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-4)' }}>주문 성공</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{live.today_order_count ?? 0}건</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-4)' }}>주문 거절</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{live.today_reject_count ?? 0}건</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-4)' }}>사전 차단</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{live.today_screened_block_count ?? 0}건</div>
              </div>
            </div>
          </section>

          <section className="page-section console-card-section" style={{ display: 'grid', gap: 12 }}>
            <div style={{ fontSize: 14, fontWeight: 700 }}>누적 운용 성과</div>
            <div className="console-metric-grid">
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-4)' }}>총 수익률</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{totalReturn != null ? formatPercent(totalReturn, 2, true) : '-'}</div>
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
                <div style={{ fontSize: 12, color: 'var(--text-4)' }}>초기 투자금</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{formatKRW(live.initial_cash_krw)}</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-4)' }}>총 체결</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{live.total_filled_count ?? 0}건</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-4)' }}>총 거절</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{live.total_reject_count ?? 0}건</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-4)' }}>사전 차단 누적</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{live.total_screened_count ?? 0}건</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-4)' }}>평균 체결 금액</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{live.avg_notional_krw != null ? formatKRW(live.avg_notional_krw) : '-'}</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-4)' }}>오픈 포지션</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{live.positions ?? 0}건</div>
              </div>
            </div>
          </section>

          <section className="page-section console-data-section" style={{ padding: 0 }}>
            <div style={{ padding: 16, fontSize: 14, fontWeight: 700 }}>체결 내역</div>
            <div className="responsive-table-desktop" style={{ overflow: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 640 }}>
                <thead>
                  <tr style={{ background: 'var(--bg-soft)', textAlign: 'left' }}>
                    <th style={{ padding: 12, fontSize: 12 }}>일시</th>
                    <th style={{ padding: 12, fontSize: 12 }}>종목</th>
                    <th style={{ padding: 12, fontSize: 12 }}>시장</th>
                    <th style={{ padding: 12, fontSize: 12 }}>방향</th>
                    <th style={{ padding: 12, fontSize: 12 }}>수량</th>
                    <th style={{ padding: 12, fontSize: 12 }}>체결가</th>
                    <th style={{ padding: 12, fontSize: 12 }}>금액</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((row, i) => (
                    <tr key={`${row.logged_at ?? ''}-${i}`} style={{ borderTop: '1px solid var(--border)' }}>
                      <td style={{ padding: 12, fontSize: 12 }}>{formatDateTime(row.logged_at)}</td>
                      <td style={{ padding: 12, fontSize: 12, fontWeight: 600 }}>{row.code ?? '-'}</td>
                      <td style={{ padding: 12, fontSize: 12 }}>{row.market ?? '-'}</td>
                      <td style={{ padding: 12, fontSize: 12 }}>
                        <span className={row.side === 'buy' ? 'inline-badge is-success' : 'inline-badge is-danger'}>
                          {row.side === 'buy' ? '매수' : '매도'}
                        </span>
                      </td>
                      <td style={{ padding: 12, fontSize: 12 }}>{row.quantity != null ? formatNumber(row.quantity, 0) : '-'}주</td>
                      <td style={{ padding: 12, fontSize: 12 }}>{row.filled_price_krw != null ? formatKRW(row.filled_price_krw) : '-'}</td>
                      <td style={{ padding: 12, fontSize: 12 }}>{row.notional_krw != null ? formatKRW(row.notional_krw) : '-'}</td>
                    </tr>
                  ))}
                  {history.length === 0 && (
                    <tr>
                      <td colSpan={7} style={{ padding: 14, fontSize: 12, color: 'var(--text-4)' }}>
                        체결된 거래가 없습니다.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
