import { buildWatchDecisionView, isRiskEntryAllowed } from '../adapters/consoleViewAdapter';
import { UI_TEXT } from '../constants/uiText';
import { formatCount, formatDateTimeWithAge } from '../utils/format';
import type { ConsoleSnapshot } from '../types/consoleView';

interface ReportsPageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
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

function renderWatchDecision(snapshot: ConsoleSnapshot) {
  const view = buildWatchDecisionView(snapshot);
  const guardAllowed = isRiskEntryAllowed(snapshot);
  const riskLevel = String(snapshot.engine.allocator?.risk_level || snapshot.signals.risk_level || '-');
  const signalsAsOf = snapshot.signals.generated_at || snapshot.fetchedAt;

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div className="page-section report-hero-card report-decision-hero">
        <div className="report-hero-topline">
          <span className="report-hero-tag">Research Queue</span>
          <span className="report-hero-meta">신호 기준 {formatDateTimeWithAge(signalsAsOf)}</span>
        </div>
        <div className="report-hero-title-row">
          <div>
            <div className="report-hero-title">관심 시나리오</div>
            <div className="report-hero-copy">이제 이 탭은 짧은 모드 문장만 보여주는 화면이 아니라, 오늘 다시 볼 허용 후보와 아직 비진입 관찰 후보를 나눠 두는 research queue로 읽으면 됩니다. 매수 확정판이 아니라 우선순위 정리판에 가깝습니다.</div>
          </div>
          <div className={`report-mode-chip is-${view.mode === '공격' ? 'good' : view.mode === '관망' ? 'bad' : 'neutral'}`}>
            {view.mode}
          </div>
        </div>
        <div className="report-decision-strip">
          <div className={`report-decision-chip ${guardAllowed ? 'is-good' : 'is-bad'}`}>신규 진입 {guardAllowed ? '가능' : '제한'}</div>
          <div className="report-decision-chip">위험도 {riskLevel}</div>
          <div className="report-decision-chip">허용 {formatCount(view.allowedCount, '건')} / 차단 {formatCount(view.blockedCount, '건')} / 관찰 {formatCount(view.observeCount, '건')}</div>
        </div>
      </div>

      <div className="report-grid-3">
        <div className="page-section report-visual-card">
          <div className="report-card-title">오늘 태도</div>
          <div className="report-card-value">{view.stanceTitle}</div>
          <div className="report-card-copy">{view.stanceSummary}</div>
        </div>
        <div className="page-section report-visual-card">
          <div className="report-card-title">지금 볼 허용 후보</div>
          <div className="report-card-value">{formatCount(view.focusCandidates.length, '건')}</div>
          <div className="report-card-copy">진입 가능 신호 중 EV/점수 상위 후보만 먼저 올렸습니다.</div>
        </div>
        <div className="page-section report-visual-card">
          <div className="report-card-title">지켜볼 관찰 후보</div>
          <div className="report-card-value">{formatCount(view.observeCandidates.length, '건')}</div>
          <div className="report-card-copy">아직 비진입 상태라 바로 주문하지 않고 조건 변화만 추적할 후보입니다.</div>
        </div>
      </div>

      <div className="report-grid-2">
        <div className="page-section report-visual-card">
          <div className="section-head-row">
            <div>
              <div className="section-title">지금 볼 허용 후보</div>
              <div className="section-copy">바로 진입한다는 뜻이 아니라, 오늘 우선순위로 다시 확인할 후보입니다.</div>
            </div>
            <div className="inline-badge is-success">{formatCount(view.focusCandidates.length, '건')}</div>
          </div>
          <div className="operator-note-grid">
            {view.focusCandidates.map((item) => (
              <div key={item.key} className="operator-note-card watch-scenario-card is-good">
                <div className="scorecard-candidate-head">
                  <div>
                    <div className="operator-note-label">{item.symbol}</div>
                    <div className="operator-note-copy">{item.market} · {item.strategyLabel}</div>
                  </div>
                  <div className="inline-badge is-success">{item.actionLabel}</div>
                </div>
                <div className="signal-chip-row">
                  {item.chips.map((chip) => <span key={`${item.key}-${chip}`} className="signal-meta-chip">{chip}</span>)}
                </div>
                <div className="operator-note-copy">
                  <strong style={{ color: 'var(--text-1)' }}>핵심 포인트</strong> {item.primaryReason}
                  <br />
                  {item.secondaryDetail}
                </div>
              </div>
            ))}
            {view.focusCandidates.length === 0 && (
              <div className="operator-note-card">
                <div className="operator-note-label">허용 후보 없음</div>
                <div className="operator-note-copy">현재는 신규 진입보다 기존 포지션 관리와 차단 사유 확인이 우선입니다.</div>
              </div>
            )}
          </div>
        </div>

        <div className="page-section report-visual-card">
          <div className="section-head-row">
            <div>
              <div className="section-title">지켜볼 관찰 후보</div>
              <div className="section-copy">차단 또는 비진입 상태라 우선순위만 유지하는 관찰 리스트입니다.</div>
            </div>
            <div className="inline-badge is-warning">{formatCount(view.observeCandidates.length, '건')}</div>
          </div>
          <div className="operator-note-grid">
            {view.observeCandidates.map((item) => (
              <div key={item.key} className="operator-note-card watch-scenario-card is-bad">
                <div className="scorecard-candidate-head">
                  <div>
                    <div className="operator-note-label">{item.symbol}</div>
                    <div className="operator-note-copy">{item.market} · {item.strategyLabel}</div>
                  </div>
                  <div className="inline-badge is-danger">{item.actionLabel}</div>
                </div>
                <div className="signal-chip-row">
                  {item.chips.map((chip) => <span key={`${item.key}-${chip}`} className="signal-meta-chip">{chip}</span>)}
                </div>
                <div className="operator-note-copy">
                  <strong style={{ color: 'var(--text-1)' }}>관찰 이유</strong> {item.primaryReason}
                  <br />
                  {item.secondaryDetail}
                </div>
              </div>
            ))}
            {view.observeCandidates.length === 0 && (
              <div className="operator-note-card">
                <div className="operator-note-label">관찰 후보 적음</div>
                <div className="operator-note-copy">오늘은 허용 후보 우선순위만 빠르게 정리해도 충분합니다.</div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="page-section report-rationale-card" style={{ padding: 16 }}>
        <div className="section-head-row">
          <div>
            <div className="section-title">추가 리서치 체크리스트</div>
            <div className="section-copy">이 탭을 본 뒤 바로 신호 화면이나 포트폴리오 화면으로 넘어갈 때 체크할 항목입니다.</div>
          </div>
          <div className="inline-badge">{formatCount(view.researchQueue.length, '줄')}</div>
        </div>
        <div className="report-brief-list is-compact">
          {renderIndexedBriefItems(view.researchQueue, 'research-queue')}
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

export function ReportsPage({ snapshot, loading, errorMessage, onRefresh }: ReportsPageProps) {
  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell" style={{ display: 'grid', gap: 16 }}>
          <div className="page-section reports-toolbar">
            <div>
              <div className="section-kicker">Investment Research</div>
              <div className="section-title">관심 시나리오</div>
              <div className="section-copy">이 화면은 오늘 다시 볼 허용 후보와 관찰 후보를 우선순위대로 정리하는 research queue야.</div>
            </div>
            <div className="reports-toolbar-actions">
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>
                콘솔 기준 {formatDateTimeWithAge(snapshot.fetchedAt)}
              </div>
              <button className="ghost-button" onClick={onRefresh}>{UI_TEXT.common.refresh}</button>
            </div>
          </div>

          {errorMessage && reportCauseCard(onRefresh, errorMessage)}
          {renderWatchDecision(snapshot)}
          {loading && <div style={{ color: 'var(--text-3)', fontSize: 12 }}>{UI_TEXT.common.loading}</div>}
        </div>
      </div>
    </div>
  );
}
