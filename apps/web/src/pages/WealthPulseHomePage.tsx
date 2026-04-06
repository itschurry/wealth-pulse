import { buildTodayReportView, buildWatchDecisionView } from '../adapters/consoleViewAdapter';
import { UI_TEXT } from '../constants/uiText';
import type { ConsoleSnapshot } from '../types/consoleView';
import { explainSizeRecommendation, formatDateTimeWithAge, formatKRW, formatNumber, formatPercent, formatSymbol, formatUSD } from '../utils/format';

interface WealthPulseHomePageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
  onGoConsole: () => void;
  onGoReports: () => void;
}

interface PositionView {
  key: string;
  symbol: string;
  market: string;
  quantity: number;
  marketValueKrw: number;
  unrealizedPnlKrw: number;
  unrealizedPnlPct: number | null;
}

function toNumber(value: unknown): number {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : 0;
}

function normalizePositionArray(raw: unknown): Array<Record<string, unknown>> {
  if (Array.isArray(raw)) return raw as Array<Record<string, unknown>>;
  if (raw && typeof raw === 'object') {
    return Object.values(raw as Record<string, unknown>)
      .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'));
  }
  return [];
}

function isUsMarket(raw: string): boolean {
  const market = raw.toUpperCase();
  return market === 'NASDAQ' || market === 'NYSE' || market === 'AMEX' || market === 'US';
}

function marketLabel(raw: string): 'KOSPI' | 'NASDAQ' | 'OTHER' {
  const market = raw.toUpperCase();
  if (market === 'KOSPI') return 'KOSPI';
  if (isUsMarket(market)) return 'NASDAQ';
  return 'OTHER';
}

function ratio(value: number, total: number): number {
  if (total <= 0) return 0;
  return Math.max(0, Math.min(1, value / total));
}

function ratioPercent(value: number, total: number): string {
  return `${(ratio(value, total) * 100).toFixed(1)}%`;
}

