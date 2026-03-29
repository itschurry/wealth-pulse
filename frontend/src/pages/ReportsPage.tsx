import {
  buildActionBoardView,
  buildTodayReportView,
  buildWatchDecisionView,
} from '../adapters/consoleViewAdapter';
import type { ReactNode } from 'react';
import { UI_TEXT } from '../constants/uiText';
import { formatDateTime } from '../utils/format';
import type { ConsoleSnapshot } from '../types/consoleView';
import type { ReportTab } from '../types/navigation';

interface ReportsPageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  reportTab: ReportTab;
  onRefresh: () => void;
}

function renderTodayReport(snapshot: ConsoleSnapshot) {
  const view = buildTodayReportView(snapshot);
  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div className="page-section" style={{ padding: 18 }}>
        <div style={{ fontSize: 22, fontWeight: 800 }}>{UI_TEXT.reportTabs.todayReport}</div>
        <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 6 }}>
          리포트 생성 시각 {formatDateTime(view.generatedAt)}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
        {view.statusItems.map((item) => (
          <div
            key={item.label}
            className="page-section"
            style={{
              padding: 16,
              borderColor: item.tone === 'good'
                ? 'var(--up-border)'
                : item.tone === 'bad'
                  ? 'var(--down-border)'
                  : undefined,
              background: item.tone === 'good'
                ? 'var(--up-bg)'
                : item.tone === 'bad'
                  ? 'var(--down-bg)'
                  : undefined,
            }}
          >
            <div style={{ fontSize: 12, color: 'var(--text-4)' }}>{item.label}</div>
            <div style={{ marginTop: 8, fontSize: 18, fontWeight: 800 }}>{item.value}</div>
          </div>
        ))}
      </div>

      {!view.hasReportContent && (
        <div className="page-section" style={{ padding: 16 }}>
          <div style={{ fontSize: 14, fontWeight: 700 }}>{UI_TEXT.empty.reportNotReady}</div>
          <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-3)', lineHeight: 1.7 }}>
            {UI_TEXT.empty.reportNextStep}
          </div>
        </div>
      )}

      <div className="page-section" style={{ padding: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>오늘 시장 요약</div>
        <div style={{ marginTop: 10, display: 'grid', gap: 8, fontSize: 13, color: 'var(--text-2)', lineHeight: 1.7 }}>
          {view.summaryLines.map((line, idx) => (
            <div key={`summary-${idx}`} style={{ borderBottom: '1px solid var(--border-light)', paddingBottom: 8 }}>
              {line}
            </div>
          ))}
        </div>
      </div>

      <div className="page-section" style={{ padding: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>오늘의 판단</div>
        <div style={{ marginTop: 8, fontSize: 20, fontWeight: 800, color: 'var(--accent)' }}>{view.judgmentTitle}</div>
        <div style={{ marginTop: 10, display: 'grid', gap: 8, fontSize: 13, color: 'var(--text-2)' }}>
          {view.judgmentLines.map((line, idx) => (
            <div key={`judgment-${idx}`} style={{ borderBottom: '1px solid var(--border-light)', paddingBottom: 8 }}>
              {line}
            </div>
          ))}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12 }}>
        {view.actionItems.map((item) => (
          <div
            key={item.label}
            className="page-section"
            style={{
              padding: 16,
              borderColor: item.tone === 'good'
                ? 'var(--up-border)'
                : item.tone === 'bad'
                  ? 'var(--down-border)'
                  : undefined,
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 700 }}>{item.label}</div>
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-3)', lineHeight: 1.7 }}>{item.detail}</div>
          </div>
        ))}
      </div>

      <div className="page-section" style={{ padding: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>관망/주의/집중 포인트</div>
        <div style={{ marginTop: 10, display: 'grid', gap: 8, fontSize: 13, color: 'var(--down)' }}>
          {view.watchPoints.map((line, idx) => (
            <div key={`watch-${idx}`} style={{ borderBottom: '1px solid var(--border-light)', paddingBottom: 8 }}>
              {line}
            </div>
          ))}
        </div>
      </div>

      <div className="page-section" style={{ padding: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>기준 시각</div>
        <div style={{ marginTop: 10, display: 'grid', gap: 6, fontSize: 12, color: 'var(--text-3)' }}>
          <div>콘솔 데이터 기준 시각: {formatDateTime(view.dataAsOf)}</div>
          <div>리포트 생성 시각: {formatDateTime(view.generatedAt)}</div>
        </div>
      </div>
    </div>
  );
}

function renderActionBoard(snapshot: ConsoleSnapshot) {
  const view = buildActionBoardView(snapshot);
  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div className="page-section" style={{ padding: 18 }}>
        <div style={{ fontSize: 22, fontWeight: 800 }}>{UI_TEXT.reportTabs.actionBoard}</div>
        <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-4)' }}>
          실행 전 확인해야 할 규칙과 체크리스트를 정리했습니다.
        </div>
      </div>

      <div className="page-section" style={{ padding: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>오늘의 기본 행동 규칙</div>
        <div style={{ marginTop: 10, display: 'grid', gap: 8, fontSize: 13, color: 'var(--text-2)' }}>
          {view.rules.map((rule, idx) => (
            <div key={`rule-${idx}`}>{rule}</div>
          ))}
        </div>
      </div>

      <div className="page-section" style={{ padding: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>체크리스트</div>
        <div style={{ marginTop: 10, display: 'grid', gap: 10 }}>
          {view.checklist.map((item, idx) => (
            <div key={`check-${idx}`} style={{ border: '1px solid var(--border)', borderRadius: 12, padding: 10 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: item.done ? 'var(--up)' : 'var(--down)' }}>
                {item.done ? '완료' : '확인 필요'} · {item.label}
              </div>
              <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-3)' }}>{item.detail}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function renderWatchDecision(snapshot: ConsoleSnapshot) {
  const view = buildWatchDecisionView(snapshot);
  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div className="page-section" style={{ padding: 18 }}>
        <div style={{ fontSize: 22, fontWeight: 800 }}>{UI_TEXT.reportTabs.watchDecision}</div>
        <div style={{ marginTop: 8, fontSize: 20, fontWeight: 800, color: 'var(--accent)' }}>{view.mode}</div>
      </div>

      <div className="page-section" style={{ padding: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>판단 근거</div>
        <div style={{ marginTop: 10, display: 'grid', gap: 8, fontSize: 13, color: 'var(--text-2)' }}>
          {view.rationale.map((line, idx) => (
            <div key={`rationale-${idx}`}>{line}</div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function ReportsPage({ snapshot, loading, errorMessage, reportTab, onRefresh }: ReportsPageProps) {
  let body: ReactNode;
  if (reportTab === 'action-board') {
    body = renderActionBoard(snapshot);
  } else if (reportTab === 'watch-decision') {
    body = renderWatchDecision(snapshot);
  } else {
    body = renderTodayReport(snapshot);
  }

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell" style={{ display: 'grid', gap: 16 }}>
          <div className="page-section" style={{ padding: 14, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ fontSize: 12, color: 'var(--text-4)' }}>
              콘솔 데이터 기준 시각 {formatDateTime(snapshot.fetchedAt)}
            </div>
            <button className="ghost-button" onClick={onRefresh}>{UI_TEXT.common.refresh}</button>
          </div>
          {body}
          {loading && <div style={{ color: 'var(--text-3)', fontSize: 12 }}>{UI_TEXT.common.loading}</div>}
          {errorMessage && <div style={{ color: 'var(--down)', fontSize: 12 }}>{errorMessage}</div>}
        </div>
      </div>
    </div>
  );
}
