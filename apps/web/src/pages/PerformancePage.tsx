import { useCallback, useMemo, useState } from 'react';
import { ConsoleActionBar } from '../components/ConsoleActionBar';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import type { PerformanceSummaryResponse } from '../types/domain';
import type { ConsoleSnapshot } from '../types/consoleView';
import { formatDateTime, formatKRW, formatLocalAmountWithKRW, formatNumber, formatPercent, formatSymbol, formatUSD, formatUSDWithKRW } from '../utils/format';

interface PerformancePageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
}

type MarketView = 'ALL' | 'KOSPI' | 'NASDAQ';
type PerformanceHistoryRow = NonNullable<NonNullable<PerformanceSummaryResponse['live']>['order_history']>[number];

function normalizeMarketView(value: string | undefined): Exclude<MarketView, 'ALL'> {
  return String(value || '').toUpperCase() === 'KOSPI' ? 'KOSPI' : 'NASDAQ';
}

function currencyByMarket(market: string | undefined): 'KRW' | 'USD' {
  return normalizeMarketView(market) === 'KOSPI' ? 'KRW' : 'USD';
}

function statusTone(status: string | undefined) {
  if (status === 'filled' || status === 'partial_fill') return 'is-success';
  if (status === 'failed' || status === 'canceled') return 'is-danger';
  return '';
}

function formatHistoryQuantity(row: PerformanceHistoryRow) {
  if (row.quantity != null) return `${formatNumber(row.quantity, 0)}주`;
  return row.is_filled ? '미확인' : '체결 대기';
}

function formatHistoryAmount(row: PerformanceHistoryRow, currency: 'KRW' | 'USD', kind: 'price' | 'notional') {
  const local = kind === 'price' ? row.filled_price_local : row.notional_local;
  const krw = kind === 'price' ? row.filled_price_krw : row.notional_krw;
  if (local != null || krw != null) return formatLocalAmountWithKRW(local, krw, currency);
  return row.is_filled ? '미확인' : '체결 대기';
}

