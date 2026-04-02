import { useCallback, useMemo } from 'react';
import { ConsoleActionBar } from '../components/ConsoleActionBar';
import { reasonCodeToKorean, reliabilityToKorean, strategyTypeToKorean, UI_TEXT } from '../constants/uiText';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import { explainSizeRecommendation, formatDateTimeWithAge, formatNumber, formatPercent, formatSymbol } from '../utils/format';
import type { ConsoleSnapshot } from '../types/consoleView';

interface SignalsPageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
}

interface SignalRowView {
  key: string;
  symbol: string;
  market: string;
  strategyLabel: string;
  sourceLabel: string;
  sourceDetail: string;
  sourceTierLabel: string;
  scoreLabel: string;
  winProbabilityLabel: string;
  evLabel: string;
  entryLabel: string;
  entryTone: 'good' | 'bad';
  sizeSummary: string;
  reliabilityLabel: string;
  liquidityLabel: string;
  slippageLabel: string;
  reasons: string[];
  primaryReason: string;
}

export function SignalsPage({ snapshot, loading, errorMessage, onRefresh }: SignalsPageProps) {
  const { entries, push, clear } = useConsoleLogs();
  const signals = (snapshot.signals.signals || []).slice(0, 80);
  const allowedCount = signals.filter((row) => row.entry_allowed).length;
  const blockedCount = signals.length - allowedCount;
  const emptyMessage = errorMessage ? UI_TEXT.empty.signalsMissingData : UI_TEXT.empty.signalsNoMatches;
  const signalsAsOf = snapshot.signals.generated_at || snapshot.fetchedAt;

  const handleRefresh = useCallback(() => {
    onRefresh();
    push('info', '신호 데이터를 수동 갱신했습니다.');
  }, [onRefresh, push]);

  const signalRows = useMemo<SignalRowView[]>(() => signals.map((signal) => {
    const winProbability = signal.ev_metrics?.win_probability;
    const size = signal.size_recommendation?.quantity ?? 0;
    const sizeSummary = explainSizeRecommendation(signal.size_recommendation);
    const reliability = reliabilityToKorean(String(signal.ev_metrics?.reliability || '').toLowerCase());
    const liquidity = String(signal.execution_realism?.liquidity_gate_status || '-');
    const slippage = signal.execution_realism?.slippage_bps;
    const reasons = (signal.reason_codes || []).map((reason) => reasonCodeToKorean(reason));
    const blocked = !signal.entry_allowed;

    const sourceLabel = String(signal.candidate_source_label || signal.candidate_source || '-');
    const sourceTier = String(signal.candidate_source_tier || '').toLowerCase();
    const sourceTierLabel = sourceTier === 'tier_1' ? 'T1' : sourceTier === 'tier_2' ? 'T2' : '-';
    return {
      key: `${signal.market || ''}:${signal.code || ''}`,
      symbol: formatSymbol(signal.code, signal.name),
      market: String(signal.market || '-'),
      strategyLabel: strategyTypeToKorean(signal.strategy_type || ''),
      sourceLabel,
      sourceDetail: String(signal.candidate_source_detail || signal.candidate_research_source || signal.candidate_runtime_source_mode || '-'),
      sourceTierLabel,
      scoreLabel: formatNumber((signal as { score?: number }).score, 2),
      winProbabilityLabel: winProbability === undefined ? '-' : formatPercent(winProbability, 2, true),
      evLabel: signal.ev_metrics?.expected_value === undefined ? '-' : formatNumber(signal.ev_metrics?.expected_value, 2),
      entryLabel: blocked ? UI_TEXT.status.blocked : UI_TEXT.status.allowed,
      entryTone: blocked ? 'bad' : 'good',
      sizeSummary: size > 0 ? sizeSummary : (sizeSummary === '-' ? '0주' : `0주 (${sizeSummary})`),
      reliabilityLabel: reliability || '-',
      liquidityLabel: liquidity,
      slippageLabel: slippage === undefined ? '-' : `${formatNumber(slippage, 2)} bps`,
      reasons,
      primaryReason: reasons[0] || (blocked ? '-' : '차단 사유 없음'),
    };
  }), [signals]);

  const statusItems = useMemo(() => ([
    {
      label: '전체 신호',
      value: `${signals.length}건`,
      tone: 'neutral' as const,
    },
    {
      label: '진입 허용',
      value: `${allowedCount}건`,
      tone: 'good' as const,
    },
    {
      label: '차단',
      value: `${blockedCount}건`,
      tone: blockedCount > 0 ? 'bad' as const : 'neutral' as const,
    },
    {
      label: '장세/위험도',
      value: `${snapshot.signals.regime || '-'} / ${snapshot.signals.risk_level || '-'}`,
      tone: 'neutral' as const,
    },
  ]), [allowedCount, blockedCount, signals.length, snapshot.signals.regime, snapshot.signals.risk_level]);

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell" style={{ display: 'grid', gap: 16 }}>
          <ConsoleActionBar
            title="신호 관리"
            subtitle="runtime 후보는 기본적으로 hybrid로 넓게 모으고, 최종 진입은 allocator·EV·risk guard·liquidity·sizing 게이트로만 막습니다. 좁은 화면에서는 카드형, 넓은 화면에서는 상세 테이블로 보면 됩니다."
            lastUpdated={snapshot.fetchedAt}
            loading={loading}
            errorMessage={errorMessage}
            statusItems={statusItems}
            onRefresh={handleRefresh}
            logs={entries}
            onClearLogs={clear}
            settingsPanel={(
              <div style={{ display: 'grid', gap: 10, fontSize: 12, color: 'var(--text-3)' }}>
                <div>표시 최대 건수: 80건</div>
                <div>정렬 기준: EV 내림차순</div>
                <div>신호 기준 시각: {formatDateTimeWithAge(signalsAsOf)}</div>
                <div>후보 소스는 quant / research / hybrid와 T1·T2로 같이 표시합니다. hybrid 기본 운영 기준으로 넓게 모읍니다.</div>
                <div>최종 진입 허용은 후보 소스가 아니라 allocator·EV·risk guard·liquidity·sizing 게이트 기준입니다.</div>
                <div>차단 사유는 요약 한 줄 + 전체 사유 리스트로 같이 표시합니다.</div>
              </div>
            )}
          />

          <div className="page-section signal-table-shell" style={{ padding: 0 }}>
            <div className="signal-table-desktop">
              <div style={{ overflow: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1600 }}>
                  <thead>
                    <tr style={{ background: 'var(--bg-soft)', textAlign: 'left' }}>
                      <th style={{ padding: 12, fontSize: 12 }}>종목</th>
                      <th style={{ padding: 12, fontSize: 12 }}>전략</th>
                      <th style={{ padding: 12, fontSize: 12 }}>소스 / 티어</th>
                      <th style={{ padding: 12, fontSize: 12 }}>점수 / 승률</th>
                      <th style={{ padding: 12, fontSize: 12 }}>EV</th>
                      <th style={{ padding: 12, fontSize: 12 }}>진입</th>
                      <th style={{ padding: 12, fontSize: 12 }}>권장 수량</th>
                      <th style={{ padding: 12, fontSize: 12 }}>검증 신뢰도</th>
                      <th style={{ padding: 12, fontSize: 12 }}>유동성 / 슬리피지</th>
                      <th style={{ padding: 12, fontSize: 12, minWidth: 340 }}>핵심 사유</th>
                    </tr>
                  </thead>
                  <tbody>
                    {signalRows.map((row) => (
                      <tr key={row.key} style={{ borderTop: '1px solid var(--border)' }}>
                        <td style={{ padding: 12, fontSize: 12, verticalAlign: 'top' }}>
                          <div style={{ fontWeight: 700, color: 'var(--text-1)' }}>{row.symbol}</div>
                          <div className="signal-cell-copy">{row.market}</div>
                        </td>
                        <td style={{ padding: 12, fontSize: 12, verticalAlign: 'top' }}>{row.strategyLabel}</td>
                        <td style={{ padding: 12, fontSize: 12, verticalAlign: 'top' }}>
                          <div>{row.sourceLabel}</div>
                          <div className="signal-cell-copy">{row.sourceTierLabel} · {row.sourceDetail}</div>
                        </td>
                        <td style={{ padding: 12, fontSize: 12, verticalAlign: 'top' }}>
                          <div>{row.scoreLabel}</div>
                          <div className="signal-cell-copy">승률 {row.winProbabilityLabel}</div>
                        </td>
                        <td style={{ padding: 12, fontSize: 12, fontWeight: 700, verticalAlign: 'top' }}>{row.evLabel}</td>
                        <td style={{ padding: 12, fontSize: 12, fontWeight: 700, color: row.entryTone === 'bad' ? 'var(--down)' : 'var(--up)', verticalAlign: 'top' }}>
                          {row.entryLabel}
                        </td>
                        <td style={{ padding: 12, fontSize: 12, verticalAlign: 'top' }}>{row.sizeSummary}</td>
                        <td style={{ padding: 12, fontSize: 12, verticalAlign: 'top' }}>{row.reliabilityLabel}</td>
                        <td style={{ padding: 12, fontSize: 12, verticalAlign: 'top' }}>
                          <div>{row.liquidityLabel}</div>
                          <div className="signal-cell-copy">{row.slippageLabel}</div>
                        </td>
                        <td style={{ padding: 12, fontSize: 12, color: row.entryTone === 'bad' ? 'var(--down)' : 'var(--text-3)', verticalAlign: 'top' }}>
                          <div style={{ fontWeight: 700, color: row.entryTone === 'bad' ? 'var(--down)' : 'var(--text-2)' }}>{row.primaryReason}</div>
                          {row.reasons.length > 1 && (
                            <div className="signal-reason-list is-inline" style={{ marginTop: 8 }}>
                              {row.reasons.slice(1).map((reason, idx) => <span key={`${row.key}-reason-${idx}`}>{reason}</span>)}
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                    {signalRows.length === 0 && (
                      <tr>
                        <td colSpan={10} style={{ padding: 14, fontSize: 12, color: 'var(--text-4)' }}>
                          {emptyMessage}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="signal-card-list">
              {signalRows.map((row) => (
                <article key={`${row.key}-card`} className="signal-card">
                  <div className="signal-card-head">
                    <div>
                      <div className="operator-note-label">{row.symbol}</div>
                      <div className="operator-note-copy" style={{ marginTop: 4 }}>{row.market} · {row.strategyLabel} · {row.sourceLabel} {row.sourceTierLabel}</div>
                    </div>
                    <div className={`inline-badge ${row.entryTone === 'bad' ? 'is-danger' : 'is-success'}`}>{row.entryLabel}</div>
                  </div>

                  <div className="signal-chip-row">
                    <span className="signal-meta-chip">소스 {row.sourceLabel}</span>
                    <span className="signal-meta-chip">티어 {row.sourceTierLabel}</span>
                    <span className="signal-meta-chip">점수 {row.scoreLabel}</span>
                    <span className="signal-meta-chip">승률 {row.winProbabilityLabel}</span>
                    <span className="signal-meta-chip">EV {row.evLabel}</span>
                    <span className="signal-meta-chip">검증 {row.reliabilityLabel}</span>
                  </div>

                  <div className="signal-kpi-grid">
                    <div className="signal-kpi-card">
                      <div className="signal-kpi-label">권장 수량</div>
                      <div className="signal-kpi-value">{row.sizeSummary}</div>
                    </div>
                    <div className="signal-kpi-card">
                      <div className="signal-kpi-label">유동성 / 슬리피지</div>
                      <div className="signal-kpi-value">{row.liquidityLabel}</div>
                      <div className="signal-cell-copy">{row.slippageLabel}</div>
                    </div>
                  </div>

                  <div className="signal-reason-box">
                    <div className="signal-kpi-label">핵심 사유</div>
                    <div className="signal-reason-primary">{row.primaryReason}</div>
                    {row.reasons.length > 1 && (
                      <div className="signal-reason-list">
                        {row.reasons.slice(1).map((reason, idx) => <span key={`${row.key}-card-reason-${idx}`}>{reason}</span>)}
                      </div>
                    )}
                  </div>
                </article>
              ))}
              {signalRows.length === 0 && <div style={{ padding: 14, fontSize: 12, color: 'var(--text-4)' }}>{emptyMessage}</div>}
            </div>
          </div>

          {loading && <div style={{ color: 'var(--text-3)', fontSize: 12 }}>{UI_TEXT.common.loading}</div>}
        </div>
      </div>
    </div>
  );
}
