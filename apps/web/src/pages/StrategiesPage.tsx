import { useCallback, useMemo, useState } from 'react';
import { ConsoleActionBar } from '../components/ConsoleActionBar';
import { saveStrategyPreset, toggleStrategyEnabled } from '../api/domain';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import type { StrategyRegistryItem } from '../types/domain';
import type { ConsoleSnapshot } from '../types/consoleView';

const STRATEGY_VALIDATION_TRANSFER_KEY = 'console_strategy_validation_transfer_v1';
import { formatDateTime, formatPercent } from '../utils/format';

interface StrategiesPageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
}

function formatParamValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '-';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(3)));
  if (typeof value === 'boolean') return value ? 'on' : 'off';
  return String(value);
}

function slugifyStrategyId(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '') || 'strategy_preset';
}

export function StrategiesPage({ snapshot, loading, errorMessage, onRefresh }: StrategiesPageProps) {
  const { entries, push, clear } = useConsoleLogs();
  const [pendingId, setPendingId] = useState('');
  const [selectedStrategyId, setSelectedStrategyId] = useState('');
  const items = snapshot.strategies.items || [];
  const summary = snapshot.strategies.summary || {};

  const statusItems = useMemo(() => ([
    { label: '전체 전략', value: `${summary.total || items.length}개`, tone: 'neutral' as const },
    { label: '활성 전략', value: `${summary.enabled || 0}개`, tone: (summary.enabled || 0) > 0 ? 'good' as const : 'neutral' as const },
    { label: '승인됨', value: `${summary.counts?.approved || 0}개`, tone: 'good' as const },
    { label: '중지/대기', value: `${(summary.counts?.paused || 0) + (summary.counts?.testing || 0)}개`, tone: 'bad' as const },
  ]), [items.length, summary]);

  const handleRefresh = useCallback(() => {
    onRefresh();
    push('info', '전략 레지스트리를 다시 불러왔습니다.', undefined, 'engine');
  }, [onRefresh, push]);

  const handleToggle = useCallback(async (strategyId: string, enabled: boolean) => {
    setPendingId(strategyId);
    try {
      const response = await toggleStrategyEnabled(strategyId, enabled);
      if (!response.ok) {
        push('error', '전략 상태를 변경하지 못했습니다.', '', 'engine');
        return;
      }
      push('success', `전략 ${strategyId} 상태를 ${enabled ? '활성' : '비활성'}로 변경했습니다.`, undefined, 'engine');
      onRefresh();
    } finally {
      setPendingId('');
    }
  }, [onRefresh, push]);

  const selectedStrategy = useMemo<StrategyRegistryItem | undefined>(() => {
    if (!items.length) return undefined;
    return items.find((item) => String(item.strategy_id || '') === selectedStrategyId) || items[0];
  }, [items, selectedStrategyId]);

  const selectedParams = useMemo(() => {
    const params = selectedStrategy?.params;
    if (!params || typeof params !== 'object') return [] as Array<[string, unknown]>;
    return Object.entries(params).slice(0, 12);
  }, [selectedStrategy]);

  const handleCreatePreset = useCallback(async () => {
    const base = selectedStrategy || items[0];
    const rawName = window.prompt('새 프리셋 이름을 입력해줘.', base?.name ? `${base.name} Copy` : 'New Strategy Preset');
    if (!rawName) return;
    const name = rawName.trim();
    const strategyId = window.prompt('전략 ID를 입력해줘.', slugifyStrategyId(name));
    if (!strategyId) return;
    const payload = {
      ...(base || {}),
      strategy_id: slugifyStrategyId(strategyId),
      name,
      enabled: false,
      approval_status: 'draft',
      approved_at: '',
    } as Record<string, unknown>;
    setPendingId(String(payload.strategy_id || 'create'));
    try {
      const response = await saveStrategyPreset(payload);
      if (!response.ok) {
        push('error', '새 프리셋을 만들지 못했습니다.', '', 'engine');
        return;
      }
      push('success', `프리셋 ${payload.strategy_id} 를 추가했어.`, undefined, 'engine');
      setSelectedStrategyId(String(payload.strategy_id || ''));
      onRefresh();
    } finally {
      setPendingId('');
    }
  }, [items, onRefresh, push, selectedStrategy]);

  const handleClonePreset = useCallback(async () => {
    if (!selectedStrategy) return;
    const rawName = window.prompt('복제할 프리셋 이름을 입력해줘.', `${selectedStrategy.name || selectedStrategy.strategy_id} Copy`);
    if (!rawName) return;
    const name = rawName.trim();
    const strategyId = window.prompt('새 전략 ID를 입력해줘.', slugifyStrategyId(name));
    if (!strategyId) return;
    const payload = {
      ...selectedStrategy,
      strategy_id: slugifyStrategyId(strategyId),
      name,
      enabled: false,
      approval_status: 'draft',
      approved_at: '',
    } as Record<string, unknown>;
    setPendingId(String(payload.strategy_id || 'clone'));
    try {
      const response = await saveStrategyPreset(payload);
      if (!response.ok) {
        push('error', '프리셋 복제에 실패했습니다.', '', 'engine');
        return;
      }
      push('success', `프리셋 ${payload.strategy_id} 를 복제했어.`, undefined, 'engine');
      setSelectedStrategyId(String(payload.strategy_id || ''));
      onRefresh();
    } finally {
      setPendingId('');
    }
  }, [onRefresh, push, selectedStrategy]);

  const handleRetirePreset = useCallback(async () => {
    if (!selectedStrategy?.strategy_id) return;
    const ok = window.confirm(`${selectedStrategy.name || selectedStrategy.strategy_id} 프리셋을 retired 상태로 보낼까?`);
    if (!ok) return;
    const payload = {
      ...selectedStrategy,
      enabled: false,
      approval_status: 'retired',
    } as Record<string, unknown>;
    setPendingId(String(selectedStrategy.strategy_id));
    try {
      const response = await saveStrategyPreset(payload);
      if (!response.ok) {
        push('error', '프리셋 삭제(은퇴) 처리에 실패했습니다.', '', 'engine');
        return;
      }
      push('success', `프리셋 ${selectedStrategy.strategy_id} 를 retired 처리했어.`, undefined, 'engine');
      onRefresh();
    } finally {
      setPendingId('');
    }
  }, [onRefresh, push, selectedStrategy]);

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell console-page-shell strategies-shell" style={{ display: 'grid', gap: 16 }}>
          <ConsoleActionBar
            title="전략 관리"
            subtitle="실시간 엔진은 승인된 Strategy Registry만 읽습니다. approval status, enable 상태, universe rule, scan cycle을 여기서 분리해서 관리합니다."
            lastUpdated={snapshot.fetchedAt}
            loading={loading}
            errorMessage={errorMessage}
            statusItems={statusItems}
            onRefresh={handleRefresh}
            logs={entries}
            onClearLogs={clear}
            actions={[
              {
                label: '새 프리셋 추가',
                onClick: () => { void handleCreatePreset(); },
                tone: 'primary',
                busy: pendingId === 'create',
                busyLabel: '생성 중...',
              },
            ]}
          />

          <div className="page-section strategies-registry-shell" style={{ padding: 0 }}>
            <div className="responsive-table-desktop" style={{ overflow: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 920 }}>
                <thead>
                  <tr style={{ background: 'var(--bg-soft)', textAlign: 'left' }}>
                    <th style={{ padding: 12, fontSize: 12 }}>전략</th>
                    <th style={{ padding: 12, fontSize: 12 }}>상태</th>
                    <th style={{ padding: 12, fontSize: 12 }}>시장</th>
                    <th style={{ padding: 12, fontSize: 12 }}>유니버스</th>
                    <th style={{ padding: 12, fontSize: 12 }}>스캔 주기</th>
                    <th style={{ padding: 12, fontSize: 12 }}>연구 성과</th>
                    <th style={{ padding: 12, fontSize: 12 }}>최근 승인</th>
                    <th style={{ padding: 12, fontSize: 12 }}>액션</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => {
                    const research = item.research_summary || {};
                    const strategyId = String(item.strategy_id || '');
                    const enabled = Boolean(item.enabled);
                    return (
                      <tr key={strategyId} style={{ borderTop: '1px solid var(--border)' }}>
                        <td style={{ padding: 12, verticalAlign: 'top' }}>
                          <button
                            type="button"
                            className="strategy-link-button"
                            onClick={() => setSelectedStrategyId(strategyId)}
                          >
                            <div style={{ fontWeight: 700 }}>{item.name || strategyId}</div>
                            <div className="signal-cell-copy">{strategyId} · v{item.version || 1}</div>
                          </button>
                        </td>
                        <td style={{ padding: 12, verticalAlign: 'top' }}>
                          <div>{item.approval_status || '-'}</div>
                          <div className={`inline-badge ${enabled ? 'is-success' : 'is-danger'}`} style={{ marginTop: 6 }}>{enabled ? 'enabled' : 'disabled'}</div>
                        </td>
                        <td style={{ padding: 12, verticalAlign: 'top' }}>{item.market || '-'}</td>
                        <td style={{ padding: 12, verticalAlign: 'top' }}>{item.universe_rule || '-'}</td>
                        <td style={{ padding: 12, verticalAlign: 'top' }}>{item.scan_cycle || '-'}</td>
                        <td style={{ padding: 12, verticalAlign: 'top' }}>
                          <div>수익률 {formatPercent(research.backtest_return_pct, 1, true)}</div>
                          <div className="signal-cell-copy">WF {formatPercent(research.walk_forward_return_pct, 1, true)} · Sharpe {research.sharpe ?? '-'}</div>
                        </td>
                        <td style={{ padding: 12, verticalAlign: 'top' }}>{formatDateTime(item.approved_at)}</td>
                        <td style={{ padding: 12, verticalAlign: 'top' }}>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                            <button
                              className="ghost-button"
                              onClick={() => setSelectedStrategyId(strategyId)}
                              disabled={!strategyId}
                            >
                              상세 보기
                            </button>
                            <button
                              className="ghost-button"
                              onClick={() => handleToggle(strategyId, !enabled)}
                              disabled={!strategyId || pendingId === strategyId}
                            >
                              {pendingId === strategyId ? '처리 중...' : enabled ? '비활성화' : '활성화'}
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                  {items.length === 0 && (
                    <tr>
                      <td colSpan={8} style={{ padding: 14, fontSize: 12, color: 'var(--text-4)' }}>표시할 전략이 없습니다.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="responsive-card-list">
              {items.map((item) => {
                const research = item.research_summary || {};
                const strategyId = String(item.strategy_id || '');
                const enabled = Boolean(item.enabled);
                return (
                  <article key={`${strategyId}-card`} className="responsive-card">
                    <div className="responsive-card-head">
                      <div>
                        <div className="responsive-card-title">{item.name || strategyId}</div>
                        <div className="signal-cell-copy">{strategyId} · v{item.version || 1}</div>
                      </div>
                      <div className={`inline-badge ${enabled ? 'is-success' : 'is-danger'}`}>{enabled ? 'enabled' : 'disabled'}</div>
                    </div>
                    <div className="responsive-card-grid">
                      <div><div className="responsive-card-label">상태</div><div className="responsive-card-value">{item.approval_status || '-'}</div></div>
                      <div><div className="responsive-card-label">시장</div><div className="responsive-card-value">{item.market || '-'}</div></div>
                      <div><div className="responsive-card-label">유니버스</div><div className="responsive-card-value">{item.universe_rule || '-'}</div></div>
                      <div><div className="responsive-card-label">스캔 주기</div><div className="responsive-card-value">{item.scan_cycle || '-'}</div></div>
                      <div><div className="responsive-card-label">연구 성과</div><div className="responsive-card-value">수익률 {formatPercent(research.backtest_return_pct, 1, true)} · WF {formatPercent(research.walk_forward_return_pct, 1, true)}</div></div>
                      <div><div className="responsive-card-label">최근 승인</div><div className="responsive-card-value">{formatDateTime(item.approved_at)}</div></div>
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                      <button
                        className="ghost-button"
                        onClick={() => setSelectedStrategyId(strategyId)}
                        disabled={!strategyId}
                      >
                        상세 보기
                      </button>
                      <button
                        className="ghost-button"
                        onClick={() => handleToggle(strategyId, !enabled)}
                        disabled={!strategyId || pendingId === strategyId}
                      >
                        {pendingId === strategyId ? '처리 중...' : enabled ? '비활성화' : '활성화'}
                      </button>
                    </div>
                  </article>
                );
              })}
              {items.length === 0 && <div style={{ padding: 14, fontSize: 12, color: 'var(--text-4)' }}>표시할 전략이 없습니다.</div>}
            </div>
          </div>

          {selectedStrategy && (
            <section className="page-section strategy-detail-panel" style={{ display: 'grid', gap: 14 }}>
              <div className="section-head-row">
                <div>
                  <div className="section-title">전략 상세</div>
                  <div className="section-copy">전략 관리와 전략 검증 랩 사이를 이어주는 현재 저장값 요약이야. 여기서 전략 정체성과 현재 프리셋을 먼저 보고, 검증 랩에서 백테스트/최적화 흐름으로 넘어가면 돼.</div>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  <span className={`inline-badge ${selectedStrategy.enabled ? 'is-success' : 'is-danger'}`}>{selectedStrategy.enabled ? 'enabled' : 'disabled'}</span>
                  <span className="inline-badge">{selectedStrategy.approval_status || 'draft'}</span>
                  <button className="ghost-button" onClick={() => { void handleClonePreset(); }} disabled={!selectedStrategy.strategy_id}>
                    현재 전략 복제
                  </button>
                  <button className="ghost-button" onClick={() => {
                    localStorage.setItem(STRATEGY_VALIDATION_TRANSFER_KEY, JSON.stringify(selectedStrategy));
                    window.location.href = '/console/validation';
                  }}>
                    전략 검증 랩 열기
                  </button>
                  <button className="ghost-button" onClick={() => { void handleRetirePreset(); }} disabled={!selectedStrategy.strategy_id}>
                    프리셋 삭제
                  </button>
                </div>
              </div>

              <div className="console-metric-grid">
                <div className="summary-metric-card">
                  <div className="summary-metric-label">전략</div>
                  <div className="summary-metric-value">{selectedStrategy.name || selectedStrategy.strategy_id}</div>
                  <div className="summary-metric-detail">{selectedStrategy.strategy_id} · v{selectedStrategy.version || 1}</div>
                </div>
                <div className="summary-metric-card">
                  <div className="summary-metric-label">시장 / 유니버스</div>
                  <div className="summary-metric-value">{selectedStrategy.market || '-'} / {selectedStrategy.universe_rule || '-'}</div>
                  <div className="summary-metric-detail">scan cycle {selectedStrategy.scan_cycle || '-'}</div>
                </div>
                <div className="summary-metric-card">
                  <div className="summary-metric-label">연구 성과</div>
                  <div className="summary-metric-value">{formatPercent(selectedStrategy.research_summary?.backtest_return_pct, 1, true)}</div>
                  <div className="summary-metric-detail">WF {formatPercent(selectedStrategy.research_summary?.walk_forward_return_pct, 1, true)} · Sharpe {selectedStrategy.research_summary?.sharpe ?? '-'}</div>
                </div>
              </div>

              <div className="strategy-detail-grid">
                <div className="page-section" style={{ padding: 16 }}>
                  <div className="section-title">현재 룰</div>
                  <div className="detail-list">
                    <div><strong>Entry</strong> · {selectedStrategy.entry_rule || '-'}</div>
                    <div><strong>Exit</strong> · {selectedStrategy.exit_rule || '-'}</div>
                    <div><strong>최근 승인</strong> · {formatDateTime(selectedStrategy.approved_at)}</div>
                  </div>
                </div>

                <div className="page-section" style={{ padding: 16 }}>
                  <div className="section-title">리스크 제한</div>
                  <div className="detail-list">
                    <div>최대 포지션 · {selectedStrategy.risk_limits?.max_positions ?? '-'}</div>
                    <div>포지션 크기 · {selectedStrategy.risk_limits?.position_size_pct ?? '-'}</div>
                    <div>일손실 제한 · {selectedStrategy.risk_limits?.daily_loss_limit_pct ?? '-'}</div>
                    <div>최소 유동성 · {selectedStrategy.risk_limits?.min_liquidity ?? '-'}</div>
                  </div>
                </div>
              </div>

              <div className="page-section" style={{ padding: 16 }}>
                <div className="section-head-row">
                  <div>
                    <div className="section-title">현재 저장된 파라미터 프리셋</div>
                    <div className="section-copy">여기 값은 현재 전략 레지스트리에 저장된 프리셋이야. 실험용으로 값을 바꿔보는 건 검증 랩에서 하는 게 맞아.</div>
                  </div>
                </div>
                <div className="strategy-param-grid">
                  {selectedParams.map(([key, value]) => (
                    <div key={key} className="summary-metric-card">
                      <div className="summary-metric-label">{key}</div>
                      <div className="summary-metric-value">{formatParamValue(value)}</div>
                    </div>
                  ))}
                  {selectedParams.length === 0 && <div style={{ fontSize: 12, color: 'var(--text-4)' }}>표시할 파라미터가 없습니다.</div>}
                </div>
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
