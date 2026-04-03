import { useCallback, useMemo, useState } from 'react';
import { ConsoleActionBar } from '../components/ConsoleActionBar';
import { reasonCodeToKorean } from '../constants/uiText';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import type { ScannerCandidate, ScannerStatusItem } from '../types/domain';
import type { ConsoleSnapshot } from '../types/consoleView';
import { formatDateTime, formatNumber, formatSymbol } from '../utils/format';

interface ScannerPageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
}

type HannaState = 'healthy' | 'degraded' | 'timeout' | 'research_unavailable';

const HANNA_STATE_LABEL: Record<HannaState, string> = {
  healthy: 'healthy',
  degraded: 'degraded',
  timeout: 'timeout',
  research_unavailable: 'research_unavailable',
};

function resolveHannaState(candidate?: ScannerCandidate): HannaState {
  if (!candidate) return 'research_unavailable';
  if (candidate.research_unavailable) return 'research_unavailable';
  if (candidate.layer_c?.research_unavailable) return 'research_unavailable';
  if (Array.isArray(candidate.layer_c?.warnings) && candidate.layer_c.warnings.some((item) => String(item) === 'research_unavailable')) return 'research_unavailable';

  const candidateStatus = candidate.research_status || candidate.layer_c?.provider_status;
  if (candidateStatus === 'missing') return 'research_unavailable';
  if (candidateStatus === 'timeout') return 'timeout';
  if (candidateStatus === 'degraded') return 'degraded';
  if (candidateStatus === 'stale_ingest') return 'degraded';
  if (candidateStatus === 'research_unavailable') return 'research_unavailable';
  if (candidateStatus) return candidateStatus === 'healthy' ? 'healthy' : 'degraded';
  return 'healthy';
}

function resolveProviderHannaState(providerStatus: string | undefined, freshness: string | undefined): HannaState {
  if (providerStatus === 'healthy') return 'healthy';
  if (providerStatus === 'degraded' || providerStatus === 'stale_ingest') return 'degraded';
  if (providerStatus === 'missing' || freshness === 'missing') return 'research_unavailable';
  if (freshness === 'stale') return 'degraded';
  if (providerStatus === 'stale') return 'degraded';
  return 'healthy';
}

function resolveHannaStateWithProvider(candidate: ScannerCandidate | undefined, providerStatus?: string, freshness?: string): HannaState {
  const fallback = resolveProviderHannaState(providerStatus, freshness);
  if (!candidate) return fallback;
  const candidateState = resolveHannaState(candidate);
  if (candidateState === 'research_unavailable') return 'research_unavailable';
  if (candidateState === 'healthy') return fallback === 'healthy' ? 'healthy' : fallback;
  if (candidateState === 'degraded' || candidateState === 'timeout') return 'degraded';
  return fallback;
}
function summarizeHannaState(item: ScannerStatusItem, providerStatus?: string, freshness?: string): HannaState {
  const candidates = item.top_candidates || [];
  const candidateStates = candidates.map((candidate) => resolveHannaStateWithProvider(candidate, providerStatus, freshness));
  if (candidateStates.some((state) => state === 'timeout')) return 'timeout';
  if (candidateStates.some((state) => state === 'degraded')) return 'degraded';
  if (candidateStates.some((state) => state === 'research_unavailable')) return 'research_unavailable';
  if (candidateStates.some((state) => state === 'healthy')) return 'healthy';
  return resolveProviderHannaState(providerStatus, freshness);
}

function toneForHanna(state: HannaState): 'neutral' | 'good' | 'bad' {
  if (state === 'healthy') return 'good';
  if (state === 'degraded' || state === 'timeout') return 'bad';
  return 'neutral';
}

function classNameForHanna(state: HannaState) {
  if (state === 'healthy') return 'inline-badge is-success';
  if (state === 'degraded' || state === 'timeout') return 'inline-badge is-danger';
  return 'inline-badge';
}

function classNameForFinalAction(action: string | undefined) {
  if (action === 'review_for_entry') return 'inline-badge is-success';
  if (action === 'blocked') return 'inline-badge is-danger';
  return 'inline-badge';
}

function translatedCodes(items: string[] | undefined) {
  const values = (items || []).map((item) => reasonCodeToKorean(item)).filter(Boolean);
  return values.length > 0 ? values.join(', ') : '-';
}

