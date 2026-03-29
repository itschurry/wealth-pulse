import { useCallback, useMemo } from 'react';
import { ConsoleActionBar } from '../components/ConsoleActionBar';
import { UI_TEXT } from '../constants/uiText';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import { formatCount, formatDateTime, formatKRW } from '../utils/format';
import type { ActionBarStatusItem, ConsoleSnapshot } from '../types/consoleView';

interface OverviewPageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
}

export function OverviewPage({ snapshot, loading, errorMessage, onRefresh }: OverviewPageProps) {
  const { entries, push, clear } = useConsoleLogs();
  const allocator = snapshot.engine.allocator || {};
  const running = Boolean(snapshot.engine.execution?.state?.running);
  const guardOk = Boolean(snapshot.engine.risk_guard_state?.entry_allowed);
  const riskReasons = snapshot.engine.risk_guard_state?.reasons || [];

  const handleRefresh = useCallback(() => {
    onRefresh();
    push('info', '콘솔 데이터를 수동 갱신했습니다.');
  }, [onRefresh, push]);

  const statusItems = useMemo<ActionBarStatusItem[]>(() => ([
    {
      label: '엔진 상태',
      value: running ? UI_TEXT.status.running : UI_TEXT.status.stopped,
      tone: running ? 'good' : 'bad',
    },
    {
      label: '신규 진입 가능',
      value: guardOk ? UI_TEXT.common.yes : UI_TEXT.common.no,
      tone: guardOk ? 'good' : 'bad',
    },
    {
      label: '허용/차단 신호',
      value: `${allocator.entry_allowed_count ?? 0} / ${allocator.blocked_count ?? 0}`,
      tone: 'neutral',
    },
    {
      label: '장세/위험도',
      value: `${allocator.regime || '-'} / ${allocator.risk_level || '-'}`,
      tone: 'neutral',
    },
  ]), [allocator.blocked_count, allocator.entry_allowed_count, allocator.regime, allocator.risk_level, guardOk, running]);

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell" style={{ display: 'grid', gap: 16 }}>
          <ConsoleActionBar
            title="엔진 개요"
            subtitle="엔진 상태와 리스크 가드의 현재 운용 상태를 확인합니다."
            lastUpdated={snapshot.fetchedAt}
            loading={loading}
            errorMessage={errorMessage}
            statusItems={statusItems}
            onRefresh={handleRefresh}
            logs={entries}
            onClearLogs={clear}
            settingsPanel={(
              <div style={{ display: 'grid', gap: 10, fontSize: 12, color: 'var(--text-3)' }}>
                <div>자동 갱신 주기: 30초</div>
                <div>콘솔 데이터 기준 시각: {formatDateTime(snapshot.fetchedAt)}</div>
                <div>오류 발생 시 로그 드로어에서 원인을 먼저 확인하세요.</div>
              </div>
            )}
          />

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
            <div className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 700 }}>리스크 가드</div>
              <div style={{ marginTop: 8, display: 'grid', gap: 6, fontSize: 12, color: 'var(--text-3)' }}>
                <div>
                  현재 진입 제한: <b style={{ color: guardOk ? 'var(--up)' : 'var(--down)' }}>
                    {guardOk ? '없음' : '있음'}
                  </b>
                </div>
                <div>일일 손실 잔여: {formatKRW(snapshot.engine.risk_guard_state?.daily_loss_left, true)}</div>
                <div>사유: {riskReasons.join(', ') || '현재 차단 사유가 없습니다.'}</div>
                <div>콘솔 데이터 기준 시각: {formatDateTime(snapshot.fetchedAt)}</div>
              </div>
            </div>
            <div className="page-section" style={{ padding: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 700 }}>계좌 요약</div>
              <div style={{ marginTop: 8, display: 'grid', gap: 6, fontSize: 12, color: 'var(--text-3)' }}>
                <div>총자산: {formatKRW(snapshot.portfolio.account?.equity_krw, true)}</div>
                <div>원화 현금: {formatKRW(snapshot.portfolio.account?.cash_krw, true)}</div>
                <div>보유 종목 수: {formatCount((snapshot.portfolio.account?.positions || []).length, '종목')}</div>
                <div>신규 진입 판단: {guardOk ? '현재 진입 가능 상태입니다.' : '리스크 가드 해제 전까지 신규 진입을 보류합니다.'}</div>
              </div>
            </div>
          </div>

          {loading && <div style={{ color: 'var(--text-3)', fontSize: 12 }}>{UI_TEXT.common.loading}</div>}
        </div>
      </div>
    </div>
  );
}
