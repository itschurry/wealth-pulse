import { useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { UI_TEXT } from '../constants/uiText';
import { formatDateTime } from '../utils/format';
import type { ActionBarAction, ActionBarStatusItem, ConsoleLogEntry, ConsoleLogLevel } from '../types/consoleView';

interface ConsoleActionBarProps {
  title: string;
  subtitle?: string;
  lastUpdated: string;
  loading?: boolean;
  errorMessage?: string;
  statusItems: ActionBarStatusItem[];
  onRefresh: () => void;
  actions?: ActionBarAction[];
  logs: ConsoleLogEntry[];
  onClearLogs: () => void;
  settingsPanel?: ReactNode;
  settingsDirty?: boolean;
  settingsSavedAt?: string;
  sticky?: boolean;
}

function levelText(level: ConsoleLogEntry['level']): string {
  if (level === 'success') return '성공';
  if (level === 'warning') return '경고';
  if (level === 'error') return '오류';
  return '정보';
}

function toneClass(tone: ActionBarStatusItem['tone']): string {
  if (tone === 'good') return 'console-status-chip is-good';
  if (tone === 'bad') return 'console-status-chip is-bad';
  return 'console-status-chip';
}

function actionClass(tone: ActionBarAction['tone']): string {
  if (tone === 'primary') return 'console-action-button is-primary';
  if (tone === 'danger') return 'console-action-button is-danger';
  return 'console-action-button';
}

interface ConsoleConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  details?: string[];
  confirmLabel?: string;
  busy?: boolean;
  tone?: ActionBarAction['tone'];
  onConfirm: () => void;
  onCancel: () => void;
}

function sourceLabel(source: string): string {
  if (source === 'backtest') return '백테스트';
  if (source === 'optimization') return '최적화';
  if (source === 'settings') return '설정';
  if (source === 'paper') return '모의투자';
  if (source === 'engine') return '엔진';
  if (source === 'refresh') return '새로고침';
  if (source === 'all') return '전체';
  return source || '전체';
}

