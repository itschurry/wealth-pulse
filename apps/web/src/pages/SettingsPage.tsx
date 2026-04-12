import { useCallback, useEffect, useMemo, useRef } from 'react';
import { ConsoleActionBar } from '../components/ConsoleActionBar';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import {
  formatValidationSettingsLabel,
  useValidationSettingsStore,
  validationSyncStatusLabel,
} from '../hooks/useValidationSettingsStore';
import type { ConsoleSnapshot } from '../types/consoleView';
import { formatDateTime } from '../utils/format';

interface SettingsPageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
  onOpenLab: () => void;
  onOpenStrategiesLab: () => void;
}

function stateTone(label: string) {
  if (label === 'applied' || label === 'saved') return 'good';
  if (label === 'draft') return 'neutral';
  return 'bad';
}

function summarizeStrategy(snapshot: ConsoleSnapshot) {
  const items = snapshot.strategies.items || [];
  const applied = items.find((item) => item.enabled);
  const approvedPending = items.filter((item) => item.status === 'ready' && !item.enabled).length;
  return {
    appliedName: applied?.name || applied?.strategy_id || '-',
    appliedVersion: applied?.version ? `v${applied.version}` : '-',
    approvedPendingCount: approvedPending,
  };
}

export function SettingsPage({
  snapshot,
  loading,
  errorMessage,
  onRefresh,
  onOpenLab,
  onOpenStrategiesLab,
}: SettingsPageProps) {
  const validationStore = useValidationSettingsStore();
  const { entries, push, clear } = useConsoleLogs();
  const strategySummary = useMemo(() => summarizeStrategy(snapshot), [snapshot]);
  const settingsLoadStarted = useRef(false);
  const syncStatusLabel = validationSyncStatusLabel(validationStore.syncStatus);

  useEffect(() => {
    if (validationStore.serverLoaded || settingsLoadStarted.current) return;
    settingsLoadStarted.current = true;
    validationStore.loadSavedFromServer().catch(() => {
      settingsLoadStarted.current = false;
      return undefined;
    });
  }, [validationStore.serverLoaded, validationStore]);

  const statusItems = useMemo(() => ([
    { label: 'sync', value: syncStatusLabel, tone: validationStore.syncStatus === 'error' ? 'bad' as const : 'neutral' as const },
    { label: 'draft', value: validationStore.unsaved ? '변경 있음' : '동기화됨', tone: validationStore.unsaved ? 'bad' as const : 'good' as const },
    { label: 'saved version', value: `v${validationStore.stateVersion}`, tone: 'neutral' as const },
    { label: 'source', value: validationStore.stateSource || 'server', tone: 'neutral' as const },
  ]), [syncStatusLabel, validationStore.stateSource, validationStore.stateVersion, validationStore.syncStatus, validationStore.unsaved]);

  const actions = useMemo(() => ([
    {
      label: '서버 저장값 새로 불러오기',
      onClick: () => {
        validationStore.loadSavedFromServer({ forceDraft: false })
          .then(() => push('success', '서버 저장값을 다시 동기화했습니다.', undefined, 'settings'))
          .catch(() => push('error', '서버 저장값 동기화에 실패했습니다.', undefined, 'settings'));
      },
      busy: validationStore.syncStatus === 'loading',
      busyLabel: '동기화 중...',
    },
    {
      label: 'draft 저장',
      onClick: () => {
        validationStore.saveDraftToServer()
          .then((savedAt) => push('success', '현재 draft를 서버 저장 기준으로 반영했습니다.', savedAt, 'settings'))
          .catch(() => push('error', 'draft 저장에 실패했습니다.', undefined, 'settings'));
      },
      tone: 'primary' as const,
      busy: validationStore.syncStatus === 'saving',
      busyLabel: '저장 중...',
    },
    {
      label: 'saved -> draft 복사',
      onClick: () => {
        validationStore.loadSavedIntoDraft();
        push('info', '서버 saved 상태를 현재 draft로 복사했습니다.', undefined, 'settings');
      },
    },
    {
      label: '서버 초기화',
      onClick: () => {
        validationStore.resetSavedToServer()
          .then(() => push('warning', '서버 저장 기준과 브라우저 draft를 기본값으로 초기화했습니다.', undefined, 'settings'))
          .catch(() => push('error', '서버 초기화에 실패했습니다.', undefined, 'settings'));
      },
      tone: 'danger' as const,
      busy: validationStore.syncStatus === 'resetting',
      busyLabel: '초기화 중...',
      confirmTitle: '서버 저장 기준을 초기화하시겠습니까?',
      confirmMessage: 'saved/displayed 기준과 현재 브라우저 draft가 함께 기본값으로 돌아갑니다.',
      confirmDetails: [
        'draft 캐시도 새 기본값으로 덮어씁니다.',
        '운영에서 보는 displayed 기준이 함께 바뀔 수 있습니다.',
      ],
    },
  ]), [push, validationStore]);

  const handleRefresh = useCallback(() => {
    onRefresh();
    validationStore.loadSavedFromServer({ forceDraft: false }).catch(() => undefined);
    push('info', '설정 화면 기준 데이터를 새로고침했습니다.', undefined, 'refresh');
  }, [onRefresh, push, validationStore]);

  const draftSummary = useMemo(
    () => formatValidationSettingsLabel(validationStore.draftSettings, validationStore.draftQuery),
    [validationStore.draftQuery, validationStore.draftSettings],
  );
  const savedSummary = useMemo(
    () => formatValidationSettingsLabel(validationStore.savedSettings, validationStore.savedQuery),
    [validationStore.savedQuery, validationStore.savedSettings],
  );
  const displayedSummary = useMemo(
    () => formatValidationSettingsLabel(validationStore.displayedSettings, validationStore.displayedQuery),
    [validationStore.displayedQuery, validationStore.displayedSettings],
  );

  const configCards = [
    { key: 'draft', title: 'draft', tone: stateTone('draft'), lines: draftSummary, foot: validationStore.unsaved ? '브라우저 초안이 saved 기준과 다릅니다.' : 'saved 기준과 동일합니다.' },
    { key: 'saved', title: 'saved', tone: stateTone('saved'), lines: savedSummary, foot: validationStore.lastSavedAt ? `마지막 저장 ${formatDateTime(validationStore.lastSavedAt)}` : '서버 저장 시각 없음' },
    { key: 'displayed', title: 'displayed', tone: stateTone('applied'), lines: displayedSummary, foot: '운영 UI가 현재 보여주는 기준입니다.' },
  ];

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell">
          <ConsoleActionBar
            title="설정 상태 관리"
            subtitle="draft, saved, displayed 상태를 분리해서 보고 서버 저장 기준과 브라우저 초안을 혼동하지 않도록 정리한 화면입니다."
            lastUpdated={snapshot.fetchedAt}
            loading={loading || validationStore.syncStatus === 'loading'}
            errorMessage={errorMessage}
            statusItems={statusItems}
            onRefresh={handleRefresh}
            actions={actions}
            logs={entries}
            onClearLogs={clear}
            settingsDirty={validationStore.unsaved}
            settingsSavedAt={validationStore.lastSavedAt}
          />

          <section className="page-section">
            <div className="section-head-row">
              <div>
                <div className="section-title">운영 반영 기준</div>
                <div className="section-copy">설정 화면에서는 saved/displayed 기준과 운영 반영 전략 상태를 같이 봅니다.</div>
              </div>
            </div>
            <div className="console-status-grid" style={{ marginTop: 16 }}>
              <div className="console-status-card">
                <div className="console-status-card-label">현재 applied 전략</div>
                <div className="console-status-card-value">{strategySummary.appliedName}</div>
                <div className="console-status-card-copy">{strategySummary.appliedVersion}</div>
              </div>
              <div className="console-status-card">
                <div className="console-status-card-label">미적용 승인 전략</div>
                <div className="console-status-card-value">{strategySummary.approvedPendingCount}개</div>
                <div className="console-status-card-copy">ready 상태이지만 아직 enabled 되지 않은 전략</div>
              </div>
              <div className="console-status-card">
                <div className="console-status-card-label">동기화 메시지</div>
                <div className="console-status-card-value">{syncStatusLabel}</div>
                <div className="console-status-card-copy">{validationStore.syncMessage || '메시지 없음'}</div>
              </div>
            </div>
            <div className="console-error-card-actions" style={{ marginTop: 16 }}>
              <button className="ghost-button" onClick={onOpenStrategiesLab}>전략 프리셋 열기</button>
              <button className="ghost-button" onClick={onOpenLab}>실험실에서 draft 편집</button>
            </div>
          </section>

          <section className="operator-note-grid">
            {configCards.map((card) => (
              <article key={card.key} className="page-section">
                <div className="section-head-row">
                  <div className="section-title">{card.title}</div>
                  <span className={`inline-badge${card.tone === 'good' ? ' is-success' : card.tone === 'bad' ? ' is-danger' : ''}`}>{card.title}</span>
                </div>
                <div className="wealth-list" style={{ marginTop: 12 }}>
                  {card.lines.map((line) => (
                    <div key={`${card.key}-${line}`} className="wealth-list-item">
                      <div className="wealth-list-copy">{line}</div>
                    </div>
                  ))}
                </div>
                <div className="section-copy" style={{ marginTop: 12 }}>{card.foot}</div>
              </article>
            ))}
          </section>
        </div>
      </div>
    </div>
  );
}