function selectedCandidateFor(item: ScannerStatusItem, selectedSignalId: string | undefined) {
  const candidates = item.top_candidates || [];
  if (!selectedSignalId) return candidates[0];
  return candidates.find((candidate) => candidate.signal_id === selectedSignalId) || candidates[0];
}

export function ScannerPage({ snapshot, loading, errorMessage, onRefresh }: ScannerPageProps) {
  const { entries, push, clear } = useConsoleLogs();
  const [selectedSignals, setSelectedSignals] = useState<Record<string, string>>({});
  const items = snapshot.scanner.items || [];

  const totalCandidates = useMemo(
    () => items.reduce((sum, item) => sum + Number(item.candidate_count || 0), 0),
    [items],
  );
  const totalScanned = useMemo(
    () => items.reduce((sum, item) => sum + Number(item.scanned_symbol_count || 0), 0),
    [items],
  );
  const activeCount = items.filter((item) => item.enabled && item.approval_status === 'approved').length;
  const providerHannaState = resolveProviderHannaState(snapshot.research.status, snapshot.research.freshness);
  const overallHannaState = useMemo<HannaState>(() => {
    if (items.some((item) => summarizeHannaState(item, snapshot.research.status, snapshot.research.freshness) === 'timeout')) return 'timeout';
    if (items.some((item) => summarizeHannaState(item, snapshot.research.status, snapshot.research.freshness) === 'degraded')) return 'degraded';
    if (items.some((item) => summarizeHannaState(item, snapshot.research.status, snapshot.research.freshness) === 'healthy')) return 'healthy';
    if (items.some((item) => summarizeHannaState(item, snapshot.research.status, snapshot.research.freshness) === 'research_unavailable')) return 'research_unavailable';
    return providerHannaState;
  }, [items, providerHannaState, snapshot.research.status, snapshot.research.freshness]);

  const statusItems = useMemo(() => ([
    { label: '스캔 전략', value: `${items.length}개`, tone: 'neutral' as const },
    { label: '활성 전략', value: `${activeCount}개`, tone: activeCount > 0 ? 'good' as const : 'neutral' as const },
    { label: '스캔 종목', value: `${totalScanned}건`, tone: totalScanned > 0 ? 'good' as const : 'neutral' as const },
    { label: '후보 수', value: `${totalCandidates}건`, tone: totalCandidates > 0 ? 'good' as const : 'neutral' as const },
    { label: 'Hanna', value: HANNA_STATE_LABEL[overallHannaState], tone: toneForHanna(overallHannaState) },
  ]), [activeCount, items.length, overallHannaState, totalCandidates, totalScanned]);

  const handleRefresh = useCallback(() => {
    onRefresh();
    push('info', '장중 스캐너 상태를 다시 불러왔습니다.', undefined, 'engine');
  }, [onRefresh, push]);

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell" style={{ display: 'grid', gap: 16 }}>
          <ConsoleActionBar
            title="장중 스캐너"
            subtitle="Layer A 유니버스부터 Layer E final action까지 같은 화면에서 읽는 운영용 스캐너입니다. 종목을 누르면 왜 review 대상인지, 왜 막혔는지 레이어별 근거를 바로 확인할 수 있습니다."
            lastUpdated={snapshot.fetchedAt}
            loading={loading}
            errorMessage={errorMessage}
            statusItems={statusItems}
            onRefresh={handleRefresh}
            logs={entries}
            onClearLogs={clear}
            settingsPanel={(
              <div style={{ display: 'grid', gap: 8, fontSize: 12, color: 'var(--text-3)' }}>
                <div>Layer A는 universe 포함 이유만 기록하고 주문 판단을 하지 않습니다.</div>
                <div>Layer C Hanna는 structured DTO와 warning code만 제공하며, buy/sell/order 명령을 내리지 못합니다.</div>
                <div>최종 실행 의미는 Layer E final action 기준입니다: review_for_entry / watch_only / blocked / do_not_touch.</div>
              </div>
            )}
          />

          {items.map((item) => {
            const strategyId = String(item.strategy_id || 'strategy');
            const selectedCandidate = selectedCandidateFor(item, selectedSignals[strategyId]);
            const strategyHannaState = summarizeHannaState(item, snapshot.research.status, snapshot.research.freshness);

            return (
              <section key={strategyId} className="page-section" style={{ display: 'grid', gap: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <div style={{ fontSize: 14, fontWeight: 700 }}>{item.strategy_name || item.strategy_id}</div>
                      <span className={classNameForHanna(strategyHannaState)}>Hanna {HANNA_STATE_LABEL[strategyHannaState]}</span>
                    </div>
                    <div className="signal-cell-copy" style={{ marginTop: 4 }}>
                      {item.market || '-'} · {item.universe_rule || '-'} · {item.scan_cycle || '-'}
                    </div>
                  </div>
                  <div style={{ display: 'grid', gap: 4, fontSize: 12, color: 'var(--text-3)', textAlign: 'right' }}>
                    <div>마지막 스캔 {formatDateTime(item.last_scan_at)}</div>
                    <div>다음 예정 {formatDateTime(item.next_scan_at)}</div>
                    <div>스캔 {formatNumber(item.scanned_symbol_count, 0)} / 유니버스 {formatNumber(item.universe_symbol_count, 0)}</div>
                  </div>
                </div>

                <div style={{ overflow: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 980 }}>
                    <thead>
                      <tr style={{ background: 'var(--bg-soft)', textAlign: 'left' }}>
                        <th style={{ padding: 12, fontSize: 12 }}>순위</th>
                        <th style={{ padding: 12, fontSize: 12 }}>종목</th>
                        <th style={{ padding: 12, fontSize: 12 }}>Layer B</th>
                        <th style={{ padding: 12, fontSize: 12 }}>Layer C</th>
                        <th style={{ padding: 12, fontSize: 12 }}>Layer D/E</th>
                        <th style={{ padding: 12, fontSize: 12 }}>사유</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(item.top_candidates || []).map((candidate) => {
                        const signalId = String(candidate.signal_id || `${candidate.strategy_id}:${candidate.code}`);
                        const isSelected = selectedCandidate?.signal_id === candidate.signal_id || (!selectedCandidate && signalId === selectedSignals[strategyId]);
                        const hannaState = resolveHannaStateWithProvider(candidate, snapshot.research.status, snapshot.research.freshness);
                        return (
                          <tr
                            key={signalId}
                            style={{
                              borderTop: '1px solid var(--border)',
                              background: isSelected ? 'var(--bg-soft)' : 'transparent',
                            }}
                          >
                            <td style={{ padding: 12, fontSize: 12 }}>{candidate.candidate_rank || '-'}</td>
                            <td style={{ padding: 12, fontSize: 12 }}>
                              <div style={{ display: 'grid', gap: 6 }}>
                                <div style={{ fontWeight: 700 }}>{formatSymbol(candidate.code, candidate.name)}</div>
                                <div className="signal-cell-copy">{candidate.sector || '-'}</div>
                                <button
                                  type="button"
                                  className="ghost-button"
                                  style={{ width: 'fit-content' }}
                                  onClick={() => setSelectedSignals((prev) => ({ ...prev, [strategyId]: signalId }))}
                                >
                                  레이어 보기
                                </button>
                              </div>
                            </td>
                            <td style={{ padding: 12, fontSize: 12 }}>
                              <div>quant {candidate.quant_score == null ? '-' : formatNumber(candidate.quant_score, 2)}</div>
                              <div className="signal-cell-copy">{candidate.signal_state || '-'} · raw {formatNumber(candidate.score, 2)}</div>
                            </td>
                            <td style={{ padding: 12, fontSize: 12 }}>
                              <div className={classNameForHanna(hannaState)}>{HANNA_STATE_LABEL[hannaState]}</div>
                              <div className="signal-cell-copy" style={{ marginTop: 6 }}>
                                score {candidate.research_score == null ? '-' : formatNumber(candidate.research_score, 2)}
                              </div>
                            </td>
                            <td style={{ padding: 12, fontSize: 12 }}>
                              <div>{candidate.risk_check?.reason_code || 'OK'}</div>
                              <div className={classNameForFinalAction(candidate.final_action)} style={{ marginTop: 6 }}>
                                {candidate.final_action || '-'}
                              </div>
                            </td>
                            <td style={{ padding: 12, fontSize: 12 }}>
                              {translatedCodes(candidate.reason_codes || candidate.reasons)}
                            </td>
                          </tr>
                        );
                      })}
                      {(item.top_candidates || []).length === 0 && (
                        <tr>
                          <td colSpan={6} style={{ padding: 14, fontSize: 12, color: 'var(--text-4)' }}>현재 후보가 없습니다.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>

                {selectedCandidate && (
                  <div className="page-section" style={{ display: 'grid', gap: 12, padding: 16 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
                      <div>
                        <div style={{ fontSize: 14, fontWeight: 700 }}>{formatSymbol(selectedCandidate.code, selectedCandidate.name)}</div>
                        <div className="signal-cell-copy" style={{ marginTop: 4 }}>
                          {selectedCandidate.strategy_name || selectedCandidate.strategy_id} · {selectedCandidate.market || '-'} · {selectedCandidate.signal_state || '-'}
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        <span className={classNameForHanna(resolveHannaStateWithProvider(selectedCandidate, snapshot.research.status, snapshot.research.freshness))}>Hanna {HANNA_STATE_LABEL[resolveHannaStateWithProvider(selectedCandidate, snapshot.research.status, snapshot.research.freshness)]}</span>
                        <span className={classNameForFinalAction(selectedCandidate.final_action)}>{selectedCandidate.final_action || '-'}</span>
                      </div>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
                      <div className="operator-note-card" style={{ display: 'grid', gap: 6 }}>
                        <div className="operator-note-label">Layer A · Universe</div>
                        <div className="operator-note-copy">rule {selectedCandidate.layer_a?.universe_rule || '-'}</div>
                        <div className="operator-note-copy">scan {formatDateTime(selectedCandidate.layer_a?.scan_time || selectedCandidate.last_scanned_at)}</div>
                        <div className="operator-note-copy">inclusion {selectedCandidate.layer_a?.inclusion_reason || '-'}</div>
                      </div>

                      <div className="operator-note-card" style={{ display: 'grid', gap: 6 }}>
                        <div className="operator-note-label">Layer B · Quant</div>
                        <div className="operator-note-copy">quant_score {selectedCandidate.layer_b?.quant_score == null ? '-' : formatNumber(selectedCandidate.layer_b?.quant_score, 2)}</div>
                        <div className="operator-note-copy">strategy {selectedCandidate.layer_b?.strategy_id || selectedCandidate.strategy_id || '-'}</div>
                        <div className="operator-note-copy">tags {translatedCodes(selectedCandidate.layer_b?.quant_tags)}</div>
                      </div>

                      <div className="operator-note-card" style={{ display: 'grid', gap: 6 }}>
                        <div className="operator-note-label">Layer C · Hanna</div>
                        <div className="operator-note-copy">research_score {selectedCandidate.layer_c?.research_score == null ? '-' : formatNumber(selectedCandidate.layer_c?.research_score, 2)}</div>
                        <div className="operator-note-copy">warnings {translatedCodes(selectedCandidate.layer_c?.warnings)}</div>
                        <div className="operator-note-copy">tags {(selectedCandidate.layer_c?.tags || []).join(', ') || '-'}</div>
                        <div className="operator-note-copy">summary {selectedCandidate.layer_c?.summary || '-'}</div>
                      </div>

                      <div className="operator-note-card" style={{ display: 'grid', gap: 6 }}>
                        <div className="operator-note-label">Layer D · Risk Gate</div>
                        <div className="operator-note-copy">{selectedCandidate.layer_d?.blocked ? 'blocked' : 'allowed'}</div>
                        <div className="operator-note-copy">reason {translatedCodes(selectedCandidate.layer_d?.reason_codes || selectedCandidate.reason_codes)}</div>
                        <div className="operator-note-copy">position/liquidity {selectedCandidate.layer_d?.position_cap_state || '-'} / {selectedCandidate.layer_d?.liquidity_state || '-'}</div>
                        <div className="operator-note-copy">spread {selectedCandidate.layer_d?.spread_state || '-'}</div>
                      </div>

                      <div className="operator-note-card" style={{ display: 'grid', gap: 6 }}>
                        <div className="operator-note-label">Layer E · Final Action</div>
                        <div className="operator-note-copy">final_action {selectedCandidate.layer_e?.final_action || selectedCandidate.final_action || '-'}</div>
                        <div className="operator-note-copy">reason {selectedCandidate.layer_e?.decision_reason || '-'}</div>
                        <div className="operator-note-copy">timestamp {formatDateTime(selectedCandidate.layer_e?.timestamp || selectedCandidate.last_scanned_at)}</div>
                        <div className="operator-note-copy">source {(selectedCandidate.layer_e?.source_context && JSON.stringify(selectedCandidate.layer_e.source_context)) || '-'}</div>
                      </div>
                    </div>
                  </div>
                )}
              </section>
            );
          })}
        </div>
      </div>
    </div>
  );
}
