import { useCallback, useMemo, useState } from 'react';
import { ConsoleActionBar } from '../components/ConsoleActionBar';
import { FreshnessBadge, GradeBadge } from '../components/QualityBadge';
import { reasonCodeToKorean, freshnessToKorean, gradeToKorean } from '../constants/uiText';
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
  healthy: '정상',
  degraded: '불안정',
  timeout: '응답 지연',
  research_unavailable: '리서치 미사용/불가',
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

function researchGrade(candidate: ScannerCandidate | undefined): string {
  return String(candidate?.layer_c?.validation?.grade || '').toUpperCase() || '-';
}

function researchFreshness(candidate: ScannerCandidate | undefined): string {
  return String(candidate?.layer_c?.freshness || candidate?.layer_c?.freshness_detail?.status || '').toLowerCase() || 'missing';
}

function researchScoreDisplay(candidate: ScannerCandidate | undefined): string {
  if (researchGrade(candidate) === 'D') return '—';
  const score = candidate?.research_score ?? candidate?.layer_c?.research_score;
  return score == null ? '-' : formatNumber(score, 2);
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
  const scannerSource = snapshot.scanner.source || 'strategy_scan_cache';
  const scannerRefreshing = Boolean(snapshot.scanner.refreshing);
  const scannerStatusText = scannerRefreshing ? '갱신 중' : (scannerSource === 'live_scan' ? '최신 반영' : '캐시');

  const totalCandidates = useMemo(
    () => items.reduce((sum, item) => sum + Number(item.candidate_count || 0), 0),
    [items],
  );
  const totalScanned = useMemo(
    () => items.reduce((sum, item) => sum + Number(item.scanned_symbol_count || 0), 0),
    [items],
  );
  const activeCount = items.filter((item) => item.enabled).length;
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
    { label: '스캔 소스', value: scannerStatusText, tone: scannerRefreshing ? 'bad' as const : 'neutral' as const },
    { label: 'Hanna', value: HANNA_STATE_LABEL[overallHannaState], tone: toneForHanna(overallHannaState) },
  ]), [activeCount, items.length, overallHannaState, scannerRefreshing, scannerStatusText, totalCandidates, totalScanned]);

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
            subtitle="1단계 유니버스부터 최종 액션까지 같은 화면에서 읽는 운영용 스캐너야. 종목을 누르면 왜 검토 대상인지, 왜 막혔는지 단계별 근거를 바로 확인할 수 있어."
            lastUpdated={snapshot.fetchedAt}
            loading={loading}
            errorMessage={errorMessage}
            statusItems={statusItems}
            onRefresh={handleRefresh}
            logs={entries}
            onClearLogs={clear}
            settingsPanel={(
              <div style={{ display: 'grid', gap: 8, fontSize: 12, color: 'var(--text-3)' }}>
                <div>1단계는 유니버스 포함 이유만 기록하고 주문 판단을 하지 않아.</div>
                <div>3단계 Hanna는 구조화된 데이터와 경고 코드만 제공하며, 매수/매도/주문 명령을 내리지 못해.</div>
                <div>최종 실행 의미는 마지막 액션 기준이야: 진입 검토 / 관찰 전용 / 차단 / 관망.</div>
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
                        <th style={{ padding: 12, fontSize: 12 }}>2단계 퀀트</th>
                        <th style={{ padding: 12, fontSize: 12 }}>3단계 리서치</th>
                        <th style={{ padding: 12, fontSize: 12 }}>4·5단계 판단</th>
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
                              <div>퀀트 {candidate.quant_score == null ? '-' : formatNumber(candidate.quant_score, 2)}</div>
                              <div className="signal-cell-copy">{reasonCodeToKorean(String(candidate.signal_state || '-'))} · 원점수 {formatNumber(candidate.score, 2)}</div>
                            </td>
                            <td style={{ padding: 12, fontSize: 12 }}>
                              <div className={classNameForHanna(hannaState)}>{HANNA_STATE_LABEL[hannaState]}</div>
                              <div className="workspace-chip-row" style={{ marginTop: 6 }}>
                                <FreshnessBadge value={researchFreshness(candidate)} />
                                <GradeBadge value={researchGrade(candidate)} />
                              </div>
                              <div className="signal-cell-copy" style={{ marginTop: 6 }}>
                                점수 {researchScoreDisplay(candidate)}
                              </div>
                            </td>
                            <td style={{ padding: 12, fontSize: 12 }}>
                              <div>{reasonCodeToKorean(String(candidate.risk_check?.reason_code || 'OK'))}</div>
                              <div className={classNameForFinalAction(candidate.final_action)} style={{ marginTop: 6 }}>
                                {reasonCodeToKorean(String(candidate.final_action || '-'))}
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
                          {selectedCandidate.strategy_name || selectedCandidate.strategy_id} · {selectedCandidate.market || '-'} · {reasonCodeToKorean(String(selectedCandidate.signal_state || '-'))}
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        <span className={classNameForHanna(resolveHannaStateWithProvider(selectedCandidate, snapshot.research.status, snapshot.research.freshness))}>Hanna {HANNA_STATE_LABEL[resolveHannaStateWithProvider(selectedCandidate, snapshot.research.status, snapshot.research.freshness)]}</span>
                        <span className={classNameForFinalAction(selectedCandidate.final_action)}>{reasonCodeToKorean(String(selectedCandidate.final_action || '-'))}</span>
                      </div>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
                      <div className="operator-note-card" style={{ display: 'grid', gap: 6 }}>
                        <div className="operator-note-label">1단계 · 유니버스</div>
                        <div className="operator-note-copy">규칙 {selectedCandidate.layer_a?.universe_rule || '-'}</div>
                        <div className="operator-note-copy">스캔 시각 {formatDateTime(selectedCandidate.layer_a?.scan_time || selectedCandidate.last_scanned_at)}</div>
                        <div className="operator-note-copy">포함 사유 {reasonCodeToKorean(String(selectedCandidate.layer_a?.inclusion_reason || '-'))}</div>
                        <div className="operator-note-copy">유니버스 최신성 {freshnessToKorean(String((snapshot.universe.items || []).find((row) => String(row.rule_name || '') === String(selectedCandidate.layer_a?.universe_rule || ''))?.freshness || 'missing'))}</div>
                      </div>

                      <div className="operator-note-card" style={{ display: 'grid', gap: 6 }}>
                        <div className="operator-note-label">2단계 · 퀀트</div>
                        <div className="operator-note-copy">퀀트 점수 {selectedCandidate.layer_b?.quant_score == null ? '-' : formatNumber(selectedCandidate.layer_b?.quant_score, 2)}</div>
                        <div className="operator-note-copy">전략 {selectedCandidate.layer_b?.strategy_id || selectedCandidate.strategy_id || '-'}</div>
                        <div className="operator-note-copy">태그 {translatedCodes(selectedCandidate.layer_b?.quant_tags)}</div>
                        <div className="operator-note-copy">시세 {selectedCandidate.layer_b?.technical_snapshot?.current_price ?? '-'} · {freshnessToKorean(String(selectedCandidate.layer_b?.technical_snapshot?.freshness || 'missing'))} · {gradeToKorean(String(selectedCandidate.layer_b?.technical_snapshot?.validation?.grade || '-'))}</div>
                      </div>

                      <div className="operator-note-card" style={{ display: 'grid', gap: 6 }}>
                        <div className="operator-note-label">3단계 · Hanna</div>
                        <div className="workspace-chip-row">
                          <FreshnessBadge value={researchFreshness(selectedCandidate)} />
                          <GradeBadge value={researchGrade(selectedCandidate)} />
                          {selectedCandidate.layer_c?.validation?.reason ? <span className="inline-badge">{reasonCodeToKorean(String(selectedCandidate.layer_c.validation.reason))}</span> : null}
                        </div>
                        <div className="operator-note-copy">리서치 점수 {researchScoreDisplay(selectedCandidate)}</div>
                        <div className="operator-note-copy">경고 {translatedCodes(selectedCandidate.layer_c?.warnings)}</div>
                        <div className="operator-note-copy">태그 {translatedCodes(selectedCandidate.layer_c?.tags)}</div>
                        <div className="operator-note-copy">요약 {researchGrade(selectedCandidate) === 'D' ? (selectedCandidate.layer_c?.validation?.exclusion_reason || '검증 제외') : (selectedCandidate.layer_c?.summary || '-')}</div>
                      </div>

                      <div className="operator-note-card" style={{ display: 'grid', gap: 6 }}>
                        <div className="operator-note-label">4단계 · 리스크 게이트</div>
                        <div className="operator-note-copy">{selectedCandidate.layer_d?.blocked ? '차단' : '허용'}</div>
                        <div className="operator-note-copy">사유 {translatedCodes(selectedCandidate.layer_d?.reason_codes || selectedCandidate.reason_codes)}</div>
                        <div className="operator-note-copy">포지션/유동성 {reasonCodeToKorean(String(selectedCandidate.layer_d?.position_cap_state || '-'))} / {reasonCodeToKorean(String(selectedCandidate.layer_d?.liquidity_state || '-'))}</div>
                        <div className="operator-note-copy">스프레드 {reasonCodeToKorean(String(selectedCandidate.layer_d?.spread_state || '-'))}</div>
                      </div>

                      <div className="operator-note-card" style={{ display: 'grid', gap: 6 }}>
                        <div className="operator-note-label">5단계 · 최종 액션</div>
                        <div className="operator-note-copy">최종 액션 {reasonCodeToKorean(String(selectedCandidate.layer_e?.final_action || selectedCandidate.final_action || '-'))}</div>
                        <div className="operator-note-copy">판단 사유 {reasonCodeToKorean(String(selectedCandidate.layer_e?.decision_reason || '-'))}</div>
                        <div className="operator-note-copy">기록 시각 {formatDateTime(selectedCandidate.layer_e?.timestamp || selectedCandidate.last_scanned_at)}</div>
                        <div className="operator-note-copy">참조 정보 {(selectedCandidate.layer_e?.source_context && JSON.stringify(selectedCandidate.layer_e.source_context)) || '-'}</div>
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
