import { useMemo } from 'react';
import {
  buildTodayReportView,
  buildWatchDecisionView,
} from '../adapters/consoleViewAdapter';
import type { ReactNode } from 'react';
import { UI_TEXT, reasonCodeToKorean, reliabilityToKorean } from '../constants/uiText';
import type { DomainSignal } from '../types/domain';
import { formatCount, formatDateTime, formatNumber, formatPercent, formatSymbol } from '../utils/format';
import {
  buildScoreComponentRows,
  buildTailRiskRows,
  describeScoreDecision,
  extractStrategyScorecard,
  strongestComponents,
  tailRiskHeadline,
  weakestComponents,
} from '../utils/strategyScorecard';
import type { ConsoleSnapshot } from '../types/consoleView';
import type { ReportTab } from '../types/navigation';

interface ReportsPageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  reportTab: ReportTab;
  onRefresh: () => void;
}

function renderIndexedBriefItems(lines: string[], keyPrefix: string) {
  return lines.map((line, index) => (
    <div key={`${keyPrefix}-${index}`} className="report-brief-item">
      <span className="report-brief-index">{index + 1}</span>
      <span>{line}</span>
    </div>
  ));
}

function reportCauseCard(onRefresh: () => void, errorMessage: string) {
  return (
    <div className="console-error-card" role="alert">
      <div className="console-error-card-title">{UI_TEXT.errors.partialLoadFailed}</div>
      <div className="console-error-card-copy">{errorMessage}</div>
      <ul className="console-error-card-list">
        <li>데이터 수집이 아직 끝나지 않았거나 리포트 생성 타이밍이 늦었을 수 있습니다.</li>
        <li>네트워크 또는 백엔드 응답 지연으로 일부 블록만 비어 있을 수 있습니다.</li>
        <li>인증이나 런타임 오류가 있으면 최신 설명 데이터가 누락될 수 있습니다.</li>
      </ul>
      <div className="console-error-card-actions">
        <button className="ghost-button" onClick={onRefresh}>재시도</button>
      </div>
    </div>
  );
}

function ratioWidth(value: number, total: number) {
  if (total <= 0) return '0%';
  return `${Math.max(6, Math.min(100, (value / total) * 100))}%`;
}

function riskScore(value: string): number {
  if (value === '높음') return 88;
  if (value === '중간') return 58;
  if (value === '낮음') return 28;
  return 46;
}

function tabHeadline(tab: ReportTab): string {
  if (tab === 'alerts') return '운영알림';
  if (tab === 'watch-decision') return '관망/관심목표 판단';
  return '오늘 리포트';
}

function tabDescription(tab: ReportTab): string {
  if (tab === 'alerts') return '지금 조치가 필요한 운영 이슈와 경고를 먼저 모아보는 화면입니다.';
  if (tab === 'watch-decision') return '신규 진입 태도와 집중 포인트만 짧게 정리한 판단 카드입니다.';
  return '오늘 시장 판단과 운영 포인트를 빠르게 읽는 브리핑 화면입니다.';
}

interface ScorecardSignalCandidate {
  signal: DomainSignal;
  symbol: string;
  compositeScore: number;
  decision: ReturnType<typeof describeScoreDecision>;
  tail: ReturnType<typeof tailRiskHeadline>;
  best: string[];
  risks: string[];
}

function buildScorecardCandidates(snapshot: ConsoleSnapshot): ScorecardSignalCandidate[] {
  return (snapshot.signals.signals || [])
    .map((signal) => {
      const scorecard = extractStrategyScorecard(
        signal.strategy_scorecard
        || signal.validation_snapshot?.strategy_scorecard
        || signal.validation_snapshot,
      );
      if (!scorecard || scorecard.compositeScore === null) return null;
      return {
        signal,
        symbol: formatSymbol(signal.code, signal.name),
        compositeScore: scorecard.compositeScore,
        decision: describeScoreDecision(scorecard),
        tail: tailRiskHeadline(scorecard),
        best: strongestComponents(scorecard).map((item) => item.label),
        risks: weakestComponents(scorecard).map((item) => item.label),
      } satisfies ScorecardSignalCandidate;
    })
    .filter((item): item is ScorecardSignalCandidate => Boolean(item))
    .sort((left, right) => {
      if (Boolean(right.signal.entry_allowed) !== Boolean(left.signal.entry_allowed)) {
        return Number(Boolean(right.signal.entry_allowed)) - Number(Boolean(left.signal.entry_allowed));
      }
      return right.compositeScore - left.compositeScore;
    });
}

