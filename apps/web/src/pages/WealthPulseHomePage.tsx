import {
  buildTodayReportView,
  buildWatchDecisionView,
  getRiskGuardState,
  isRiskBlockedSignal,
  isRiskEntryAllowed,
} from '../adapters/consoleViewAdapter';
import { UI_TEXT, reasonCodeToKorean, reliabilityToKorean, freshnessToKorean, providerSourceToKorean, providerStatusToKorean } from '../constants/uiText';
import type { ConsoleSnapshot } from '../types/consoleView';
import { explainSizeRecommendation, formatDateTime, formatDateTimeWithAge, formatKRW, formatNumber, formatSymbol, formatUSD } from '../utils/format';

interface WealthPulseHomePageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
  onGoLab: () => void;
  onGoAnalysis: () => void;
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

function sessionTone(status: string | undefined): string {
  if (status === 'open') return 'is-success';
  if (status === 'pre_open') return 'is-warning';
  if (status === 'after_close') return 'is-neutral';
  return 'is-danger';
}

function countLabel(value: number): string {
  return `${formatNumber(value, 0)}건`;
}

export function WealthPulseHomePage({
  snapshot,
  loading,
  errorMessage,
  onRefresh,
  onGoLab,
  onGoAnalysis,
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
  const blockedSignals = signals.filter(isRiskBlockedSignal);
  const totalAllowedSignals = Number(allocator.entry_allowed_count ?? allowedSignals.length);
  const totalBlockedSignals = Number(allocator.blocked_count ?? blockedSignals.length);
  const totalObserveSignals = Math.max(signals.length - totalAllowedSignals - totalBlockedSignals, 0);
  const totalSignalCount = Math.max(0, totalAllowedSignals + totalBlockedSignals + totalObserveSignals);
  const topSignals = [...allowedSignals]
    .sort((left, right) => toNumber(right.ev_metrics?.expected_value) - toNumber(left.ev_metrics?.expected_value))
    .slice(0, 5);

  const riskGuard = getRiskGuardState(snapshot);
  const riskGuardAllowed = isRiskEntryAllowed(snapshot);
  const riskReasons = Array.isArray(riskGuard.reasons) ? riskGuard.reasons.map((reason) => reasonCodeToKorean(String(reason))) : [];
  const validationSummary = snapshot.validation.summary || {};
  const reportGeneratedAt = todayView.generatedAt || snapshot.reports.generated_at || '';
  const todayActions = todayView.actionItems.slice(0, 2);
  const avoidActions = [...todayView.watchPoints, ...todayView.judgmentLines]
    .filter((line, index, arr) => line && arr.indexOf(line) === index)
    .slice(0, 3);
  const insightLines = [...todayView.judgmentLines, ...watchView.researchQueue]
    .filter((line, index, arr) => line && arr.indexOf(line) === index)
    .slice(0, 3);
  const failedOrders = Number(engineState.today_order_counts?.failed || 0);
  const skippedCount = Number((engineState.last_summary as { skipped_count?: number } | undefined)?.skipped_count || 0);
  const staleOptimized = Boolean(engineState.optimized_params?.is_stale);
  const validationGateEnabled = Boolean(engineState.validation_policy?.validation_gate_enabled);
  const validationReliability = reliabilityToKorean(String(validationSummary.oos_reliability || '').toLowerCase());
  const engineRunning = Boolean(engineState.running);
  const engineStatusLabel = engineRunning ? '실행 중' : engineState.engine_state === 'paused' ? '일시정지' : engineState.engine_state === 'error' ? '오류' : '중지';
  const riskAlertItems = [
    {
      key: 'engine',
      label: '엔진 상태',
      value: engineStatusLabel,
      detail: engineState.last_error || (engineRunning ? `다음 실행 ${formatDateTime(engineState.next_run_at || '')}` : '자동 실행 루프가 멈춰 있습니다.'),
      tone: engineRunning ? 'good' : 'bad',
    },
    {
      key: 'guard',
      label: '신규 진입',
      value: riskGuardAllowed ? '가능' : '제한',
      detail: riskReasons.join(' · ') || (riskGuardAllowed ? '현재 강한 차단 사유 없음' : '리스크 가드 사유 확인 필요'),
      tone: riskGuardAllowed ? 'good' : 'bad',
    },
    {
      key: 'orders',
      label: '실패/스킵',
      value: `${countLabel(failedOrders)} / ${countLabel(skippedCount)}`,
      detail: failedOrders > 0 || skippedCount > 0 ? '최근 주문 실패나 스킵 사유를 먼저 확인해.' : '최근 실행 이상 징후가 크지 않아.',
      tone: failedOrders > 0 || skippedCount > 0 ? 'bad' : 'good',
    },
    {
      key: 'validation',
      label: 'Validation Gate',
      value: validationGateEnabled ? '활성' : '비활성',
      detail: staleOptimized
        ? `최적화 지연 · OOS 신뢰도 ${validationReliability || '-'}`
        : `OOS 신뢰도 ${validationReliability || '-'} · 최소 거래 ${formatNumber(Number(engineState.validation_policy?.validation_min_trades || 0), 0)}건`,
      tone: staleOptimized || String(validationSummary.oos_reliability || '').toLowerCase() === 'low' ? 'bad' : 'good',
    },
  ];

  const liveMarket = snapshot.liveMarket || {};
  const marketCtx = snapshot.marketContext || {};
  const marketSessions = liveMarket.market_sessions || {};
  const sessionCards = [marketSessions.KR, marketSessions.US].filter(Boolean);
  const summaryItems = [
    {
      label: '포트폴리오 총액',
      value: formatKRW(totalEquityKrw, true),
      detail: `현금 KRW ${formatKRW(cashKrw, true)} · USD ${formatUSD(cashUsd, true)}`,
    },
    {
      label: '오늘 실현 손익',
      value: formatKRW(todayRealizedPnlKrw, true),
      detail: `현재 보유분 미실현 손익 ${formatKRW(totalUnrealizedPnlKrw, true)}`,
      tone: todayRealizedPnlKrw >= 0 ? 'is-up' : 'is-down',
    },
    {
      label: '보유 포지션',
      value: `${formatNumber(positions.length, 0)}개`,
      detail: `허용 ${formatNumber(totalAllowedSignals, 0)}건 · 차단 ${formatNumber(totalBlockedSignals, 0)}건 · 관찰 ${formatNumber(totalObserveSignals, 0)}건`,
    },
  ];
  const exposureRows = [
    { label: 'KOSPI', width: ratioPercent(kospiExposureKrw, totalMarketValueKrw), value: ratioPercent(kospiExposureKrw, totalMarketValueKrw), tone: 'is-kospi' },
    { label: 'NASDAQ', width: ratioPercent(nasdaqExposureKrw, totalMarketValueKrw), value: ratioPercent(nasdaqExposureKrw, totalMarketValueKrw), tone: 'is-nasdaq' },
  ];
  const signalRows = [
    { label: '허용', width: ratioPercent(totalAllowedSignals, totalSignalCount || 1), value: `${formatNumber(totalAllowedSignals, 0)}건`, tone: 'is-allowed' },
    { label: '차단', width: ratioPercent(totalBlockedSignals, totalSignalCount || 1), value: `${formatNumber(totalBlockedSignals, 0)}건`, tone: 'is-blocked' },
    { label: '관찰', width: ratioPercent(totalObserveSignals, totalSignalCount || 1), value: `${formatNumber(totalObserveSignals, 0)}건`, tone: '' },
  ];
  const noteItems = [
    { label: '상세 포지션 확인', detail: '포지션 상세 목록은 운영 개요에서 빼고 주문/체결 화면에서 보는 편이 더 정확해.' },
    { label: '리서치 입력 상태', detail: `${freshnessToKorean(String(snapshot.research.freshness || 'missing'))} · ${providerSourceToKorean(String(snapshot.research.source || snapshot.research.status || '-')) || providerStatusToKorean(String(snapshot.research.status || '-'))}` },
    { label: '최근 성공 시각', detail: formatDateTime(engineState.last_success_at || '') },
  ];
  const marketContextRows = [
    marketCtx.regime ? { label: '장세', value: marketCtx.regime } : null,
    marketCtx.risk_level ? { label: '위험도', value: marketCtx.risk_level } : null,
    marketCtx.inflation_signal ? { label: '인플레이션', value: marketCtx.inflation_signal } : null,
    marketCtx.policy_signal ? { label: '정책', value: marketCtx.policy_signal } : null,
    marketCtx.dollar_signal ? { label: '달러', value: marketCtx.dollar_signal } : null,
  ].filter(Boolean) as Array<{ label: string; value: string }>;

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
            <div className="wealth-home-hero-title">오늘 자산 흐름과 실행 판단</div>
            <div className="wealth-home-hero-copy">브리프 요약, 운영 리스크, 신호 상태를 운영 개요 한 화면에서 확인합니다.</div>
            <div className="wealth-home-hero-actions">
              <button className="ghost-button" onClick={onRefresh}>데이터 새로고침</button>
              <button className="ghost-button" onClick={onGoLab}>실험 모드 열기</button>
              <button className="ghost-button" onClick={onGoAnalysis}>후보 리서치 열기</button>
            </div>
            {!!errorMessage && <div className="wealth-home-error">{errorMessage}</div>}
          </section>

          <section className="page-section" style={{ display: 'grid', gap: 12, padding: '12px 16px' }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'center' }}>
              {[
                { label: 'KOSPI', price: liveMarket.kospi, pct: liveMarket.kospi_pct },
                { label: 'KOSDAQ', price: liveMarket.kosdaq, pct: liveMarket.kosdaq_pct },
                { label: 'NASDAQ', price: liveMarket.nasdaq, pct: liveMarket.nasdaq_pct },
                { label: 'S&P100', price: liveMarket.sp100, pct: liveMarket.sp100_pct },
                { label: 'WTI', price: liveMarket.wti, pct: liveMarket.wti_pct },
              ].map((item) => (
                <div key={item.label} style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                  <span style={{ fontSize: 14, color: 'var(--text-3)', fontWeight: 600 }}>{item.label}</span>
                  <span style={{ fontSize: 16, fontWeight: 700 }}>{item.price != null ? formatNumber(item.price, 2) : '-'}</span>
                  <span className={pctTone(item.pct)} style={{ fontSize: 15 }}>{formatPct(item.pct)}</span>
                </div>
              ))}
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                <span style={{ fontSize: 14, color: 'var(--text-3)', fontWeight: 600 }}>USD/KRW</span>
                <span style={{ fontSize: 16, fontWeight: 700 }}>{liveMarket.usd_krw != null ? formatNumber(liveMarket.usd_krw, 0) : '-'}</span>
              </div>
              {liveMarket.updated_at && (
                <span className="wealth-home-muted" style={{ marginLeft: 'auto', fontSize: 14 }}>
                  시세 {liveMarket.updated_at}
                </span>
              )}
            </div>
            {sessionCards.length > 0 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
                <span className="wealth-home-muted" style={{ fontSize: 14 }}>시장 상태</span>
                {sessionCards.map((session) => (
                  <div
                    key={String(session.label || session.status || session.local_time || '-')}
                    className={`inline-badge ${sessionTone(session.status)}`}
                    style={{ display: 'flex', gap: 6, alignItems: 'center', padding: '6px 10px' }}
                  >
                    <span>{session.label || '-'}</span>
                    <strong>{session.status_label || '-'}</strong>
                    <span style={{ opacity: 0.8 }}>{session.local_time || '-'}</span>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="page-section wealth-summary-strip">
            {summaryItems.map((item) => (
              <div key={item.label} className="wealth-summary-cell">
                <div className="wealth-kpi-label">{item.label}</div>
                <div className={`wealth-kpi-value ${item.tone || ''}`.trim()}>{item.value}</div>
                <div className="wealth-kpi-copy">{item.detail}</div>
              </div>
            ))}
          </section>

          <section className="page-section">
            <div className="section-head-row">
              <div>
                <div className="section-title">시장·신호 개요</div>
                <div className="section-copy">노출 비중과 오늘 신호 상태를 카드 없이 한 흐름으로 정리했어.</div>
              </div>
            </div>
            <div className="wealth-inline-grid">
              <div className="wealth-inline-block">
                <div className="wealth-inline-label">시장별 노출 비중</div>
                <div className="wealth-bars">
                  {exposureRows.map((item) => (
                    <div key={item.label} className="wealth-bar-row">
                      <div className="wealth-bar-label">{item.label}</div>
                      <div className="wealth-bar-track"><div className={`wealth-bar-fill ${item.tone}`.trim()} style={{ width: item.width }} /></div>
                      <div className="wealth-bar-value">{item.value}</div>
                    </div>
                  ))}
                </div>
              </div>
              <div className="wealth-inline-block">
                <div className="wealth-inline-label">오늘 신호 요약</div>
                <div className="wealth-bars">
                  {signalRows.map((item) => (
                    <div key={item.label} className="wealth-bar-row">
                      <div className="wealth-bar-label">{item.label}</div>
                      <div className="wealth-bar-track"><div className={`wealth-bar-fill ${item.tone}`.trim()} style={{ width: item.width }} /></div>
                      <div className="wealth-bar-value">{item.value}</div>
                    </div>
                  ))}
                </div>
                <div className="wealth-home-muted" style={{ marginTop: 12 }}>장세 {allocator.regime || snapshot.signals.regime || '-'} · 위험도 {allocator.risk_level || snapshot.signals.risk_level || '-'}</div>
              </div>
            </div>
          </section>

          <section className="page-section">
            <div className="section-head-row">
              <div>
                <div className="section-title">운영 브리프</div>
                <div className="section-copy">기존 투자 브리프 핵심만 운영 개요로 합쳤어.</div>
              </div>
              <div className="inline-badge">{reportGeneratedAt ? formatDateTimeWithAge(reportGeneratedAt) : '브리프 대기'}</div>
            </div>
            <div className="wealth-list">
              <div className="wealth-list-item">
                <div className="wealth-list-title">오늘 결론</div>
                <div className="wealth-list-copy">{riskGuardAllowed ? (todayView.judgmentTitle || '선별') : '방어'} · 장세 {allocator.regime || snapshot.signals.regime || '-'} · 위험도 {allocator.risk_level || snapshot.signals.risk_level || '-'}</div>
              </div>
              {todayActions.map((item, index) => (
                <div key={`action-${index}`} className="wealth-list-item">
                  <div className="wealth-list-title">{item.label}</div>
                  <div className="wealth-list-copy">{item.detail}</div>
                </div>
              ))}
              {avoidActions.map((line, index) => (
                <div key={`avoid-${index}`} className="wealth-list-item">
                  <div className="wealth-list-title">회피 {index + 1}</div>
                  <div className="wealth-list-copy">{line}</div>
                </div>
              ))}
              {insightLines.map((line, index) => (
                <div key={`insight-${index}`} className="wealth-list-item">
                  <div className="wealth-list-title">근거 {index + 1}</div>
                  <div className="wealth-list-copy">{line}</div>
                </div>
              ))}
            </div>
          </section>

          <section className="page-section">
            <div className="section-head-row">
              <div>
                <div className="section-title">운영 리스크</div>
                <div className="section-copy">상태 타일 대신 줄형 상태 목록으로 정리했어.</div>
              </div>
              <div className="inline-badge">실시간</div>
            </div>
            <div className="wealth-data-list">
              {riskAlertItems.map((item) => (
                <div key={item.key} className={`wealth-data-row ${item.tone === 'bad' ? 'is-bad' : 'is-good'}`.trim()}>
                  <div className="wealth-data-label">{item.label}</div>
                  <div className="wealth-data-main">{item.value}</div>
                  <div className="wealth-data-meta">{item.detail}</div>
                </div>
              ))}
            </div>
          </section>

          <section className="page-section">
            <div className="section-head-row">
              <div>
                <div className="section-title">오늘 시그널 후보</div>
                <div className="section-copy">지금 바로 확인할 종목만 줄형으로 노출해.</div>
              </div>
            </div>
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
          </section>

          <section className="page-section">
            <div className="section-head-row">
              <div>
                <div className="section-title">운영 메모</div>
                <div className="section-copy">운영 개요에서 필요한 메모만 짧게 남겼어.</div>
              </div>
            </div>
            <div className="wealth-list">
              {noteItems.map((item) => (
                <div key={item.label} className="wealth-list-item">
                  <div className="wealth-list-title">{item.label}</div>
                  <div className="wealth-list-copy">{item.detail}</div>
                </div>
              ))}
            </div>
          </section>

          {(marketCtx.regime || marketCtx.summary) && (
            <section className="page-section">
              <div className="section-head-row">
                <div>
                  <div className="section-title">시장 컨텍스트</div>
                  <div className="section-copy">시장 환경과 요약 코멘트를 같은 섹션에 붙였어.</div>
                </div>
              </div>
              {marketContextRows.length > 0 && (
                <div className="detail-list" style={{ marginTop: 10 }}>
                  {marketContextRows.map((item) => (
                    <div key={item.label} className="detail-row"><span className="detail-label">{item.label}</span><span className="detail-value">{item.value}</span></div>
                  ))}
                </div>
              )}
              {marketCtx.summary && (
                <div className="wealth-list" style={{ marginTop: 14 }}>
                  <div className="wealth-list-item">
                    <div className="wealth-list-title">시장 요약</div>
                    <div className="wealth-list-copy">{marketCtx.summary}</div>
                  </div>
                  {(marketCtx.risks || []).map((risk, i) => (
                    <div key={i} className="wealth-list-item">
                      <div className="wealth-list-title">주의 {i + 1}</div>
                      <div className="wealth-list-copy">{risk}</div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}

          {loading && <div className="wealth-home-muted">{UI_TEXT.common.loading}</div>}
        </div>
      </div>
    </div>
  );
}
