import { startTransition, useMemo, useState } from 'react';
import {
  buildActionBoardView,
  buildTodayReportView,
  buildWatchDecisionView,
} from '../adapters/consoleViewAdapter';
import type { ReactNode } from 'react';
import { UI_TEXT } from '../constants/uiText';
import { formatCount, formatDateTime } from '../utils/format';
import type { ConsoleSnapshot } from '../types/consoleView';
import type { ReportTab } from '../types/navigation';

interface ReportsPageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  reportTab: ReportTab;
  onRefresh: () => void;
}

interface CustomChecklistItem {
  id: string;
  label: string;
  detail: string;
}

const ACTION_BOARD_STATE_KEY = 'reports_action_board_state_v1';

function readActionBoardState() {
  try {
    const raw = JSON.parse(localStorage.getItem(ACTION_BOARD_STATE_KEY) || 'null') as {
      done?: Record<string, boolean>;
      custom?: CustomChecklistItem[];
    } | null;
    return {
      done: raw?.done || {},
      custom: Array.isArray(raw?.custom) ? raw?.custom : [],
    };
  } catch {
    return { done: {}, custom: [] as CustomChecklistItem[] };
  }
}

function persistActionBoardState(done: Record<string, boolean>, custom: CustomChecklistItem[]) {
  localStorage.setItem(ACTION_BOARD_STATE_KEY, JSON.stringify({ done, custom }));
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
  if (tab === 'action-board') return '액션보드';
  if (tab === 'watch-decision') return '관망/관심목표 판단';
  return '오늘 리포트';
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

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div className="page-section report-hero-card">
        <div className="report-hero-topline">
          <span className="report-hero-tag">오늘의 판단</span>
          <span className="report-hero-meta">리포트 생성 {formatDateTime(view.generatedAt)}</span>
        </div>
        <div className="report-hero-title-row">
          <div>
            <div className="report-hero-title">오늘 리포트</div>
            <div className="report-hero-copy">시장 요약, 리스크 가드, 허용 신호 비율을 한 화면에서 점검합니다.</div>
          </div>
          <div className={`report-mode-chip is-${view.judgmentTitle === '공격' ? 'good' : view.judgmentTitle === '관망' ? 'bad' : 'neutral'}`}>
            {view.judgmentTitle}
          </div>
        </div>
      </div>

      <div className="report-grid-3">
        <div className="page-section report-visual-card">
          <div className="report-card-title">리스크 가드 / 장세</div>
          <div className="report-card-value">{guardAllowed ? '진입 가능' : '진입 제한'}</div>
          <div className="report-card-copy">{regime} · 위험도 {riskLevel}</div>
          <div className="risk-meter">
            <div className="risk-meter-fill" style={{ width: `${meterScore}%` }} />
          </div>
          <div className="risk-meter-scale">
            <span>방어</span>
            <span>중립</span>
            <span>주의</span>
          </div>
        </div>

        <div className="page-section report-visual-card">
          <div className="report-card-title">허용 / 차단 신호</div>
          <div className="report-card-value">{formatCount(allowedCount, '건')} / {formatCount(blockedCount, '건')}</div>
          <div className="signal-balance-bar">
            <div className="signal-balance-segment is-good" style={{ width: ratioWidth(allowedCount, totalSignals) }} />
            <div className="signal-balance-segment is-bad" style={{ width: ratioWidth(blockedCount, totalSignals) }} />
          </div>
          <div className="report-card-copy">허용 비율 {(allowedCount / totalSignals * 100).toFixed(0)}% · 차단 비율 {(blockedCount / totalSignals * 100).toFixed(0)}%</div>
        </div>

        <div className="page-section report-visual-card">
          <div className="report-card-title">핵심 행동 가이드</div>
          <div className="report-card-value">{view.actionItems[0]?.label || '오늘 해야 할 일'}</div>
          <div className="report-card-copy">{view.actionItems[0]?.detail || '오늘 해야 할 작업이 아직 정리되지 않았습니다.'}</div>
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

      <div className="report-grid-2">
        <div className="page-section" style={{ padding: 16 }}>
          <div className="section-title">오늘 시장 요약</div>
          <div className="report-brief-list">
            {view.summaryLines.map((line, index) => (
              <div key={`summary-${index}`} className="report-brief-item">{line}</div>
            ))}
          </div>
        </div>

        <div className="page-section" style={{ padding: 16 }}>
          <div className="section-title">오늘의 판단 근거</div>
          <div className="report-brief-list">
            {view.judgmentLines.map((line, index) => (
              <div key={`judgment-${index}`} className="report-brief-item">{line}</div>
            ))}
          </div>
        </div>
      </div>

      <div className="report-grid-3">
        {view.actionItems.map((item) => (
          <div
            key={item.label}
            className={`page-section report-visual-card ${item.tone === 'good' ? 'is-good' : item.tone === 'bad' ? 'is-bad' : ''}`}
          >
            <div className="report-card-title">{item.label}</div>
            <div className="report-card-copy" style={{ marginTop: 12 }}>{item.detail}</div>
          </div>
        ))}
      </div>

      <div className="page-section" style={{ padding: 16 }}>
        <div className="section-title">관망/주의/집중 포인트</div>
        <div className="watch-grid">
          {view.watchPoints.map((line, index) => (
            <div key={`watch-${index}`} className="watch-card">{line}</div>
          ))}
        </div>
      </div>

      <div className="page-section" style={{ padding: 16 }}>
        <div className="section-title">기준 시각</div>
        <div className="detail-list">
          <div>콘솔 데이터 기준 시각: {formatDateTime(view.dataAsOf)}</div>
          <div>리포트 생성 시각: {formatDateTime(view.generatedAt)}</div>
        </div>
      </div>
    </div>
  );
}