export function ConsoleConfirmDialog({
  open,
  title,
  message,
  details = [],
  confirmLabel = UI_TEXT.confirm.confirmAction,
  busy = false,
  tone = 'danger',
  onConfirm,
  onCancel,
}: ConsoleConfirmDialogProps) {
  const cancelButtonRef = useRef<HTMLButtonElement | null>(null);
  const [dangerChecked, setDangerChecked] = useState(false);

  useEffect(() => {
    if (!open || busy) return;
    cancelButtonRef.current?.focus();
  }, [busy, open]);

  useEffect(() => {
    if (!open) {
      setDangerChecked(false);
    }
  }, [open]);

  if (!open) return null;

  return (
    <>
      <div className="console-overlay" onClick={busy ? undefined : onCancel} />
      <div className="console-confirm-shell" role="dialog" aria-modal="true" aria-labelledby="console-confirm-title">
        <div className="console-confirm-card" onKeyDown={(event) => {
          if (event.key === 'Escape' && !busy) {
            event.preventDefault();
            onCancel();
          }
        }}
        >
          <div id="console-confirm-title" className="console-confirm-title">{title}</div>
          <div className="console-confirm-message">{message}</div>
          {details.length > 0 && (
            <ul className="console-confirm-list">
              {details.map((detail) => (
                <li key={detail}>{detail}</li>
              ))}
            </ul>
          )}
          {tone === 'danger' && (
            <div className="console-confirm-danger-box">
              <div className="console-confirm-danger-title">위험 작업 확인</div>
              <label className="console-confirm-check">
                <input type="checkbox" checked={dangerChecked} onChange={(event) => setDangerChecked(event.target.checked)} disabled={busy} />
                <span>영향 범위를 확인했고 되돌리기 어렵다는 점을 이해했습니다.</span>
              </label>
            </div>
          )}
          <div className="console-confirm-actions">
            <button ref={cancelButtonRef} className="ghost-button" onClick={onCancel} disabled={busy}>
              {UI_TEXT.confirm.cancelAction}
            </button>
            <button className={actionClass(tone)} onClick={onConfirm} disabled={busy || (tone === 'danger' && !dangerChecked)}>
              {busy ? (
                <span className="button-content">
                  <span className="button-spinner" aria-hidden="true" />
                  처리 중...
                </span>
              ) : confirmLabel}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

function renderButtonLabel(label: string, busy?: boolean, busyLabel?: string) {
  if (!busy) return label;
  return (
    <span className="button-content">
      <span className="button-spinner" aria-hidden="true" />
      {busyLabel || '처리 중...'}
    </span>
  );
}

function renderLoadFailure(errorMessage: string, onRetry: () => void, onOpenLogs: () => void) {
  return (
    <div className="console-error-card" role="alert">
      <div className="console-error-card-title">{UI_TEXT.errors.partialLoadFailed}</div>
      <div className="console-error-card-copy">{errorMessage}</div>
      <ul className="console-error-card-list">
        <li>네트워크 지연 또는 API 일시 장애가 있었을 수 있습니다.</li>
        <li>아직 수집되지 않은 데이터라 화면 일부가 비어 있을 수 있습니다.</li>
        <li>인증 또는 백엔드 런타임 오류로 일부 엔드포인트가 실패했을 수 있습니다.</li>
      </ul>
      <div className="console-error-card-actions">
        <button className="ghost-button" onClick={onRetry}>재시도</button>
        <button className="ghost-button" onClick={onOpenLogs}>로그 보기</button>
      </div>
    </div>
  );
}

export function ConsoleActionBar({
  title,
  subtitle = '',
  lastUpdated,
  loading = false,
  errorMessage = '',
  statusItems,
  onRefresh,
  actions = [],
  logs,
  onClearLogs,
  settingsPanel,
  settingsDirty = false,
  settingsSavedAt = '',
  sticky = false,
}: ConsoleActionBarProps) {
  function renderActionButton(action: ActionBarAction) {
    return (
      <div key={action.label} className="console-actionbar-action-wrap">
        <button
          className={actionClass(action.tone)}
          onClick={() => {
            if (action.disabled || action.busy) return;
            if (action.confirmTitle || action.confirmMessage || action.tone === 'danger') {
              openActionConfirm(action);
              return;
            }
            action.onClick();
          }}
          disabled={Boolean(action.disabled) || Boolean(action.busy)}
          title={action.disabled && action.disabledReason ? `${action.label} · ${action.disabledReason}` : action.label}
        >
          {renderButtonLabel(action.label, action.busy, action.busyLabel)}
        </button>
        {action.disabled && action.disabledReason && <div className="console-actionbar-action-reason">{action.disabledReason}</div>}
      </div>
    );
  }

  const [logOpen, setLogOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [levelFilter, setLevelFilter] = useState<'all' | ConsoleLogLevel>('all');
  const [sourceFilter, setSourceFilter] = useState<'all' | string>('all');
  const [confirmState, setConfirmState] = useState<{
    title: string;
    message: string;
    confirmLabel?: string;
    tone?: ActionBarAction['tone'];
    details?: string[];
    onConfirm: () => void;
  } | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const updateText = formatDateTime(lastUpdated);

  const logSources = useMemo(() => (
    ['all', ...new Set(logs.map((log) => log.source).filter((source): source is string => Boolean(source)))]
  ), [logs]);

  const safeActions = actions.filter((action) => action.tone !== 'danger');
  const dangerActions = actions.filter((action) => action.tone === 'danger');

  const filteredLogs = useMemo(() => {
    const keyword = searchText.trim().toLowerCase();
    return logs
      .filter((log) => levelFilter === 'all' || log.level === levelFilter)
      .filter((log) => sourceFilter === 'all' || log.source === sourceFilter)
      .filter((log) => {
        if (!keyword) return true;
        return [log.message, log.context || '', log.source || '']
          .join(' ')
          .toLowerCase()
          .includes(keyword);
      })
      .slice(0, 80);
  }, [levelFilter, logs, searchText, sourceFilter]);

  function closeConfirm() {
    if (confirmBusy) return;
    setConfirmState(null);
  }

  function openActionConfirm(action: ActionBarAction) {
    setConfirmState({
      title: action.confirmTitle || UI_TEXT.confirm.defaultTitle,
      message: action.confirmMessage || UI_TEXT.confirm.defaultMessage,
      confirmLabel: action.confirmLabel,
      tone: action.tone,
      details: action.confirmDetails,
      onConfirm: action.onClick,
    });
  }

  async function runConfirmedAction() {
    if (!confirmState) return;
    try {
      setConfirmBusy(true);
      await Promise.resolve(confirmState.onConfirm());
      setConfirmState(null);
    } finally {
      setConfirmBusy(false);
    }
  }

  return (
    <>
      <div className={`page-section console-actionbar-shell ${sticky ? 'is-sticky' : ''}`.trim()}>
        <div className="console-actionbar-head">
          <div>
            <div className="console-actionbar-title">{title}</div>
            {subtitle && <div className="console-actionbar-subtitle">{subtitle}</div>}
            <div className="console-actionbar-meta">마지막 업데이트 {updateText}</div>
          </div>
          <div className="console-actionbar-buttons">
            <button className="ghost-button" onClick={onRefresh} disabled={loading}>
              {renderButtonLabel(loading ? '갱신 중' : '새로고침', loading, '갱신 중...')}
            </button>
            <button className="ghost-button" onClick={() => setLogOpen(true)}>
              로그 보기
            </button>
            {settingsPanel && (
              <button className="ghost-button" onClick={() => setSettingsOpen(true)}>
                <span className="button-content">
                  설정/실행
                  {settingsDirty && <span className="inline-badge is-warning">저장 필요</span>}
                </span>
              </button>
            )}
            {safeActions.map(renderActionButton)}
          </div>
        </div>

        {dangerActions.length > 0 && (
          <div className="console-actionbar-danger-row">
            <div className="console-actionbar-danger-copy">위험 작업은 실행계·계좌 상태를 직접 바꾸니 아래 빨간 버튼에서만 처리하세요.</div>
            <div className="console-actionbar-danger-buttons">
              {dangerActions.map(renderActionButton)}
            </div>
          </div>
        )}

        <div className="console-status-grid">
          {statusItems.map((item) => (
            <div key={`${item.label}:${item.value}`} className={toneClass(item.tone)}>
              <div className="console-status-label">{item.label}</div>
              <div className="console-status-value">{item.value}</div>
            </div>
          ))}
        </div>

        {errorMessage && renderLoadFailure(errorMessage, onRefresh, () => setLogOpen(true))}
      </div>

      {(logOpen || settingsOpen) && (
        <div className="console-overlay" onClick={() => { setLogOpen(false); setSettingsOpen(false); }} />
      )}

      <aside className={`console-drawer ${logOpen ? 'open' : ''}`} aria-hidden={!logOpen}>
        <div className="console-drawer-head">
          <div>
            <div className="console-drawer-title">실행 로그</div>
            <div className="console-drawer-caption">레벨/작업별로 빠르게 필터링할 수 있습니다.</div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              className="ghost-button"
              onClick={() => setConfirmState({
                title: UI_TEXT.confirm.clearLogsTitle,
                message: UI_TEXT.confirm.clearLogsMessage,
                details: ['현재 화면에 쌓인 로그가 모두 제거됩니다.', '삭제 후에는 복구할 수 없습니다.'],
                tone: 'danger',
                onConfirm: onClearLogs,
              })}
            >
              로그 비우기
            </button>
            <button className="ghost-button" onClick={() => setLogOpen(false)}>닫기</button>
          </div>
        </div>
        <div className="console-drawer-toolbar">
          <input
            className="console-search-input"
            type="search"
            placeholder="메시지, 상세 문구, 작업명을 검색하세요"
            value={searchText}
            onChange={(event) => setSearchText(event.target.value)}
            aria-label="로그 검색"
          />
          <div className="filter-chip-row" role="tablist" aria-label="로그 레벨 필터">
            {(['all', 'info', 'success', 'warning', 'error'] as const).map((level) => (
              <button
                key={level}
                className={`filter-chip ${levelFilter === level ? 'active' : ''}`}
                onClick={() => setLevelFilter(level)}
              >
                {level === 'all' ? '전체' : levelText(level)}
              </button>
            ))}
          </div>
          <div className="filter-chip-row" role="tablist" aria-label="로그 작업 필터">
            {logSources.map((source) => (
              <button
                key={source}
                className={`filter-chip ${sourceFilter === source ? 'active' : ''}`}
                onClick={() => setSourceFilter(source)}
              >
                {sourceLabel(source)}
              </button>
            ))}
          </div>
        </div>
        <div className="console-drawer-body">
          {filteredLogs.length === 0 && (
            <div className="console-drawer-empty">
              {logs.length === 0 ? UI_TEXT.empty.noLogs : '선택한 조건과 일치하는 로그가 없습니다.'}
            </div>
          )}
          {filteredLogs.map((log) => (
            <div key={log.id} className={`console-log-item is-${log.level}`}>
              <div className="console-log-head">
                <span>{levelText(log.level)}</span>
                <span>{formatDateTime(log.timestamp)}</span>
              </div>
              <div className="console-log-message">{log.message}</div>
              <div className="console-log-meta">
                <span>{sourceLabel(log.source || 'all')}</span>
                {log.context && <span>상세 있음</span>}
              </div>
              {log.context && <div className="console-log-context">{log.context}</div>}
            </div>
          ))}
        </div>
      </aside>

      <aside className={`console-drawer ${settingsOpen ? 'open' : ''}`} aria-hidden={!settingsOpen}>
        <div className="console-drawer-head">
          <div>
            <div className="console-drawer-title">전략 설정 · 실행 준비</div>
            <div className="console-drawer-caption">
              {settingsDirty ? '저장되지 않은 변경 사항이 있습니다.' : settingsSavedAt ? `마지막 저장 ${formatDateTime(settingsSavedAt)}` : '저장된 설정이 아직 없습니다.'}
            </div>
          </div>
          <button className="ghost-button" onClick={() => setSettingsOpen(false)}>닫기</button>
        </div>
        <div className="console-drawer-body">
          {settingsPanel || <div className="console-drawer-empty">설정 항목이 없습니다.</div>}
        </div>
      </aside>

      <ConsoleConfirmDialog
        open={Boolean(confirmState)}
        title={confirmState?.title || UI_TEXT.confirm.defaultTitle}
        message={confirmState?.message || UI_TEXT.confirm.defaultMessage}
        details={confirmState?.details}
        confirmLabel={confirmState?.confirmLabel}
        tone={confirmState?.tone}
        busy={confirmBusy}
        onConfirm={() => { void runConfirmedAction(); }}
        onCancel={closeConfirm}
      />
    </>
  );
}