export function WealthPulseHomePage({
  snapshot,
  loading,
  errorMessage,
  onRefresh,
  onGoConsole,
  onGoReports,
}: WealthPulseHomePageProps) {
  const todayView = buildTodayReportView(snapshot);
  const watchView = buildWatchDecisionView(snapshot);
  const engineState = snapshot.engine.execution?.state || {};
  const engineAccount = snapshot.engine.execution?.account || {};
  const portfolioAccount = snapshot.portfolio.account || engineAccount || {};
  const rawPositions = normalizePositionArray(portfolioAccount.positions || engineAccount.positions);

  const positions: PositionView[] = rawPositions
    .map((raw, index) => {
      const market = String(raw.market || '-').toUpperCase();
      const quantity = toNumber(raw.quantity);
      const marketValueKrw = toNumber(raw.market_value_krw) || (toNumber(raw.last_price_krw) * quantity);
      const unrealizedPnlKrw = toNumber(raw.unrealized_pnl_krw);
      const unrealizedPnlPct = Number.isFinite(Number(raw.unrealized_pnl_pct)) ? Number(raw.unrealized_pnl_pct) : null;
      const code = String(raw.code || '');
      const name = String(raw.name || '');

      return {
        key: `${market}:${code}:${index}`,
        symbol: formatSymbol(code, name),
        market,
        quantity,
        marketValueKrw,
        unrealizedPnlKrw,
        unrealizedPnlPct,
      } satisfies PositionView;
    })
    .sort((left, right) => right.marketValueKrw - left.marketValueKrw);

  const totalMarketValueKrw = positions.reduce((sum, item) => sum + item.marketValueKrw, 0);
  const totalUnrealizedPnlKrw = positions.reduce((sum, item) => sum + item.unrealizedPnlKrw, 0);
  const totalEquityKrw = toNumber(portfolioAccount.equity_krw) || toNumber(engineState.current_equity) || toNumber(engineAccount.equity_krw);
  const cashKrw = toNumber(portfolioAccount.cash_krw) || toNumber(engineAccount.cash_krw);
  const cashUsd = toNumber(portfolioAccount.cash_usd) || toNumber(engineAccount.cash_usd);
  const todayRealizedPnlKrw = toNumber(engineState.today_realized_pnl);

  const kospiExposureKrw = positions
    .filter((item) => marketLabel(item.market) === 'KOSPI')
    .reduce((sum, item) => sum + item.marketValueKrw, 0);
  const nasdaqExposureKrw = positions
    .filter((item) => marketLabel(item.market) === 'NASDAQ')
    .reduce((sum, item) => sum + item.marketValueKrw, 0);

  const allocator = snapshot.engine.allocator || {};
  const signals = snapshot.signals.signals || [];
  const allowedSignals = signals.filter((item) => item.entry_allowed);
  const blockedSignals = signals.filter((item) => !item.entry_allowed);
  const totalAllowedSignals = Number(allocator.entry_allowed_count ?? allowedSignals.length);
  const totalBlockedSignals = Number(allocator.blocked_count ?? blockedSignals.length);
  const totalSignalCount = Math.max(0, totalAllowedSignals + totalBlockedSignals);
  const topSignals = [...allowedSignals]
    .sort((left, right) => toNumber(right.ev_metrics?.expected_value) - toNumber(left.ev_metrics?.expected_value))
    .slice(0, 5);

  const riskGuard = snapshot.engine.risk_guard_state || snapshot.portfolio.risk_guard_state || {};
  const riskGuardAllowed = Boolean(riskGuard.entry_allowed);
  const riskReasons = riskGuard.reasons || [];

  const liveMarket = snapshot.liveMarket || {};
  const marketCtx = snapshot.marketContext || {};

  function formatPct(value: number | undefined): string {
    if (value == null) return '-';
    const sign = value >= 0 ? '▲' : '▼';
    return `${sign}${Math.abs(value).toFixed(2)}%`;
  }
  function pctTone(value: number | undefined): string {
    if (value == null) return '';
    return value >= 0 ? 'is-up' : 'is-down';
  }

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell wealth-home-shell">
          <section className="page-section wealth-home-hero">
            <div className="wealth-home-hero-topline">
              <span className="inline-badge">WealthPulse</span>
              <span className="wealth-home-muted">KOSPI + NASDAQ</span>
              <span className="wealth-home-muted">기준 시각 {formatDateTimeWithAge(snapshot.fetchedAt)}</span>
            </div>
            <div className="wealth-home-hero-title">오늘 자산 흐름과 실행 포인트</div>
            <div className="wealth-home-hero-copy">포트폴리오 요약, 진입 가능 신호, 리스크 상태를 한 화면에서 확인합니다.</div>
            <div className="wealth-home-hero-actions">
              <button className="ghost-button" onClick={onRefresh}>데이터 새로고침</button>
              <button className="ghost-button" onClick={onGoConsole}>운영 콘솔 열기</button>
              <button className="ghost-button" onClick={onGoReports}>리포트 열기</button>
            </div>
            {!!errorMessage && <div className="wealth-home-error">{errorMessage}</div>}
          </section>

          <section className="page-section" style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'center', padding: '12px 16px' }}>
            {[
              { label: 'KOSPI', price: liveMarket.kospi, pct: liveMarket.kospi_pct },
              { label: 'KOSDAQ', price: liveMarket.kosdaq, pct: liveMarket.kosdaq_pct },
              { label: 'NASDAQ', price: liveMarket.nasdaq, pct: liveMarket.nasdaq_pct },
              { label: 'S&P100', price: liveMarket.sp100, pct: liveMarket.sp100_pct },
              { label: 'WTI', price: liveMarket.wti, pct: liveMarket.wti_pct },
            ].map((item) => (
              <div key={item.label} style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                <span style={{ fontSize: 11, color: 'var(--text-3)', fontWeight: 600 }}>{item.label}</span>
                <span style={{ fontSize: 13, fontWeight: 700 }}>{item.price != null ? formatNumber(item.price, 2) : '-'}</span>
                <span className={pctTone(item.pct)} style={{ fontSize: 12 }}>{formatPct(item.pct)}</span>
              </div>
            ))}
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
              <span style={{ fontSize: 11, color: 'var(--text-3)', fontWeight: 600 }}>USD/KRW</span>
              <span style={{ fontSize: 13, fontWeight: 700 }}>{liveMarket.usd_krw != null ? formatNumber(liveMarket.usd_krw, 0) : '-'}</span>
            </div>
            {liveMarket.updated_at && (
              <span className="wealth-home-muted" style={{ marginLeft: 'auto', fontSize: 11 }}>
                시세 {liveMarket.updated_at}
              </span>
            )}
          </section>

          <section className="wealth-kpi-grid">
            <article className="page-section wealth-kpi-card">
              <div className="wealth-kpi-label">포트폴리오 총액</div>
              <div className="wealth-kpi-value">{formatKRW(totalEquityKrw, true)}</div>
              <div className="wealth-kpi-copy">현금 KRW {formatKRW(cashKrw, true)} · USD {formatUSD(cashUsd, true)}</div>
            </article>
            <article className="page-section wealth-kpi-card">
              <div className="wealth-kpi-label">오늘 PnL</div>
              <div className={`wealth-kpi-value ${todayRealizedPnlKrw >= 0 ? 'is-up' : 'is-down'}`}>{formatKRW(todayRealizedPnlKrw, true)}</div>
              <div className="wealth-kpi-copy">평가손익 {formatKRW(totalUnrealizedPnlKrw, true)}</div>
            </article>
            <article className="page-section wealth-kpi-card">
              <div className="wealth-kpi-label">보유 포지션</div>
              <div className="wealth-kpi-value">{formatNumber(positions.length, 0)}개</div>
              <div className="wealth-kpi-copy">허용 신호 {formatNumber(totalAllowedSignals, 0)}건 · 차단 {formatNumber(totalBlockedSignals, 0)}건</div>
            </article>
          </section>

          <section className="wealth-grid-2">
            <article className="page-section">
              <div className="section-head-row">
                <div>
                  <div className="section-title">시장별 노출 비중</div>
                  <div className="section-copy">보유 포지션의 현재 평가금액(KRW 기준)으로 계산했습니다.</div>
                </div>
              </div>
              <div className="wealth-bars">
                <div className="wealth-bar-row">
                  <div className="wealth-bar-label">KOSPI</div>
                  <div className="wealth-bar-track"><div className="wealth-bar-fill is-kospi" style={{ width: ratioPercent(kospiExposureKrw, totalMarketValueKrw) }} /></div>
                  <div className="wealth-bar-value">{ratioPercent(kospiExposureKrw, totalMarketValueKrw)}</div>
                </div>
                <div className="wealth-bar-row">
                  <div className="wealth-bar-label">NASDAQ</div>
                  <div className="wealth-bar-track"><div className="wealth-bar-fill is-nasdaq" style={{ width: ratioPercent(nasdaqExposureKrw, totalMarketValueKrw) }} /></div>
                  <div className="wealth-bar-value">{ratioPercent(nasdaqExposureKrw, totalMarketValueKrw)}</div>
                </div>
              </div>
            </article>

            <article className="page-section">
              <div className="section-title">오늘 신호 요약</div>
              <div className="section-copy">진입 허용/차단 비율과 리스크 레벨을 함께 봅니다.</div>
              <div className="wealth-bars">
                <div className="wealth-bar-row">
                  <div className="wealth-bar-label">허용</div>
                  <div className="wealth-bar-track"><div className="wealth-bar-fill is-allowed" style={{ width: ratioPercent(totalAllowedSignals, totalSignalCount || 1) }} /></div>
                  <div className="wealth-bar-value">{formatNumber(totalAllowedSignals, 0)}건</div>
                </div>
                <div className="wealth-bar-row">
                  <div className="wealth-bar-label">차단</div>
                  <div className="wealth-bar-track"><div className="wealth-bar-fill is-blocked" style={{ width: ratioPercent(totalBlockedSignals, totalSignalCount || 1) }} /></div>
                  <div className="wealth-bar-value">{formatNumber(totalBlockedSignals, 0)}건</div>
                </div>
              </div>
              <div className="wealth-home-muted" style={{ marginTop: 12 }}>장세 {allocator.regime || snapshot.signals.regime || '-'} · 위험도 {allocator.risk_level || snapshot.signals.risk_level || '-'}</div>
            </article>
          </section>

          <section className="wealth-grid-2">
            <article className="page-section">
              <div className="section-title">오늘 액션 / 인사이트</div>
              <div className="wealth-list">
                {todayView.actionItems.slice(0, 3).map((item, index) => (
                  <div key={`action-${index}`} className="wealth-list-item">
                    <div className="wealth-list-title">{item.label}</div>
                    <div className="wealth-list-copy">{item.detail}</div>
                  </div>
                ))}
                {watchView.researchQueue.slice(0, 2).map((line, index) => (
                  <div key={`insight-${index}`} className="wealth-list-item">
                    <div className="wealth-list-title">인사이트 {index + 1}</div>
                    <div className="wealth-list-copy">{line}</div>
                  </div>
                ))}
              </div>
            </article>

            <article className="page-section">
              <div className="section-title">오늘 시그널 후보</div>
              <div className="wealth-position-list">
                {topSignals.map((signal, index) => (
                  <div key={`signal-${signal.market || ''}-${signal.code || ''}-${index}`} className="wealth-position-row">
                    <div>
                      <div className="wealth-position-symbol">{formatSymbol(signal.code, signal.name)}</div>
                      <div className="wealth-position-copy">{signal.market || '-'} · {signal.strategy_type || '-'}</div>
                    </div>
                    <div className="wealth-position-right">
                      <div className="wealth-position-symbol">EV {formatNumber(signal.ev_metrics?.expected_value, 2)}</div>
                      <div className="wealth-position-copy">{explainSizeRecommendation(signal.size_recommendation)}</div>
                    </div>
                  </div>
                ))}
                {topSignals.length === 0 && <div className="wealth-home-muted">{UI_TEXT.empty.signalsNoMatches}</div>}
              </div>
            </article>
          </section>

          <section className="wealth-grid-2">
            <article className="page-section">
              <div className="section-title">포지션 요약</div>
              <div className="wealth-position-list">
                {positions.slice(0, 6).map((position) => (
                  <div key={position.key} className="wealth-position-row">
                    <div>
                      <div className="wealth-position-symbol">{position.symbol}</div>
                      <div className="wealth-position-copy">{position.market} · {formatNumber(position.quantity, 0)}주</div>
                    </div>
                    <div className="wealth-position-right">
                      <div className="wealth-position-symbol">{formatKRW(position.marketValueKrw, true)}</div>
                      <div className={`wealth-position-copy ${position.unrealizedPnlKrw >= 0 ? 'is-up' : 'is-down'}`}>
                        {formatKRW(position.unrealizedPnlKrw, true)}
                        {position.unrealizedPnlPct === null ? '' : ` (${formatPercent(position.unrealizedPnlPct, 1)})`}
                      </div>
                    </div>
                  </div>
                ))}
                {positions.length === 0 && <div className="wealth-home-muted">{UI_TEXT.empty.noPositions}</div>}
              </div>
            </article>

            <article className="page-section">
              <div className="section-title">알림 / 리스크 상태</div>
              <div className="wealth-list">
                <div className="wealth-list-item">
                  <div className="wealth-list-title">리스크 가드</div>
                  <div className={`wealth-list-copy ${riskGuardAllowed ? 'is-up' : 'is-down'}`}>
                    {riskGuardAllowed ? '신규 진입 가능' : '신규 진입 제한'}
                  </div>
                  <div className="wealth-list-copy">{riskReasons.join(' · ') || '현재 차단 사유 없음'}</div>
                </div>
                <div className="wealth-list-item">
                  <div className="wealth-list-title">오늘의 모드</div>
                  <div className="wealth-list-copy">{watchView.mode} · {watchView.stanceTitle}</div>
                </div>
              </div>
            </article>
          </section>

          {(marketCtx.regime || marketCtx.summary) && (
            <section className="wealth-grid-2">
              <article className="page-section">
                <div className="section-title">시장 컨텍스트</div>
                <div className="detail-list" style={{ marginTop: 8 }}>
                  {marketCtx.regime && <div className="detail-row"><span className="detail-label">장세</span><span className="detail-value">{marketCtx.regime}</span></div>}
                  {marketCtx.risk_level && <div className="detail-row"><span className="detail-label">위험도</span><span className="detail-value">{marketCtx.risk_level}</span></div>}
                  {marketCtx.inflation_signal && <div className="detail-row"><span className="detail-label">인플레이션</span><span className="detail-value">{marketCtx.inflation_signal}</span></div>}
                  {marketCtx.policy_signal && <div className="detail-row"><span className="detail-label">정책</span><span className="detail-value">{marketCtx.policy_signal}</span></div>}
                  {marketCtx.dollar_signal && <div className="detail-row"><span className="detail-label">달러</span><span className="detail-value">{marketCtx.dollar_signal}</span></div>}
                </div>
              </article>
              {marketCtx.summary && (
                <article className="page-section">
                  <div className="section-title">시장 요약</div>
                  <div className="section-copy" style={{ marginTop: 8, lineHeight: 1.6 }}>{marketCtx.summary}</div>
                  {(marketCtx.risks || []).length > 0 && (
                    <div style={{ marginTop: 10 }}>
                      {(marketCtx.risks || []).map((risk, i) => (
                        <div key={i} className="wealth-list-copy" style={{ marginTop: 4 }}>· {risk}</div>
                      ))}
                    </div>
                  )}
                </article>
              )}
            </section>
          )}

          {loading && <div className="wealth-home-muted">{UI_TEXT.common.loading}</div>}
        </div>
      </div>
    </div>
  );
}
