import { useCallback, useMemo } from 'react';
import { ConsoleActionBar } from '../components/ConsoleActionBar';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import type { ConsoleSnapshot } from '../types/consoleView';
import { formatKRW, formatPercent, formatUSDWithKRW } from '../utils/format';

interface PerformancePageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
}

export function PerformancePage({ snapshot, loading, errorMessage, onRefresh }: PerformancePageProps) {
  const { entries, push, clear } = useConsoleLogs();
  const live = snapshot.performance.live || {};

  const totalReturn = live.total_return_pct;
  const positionReturn = live.position_return_pct;
  const krwPositionReturn = live.position_return_pct_krw;
  const usdPositionReturn = live.position_return_pct_usd;
  const returnTone = totalReturn == null
    ? 'neutral' as const
    : totalReturn >= 0 ? 'good' as const : 'bad' as const;

  const statusItems = useMemo(() => ([
    { label: '오늘 신호', value: `${live.today_signal_count ?? 0}건`, tone: 'neutral' as const },
    { label: '오늘 주문', value: `${live.today_order_count ?? 0}건`, tone: 'neutral' as const },
    { label: '오늘 체결', value: `${live.today_filled_count ?? 0}건`, tone: 'neutral' as const },
    { label: '오늘 거절', value: `${live.today_reject_count ?? 0}건`, tone: (live.today_reject_count ?? 0) > 0 ? 'bad' as const : 'neutral' as const },
    { label: '사전 차단', value: `${live.today_screened_block_count ?? 0}건`, tone: 'neutral' as const },
    { label: '통합 수익률', value: totalReturn != null ? formatPercent(totalReturn, 2) : '-', tone: returnTone },
    { label: '보유 총 수익률', value: positionReturn != null ? formatPercent(positionReturn, 2) : '-', tone: positionReturn == null ? 'neutral' as const : positionReturn >= 0 ? 'good' as const : 'bad' as const },
  ]), [live, positionReturn, returnTone, totalReturn]);

  const handleRefresh = useCallback(() => {
    onRefresh();
    push('info', '성과 갱신', undefined, 'refresh');
  }, [onRefresh, push]);

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell console-page-shell performance-shell" style={{ display: 'grid', gap: 16 }}>
          <ConsoleActionBar
            title="성과"
            subtitle=""
            lastUpdated={snapshot.fetchedAt}
            loading={loading}
            errorMessage={errorMessage}
            statusItems={statusItems}
            onRefresh={handleRefresh}
            logs={entries}
            onClearLogs={clear}
          />

          <section className="page-section console-card-section" style={{ display: 'grid', gap: 12 }}>
            <div className="section-head-row">
              <div>
                <div className="section-title">통합</div>
                <div className="section-copy">원화와 달러를 따로 설정한 계좌라서, 이 값은 원화 환산 기준의 통합 결과야. 시작 자산은 첫 실계좌 스냅샷 기준으로 고정했어.</div>
              </div>
              <div className="section-toolbar">
                <span className={`inline-badge ${totalReturn != null && totalReturn >= 0 ? 'is-success' : totalReturn != null ? 'is-danger' : ''}`}>{totalReturn != null ? formatPercent(totalReturn, 2) : '-'}</span>
                <span className="inline-badge">환율 {live.fx_rate ? formatKRW(live.fx_rate) : '-'}</span>
              </div>
            </div>
            <div className="console-metric-grid">
              <div>
                <div style={{ fontSize: 15, color: 'var(--text-4)' }}>시작</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{formatKRW(live.starting_equity_krw, true)}</div>
              </div>
              <div>
                <div style={{ fontSize: 15, color: 'var(--text-4)' }}>현재</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{formatKRW(live.equity_krw, true)}</div>
              </div>
              <div>
                <div style={{ fontSize: 15, color: 'var(--text-4)' }}>수익률</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{totalReturn != null ? formatPercent(totalReturn, 2) : '-'}</div>
              </div>
              <div>
                <div style={{ fontSize: 15, color: 'var(--text-4)' }}>보유</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{positionReturn != null ? formatPercent(positionReturn, 2) : '-'}</div>
              </div>
              <div>
                <div style={{ fontSize: 15, color: 'var(--text-4)' }}>투자 / 평가</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{formatKRW(live.position_cost_krw, true)} / {formatKRW(live.position_market_value_krw, true)}</div>
              </div>
              <div>
                <div style={{ fontSize: 15, color: 'var(--text-4)' }}>주문 / 체결</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{live.total_order_count ?? 0}건 / {live.total_filled_count ?? 0}건</div>
              </div>
            </div>
          </section>

          <div className="console-metric-grid">
            <section className="page-section console-card-section" style={{ display: 'grid', gap: 12 }}>
              <div className="section-head-row">
                <div>
                  <div className="section-title">원화</div>
                  <div className="section-copy">한국장 보유 종목만 봐. 현금은 빼고 매입 투자금, 보유 평가금, 평가손익, 수익률만 보여줘.</div>
                </div>
                <div className="section-toolbar">
                  <span className={`inline-badge ${krwPositionReturn != null && krwPositionReturn >= 0 ? 'is-success' : krwPositionReturn != null ? 'is-danger' : ''}`}>수익률 {krwPositionReturn != null ? formatPercent(krwPositionReturn, 2) : '-'}</span>
                </div>
              </div>
              <div className="console-metric-grid">
                <div>
                  <div style={{ fontSize: 15, color: 'var(--text-4)' }}>투자금</div>
                  <div style={{ marginTop: 6, fontWeight: 700 }}>{formatKRW(live.position_cost_krw_only, true)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 15, color: 'var(--text-4)' }}>보유 평가금</div>
                  <div style={{ marginTop: 6, fontWeight: 700 }}>{formatKRW(live.position_market_value_krw_only, true)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 15, color: 'var(--text-4)' }}>평가손익</div>
                  <div style={{ marginTop: 6, fontWeight: 700 }}>{formatKRW(live.position_unrealized_pnl_krw_only, true)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 15, color: 'var(--text-4)' }}>수익률</div>
                  <div style={{ marginTop: 6, fontWeight: 700 }}>{krwPositionReturn != null ? formatPercent(krwPositionReturn, 2) : '-'}</div>
                </div>
              </div>
            </section>

            <section className="page-section console-card-section" style={{ display: 'grid', gap: 12 }}>
              <div className="section-head-row">
                <div>
                  <div className="section-title">달러</div>
                  <div className="section-copy">미국장 보유 종목만 봐. 달러 기준 투자금, 보유 평가금, 평가손익, 수익률이 핵심이야.</div>
                </div>
                <div className="section-toolbar">
                  <span className={`inline-badge ${usdPositionReturn != null && usdPositionReturn >= 0 ? 'is-success' : usdPositionReturn != null ? 'is-danger' : ''}`}>수익률 {usdPositionReturn != null ? formatPercent(usdPositionReturn, 2) : '-'}</span>
                </div>
              </div>
              <div className="console-metric-grid">
                <div>
                  <div style={{ fontSize: 15, color: 'var(--text-4)' }}>투자금</div>
                  <div style={{ marginTop: 6, fontWeight: 700 }}>{formatUSDWithKRW(live.position_cost_usd, live.position_cost_usd_krw)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 15, color: 'var(--text-4)' }}>보유 평가금</div>
                  <div style={{ marginTop: 6, fontWeight: 700 }}>{formatUSDWithKRW(live.position_market_value_usd, live.position_market_value_usd_krw)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 15, color: 'var(--text-4)' }}>평가손익</div>
                  <div style={{ marginTop: 6, fontWeight: 700 }}>{formatUSDWithKRW(live.position_unrealized_pnl_usd, live.position_unrealized_pnl_usd && live.fx_rate ? live.position_unrealized_pnl_usd * live.fx_rate : null)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 15, color: 'var(--text-4)' }}>수익률</div>
                  <div style={{ marginTop: 6, fontWeight: 700 }}>{usdPositionReturn != null ? formatPercent(usdPositionReturn, 2) : '-'}</div>
                </div>
              </div>
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}
