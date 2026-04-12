import { useCallback, useMemo, useState } from 'react';
import { ConsoleActionBar } from '../components/ConsoleActionBar';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import type { ConsoleSnapshot } from '../types/consoleView';
import { formatDateTime, formatKRW, formatLocalAmountWithKRW, formatNumber, formatPercent, formatUSD, formatUSDWithKRW } from '../utils/format';

interface PerformancePageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
}

type MarketView = 'ALL' | 'KOSPI' | 'NASDAQ';

function normalizeMarketView(value: string | undefined): Exclude<MarketView, 'ALL'> {
  return String(value || '').toUpperCase() === 'KOSPI' ? 'KOSPI' : 'NASDAQ';
}

function currencyByMarket(market: string | undefined): 'KRW' | 'USD' {
  return normalizeMarketView(market) === 'KOSPI' ? 'KRW' : 'USD';
}

export function PerformancePage({ snapshot, loading, errorMessage, onRefresh }: PerformancePageProps) {
  const { entries, push, clear } = useConsoleLogs();
  const live = snapshot.performance.live || {};
  const history = live.filled_history || [];
  const [marketView, setMarketView] = useState<MarketView>('ALL');

  const totalReturn = live.total_return_pct;
  const returnTone = totalReturn == null
    ? 'neutral' as const
    : totalReturn >= 0 ? 'good' as const : 'bad' as const;

  const marketCounts = useMemo(() => {
    const counts: Record<MarketView, number> = { ALL: history.length, KOSPI: 0, NASDAQ: 0 };
    history.forEach((row) => {
      counts[normalizeMarketView(row.market)] += 1;
    });
    return counts;
  }, [history]);

  const filteredHistory = useMemo(() => {
    if (marketView === 'ALL') return history;
    return history.filter((row) => normalizeMarketView(row.market) === marketView);
  }, [history, marketView]);

  const statusItems = useMemo(() => ([
    { label: '오늘 신호', value: `${live.today_signal_count ?? 0}건`, tone: 'neutral' as const },
    { label: '오늘 주문', value: `${live.today_order_count ?? 0}건`, tone: 'neutral' as const },
    { label: '오늘 거절', value: `${live.today_reject_count ?? 0}건`, tone: (live.today_reject_count ?? 0) > 0 ? 'bad' as const : 'neutral' as const },
    { label: '사전 차단', value: `${live.today_screened_block_count ?? 0}건`, tone: 'neutral' as const },
    { label: '통합 수익률', value: totalReturn != null ? formatPercent(totalReturn, 2) : '-', tone: returnTone },
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
            subtitle="원화/달러를 따로 운용하는 계좌 구조를 반영해서 누적 성과도 분리해서 보도록 정리했습니다."
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
                <div className="section-title">통합 운용 성과</div>
                <div className="section-copy">원화와 달러를 따로 설정한 계좌라서, 이 값은 원화 환산 기준의 통합 결과야. 시작 자산도 KRW+USD 합산 기준으로 다시 잡았어.</div>
              </div>
              <div className="section-toolbar">
                <span className={`inline-badge ${totalReturn != null && totalReturn >= 0 ? 'is-success' : totalReturn != null ? 'is-danger' : ''}`}>통합 수익률 {totalReturn != null ? formatPercent(totalReturn, 2) : '-'}</span>
                <span className="inline-badge">환율 {live.fx_rate ? formatKRW(live.fx_rate) : '-'}</span>
              </div>
            </div>
            <div className="console-metric-grid">
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-4)' }}>시작 총자산(원화환산)</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{formatKRW(live.starting_equity_krw, true)}</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-4)' }}>현재 총자산(원화환산)</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{formatKRW(live.equity_krw, true)}</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-4)' }}>통합 수익률</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{totalReturn != null ? formatPercent(totalReturn, 2) : '-'}</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-4)' }}>총 체결</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{live.total_filled_count ?? 0}건</div>
              </div>
            </div>
          </section>

          <div className="console-metric-grid">
            <section className="page-section console-card-section" style={{ display: 'grid', gap: 12 }}>
              <div className="section-head-row">
                <div>
                  <div className="section-title">원화 계정 성과</div>
                  <div className="section-copy">한국장 기준 현금/평가금액/실현 손익을 따로 봐. 지금처럼 KRW와 USD를 같이 쓰는 계좌면 이 구분이 훨씬 덜 헷갈려.</div>
                </div>
                <div className="section-toolbar">
                  <span className="inline-badge">초기 {formatKRW(live.initial_cash_krw, true)}</span>
                </div>
              </div>
              <div className="console-metric-grid">
                <div>
                  <div style={{ fontSize: 12, color: 'var(--text-4)' }}>초기 자금</div>
                  <div style={{ marginTop: 6, fontWeight: 700 }}>{formatKRW(live.initial_cash_krw, true)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: 'var(--text-4)' }}>현재 현금</div>
                  <div style={{ marginTop: 6, fontWeight: 700 }}>{formatKRW(live.cash_krw, true)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: 'var(--text-4)' }}>보유 평가금액</div>
                  <div style={{ marginTop: 6, fontWeight: 700 }}>{formatKRW(live.market_value_krw_only, true)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: 'var(--text-4)' }}>실현 손익</div>
                  <div style={{ marginTop: 6, fontWeight: 700 }}>{formatKRW(live.realized_pnl_krw, true)}</div>
                </div>
              </div>
            </section>

            <section className="page-section console-card-section" style={{ display: 'grid', gap: 12 }}>
              <div className="section-head-row">
                <div>
                  <div className="section-title">달러 계정 성과</div>
                  <div className="section-copy">미국장은 달러 기준 수치가 먼저 보여야 두 번 계산 안 하게 돼. 괄호엔 원화 환산 금액을 같이 붙였어.</div>
                </div>
                <div className="section-toolbar">
                  <span className="inline-badge">초기 {formatUSD(live.initial_cash_usd, true)}</span>
                </div>
              </div>
              <div className="console-metric-grid">
                <div>
                  <div style={{ fontSize: 12, color: 'var(--text-4)' }}>초기 자금</div>
                  <div style={{ marginTop: 6, fontWeight: 700 }}>{formatUSDWithKRW(live.initial_cash_usd, live.initial_cash_usd && live.fx_rate ? live.initial_cash_usd * live.fx_rate : null)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: 'var(--text-4)' }}>현재 현금</div>
                  <div style={{ marginTop: 6, fontWeight: 700 }}>{formatUSDWithKRW(live.cash_usd, live.cash_usd && live.fx_rate ? live.cash_usd * live.fx_rate : null)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: 'var(--text-4)' }}>보유 평가금액</div>
                  <div style={{ marginTop: 6, fontWeight: 700 }}>{formatUSDWithKRW(live.market_value_usd, live.market_value_usd_krw)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: 'var(--text-4)' }}>실현 손익</div>
                  <div style={{ marginTop: 6, fontWeight: 700 }}>{formatUSDWithKRW(live.realized_pnl_usd, live.realized_pnl_usd && live.fx_rate ? live.realized_pnl_usd * live.fx_rate : null)}</div>
                </div>
              </div>
            </section>
          </div>

          <section className="page-section console-data-section" style={{ padding: 0 }}>
            <div style={{ padding: 16, display: 'grid', gap: 10 }}>
              <div className="section-head-row">
                <div>
                  <div className="section-title">체결 내역</div>
                  <div className="section-copy">성과 화면은 이제 통합 성과 + KRW/USD 분리 성과 + 체결 필터 순서로 읽으면 돼.</div>
                </div>
                <div className="section-filter-row">
                  {(['ALL', 'KOSPI', 'NASDAQ'] as const).map((view) => (
                    <button
                      key={view}
                      type="button"
                      className={marketView === view ? 'ghost-button is-active' : 'ghost-button'}
                      onClick={() => setMarketView(view)}
                    >
                      {view === 'ALL' ? `전체 ${marketCounts.ALL}건` : `${view} ${marketCounts[view]}건`}
                    </button>
                  ))}
                </div>
              </div>
              <div className="section-table-meta">
                미국장은 달러 기준 체결가를 먼저 보여주고, 괄호에 원화 환산 금액을 같이 붙였습니다.
              </div>
            </div>
            <div className="responsive-table-desktop" style={{ overflow: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 760 }}>
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
                  {filteredHistory.map((row, i) => {
                    const currency = row.currency === 'USD' || currencyByMarket(row.market) === 'USD' ? 'USD' : 'KRW';
                    return (
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
                        <td style={{ padding: 12, fontSize: 12 }}>{formatLocalAmountWithKRW(row.filled_price_local, row.filled_price_krw, currency)}</td>
                        <td style={{ padding: 12, fontSize: 12 }}>{formatLocalAmountWithKRW(row.notional_local, row.notional_krw, currency)}</td>
                      </tr>
                    );
                  })}
                  {filteredHistory.length === 0 && (
                    <tr>
                      <td colSpan={7} style={{ padding: 14, fontSize: 12, color: 'var(--text-4)' }}>
                        {marketView === 'ALL' ? '체결된 거래가 없습니다.' : `${marketView} 체결 내역이 없습니다.`}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="responsive-card-list">
              {filteredHistory.map((row, i) => {
                const currency = row.currency === 'USD' || currencyByMarket(row.market) === 'USD' ? 'USD' : 'KRW';
                return (
                  <article key={`${row.logged_at ?? ''}-${i}-card`} className="responsive-card">
                    <div className="responsive-card-head">
                      <div>
                        <div className="responsive-card-title">{row.code ?? '-'}</div>
                        <div className="signal-cell-copy">{row.market ?? '-'} · {formatDateTime(row.logged_at)}</div>
                      </div>
                      <span className={row.side === 'buy' ? 'inline-badge is-success' : 'inline-badge is-danger'}>{row.side === 'buy' ? '매수' : '매도'}</span>
                    </div>
                    <div className="responsive-card-grid">
                      <div><div className="responsive-card-label">수량</div><div className="responsive-card-value">{row.quantity != null ? formatNumber(row.quantity, 0) : '-'}주</div></div>
                      <div><div className="responsive-card-label">체결가</div><div className="responsive-card-value">{formatLocalAmountWithKRW(row.filled_price_local, row.filled_price_krw, currency)}</div></div>
                      <div><div className="responsive-card-label">금액</div><div className="responsive-card-value">{formatLocalAmountWithKRW(row.notional_local, row.notional_krw, currency)}</div></div>
                      <div><div className="responsive-card-label">시장</div><div className="responsive-card-value">{row.market ?? '-'}</div></div>
                    </div>
                  </article>
                );
              })}
              {filteredHistory.length === 0 && <div style={{ padding: 14, fontSize: 12, color: 'var(--text-4)' }}>{marketView === 'ALL' ? '체결된 거래가 없습니다.' : `${marketView} 체결 내역이 없습니다.`}</div>}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
