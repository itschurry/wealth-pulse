import { useCallback, useMemo } from 'react';
import { buildSignalRows } from '../adapters/consoleViewAdapter';
import { ConsoleActionBar } from '../components/ConsoleActionBar';
import { strategyTypeToKorean, UI_TEXT } from '../constants/uiText';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import { formatCount, formatNumber, formatPercent } from '../utils/format';
import type { ConsoleSnapshot } from '../types/consoleView';

interface SignalsPageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
}

export function SignalsPage({ snapshot, loading, errorMessage, onRefresh }: SignalsPageProps) {
  const { entries, push, clear } = useConsoleLogs();
  const rows = buildSignalRows(snapshot).slice(0, 60);
  const allowedCount = rows.filter((row) => row.statusLabel === UI_TEXT.status.allowed).length;
  const blockedCount = rows.length - allowedCount;
  const emptyMessage = errorMessage ? UI_TEXT.empty.signalsMissingData : UI_TEXT.empty.signalsNoMatches;

  const handleRefresh = useCallback(() => {
    onRefresh();
    push('info', '신호 데이터를 수동 갱신했습니다.');
  }, [onRefresh, push]);

  const statusItems = useMemo(() => ([
    {
      label: '전체 신호',
      value: `${rows.length}건`,
      tone: 'neutral' as const,
    },
    {
      label: '추천',
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
  ]), [allowedCount, blockedCount, rows.length, snapshot.signals.regime, snapshot.signals.risk_level]);

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell" style={{ display: 'grid', gap: 16 }}>
          <ConsoleActionBar
            title="신호 관리"
            subtitle="EV 기반 추천/차단 상태와 차단 사유를 운영 관점으로 확인합니다."
            lastUpdated={snapshot.fetchedAt}
            loading={loading}
            errorMessage={errorMessage}
            statusItems={statusItems}
            onRefresh={handleRefresh}
            logs={entries}
            onClearLogs={clear}
            settingsPanel={(
              <div style={{ display: 'grid', gap: 10, fontSize: 12, color: 'var(--text-3)' }}>
                <div>표시 최대 건수: 60건</div>
                <div>정렬 기준: EV 내림차순</div>
                <div>추천 기준: `entry_allowed && size&gt;0`</div>
              </div>
            )}
          />

          <div className="page-section" style={{ padding: 0, overflow: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: 'var(--bg-soft)', textAlign: 'left' }}>
                  <th style={{ padding: 12, fontSize: 12 }}>종목</th>
                  <th style={{ padding: 12, fontSize: 12 }}>전략</th>
                  <th style={{ padding: 12, fontSize: 12 }}>EV</th>
                  <th style={{ padding: 12, fontSize: 12 }}>승률</th>
                  <th style={{ padding: 12, fontSize: 12 }}>추천 비중</th>
                  <th style={{ padding: 12, fontSize: 12 }}>신호 상태</th>
                  <th style={{ padding: 12, fontSize: 12 }}>차단 사유</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const signal = row.signal;
                  const ev = signal.ev_metrics?.expected_value;
                  const winProbability = signal.ev_metrics?.win_probability;
                  const size = signal.size_recommendation?.quantity ?? 0;
                  return (
                    <tr key={`${signal.market || ''}:${signal.code || ''}`} style={{ borderTop: '1px solid var(--border)' }}>
                      <td style={{ padding: 12, fontSize: 12 }}>{row.symbol}</td>
                      <td style={{ padding: 12, fontSize: 12 }}>{strategyTypeToKorean(signal.strategy_type || '')}</td>
                      <td style={{ padding: 12, fontSize: 12, fontWeight: 700 }}>
                        {ev === undefined ? '-' : formatNumber(ev, 2)}
                      </td>
                      <td style={{ padding: 12, fontSize: 12 }}>
                        {winProbability === undefined ? '-' : formatPercent(winProbability, 2, true)}
                      </td>
                      <td style={{ padding: 12, fontSize: 12 }}>
                        {size > 0 ? formatCount(size, '주') : '-'}
                      </td>
                      <td style={{ padding: 12, fontSize: 12, color: row.statusLabel === '추천' ? 'var(--up)' : 'var(--down)', fontWeight: 700 }}>
                        {row.statusLabel}
                      </td>
                      <td style={{ padding: 12, fontSize: 12, color: row.statusLabel === '추천' ? 'var(--text-4)' : 'var(--down)' }}>
                        {row.reasonSummary}
                      </td>
                    </tr>
                  );
                })}
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={7} style={{ padding: 14, fontSize: 12, color: 'var(--text-4)' }}>
                      {emptyMessage}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {loading && <div style={{ color: 'var(--text-3)', fontSize: 12 }}>{UI_TEXT.common.loading}</div>}
        </div>
      </div>
    </div>
  );
}