function renderTodayReport(snapshot: ConsoleSnapshot) {
  const view = buildTodayReportView(snapshot);
  const signals = snapshot.signals.signals || [];
  const allowedCount = signals.filter((signal) => signal.entry_allowed).length;
  const blockedCount = signals.length - allowedCount;
  const totalSignals = Math.max(allowedCount + blockedCount, 1);
  const guardAllowed = Boolean(snapshot.engine.risk_guard_state?.entry_allowed);
  const riskLevel = String(snapshot.engine.allocator?.risk_level || snapshot.signals.risk_level || '-');
  const regime = String(snapshot.engine.allocator?.regime || snapshot.signals.regime || '-');
  const meterScore = riskScore(riskLevel);
  const topAction = view.actionItems[0];
  const modeLabel = guardAllowed ? (view.judgmentTitle || '중립') : '방어';
  const todayActions = view.actionItems.slice(0, 4);
  const avoidActions = [...view.watchPoints, ...view.judgmentLines]
    .filter((line, index, arr) => line && arr.indexOf(line) === index)
    .slice(0, 4);
  const evidenceLines = [...view.summaryLines, ...view.judgmentLines]
    .filter((line, index, arr) => line && arr.indexOf(line) === index)
    .slice(0, 6);
  const scorecardCandidates = buildScorecardCandidates(snapshot);
  const approvedScorecards = scorecardCandidates.filter((item) => item.signal.entry_allowed);
  const averageCompositeScore = approvedScorecards.length > 0
    ? approvedScorecards.reduce((sum, item) => sum + item.compositeScore, 0) / approvedScorecards.length
    : null;
  const topScorecard = approvedScorecards[0] || scorecardCandidates[0];
  const tailRiskWarningCount = approvedScorecards.filter((item) => item.tail.tone === 'bad').length;
  const worstTailCandidate = [...approvedScorecards]
    .sort((left, right) => {
      const leftTail = extractStrategyScorecard(left.signal.strategy_scorecard || left.signal.validation_snapshot?.strategy_scorecard || left.signal.validation_snapshot);
      const rightTail = extractStrategyScorecard(right.signal.strategy_scorecard || right.signal.validation_snapshot?.strategy_scorecard || right.signal.validation_snapshot);
      const leftEs = buildTailRiskRows(leftTail).find((row) => row.key === 'expected_shortfall_5_pct')?.value ?? 0;
      const rightEs = buildTailRiskRows(rightTail).find((row) => row.key === 'expected_shortfall_5_pct')?.value ?? 0;
      return leftEs - rightEs;
    })[0];

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div className="page-section report-hero-card report-decision-hero">
        <div className="report-hero-topline">
          <span className="report-hero-tag">Decision First</span>
          <span className="report-hero-meta">리포트 생성 {formatDateTime(view.generatedAt)}</span>
        </div>
        <div className="report-decision-title">오늘 결론: {modeLabel}</div>
        <div className="report-hero-copy">근거보다 실행 순서를 먼저 고정합니다. 지금은 {guardAllowed ? '허용된 진입만 선별 실행' : '신규 진입 중단과 보유 리스크 관리'}이 우선입니다.</div>
        <div className="report-decision-strip">
          <div className={`report-decision-chip ${guardAllowed ? 'is-good' : 'is-bad'}`}>
            진입 {guardAllowed ? '가능' : '제한'}
          </div>
          <div className="report-decision-chip">위험도 {riskLevel}</div>
          <div className="report-decision-chip">허용 {formatCount(allowedCount, '건')} / 차단 {formatCount(blockedCount, '건')}</div>
        </div>
      </div>

      {scorecardCandidates.length > 0 && (
        <>
          <div className="report-grid-3">
            <div className={`page-section report-visual-card ${topScorecard?.decision.tone === 'good' ? 'is-good' : topScorecard?.decision.tone === 'bad' ? 'is-bad' : ''}`}>
              <div className="report-card-title">허용 후보 평균 점수</div>
              <div className="report-card-value">{averageCompositeScore === null ? '-' : `${formatNumber(averageCompositeScore, 1)}점`}</div>
              <div className="report-card-copy">점수카드가 있는 허용 후보 {formatCount(approvedScorecards.length, '건')} 기준</div>
            </div>
            <div className={`page-section report-visual-card ${topScorecard?.tail.tone === 'good' ? 'is-good' : topScorecard?.tail.tone === 'bad' ? 'is-bad' : ''}`}>
              <div className="report-card-title">오늘 1순위 전략 상태</div>
              <div className="report-card-value">{topScorecard?.decision.label || '-'}</div>
              <div className="report-card-copy">{topScorecard ? `${topScorecard.symbol} · ${formatNumber(topScorecard.compositeScore, 1)}점` : '점수카드 후보 없음'}</div>
            </div>
            <div className={`page-section report-visual-card ${tailRiskWarningCount > 0 ? 'is-bad' : 'is-good'}`}>
              <div className="report-card-title">테일리스크 경고</div>
              <div className="report-card-value">{formatCount(tailRiskWarningCount, '건')}</div>
              <div className="report-card-copy">{worstTailCandidate ? `${worstTailCandidate.symbol}가 가장 깊은 꼬리손실 구간입니다.` : '허용 후보 기준 뚜렷한 꼬리손실 경고가 없습니다.'}</div>
            </div>
          </div>

          <div className="page-section" style={{ padding: 16 }}>
            <div className="section-head-row">
              <div>
                <div className="section-title">오늘 전략 점수판</div>
                <div className="section-copy">EV만 보지 않고 점수 구성과 꼬리손실까지 함께 확인하는 운영용 카드입니다.</div>
              </div>
              <div className="inline-badge">상위 {formatCount(Math.min(scorecardCandidates.length, 3), '건')}</div>
            </div>
            <div className="operator-note-grid" style={{ marginTop: 12 }}>
              {scorecardCandidates.slice(0, 3).map((item) => {
                const scorecard = extractStrategyScorecard(item.signal.strategy_scorecard || item.signal.validation_snapshot?.strategy_scorecard || item.signal.validation_snapshot);
                const componentRows = buildScoreComponentRows(scorecard).slice(0, 3);
                const tailRows = buildTailRiskRows(scorecard).slice(0, 2);
                return (
                  <div
                    key={`${item.signal.market || ''}:${item.signal.code || item.symbol}`}
                    className={`operator-note-card scorecard-candidate-card ${item.decision.tone === 'good' ? 'is-good' : item.decision.tone === 'bad' ? 'is-bad' : ''}`}
                  >
                    <div className="scorecard-candidate-head">
                      <div>
                        <div className="operator-note-label">{item.symbol}</div>
                        <div className="operator-note-copy">{item.signal.strategy_type || 'strategy'} · {item.signal.entry_allowed ? '진입 가능' : '차단'}</div>
                      </div>
                      <div className={`report-decision-chip ${item.signal.entry_allowed ? 'is-good' : 'is-bad'}`}>{item.decision.label}</div>
                    </div>

                    <div className="scorecard-kpi-row">
                      <div className="scorecard-kpi">
                        <span className="scorecard-kpi-label">복합 점수</span>
                        <span className="scorecard-kpi-value">{formatNumber(item.compositeScore, 1)}점</span>
                      </div>
                      <div className="scorecard-kpi">
                        <span className="scorecard-kpi-label">꼬리손실</span>
                        <span className={`scorecard-kpi-value is-${item.tail.tone}`}>{item.tail.label}</span>
                      </div>
                    </div>

                    <div className="scorecard-component-list is-compact">
                      {componentRows.map((row) => (
                        <div key={`${item.symbol}-${row.key}`} className={`scorecard-component-row is-${row.tone}`}>
                          <div className="scorecard-component-label">{row.label}</div>
                          <div className="scorecard-component-value">{row.value >= 0 ? '+' : ''}{formatNumber(row.value, 1)}점</div>
                        </div>
                      ))}
                    </div>

                    <div className="scorecard-tail-inline">
                      {tailRows.map((row) => (
                        <div key={`${item.symbol}-${row.key}`} className={`scorecard-tail-pill is-${row.tone}`}>
                          {row.label} {formatPercent(row.value, 1)}
                        </div>
                      ))}
                    </div>

                    <div className="operator-note-copy">
                      강점: {item.best.join(' · ') || '없음'}
                      <br />
                      주의: {item.risks.join(' · ') || item.tail.detail}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}

      <div className="report-grid-2">
        <div className="page-section report-visual-card">
          <div className="section-head-row">
            <div>
              <div className="section-title">오늘 실행</div>
              <div className="section-copy">지금 바로 처리할 액션</div>
            </div>
            <div className="inline-badge is-success">{formatCount(todayActions.length, '개')}</div>
          </div>
          <div className="operator-note-grid">
            {todayActions.map((item) => (
              <div
                key={item.label}
                className={`operator-note-card ${item.tone === 'good' ? 'is-good' : item.tone === 'bad' ? 'is-bad' : ''}`}
              >
                <div className="operator-note-label">{item.label}</div>
                <div className="operator-note-copy">{item.detail}</div>
              </div>
            ))}
            {todayActions.length === 0 && (
              <div className="operator-note-card">
                <div className="operator-note-label">실행 대기</div>
                <div className="operator-note-copy">오늘 액션 포인트가 아직 정리되지 않았습니다.</div>
              </div>
            )}
          </div>
        </div>

        <div className="page-section report-visual-card">
          <div className="section-head-row">
            <div>
              <div className="section-title">오늘 금지/회피</div>
              <div className="section-copy">수익 기회보다 손실 회피 우선</div>
            </div>
            <div className="inline-badge is-danger">{formatCount(avoidActions.length, '개')}</div>
          </div>
          <div className="watch-grid">
            {avoidActions.map((line, index) => (
              <div key={`avoid-${index}`} className="watch-card">{line}</div>
            ))}
            {avoidActions.length === 0 && <div className="watch-card">현재 강한 회피 시그널은 없습니다. 진입은 가드 기준을 유지하세요.</div>}
          </div>
        </div>
      </div>

      <div className="report-grid-3">
        <div className="page-section report-visual-card">
          <div className="report-card-title">운영 모드</div>
          <div className="report-card-value">{guardAllowed ? '진입 가능' : '진입 제한'}</div>
          <div className="report-card-copy">{regime} · 위험도 {riskLevel}</div>
          <div className="risk-meter">
            <div className="risk-meter-fill" style={{ width: `${meterScore}%` }} />
          </div>
        </div>

        <div className="page-section report-visual-card">
          <div className="report-card-title">허용 / 차단 신호</div>
          <div className="report-card-value">{formatCount(allowedCount, '건')} / {formatCount(blockedCount, '건')}</div>
          <div className="signal-balance-bar">
            <div className="signal-balance-segment is-good" style={{ width: ratioWidth(allowedCount, totalSignals) }} />
            <div className="signal-balance-segment is-bad" style={{ width: ratioWidth(blockedCount, totalSignals) }} />
          </div>
          <div className="report-card-copy">허용 {(allowedCount / totalSignals * 100).toFixed(0)}% · 차단 {(blockedCount / totalSignals * 100).toFixed(0)}%</div>
        </div>

        <div className="page-section report-visual-card">
          <div className="report-card-title">첫 액션</div>
          <div className="report-card-value">{topAction?.label || '대기'}</div>
          <div className="report-card-copy">{topAction?.detail || '오늘 액션 포인트가 아직 정리되지 않았습니다.'}</div>
        </div>
      </div>

      {!view.hasReportContent && (
        <div className="page-section" style={{ padding: 16 }}>
          <div style={{ fontSize: 14, fontWeight: 700 }}>{UI_TEXT.empty.reportNotReady}</div>
          <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-3)', lineHeight: 1.7 }}>
            {UI_TEXT.empty.reportNextStep}
          </div>
        </div>
      )}

      <div className="page-section report-evidence-card" style={{ padding: 16 }}>
        <div className="section-head-row">
          <div>
            <div className="section-title">근거 요약 (참고용)</div>
            <div className="section-copy">최종 의사결정 이후에만 확인하는 보조 근거</div>
          </div>
          <div className="inline-badge">{formatCount(evidenceLines.length, '줄')}</div>
        </div>
        <div className="report-brief-list is-compact">
          {renderIndexedBriefItems(evidenceLines, 'evidence')}
        </div>
      </div>

      <div className="report-grid-2">
        <div className="page-section" style={{ padding: 16 }}>
          <div className="section-title">시장 3줄 요약</div>
          <div className="report-brief-list is-compact">
            {renderIndexedBriefItems(view.summaryLines, 'summary')}
          </div>
        </div>
        <div className="page-section" style={{ padding: 16 }}>
          <div className="section-title">판단 근거</div>
          <div className="report-brief-list is-compact">
            {renderIndexedBriefItems(view.judgmentLines, 'judgment')}
          </div>
        </div>
      </div>
    </div>
  );
}

function severityTone(severity: number): 'good' | 'neutral' | 'bad' {
  if (severity >= 2) return 'bad';
  if (severity <= -1) return 'good';
  return 'neutral';
}

function renderAlerts(snapshot: ConsoleSnapshot) {
  const engineState = snapshot.engine.execution?.state || {};
  const riskGuard = snapshot.engine.risk_guard_state || snapshot.portfolio.risk_guard_state || {};
  const allocator = snapshot.engine.allocator || {};
  const notifications = snapshot.notifications || {};
  const validationSummary = snapshot.validation.summary || {};
  const allowedSignals = Number(allocator.entry_allowed_count || 0);
  const blockedSignals = Number(allocator.blocked_count || 0);
  const failedOrders = Number(engineState.today_order_counts?.failed || 0);
  const skippedCount = Number((engineState.last_summary as { skipped_count?: number } | undefined)?.skipped_count || 0);
  const isRunning = Boolean(engineState.running);
  const isPaused = engineState.engine_state === 'paused';
  const staleOptimized = Boolean(engineState.optimized_params?.is_stale);
  const guardBlocked = riskGuard.entry_allowed === false;
  const validationGateEnabled = Boolean(engineState.validation_policy?.validation_gate_enabled);
  const reliability = reliabilityToKorean(String(validationSummary.oos_reliability || '').toLowerCase());
  const notificationConfigured = Boolean(notifications.enabled && notifications.configured && notifications.chat_id_configured);
  const latestSignals = (snapshot.signals.signals || []).filter((item) => !item.entry_allowed).slice(0, 5);

  const alerts = [
    {
      key: 'engine',
      label: '엔진 상태',
      value: isRunning ? '실행 중' : isPaused ? '일시정지' : engineState.engine_state === 'error' ? '오류' : '중지',
      detail: engineState.last_error || (isRunning ? '자동 실행 루프가 동작 중입니다.' : '자동 실행이 멈춰 있습니다.'),
      severity: engineState.engine_state === 'error' ? 3 : (!isRunning ? 2 : 0),
    },
    {
      key: 'risk-guard',
      label: '신규 진입 제한',
      value: guardBlocked ? '차단' : '허용',
      detail: guardBlocked
        ? (riskGuard.reasons || []).map((reason) => reasonCodeToKorean(reason)).join(' · ') || '리스크 가드가 신규 진입을 막고 있습니다.'
        : '현재 기준으로 신규 진입이 가능합니다.',
      severity: guardBlocked ? 2 : -1,
    },
    {
      key: 'optimized',
      label: '최적화 파라미터',
      value: staleOptimized ? 'stale' : '정상',
      detail: staleOptimized
        ? `버전 ${String(engineState.optimized_params?.version || '-')} · 최신 최적화 재실행 권장`
        : `버전 ${String(engineState.optimized_params?.version || '-')} · ${formatDateTime(engineState.optimized_params?.optimized_at || '')}`,
      severity: staleOptimized ? 2 : -1,
    },
    {
      key: 'orders',
      label: '실패/스킵',
      value: `${formatCount(failedOrders, '건')} / ${formatCount(skippedCount, '건')}`,
      detail: `실패 주문 ${formatCount(failedOrders, '건')} · 최근 스킵 ${formatCount(skippedCount, '건')}`,
      severity: failedOrders > 0 || skippedCount >= 3 ? 2 : 0,
    },
    {
      key: 'validation',
      label: 'Validation Gate',
      value: validationGateEnabled ? '활성' : '비활성',
      detail: `OOS 신뢰도 ${reliability || '-'} · min trades ${formatCount(Number(engineState.validation_policy?.validation_min_trades || 0), '건')}`,
      severity: validationGateEnabled && String(validationSummary.oos_reliability || '').toLowerCase() === 'low' ? 2 : 0,
    },
    {
      key: 'notifications',
      label: '알림 채널',
      value: notifications.enabled ? '사용' : '꺼짐',
      detail: notifications.enabled
        ? notificationConfigured
          ? `${String(notifications.channel || 'channel')} 연결 완료`
          : `${String(notifications.channel || 'channel')} 설정 미완료`
        : '알림 발송이 비활성 상태입니다.',
      severity: notifications.enabled && !notificationConfigured ? 2 : (!notifications.enabled ? 1 : -1),
    },
  ];

  const actionLines = [
    !isRunning ? '엔진이 멈춰 있으면 모의투자 화면에서 상태를 확인하고 시작 여부를 결정하세요.' : '',
    guardBlocked ? '리스크 가드 차단 사유를 먼저 해소하거나 오늘은 신규 진입 없이 운영하세요.' : '',
    staleOptimized ? '최적화 파라미터가 stale 상태면 검증 화면에서 최적화를 다시 돌리는 편이 안전합니다.' : '',
    failedOrders > 0 ? '실패 주문이 있으면 최근 체결 내역과 엔진 이벤트 로그를 먼저 확인하세요.' : '',
    notifications.enabled && !notificationConfigured ? '텔레그램 알림이 미완료 상태라면 운영 전에 채널 설정부터 맞추는 게 좋습니다.' : '',
  ].filter(Boolean);

  const riskReasons = (riskGuard.reasons || []).map((reason) => reasonCodeToKorean(reason));
  const blockedReasonLines = latestSignals.flatMap((signal) => (signal.reason_codes || []).map((reason) => `${formatSymbol(signal.code, signal.name)} · ${reasonCodeToKorean(reason)}`));

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div className="page-section report-hero-card report-decision-hero">
        <div className="report-hero-topline">
          <span className="report-hero-tag">Alert First</span>
          <span className="report-hero-meta">운영 경고 우선 확인</span>
        </div>
        <div className="report-decision-title">지금 조치 필요: {alerts.filter((item) => item.severity >= 2).length}건</div>
        <div className="report-hero-copy">액션보드 대신 실제 운영에 영향을 주는 경고만 앞으로 모았습니다. 엔진 상태, 진입 차단, stale optimization, 실패 주문, 알림 이상부터 먼저 확인하면 됩니다.</div>
        <div className="report-decision-strip">
          <div className={`report-decision-chip ${isRunning ? 'is-good' : 'is-bad'}`}>엔진 {isRunning ? '실행 중' : '정지'}</div>
          <div className={`report-decision-chip ${guardBlocked ? 'is-bad' : 'is-good'}`}>진입 {guardBlocked ? '차단' : '허용'}</div>
          <div className={`report-decision-chip ${failedOrders > 0 ? 'is-bad' : 'is-good'}`}>실패 주문 {formatCount(failedOrders, '건')}</div>
        </div>
      </div>

      <div className="report-grid-3">
        {alerts.map((item) => (
          <div key={item.key} className={`page-section report-visual-card ${severityTone(item.severity) === 'bad' ? 'is-bad' : severityTone(item.severity) === 'good' ? 'is-good' : ''}`}>
            <div className="report-card-title">{item.label}</div>
            <div className="report-card-value">{item.value}</div>
            <div className="report-card-copy">{item.detail}</div>
          </div>
        ))}
      </div>

      <div className="report-grid-2">
        <div className="page-section report-visual-card">
          <div className="section-head-row">
            <div>
              <div className="section-title">지금 바로 할 일</div>
              <div className="section-copy">운영자가 바로 처리할 항목만 추렸습니다.</div>
            </div>
            <div className="inline-badge is-danger">{formatCount(actionLines.length, '개')}</div>
          </div>
          <div className="watch-grid">
            {actionLines.map((line, index) => (
              <div key={`action-${index}`} className="watch-card">{line}</div>
            ))}
            {actionLines.length === 0 && <div className="watch-card">지금 당장 조치가 필요한 운영 이슈는 크지 않습니다.</div>}
          </div>
        </div>

        <div className="page-section report-visual-card">
          <div className="section-head-row">
            <div>
              <div className="section-title">운영 기준값</div>
              <div className="section-copy">현재 런타임이 보는 핵심 기준입니다.</div>
            </div>
            <div className="inline-badge">실시간</div>
          </div>
          <div className="detail-list">
            <div>허용 / 차단 신호: {formatCount(allowedSignals, '건')} / {formatCount(blockedSignals, '건')}</div>
            <div>다음 실행 시각: {formatDateTime(engineState.next_run_at || '')}</div>
            <div>최근 성공 시각: {formatDateTime(engineState.last_success_at || '')}</div>
            <div>오늘 실현손익: {formatNumber(Number(engineState.today_realized_pnl || 0), 0)}원</div>
            <div>일일 손실 잔여: {formatNumber(Number(riskGuard.daily_loss_left || 0), 0)}원</div>
          </div>
        </div>
      </div>

      <div className="report-grid-2">
        <div className="page-section" style={{ padding: 16 }}>
          <div className="section-title">리스크 가드 사유</div>
          <div className="report-brief-list is-compact">
            {riskReasons.length > 0 ? renderIndexedBriefItems(riskReasons.slice(0, 6), 'risk-reason') : <div className="watch-card">현재 강한 차단 사유는 없습니다.</div>}
          </div>
        </div>

        <div className="page-section" style={{ padding: 16 }}>
          <div className="section-title">최근 차단 신호 예시</div>
          <div className="report-brief-list is-compact">
            {blockedReasonLines.length > 0 ? renderIndexedBriefItems(blockedReasonLines.slice(0, 6), 'blocked-signal') : <div className="watch-card">최근 차단 신호가 많지 않습니다.</div>}
          </div>
        </div>
      </div>

      <div className="page-section report-evidence-card" style={{ padding: 16 }}>
        <div className="section-head-row">
          <div>
            <div className="section-title">알림 채널 상태</div>
            <div className="section-copy">문제가 생기면 운영자가 놓치기 쉬운 부분입니다.</div>
          </div>
          <div className={`inline-badge ${notificationConfigured ? 'is-success' : 'is-warning'}`}>{notificationConfigured ? '정상' : '점검 필요'}</div>
        </div>
        <div className="detail-list">
          <div>채널: {String(notifications.channel || '-')}</div>
          <div>enabled: {notifications.enabled ? 'true' : 'false'}</div>
          <div>configured: {notifications.configured ? 'true' : 'false'}</div>
          <div>chat_id_configured: {notifications.chat_id_configured ? 'true' : 'false'}</div>
          <div>last_sent_at: {formatDateTime(notifications.last_sent_at || '')}</div>
          <div>last_error: {String(notifications.last_error || '-')}</div>
        </div>
      </div>
    </div>
  );
}

function renderWatchDecision(snapshot: ConsoleSnapshot) {
  const view = buildWatchDecisionView(snapshot);
  const guardAllowed = Boolean(snapshot.engine.risk_guard_state?.entry_allowed);
  const riskLevel = String(snapshot.engine.allocator?.risk_level || snapshot.signals.risk_level || '-');
  const allowedCount = (snapshot.signals.signals || []).filter((signal) => signal.entry_allowed).length;

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div className="page-section report-hero-card">
        <div className="report-hero-topline">
          <span className="report-hero-tag">Watch Decision</span>
          <span className="report-hero-meta">진입 태도 요약</span>
        </div>
        <div className="report-hero-title-row">
          <div>
            <div className="report-hero-title">관망/관심목표 판단</div>
            <div className="report-hero-copy">오늘 신규 진입 태도와 집중 포인트만 남겨 둔 짧은 판단 화면입니다.</div>
          </div>
          <div className={`report-mode-chip is-${view.mode === '공격' ? 'good' : view.mode === '관망' ? 'bad' : 'neutral'}`}>
            {view.mode}
          </div>
        </div>
      </div>

      <div className="report-grid-3">
        <div className="page-section report-visual-card">
          <div className="report-card-title">신규 진입</div>
          <div className="report-card-value">{guardAllowed ? '가능' : '제한'}</div>
          <div className="report-card-copy">리스크 가드 기준</div>
        </div>
        <div className="page-section report-visual-card">
          <div className="report-card-title">위험도</div>
          <div className="report-card-value">{riskLevel}</div>
          <div className="report-card-copy">allocator / signals 기준</div>
        </div>
        <div className="page-section report-visual-card">
          <div className="report-card-title">허용 신호</div>
          <div className="report-card-value">{formatCount(allowedCount, '건')}</div>
          <div className="report-card-copy">오늘 진입 후보 수</div>
        </div>
      </div>

      <div className="page-section report-rationale-card" style={{ padding: 16 }}>
        <div className="section-title">판단 근거</div>
        <div className="report-brief-list is-compact">
          {renderIndexedBriefItems(view.rationale, 'rationale')}
        </div>
      </div>
    </div>
  );
}

export function ReportsPage({ snapshot, loading, errorMessage, reportTab, onRefresh }: ReportsPageProps) {
  const body: ReactNode = useMemo(() => {
    if (reportTab === 'alerts') {
      return renderAlerts(snapshot);
    }
    if (reportTab === 'watch-decision') {
      return renderWatchDecision(snapshot);
    }
    return renderTodayReport(snapshot);
  }, [reportTab, snapshot]);

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell" style={{ display: 'grid', gap: 16 }}>
          <div className="page-section reports-toolbar">
            <div>
              <div className="section-kicker">Decision Report</div>
              <div className="section-title">{tabHeadline(reportTab)}</div>
              <div className="section-copy">{tabDescription(reportTab)}</div>
            </div>
            <div className="reports-toolbar-actions">
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>
                콘솔 데이터 기준 시각 {formatDateTime(snapshot.fetchedAt)}
              </div>
              <button className="ghost-button" onClick={onRefresh}>{UI_TEXT.common.refresh}</button>
            </div>
          </div>

          {errorMessage && reportCauseCard(onRefresh, errorMessage)}
          {body}
          {loading && <div style={{ color: 'var(--text-3)', fontSize: 12 }}>{UI_TEXT.common.loading}</div>}
        </div>
      </div>
    </div>
  );
}