function renderActionBoard(
  snapshot: ConsoleSnapshot,
  doneMap: Record<string, boolean>,
  customItems: CustomChecklistItem[],
  onToggle: (id: string, next: boolean) => void,
  newItemLabel: string,
  setNewItemLabel: (value: string) => void,
  newItemDetail: string,
  setNewItemDetail: (value: string) => void,
  onAddItem: () => void,
  onRemoveItem: (id: string) => void,
) {
  const view = buildActionBoardView(snapshot);
  const checklist = [
    ...view.checklist.map((item, index) => ({
      id: `base-${index}`,
      label: item.label,
      detail: item.detail,
      done: doneMap[`base-${index}`] ?? item.done,
      custom: false,
    })),
    ...customItems.map((item) => ({
      id: item.id,
      label: item.label,
      detail: item.detail,
      done: doneMap[item.id] ?? false,
      custom: true,
    })),
  ];

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div className="page-section report-hero-card">
        <div className="report-hero-topline">
          <span className="report-hero-tag">Action Board</span>
          <span className="report-hero-meta">운영 전 체크리스트와 실행 규칙</span>
        </div>
        <div className="report-hero-title">액션보드</div>
        <div className="report-hero-copy">완료 여부를 직접 기록하고, 운영자 전용 항목을 추가할 수 있습니다.</div>
      </div>

      <div className="page-section" style={{ padding: 16 }}>
        <div className="section-title">오늘의 기본 행동 규칙</div>
        <div className="report-brief-list">
          {view.rules.map((rule, index) => (
            <div key={`rule-${index}`} className="report-brief-item">{rule}</div>
          ))}
        </div>
      </div>

      <div className="page-section" style={{ padding: 16 }}>
        <div className="section-head-row">
          <div>
            <div className="section-title">체크리스트</div>
            <div className="section-copy">키보드와 버튼으로 바로 완료 상태를 변경할 수 있습니다.</div>
          </div>
          <div className="inline-badge is-success">
            완료 {formatCount(checklist.filter((item) => item.done).length, '건')}
          </div>
        </div>

        <div className="action-checklist-grid">
          {checklist.map((item) => (
            <div key={item.id} className={`checklist-card ${item.done ? 'is-done' : ''}`}>
              <button
                type="button"
                className={`checklist-toggle ${item.done ? 'is-done' : ''}`}
                onClick={() => onToggle(item.id, !item.done)}
                aria-pressed={item.done}
                aria-label={`${item.label} ${item.done ? '미완료로 변경' : '완료로 변경'}`}
              >
                {item.done ? '완료' : '확인 필요'}
              </button>
              <div className="checklist-title">{item.label}</div>
              <div className="checklist-copy">{item.detail}</div>
              {item.custom && (
                <button type="button" className="ghost-button" onClick={() => onRemoveItem(item.id)}>
                  항목 삭제
                </button>
              )}
            </div>
          ))}
        </div>

        <div className="custom-checklist-form">
          <input
            className="console-search-input"
            placeholder="추가 체크 항목 제목"
            value={newItemLabel}
            onChange={(event) => setNewItemLabel(event.target.value)}
            aria-label="추가 체크 항목 제목"
          />
          <input
            className="console-search-input"
            placeholder="세부 메모 또는 확인 기준"
            value={newItemDetail}
            onChange={(event) => setNewItemDetail(event.target.value)}
            aria-label="추가 체크 항목 메모"
          />
          <button className="console-action-button is-primary" onClick={onAddItem}>
            항목 추가
          </button>
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
          <span className="report-hero-meta">현재 운용 모드와 집중 포인트</span>
        </div>
        <div className="report-hero-title-row">
          <div>
            <div className="report-hero-title">관망/관심목표 판단</div>
            <div className="report-hero-copy">신규 진입 여건과 신호 밀도를 기준으로 오늘의 운영 태도를 정리했습니다.</div>
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
          <div className="report-card-copy">리스크 가드 기준 상태</div>
        </div>
        <div className="page-section report-visual-card">
          <div className="report-card-title">위험도</div>
          <div className="report-card-value">{riskLevel}</div>
          <div className="report-card-copy">콘솔 allocator / signals 기준</div>
        </div>
        <div className="page-section report-visual-card">
          <div className="report-card-title">허용 신호</div>
          <div className="report-card-value">{formatCount(allowedCount, '건')}</div>
          <div className="report-card-copy">오늘 진입 후보 신호 수</div>
        </div>
      </div>

      <div className="page-section" style={{ padding: 16 }}>
        <div className="section-title">판단 근거</div>
        <div className="report-brief-list">
          {view.rationale.map((line, index) => (
            <div key={`rationale-${index}`} className="report-brief-item">{line}</div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function ReportsPage({ snapshot, loading, errorMessage, reportTab, onRefresh }: ReportsPageProps) {
  const initialActionBoardState = useMemo(() => readActionBoardState(), []);
  const [doneMap, setDoneMap] = useState<Record<string, boolean>>(initialActionBoardState.done);
  const [customItems, setCustomItems] = useState<CustomChecklistItem[]>(initialActionBoardState.custom);
  const [newItemLabel, setNewItemLabel] = useState('');
  const [newItemDetail, setNewItemDetail] = useState('');

  const body: ReactNode = useMemo(() => {
    if (reportTab === 'action-board') {
      return renderActionBoard(
        snapshot,
        doneMap,
        customItems,
        (id, next) => {
          startTransition(() => {
            setDoneMap((prev) => {
              const updated = { ...prev, [id]: next };
              persistActionBoardState(updated, customItems);
              return updated;
            });
          });
        },
        newItemLabel,
        setNewItemLabel,
        newItemDetail,
        setNewItemDetail,
        () => {
          const label = newItemLabel.trim();
          const detail = newItemDetail.trim();
          if (!label) return;
          const nextCustomItem: CustomChecklistItem = {
            id: `custom-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
            label,
            detail: detail || '운영자 추가 메모',
          };
          startTransition(() => {
            const nextItems = [nextCustomItem, ...customItems];
            setCustomItems(nextItems);
            persistActionBoardState(doneMap, nextItems);
            setNewItemLabel('');
            setNewItemDetail('');
          });
        },
        (id) => {
          startTransition(() => {
            const nextCustomItems = customItems.filter((item) => item.id !== id);
            const nextDoneMap = { ...doneMap };
            delete nextDoneMap[id];
            setCustomItems(nextCustomItems);
            setDoneMap(nextDoneMap);
            persistActionBoardState(nextDoneMap, nextCustomItems);
          });
        },
      );
    }
    if (reportTab === 'watch-decision') {
      return renderWatchDecision(snapshot);
    }
    return renderTodayReport(snapshot);
  }, [customItems, doneMap, newItemDetail, newItemLabel, reportTab, snapshot]);

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell" style={{ display: 'grid', gap: 16 }}>
          <div className="page-section reports-toolbar">
            <div>
              <div className="section-title">{tabHeadline(reportTab)}</div>
              <div className="section-copy">콘솔 스냅샷을 기반으로 오늘의 판단과 운영 포인트를 보여줍니다.</div>
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