export function PerformancePage({ snapshot, loading, errorMessage, onRefresh }: PerformancePageProps) {
  const { entries, push, clear } = useConsoleLogs();
  const live = snapshot.performance.live || {};
  const history = live.order_history || live.filled_history || [];
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
    { label: '오늘 체결', value: `${live.today_filled_count ?? 0}건`, tone: 'neutral' as const },
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
            subtitle="주문 접수와 실제 체결을 분리해서 봐. 접수만 된 주문은 체결 성과에 섞지 않게 정리했어."
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
                <div className="section-copy">원화와 달러를 따로 설정한 계좌라서, 이 값은 원화 환산 기준의 통합 결과야. 시작 자산은 첫 실계좌 스냅샷 기준으로 고정했어.</div>
              </div>
              <div className="section-toolbar">
                <span className={`inline-badge ${totalReturn != null && totalReturn >= 0 ? 'is-success' : totalReturn != null ? 'is-danger' : ''}`}>통합 수익률 {totalReturn != null ? formatPercent(totalReturn, 2) : '-'}</span>
                <span className="inline-badge">환율 {live.fx_rate ? formatKRW(live.fx_rate) : '-'}</span>
              </div>
            </div>
            <div className="console-metric-grid">
              <div>
                <div style={{ fontSize: 15, color: 'var(--text-4)' }}>시작 총자산(원화환산)</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{formatKRW(live.starting_equity_krw, true)}</div>
              </div>
              <div>
                <div style={{ fontSize: 15, color: 'var(--text-4)' }}>현재 총자산(원화환산)</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{formatKRW(live.equity_krw, true)}</div>
              </div>
              <div>
                <div style={{ fontSize: 15, color: 'var(--text-4)' }}>통합 수익률</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{totalReturn != null ? formatPercent(totalReturn, 2) : '-'}</div>
              </div>
              <div>
                <div style={{ fontSize: 15, color: 'var(--text-4)' }}>누적 주문 / 체결</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{live.total_order_count ?? 0}건 / {live.total_filled_count ?? 0}건</div>
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
                  <div style={{ fontSize: 15, color: 'var(--text-4)' }}>초기 자금</div>
                  <div style={{ marginTop: 6, fontWeight: 700 }}>{formatKRW(live.initial_cash_krw, true)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 15, color: 'var(--text-4)' }}>현재 현금</div>
                  <div style={{ marginTop: 6, fontWeight: 700 }}>{formatKRW(live.cash_krw, true)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 15, color: 'var(--text-4)' }}>보유 평가금액</div>
                  <div style={{ marginTop: 6, fontWeight: 700 }}>{formatKRW(live.market_value_krw_only, true)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 15, color: 'var(--text-4)' }}>실현 손익</div>
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
                  <div style={{ fontSize: 15, color: 'var(--text-4)' }}>초기 자금</div>
                  <div style={{ marginTop: 6, fontWeight: 700 }}>{formatUSDWithKRW(live.initial_cash_usd, live.initial_cash_usd && live.fx_rate ? live.initial_cash_usd * live.fx_rate : null)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 15, color: 'var(--text-4)' }}>현재 현금</div>
                  <div style={{ marginTop: 6, fontWeight: 700 }}>{formatUSDWithKRW(live.cash_usd, live.cash_usd && live.fx_rate ? live.cash_usd * live.fx_rate : null)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 15, color: 'var(--text-4)' }}>보유 평가금액</div>
                  <div style={{ marginTop: 6, fontWeight: 700 }}>{formatUSDWithKRW(live.market_value_usd, live.market_value_usd_krw)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 15, color: 'var(--text-4)' }}>실현 손익</div>
                  <div style={{ marginTop: 6, fontWeight: 700 }}>{formatUSDWithKRW(live.realized_pnl_usd, live.realized_pnl_usd && live.fx_rate ? live.realized_pnl_usd * live.fx_rate : null)}</div>
                </div>
              </div>
            </section>
          </div>

          <section className="page-section console-data-section" style={{ padding: 0 }}>
            <div style={{ padding: 16, display: 'grid', gap: 10 }}>
              <div className="section-head-row">
                <div>
                  <div className="section-title">주문 / 체결 내역</div>
                  <div className="section-copy">체결 완료와 주문 접수를 분리해서 보여줘. 체결 전 단계면 수량/단가 대신 상태를 먼저 보면 돼.</div>
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
                접수만 된 주문은 체결 성과에서 제외했고, 체결 상세가 아직 없으면 `체결 대기` 또는 `미확인`으로 표시해.
              </div>
            </div>
            <div className="responsive-table-desktop" style={{ overflow: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 880 }}>
                <thead>
                  <tr style={{ background: 'var(--bg-soft)', textAlign: 'left' }}>
                    <th style={{ padding: 12, fontSize: 15 }}>일시</th>
                    <th style={{ padding: 12, fontSize: 15 }}>종목</th>
                    <th style={{ padding: 12, fontSize: 15 }}>시장</th>
                    <th style={{ padding: 12, fontSize: 15 }}>방향</th>
                    <th style={{ padding: 12, fontSize: 15 }}>상태</th>
                    <th style={{ padding: 12, fontSize: 15 }}>수량</th>
                    <th style={{ padding: 12, fontSize: 15 }}>체결가</th>
                    <th style={{ padding: 12, fontSize: 15 }}>금액</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredHistory.map((row, i) => {
                    const currency = row.currency === 'USD' || currencyByMarket(row.market) === 'USD' ? 'USD' : 'KRW';
                    return (
                      <tr key={`${row.logged_at ?? ''}-${row.order_id ?? ''}-${i}`} style={{ borderTop: '1px solid var(--border)' }}>
                        <td style={{ padding: 12, fontSize: 15 }}>{formatDateTime(row.logged_at)}</td>
                        <td style={{ padding: 12, fontSize: 15, fontWeight: 600 }}>{formatSymbol(row.code, row.name)}</td>
                        <td style={{ padding: 12, fontSize: 15 }}>{row.market ?? '-'}</td>
                        <td style={{ padding: 12, fontSize: 15 }}>
                          <span className={row.side === 'buy' ? 'inline-badge is-success' : 'inline-badge is-danger'}>
                            {row.side === 'buy' ? '매수' : '매도'}
                          </span>
                        </td>
                        <td style={{ padding: 12, fontSize: 15 }}>
                          <span className={`inline-badge ${statusTone(row.status)}`}>{row.status_label ?? '상태 미확인'}</span>
                        </td>
                        <td style={{ padding: 12, fontSize: 15 }}>{formatHistoryQuantity(row)}</td>
                        <td style={{ padding: 12, fontSize: 15 }}>{formatHistoryAmount(row, currency, 'price')}</td>
                        <td style={{ padding: 12, fontSize: 15 }}>{formatHistoryAmount(row, currency, 'notional')}</td>
                      </tr>
                    );
                  })}
                  {filteredHistory.length === 0 && (
                    <tr>
                      <td colSpan={8} style={{ padding: 14, fontSize: 15, color: 'var(--text-4)' }}>
                        {marketView === 'ALL' ? '주문/체결 내역이 없습니다.' : `${marketView} 주문/체결 내역이 없습니다.`}
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
                  <article key={`${row.logged_at ?? ''}-${row.order_id ?? ''}-${i}-card`} className="responsive-card">
                    <div className="responsive-card-head">
                      <div>
                        <div className="responsive-card-title">{formatSymbol(row.code, row.name)}</div>
                        <div className="signal-cell-copy">{row.market ?? '-'} · {formatDateTime(row.logged_at)}</div>
                      </div>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                        <span className={row.side === 'buy' ? 'inline-badge is-success' : 'inline-badge is-danger'}>{row.side === 'buy' ? '매수' : '매도'}</span>
                        <span className={`inline-badge ${statusTone(row.status)}`}>{row.status_label ?? '상태 미확인'}</span>
                      </div>
                    </div>
                    <div className="responsive-card-grid">
                      <div><div className="responsive-card-label">수량</div><div className="responsive-card-value">{formatHistoryQuantity(row)}</div></div>
                      <div><div className="responsive-card-label">체결가</div><div className="responsive-card-value">{formatHistoryAmount(row, currency, 'price')}</div></div>
                      <div><div className="responsive-card-label">금액</div><div className="responsive-card-value">{formatHistoryAmount(row, currency, 'notional')}</div></div>
                      <div><div className="responsive-card-label">시장</div><div className="responsive-card-value">{row.market ?? '-'}</div></div>
                    </div>
                  </article>
                );
              })}
              {filteredHistory.length === 0 && <div style={{ padding: 14, fontSize: 15, color: 'var(--text-4)' }}>{marketView === 'ALL' ? '주문/체결 내역이 없습니다.' : `${marketView} 주문/체결 내역이 없습니다.`}</div>}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
