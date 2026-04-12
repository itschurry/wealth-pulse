import { useCallback, useMemo, useState } from 'react';
import { ConsoleActionBar } from '../components/ConsoleActionBar';
import { deleteStrategyPreset, saveStrategyPreset, seedDefaultStrategies, toggleStrategyEnabled } from '../api/domain';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import { loadBacktestQuery } from '../hooks/useBacktest';
import { VALIDATION_TRANSFER_STORAGE_KEY } from '../lib/validationConfigStorage';
import type { StrategyRegistryItem } from '../types/domain';
import type { ConsoleSnapshot } from '../types/consoleView';
import { formatDateTime, formatPercent } from '../utils/format';

interface StrategiesPageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
  mode?: 'operations' | 'lab';
}

function lifecycleBadge(item: StrategyRegistryItem): { className: string; label: string } {
  if (item.enabled) return { className: 'inline-badge is-success', label: 'applied' };
  if (item.status === 'ready') return { className: 'inline-badge', label: 'approved' };
  if (item.status === 'paused') return { className: 'inline-badge is-warning', label: 'stale' };
  if (item.status === 'archived') return { className: 'inline-badge is-danger', label: 'blocked' };
  return { className: 'inline-badge is-danger', label: 'candidate' };
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

function strategyContextFromValidationLab() {
  const query = loadBacktestQuery();
  if (query.market_scope === 'nasdaq') {
    return { market: 'NASDAQ', universe_rule: 'sp500', scan_cycle: '5m' };
  }
  if (query.market_scope === 'all') {
    return { market: 'KOSPI', universe_rule: 'multi_market', scan_cycle: '10m' };
  }
  return { market: 'KOSPI', universe_rule: 'kospi', scan_cycle: '5m' };
}

const PRESET_PARAMS_CONTEXT_FIELDS = new Set([
  'market', 'strategy_kind', 'regime_mode',
  'signal_interval', 'signal_range',
  'scan_limit', 'candidate_top_n',
]);

function buildPresetPayload(
  source: StrategyRegistryItem | undefined,
  options: { strategyId: string; name: string },
): Record<string, unknown> {
  const { strategyId, name } = options;
  const validationContext = strategyContextFromValidationLab();
  // strip context fields — backend fills these from the outer strategy fields
  const rawParams = source?.params && typeof source.params === 'object' ? source.params : {};
  const params = Object.fromEntries(
    Object.entries(rawParams).filter(([key]) => !PRESET_PARAMS_CONTEXT_FIELDS.has(key)),
  );
  const riskLimits = source?.risk_limits && typeof source.risk_limits === 'object' ? source.risk_limits : {};
  const strategyKind = String(source?.strategy_kind || source?.strategy_id || 'trend_following');
  return {
    strategy_id: slugifyStrategyId(strategyId),
    strategy_kind: strategyKind,
    name,
    enabled: false,
    status: 'draft',
    enabled_at: '',
    market: validationContext.market,
    universe_rule: validationContext.universe_rule,
    scan_cycle: validationContext.scan_cycle,
    params,
    risk_limits: riskLimits,
    research_summary: {},
  };
}

export function StrategiesPage({ snapshot, loading, errorMessage, onRefresh, mode = 'lab' }: StrategiesPageProps) {
  const { entries, push, clear } = useConsoleLogs();
  const [pendingId, setPendingId] = useState('');
  const [selectedStrategyId, setSelectedStrategyId] = useState('');
  const items = snapshot.strategies.items || [];
  const summary = snapshot.strategies.summary || {};
  const readOnly = mode === 'operations';

  const statusItems = useMemo(() => ([
    { label: '전체 전략', value: `${summary.total || items.length}개`, tone: 'neutral' as const },
    { label: '적용됨', value: `${summary.enabled || 0}개`, tone: (summary.enabled || 0) > 0 ? 'good' as const : 'neutral' as const },
    { label: '승인됨', value: `${summary.counts?.approved || 0}개`, tone: 'good' as const },
    { label: '재확인 필요', value: `${(summary.counts?.paused || 0) + (summary.counts?.testing || 0)}개`, tone: 'bad' as const },
  ]), [items.length, summary]);

  const handleRefresh = useCallback(() => {
    onRefresh();
    push('info', '전략 레지스트리를 다시 불러왔습니다.', undefined, 'engine');
  }, [onRefresh, push]);

  const handleToggle = useCallback(async (strategyId: string, enabled: boolean) => {
    setPendingId(strategyId);
    try {
      const response = await toggleStrategyEnabled(strategyId, enabled);
      if (!response.ok || response.data?.ok === false) {
        push('error', '전략 상태를 변경하지 못했습니다.', response.data?.error || response.error?.message || '', 'engine');
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

  const PARAMS_CONTEXT_FIELDS = new Set([
    'market', 'strategy_kind', 'regime_mode',
    'signal_interval', 'signal_range',
    'scan_limit', 'candidate_top_n',
  ]);
  const selectedParams = useMemo(() => {
    const params = selectedStrategy?.params;
    if (!params || typeof params !== 'object') return [] as Array<[string, unknown]>;
    return Object.entries(params).filter(([key]) => !PARAMS_CONTEXT_FIELDS.has(key));
  }, [selectedStrategy]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSeedDefaults = useCallback(async () => {
    setPendingId('seed');
    try {
      const response = await seedDefaultStrategies();
      if (!response.ok || response.data?.ok === false) {
        push('error', '기본 전략 추가에 실패했습니다.', response.data?.error || response.error?.message || '', 'engine');
        return;
      }
      const seeded = response.data?.seeded || [];
      if (seeded.length === 0) {
        push('info', '추가할 기본 전략이 없습니다. 이미 모두 존재합니다.', undefined, 'engine');
      } else {
        push('success', `기본 전략 ${seeded.length}개를 추가했습니다.`, seeded.join(', '), 'engine');
      }
      onRefresh();
    } finally {
      setPendingId('');
    }
  }, [onRefresh, push]);

  const handleCreatePreset = useCallback(async () => {
    const base = selectedStrategy || items.find((item) => item.strategy_kind === 'trend_following') || items[0];
    const rawName = window.prompt('새 프리셋 이름을 입력해줘.', base?.name ? `${base.name} Copy` : 'New Strategy Preset');
    if (!rawName) return;
    const name = rawName.trim();
    const strategyId = window.prompt('전략 ID를 입력해줘.', slugifyStrategyId(name));
    if (!strategyId) return;
    const payload = buildPresetPayload(base, { strategyId, name });
    setPendingId(String(payload.strategy_id || 'create'));
    try {
      const response = await saveStrategyPreset(payload);
      if (!response.ok || response.data?.ok === false) {
        push('error', '새 프리셋을 만들지 못했습니다.', response.data?.error || response.error?.message || '', 'engine');
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
    const payload = buildPresetPayload(selectedStrategy, { strategyId, name });
    setPendingId(String(payload.strategy_id || 'clone'));
    try {
      const response = await saveStrategyPreset(payload);
      if (!response.ok || response.data?.ok === false) {
        push('error', '프리셋 복제에 실패했습니다.', response.data?.error || response.error?.message || '', 'engine');
        return;
      }
      push('success', `프리셋 ${payload.strategy_id} 를 복제했어.`, undefined, 'engine');
      setSelectedStrategyId(String(payload.strategy_id || ''));
      onRefresh();
    } finally {
      setPendingId('');
    }
  }, [onRefresh, push, selectedStrategy]);

  const handleDeletePreset = useCallback(async () => {
    if (!selectedStrategy?.strategy_id) return;
    const ok = window.confirm(`${selectedStrategy.name || selectedStrategy.strategy_id} 프리셋을 완전히 삭제할까? 이 작업은 되돌릴 수 없어.`);
    if (!ok) return;
    setPendingId(String(selectedStrategy.strategy_id));
    try {
      const response = await deleteStrategyPreset(String(selectedStrategy.strategy_id));
      if (!response.ok) {
        push('error', '프리셋 삭제에 실패했습니다.', response.data?.error || '', 'engine');
        return;
      }
      push('success', `프리셋 ${selectedStrategy.strategy_id} 를 삭제했어.`, undefined, 'engine');
      setSelectedStrategyId('');
      onRefresh();
    } finally {
      setPendingId('');
    }
  }, [onRefresh, push, selectedStrategy]);

  const SCAN_CYCLE_OPTIONS = ['10s', '30s', '1m', '5m', '10m', '15m', '30m', '1h'];

  const handleEditScanCycle = useCallback(async (value: string) => {
    if (!selectedStrategy || value === (selectedStrategy.scan_cycle || '5m')) return;
    setPendingId(String(selectedStrategy.strategy_id || 'scan_cycle'));
    try {
      const response = await saveStrategyPreset({ ...selectedStrategy, scan_cycle: value });
      if (!response.ok || response.data?.ok === false) {
        push('error', '스캔 주기 변경에 실패했습니다.', response.data?.error || response.error?.message || '', 'engine');
        return;
      }
      push('success', `스캔 주기를 ${value} 로 변경했어.`, undefined, 'engine');
      onRefresh();
    } finally {
      setPendingId('');
    }
  }, [onRefresh, push, selectedStrategy]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell console-page-shell strategies-shell" style={{ display: 'grid', gap: 16 }}>
          <ConsoleActionBar
            title={readOnly ? '전략 상태' : '전략 프리셋'}
            subtitle={readOnly
              ? '운영 모드에서는 승인/적용된 전략 상태와 enable 현황만 확인합니다. 프리셋 생성, 삭제, 검증 이관은 실험 모드에서만 허용합니다.'
              : '실시간 엔진은 승인된 Strategy Registry만 읽습니다. approval status, enable 상태, universe rule, scan cycle을 여기서 분리해서 관리합니다.'}
            lastUpdated={snapshot.fetchedAt}
            loading={loading}
            errorMessage={errorMessage}
            statusItems={statusItems}
            onRefresh={handleRefresh}
            logs={entries}
            onClearLogs={clear}
            actions={readOnly ? [] : [
              {
                label: '기본 전략 추가',
                onClick: () => { void handleSeedDefaults(); },
                tone: 'default',
                busy: pendingId === 'seed',
                busyLabel: '추가 중...',
              },
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
                    <th style={{ padding: 12, fontSize: 12 }}>활성화 일시</th>
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
                          <span className={lifecycleBadge(item).className}>{lifecycleBadge(item).label}</span>
                        </td>
                        <td style={{ padding: 12, verticalAlign: 'top' }}>{item.market || '-'}</td>
                        <td style={{ padding: 12, verticalAlign: 'top' }}>{item.universe_rule || '-'}</td>
                        <td style={{ padding: 12, verticalAlign: 'top' }}>{item.scan_cycle || '-'}</td>
                        <td style={{ padding: 12, verticalAlign: 'top' }}>
                          <div>수익률 {formatPercent(research.backtest_return_pct, 1)}</div>
                          <div className="signal-cell-copy">WF {formatPercent(research.walk_forward_return_pct, 1)} · Sharpe {research.sharpe ?? '-'}</div>
                        </td>
                        <td style={{ padding: 12, verticalAlign: 'top' }}>{formatDateTime(item.enabled_at)}</td>
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
                              disabled={readOnly || !strategyId || pendingId === strategyId}
                            >
                              {readOnly ? '운영 전용' : pendingId === strategyId ? '처리 중...' : enabled ? '비활성화' : '활성화'}
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
                      <span className={lifecycleBadge(item).className}>{lifecycleBadge(item).label}</span>
                    </div>
                    <div className="responsive-card-grid">
                      <div><div className="responsive-card-label">상태</div><div className="responsive-card-value" style={{ marginTop: 4 }}><span className={lifecycleBadge(item).className}>{lifecycleBadge(item).label}</span></div></div>
                      <div><div className="responsive-card-label">시장</div><div className="responsive-card-value">{item.market || '-'}</div></div>
                      <div><div className="responsive-card-label">유니버스</div><div className="responsive-card-value">{item.universe_rule || '-'}</div></div>
                      <div><div className="responsive-card-label">스캔 주기</div><div className="responsive-card-value">{item.scan_cycle || '-'}</div></div>
                      <div><div className="responsive-card-label">연구 성과</div><div className="responsive-card-value">수익률 {formatPercent(research.backtest_return_pct, 1)} · WF {formatPercent(research.walk_forward_return_pct, 1)}</div></div>
                      <div><div className="responsive-card-label">활성화 일시</div><div className="responsive-card-value">{formatDateTime(item.enabled_at)}</div></div>
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
                        disabled={readOnly || !strategyId || pendingId === strategyId}
                      >
                        {readOnly ? '운영 전용' : pendingId === strategyId ? '처리 중...' : enabled ? '비활성화' : '활성화'}
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
                  <span className={lifecycleBadge(selectedStrategy).className}>{lifecycleBadge(selectedStrategy).label}</span>
                  {!readOnly && (
                    <>
                      <button className="ghost-button" onClick={() => { void handleClonePreset(); }} disabled={!selectedStrategy.strategy_id}>
                        현재 전략 복제
                      </button>
                      <button className="ghost-button" onClick={() => {
                        localStorage.setItem(VALIDATION_TRANSFER_STORAGE_KEY, JSON.stringify(selectedStrategy));
                        window.location.href = '/lab/validation';
                      }}>
                        전략 검증 랩 열기
                      </button>
                      <button className="ghost-button" onClick={() => { void handleDeletePreset(); }} disabled={!selectedStrategy.strategy_id || pendingId === String(selectedStrategy.strategy_id)}>
                        프리셋 삭제
                      </button>
                    </>
                  )}
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
                  <div className="summary-metric-detail" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    scan cycle
                    {!readOnly ? (
                      <select
                        value={selectedStrategy.scan_cycle || '5m'}
                        disabled={!!pendingId}
                        onChange={(e) => { void handleEditScanCycle(e.target.value); }}
                        style={{ fontSize: 11, padding: '1px 4px', marginLeft: 2 }}
                      >
                        {SCAN_CYCLE_OPTIONS.map(opt => (
                          <option key={opt} value={opt}>{opt}</option>
                        ))}
                      </select>
                    ) : (
                      <span>{selectedStrategy.scan_cycle || '-'}</span>
                    )}
                  </div>
                </div>
                <div className="summary-metric-card">
                  <div className="summary-metric-label">연구 성과</div>
                  <div className="summary-metric-value">{formatPercent(selectedStrategy.research_summary?.backtest_return_pct, 1)}</div>
                  <div className="summary-metric-detail">WF {formatPercent(selectedStrategy.research_summary?.walk_forward_return_pct, 1)} · Sharpe {selectedStrategy.research_summary?.sharpe ?? '-'}</div>
                </div>
              </div>

              <div className="strategy-detail-grid">
                <div className="page-section" style={{ padding: 16 }}>
                  <div className="section-title">현재 룰</div>
                  <div className="detail-list">
                    <div><strong>Entry</strong> · {selectedStrategy.entry_rule || '-'}</div>
                    <div><strong>Exit</strong> · {selectedStrategy.exit_rule || '-'}</div>
                    <div><strong>활성화 일시</strong> · {formatDateTime(selectedStrategy.enabled_at)}</div>
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
                    <div className="section-copy">
                      {readOnly
                        ? '운영 모드에서는 적용 후보를 읽기 전용으로 확인합니다. 값 변경과 검증은 실험 모드에서만 수행합니다.'
                        : '여기 값은 현재 전략 레지스트리에 저장된 프리셋이야. 실험용으로 값을 바꿔보는 건 검증 랩에서 하는 게 맞아.'}
                    </div>
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
