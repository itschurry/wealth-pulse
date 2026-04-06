import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ChangeEvent } from 'react';
import { getJSON, postJSON } from '../api/client';
import { fetchStrategyMetadata, fetchValidationBacktest, fetchValidationWalkForward, saveStrategyPreset } from '../api/domain';
import { ConsoleActionBar } from '../components/ConsoleActionBar';
import { defaultBacktestQuery } from '../hooks/useBacktest';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import { formatValidationSettingsLabel, useValidationSettingsStore } from '../hooks/useValidationSettingsStore';
import type { ValidationSettings } from '../hooks/useValidationSettingsStore';
import type { BacktestData, BacktestQuery, StrategyKind } from '../types';
import type { StrategyRegistryItem, ValidationResponse } from '../types/domain';
import type { ActionBarAction, ConsoleSnapshot } from '../types/consoleView';
import type { StrategiesMetadataResponse } from '../types/domain';
import { formatCount, formatDateTime, formatKRW, formatNumber, formatPercent, formatUSD } from '../utils/format';

interface BacktestValidationPageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
}

const STRATEGY_VALIDATION_TRANSFER_KEY = 'console_strategy_validation_transfer_v1';

function strategyLabel(strategyKind: string | undefined) {
  if (strategyKind === 'mean_reversion') return 'Mean Reversion';
  if (strategyKind === 'defensive') return 'Defensive';
  return 'Trend Following';
}

function marketLabel(scope: BacktestQuery['market_scope']) {
  if (scope === 'nasdaq') return 'NASDAQ';
  if (scope === 'all') return 'KOSPI + NASDAQ';
  return 'KOSPI';
}

function numberOrNull(value: string): number | null {
  if (!value.trim()) return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function strategyKindFromUnknown(value: unknown): StrategyKind {
  if (value === 'mean_reversion' || value === 'defensive') return value;
  return 'trend_following';
}

function currencyCode(scope: BacktestQuery['market_scope']) {
  return scope === 'nasdaq' ? 'USD' : 'KRW';
}

function formatNumericDisplay(
  value: number | null | undefined,
  options?: { decimals?: number; currency?: 'KRW' | 'USD' | null },
) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '';
  if (options?.currency === 'USD') return formatUSD(value, false);
  if (options?.currency === 'KRW') return formatKRW(value, false);
  return formatNumber(value, options?.decimals ?? 0);
}

function formatEditingValue(value: number | null | undefined, decimals = 0) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '';
  if (decimals <= 0) return String(Math.round(value));
  return String(value);
}

function applyStrategyParamsToQuery(
  query: BacktestQuery,
  strategyParams: Record<string, unknown>,
): BacktestQuery {
  const mergedParams: Record<string, number | string | boolean | null> = {
    ...query.strategy_params,
    ...strategyParams,
  } as Record<string, number | string | boolean | null>;

  const maxHoldingDaysValue = mergedParams.max_holding_days;
  const maxHoldingDays = typeof maxHoldingDaysValue === 'number' && Number.isFinite(maxHoldingDaysValue)
    ? maxHoldingDaysValue
    : query.portfolio_constraints.max_holding_days;

  return {
    ...query,
    strategy_params: mergedParams,
    max_holding_days: maxHoldingDays,
    portfolio_constraints: {
      ...query.portfolio_constraints,
      max_holding_days: maxHoldingDays,
    },
    rsi_min: Number(mergedParams.rsi_min ?? query.rsi_min),
    rsi_max: Number(mergedParams.rsi_max ?? query.rsi_max),
    volume_ratio_min: Number(mergedParams.volume_ratio_min ?? query.volume_ratio_min),
    stop_loss_pct: mergedParams.stop_loss_pct == null ? null : Number(mergedParams.stop_loss_pct),
    take_profit_pct: mergedParams.take_profit_pct == null ? null : Number(mergedParams.take_profit_pct),
    adx_min: mergedParams.adx_min == null ? null : Number(mergedParams.adx_min),
    mfi_min: mergedParams.mfi_min == null ? null : Number(mergedParams.mfi_min),
    mfi_max: mergedParams.mfi_max == null ? null : Number(mergedParams.mfi_max),
    bb_pct_min: mergedParams.bb_pct_min == null ? null : Number(mergedParams.bb_pct_min),
    bb_pct_max: mergedParams.bb_pct_max == null ? null : Number(mergedParams.bb_pct_max),
    stoch_k_min: mergedParams.stoch_k_min == null ? null : Number(mergedParams.stoch_k_min),
    stoch_k_max: mergedParams.stoch_k_max == null ? null : Number(mergedParams.stoch_k_max),
  };
}

interface NumericInputProps {
  value: number | null | undefined;
  onCommit: (value: number | null) => void;
  min?: number;
  max?: number;
  step?: number;
  allowNull?: boolean;
  decimals?: number;
  currency?: 'KRW' | 'USD' | null;
}

function NumericInput({
  value,
  onCommit,
  min,
  max,
  step,
  allowNull = false,
  decimals = 0,
  currency = null,
}: NumericInputProps) {
  const [focused, setFocused] = useState(false);
  const [draft, setDraft] = useState('');

  useEffect(() => {
    if (!focused) {
      setDraft(formatEditingValue(value, decimals));
    }
  }, [decimals, focused, value]);

  const commitCurrent = useCallback(() => {
    const raw = draft.replace(/,/g, '').trim();
    setFocused(false);
    if (!raw) {
      if (allowNull) {
        onCommit(null);
        setDraft('');
      } else {
        setDraft(formatEditingValue(value, decimals));
      }
      return;
    }

    const parsed = Number(raw);
    if (!Number.isFinite(parsed)) {
      setDraft(formatEditingValue(value, decimals));
      return;
    }

    let nextValue = decimals <= 0 ? Math.round(parsed) : parsed;
    if (typeof min === 'number') nextValue = Math.max(min, nextValue);
    if (typeof max === 'number') nextValue = Math.min(max, nextValue);
    onCommit(nextValue);
    setDraft(formatEditingValue(nextValue, decimals));
  }, [allowNull, decimals, draft, max, min, onCommit, value]);

  return (
    <input
      className="backtest-input-wrap"
      type="text"
      inputMode={decimals > 0 ? 'decimal' : 'numeric'}
      value={focused ? draft : formatNumericDisplay(value, { decimals, currency })}
      onFocus={() => {
        setFocused(true);
        setDraft(formatEditingValue(value, decimals));
      }}
      onChange={(event) => {
        const raw = event.target.value.replace(/,/g, '');
        if (raw === '' || /^-?\d*(\.\d*)?$/.test(raw)) {
          setDraft(raw);
        }
      }}
      onBlur={commitCurrent}
      onKeyDown={(event) => {
        if (event.key === 'Enter') {
          event.currentTarget.blur();
        }
      }}
      data-step={step ?? undefined}
    />
  );
}

function strategyDefaultsFromMetadata(
  metadata: StrategiesMetadataResponse | null,
  strategyKind: StrategyKind,
  marketScope: BacktestQuery['market_scope'],
  riskProfile: BacktestQuery['risk_profile'],
) {
  const marketKey = marketScope === 'nasdaq' ? 'NASDAQ' : 'KOSPI';
  const strategy = metadata?.available_strategies?.find((item) => item.strategy_kind === strategyKind);
  if (strategy?.defaults_by_market_and_risk?.[marketKey]?.[riskProfile]) {
    return strategy.defaults_by_market_and_risk[marketKey][riskProfile] as Record<string, unknown>;
  }
  if (strategy?.defaults_by_market?.[marketKey]) {
    return strategy.defaults_by_market[marketKey] as Record<string, unknown>;
  }
  return defaultBacktestQuery(marketScope, strategyKind, riskProfile).strategy_params;
}

function syncQueryWithStrategy(
  query: BacktestQuery,
  strategyKind: StrategyKind,
  marketScope: BacktestQuery['market_scope'],
  metadata: StrategiesMetadataResponse | null,
): BacktestQuery {
  const fallback = defaultBacktestQuery(marketScope, strategyKind, query.risk_profile);
  const strategyDefaults = strategyDefaultsFromMetadata(metadata, strategyKind, marketScope, query.risk_profile);
  const portfolioDefaults = metadata?.portfolio_defaults?.[marketScope] as Record<string, unknown> | undefined;
  const maxHoldingDays = Number(strategyDefaults.max_holding_days ?? portfolioDefaults?.max_holding_days ?? fallback.max_holding_days);
  const nextQuery: BacktestQuery = {
    ...fallback,
    ...query,
    market_scope: marketScope,
    strategy_kind: strategyKind,
    max_holding_days: maxHoldingDays,
    portfolio_constraints: {
      market_scope: marketScope,
      initial_cash: Number(query.portfolio_constraints?.initial_cash ?? portfolioDefaults?.initial_cash ?? fallback.portfolio_constraints.initial_cash),
      max_positions: Number(query.portfolio_constraints?.max_positions ?? portfolioDefaults?.max_positions ?? fallback.portfolio_constraints.max_positions),
      max_holding_days: maxHoldingDays,
    },
    strategy_params: {
      ...strategyDefaults,
    } as Record<string, number | string | boolean | null>,
  };
  const params = nextQuery.strategy_params;
  return applyStrategyParamsToQuery({
    ...nextQuery,
    initial_cash: nextQuery.portfolio_constraints.initial_cash,
    max_positions: nextQuery.portfolio_constraints.max_positions,
  }, params as Record<string, unknown>);
}

export function BacktestValidationPage({ snapshot, loading, errorMessage, onRefresh }: BacktestValidationPageProps) {
  const validationStore = useValidationSettingsStore();
  const { entries, push, clear } = useConsoleLogs();
  const [metadata, setMetadata] = useState<StrategiesMetadataResponse | null>(null);
  const [metadataLoading, setMetadataLoading] = useState(true);
  const [optimizationRunning, setOptimizationRunning] = useState(false);
  const [optimizationPayload, setOptimizationPayload] = useState<Record<string, unknown> | null>(null);
  const [optimizationMessage, setOptimizationMessage] = useState('');
  const [data, setData] = useState<BacktestData>({});
  const [status, setStatus] = useState<'idle' | 'loading' | 'ok' | 'error'>('idle');
  const [lastError, setLastError] = useState('');
  const [wfData, setWfData] = useState<ValidationResponse>({});
  const [wfStatus, setWfStatus] = useState<'idle' | 'loading' | 'ok' | 'error'>('idle');
  const [wfLastError, setWfLastError] = useState('');

  // Bug 1 fix: read transfer payload immediately on mount before any effects run,
  // then apply once metadata is available to avoid the race condition where
  // the effect ran with null metadata and cleared the localStorage key.
  const transferRef = useRef<StrategyRegistryItem | null>(null);
  const transferApplied = useRef(false);
  if (transferRef.current === null && !transferApplied.current) {
    const raw = localStorage.getItem(STRATEGY_VALIDATION_TRANSFER_KEY);
    if (raw) {
      localStorage.removeItem(STRATEGY_VALIDATION_TRANSFER_KEY);
      try { transferRef.current = JSON.parse(raw) as StrategyRegistryItem; } catch { /* ignore */ }
    }
  }

  useEffect(() => {
    let cancelled = false;
    async function loadMetadata() {
      setMetadataLoading(true);
      try {
        const payload = await fetchStrategyMetadata();
        if (!cancelled) setMetadata(payload);
      } catch {
        if (!cancelled) setMetadata(null);
      } finally {
        if (!cancelled) setMetadataLoading(false);
      }
    }
    loadMetadata();
    return () => {
      cancelled = true;
    };
  }, []);

  // Bug 1 fix: apply the transfer only after metadata is loaded (1 time)
  useEffect(() => {
    if (metadataLoading || transferApplied.current || !transferRef.current) return;
    transferApplied.current = true;
    const payload = transferRef.current;
    try {
      const strategyKind = strategyKindFromUnknown(payload.strategy_kind || payload.strategy_id);
      const sourceParams = payload.params && typeof payload.params === 'object' ? payload.params as Record<string, unknown> : {};
      validationStore.setDraftQuery((prev) => {
        const synced = syncQueryWithStrategy(prev, strategyKind, prev.market_scope, metadata);
        return applyStrategyParamsToQuery(synced, sourceParams);
      });
      push('info', '전략 프리셋을 검증 랩으로 불러왔습니다.', `${strategyLabel(strategyKind)} · 시장/유니버스는 현재 검증 랩 설정을 유지합니다.`, 'transfer');
    } catch {
      push('warning', '전략 프리셋 전달값을 적용하지 못했습니다.', undefined, 'transfer');
    }
  }, [metadataLoading, metadata, push, validationStore]);

  useEffect(() => {
    if (validationStore.serverLoaded) return;
    validationStore.loadSavedFromServer().catch(() => undefined);
  }, [validationStore]);

  const fetchOptimizationArtifacts = useCallback(async () => {
    try {
      const payload = await getJSON<Record<string, unknown>>('/api/optimized-params', { noStore: true });
      setOptimizationPayload(payload);
    } catch {
      setOptimizationPayload(null);
    }
    try {
      const statusPayload = await getJSON<{ running?: boolean }>('/api/optimization-status', { noStore: true });
      setOptimizationRunning(Boolean(statusPayload.running));
    } catch {
      setOptimizationRunning(false);
    }
  }, []);

  useEffect(() => {
    fetchOptimizationArtifacts().catch(() => undefined);
  }, [fetchOptimizationArtifacts]);

  useEffect(() => {
    if (!optimizationRunning) return;
    const timer = window.setInterval(() => {
      fetchOptimizationArtifacts().catch(() => undefined);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [fetchOptimizationArtifacts, optimizationRunning]);

  const displayedResult = useMemo<BacktestData>(() => {
    if (status === 'ok' || status === 'error') return data;
    return {};
  }, [data, status]);

  const editableFields = useMemo(() => {
    const strategy = metadata?.available_strategies?.find((item) => item.strategy_kind === validationStore.draftQuery.strategy_kind);
    return strategy?.editable_fields || [];
  }, [metadata, validationStore.draftQuery.strategy_kind]);

  const statusItems = useMemo(() => ([
    { label: '전략', value: strategyLabel(validationStore.draftQuery.strategy_kind), tone: 'neutral' as const },
    { label: 'Regime', value: validationStore.draftQuery.regime_mode === 'auto' ? '자동' : '수동', tone: 'neutral' as const },
    { label: '리스크', value: validationStore.draftQuery.risk_profile, tone: 'neutral' as const },
    { label: '백테스트', value: status === 'loading' ? '실행 중' : displayedResult.error ? '실패' : displayedResult.metrics ? '완료' : '대기', tone: displayedResult.error ? 'bad' as const : displayedResult.metrics ? 'good' as const : 'neutral' as const },
    { label: '최적화', value: optimizationRunning ? '실행 중' : optimizationPayload?.status === 'ok' ? '결과 있음' : '대기', tone: optimizationRunning ? 'neutral' as const : optimizationPayload?.status === 'ok' ? 'good' as const : 'neutral' as const },
  ]), [displayedResult.error, displayedResult.metrics, optimizationPayload?.status, optimizationRunning, status, validationStore.draftQuery.regime_mode, validationStore.draftQuery.risk_profile, validationStore.draftQuery.strategy_kind]);

  const applyStrategyPreset = useCallback((strategyKind: StrategyKind, marketScope: BacktestQuery['market_scope']) => {
    validationStore.setDraftQuery((prev) => syncQueryWithStrategy(prev, strategyKind, marketScope, metadata));
  }, [metadata, validationStore]);

  const handleMarketChange = useCallback((event: ChangeEvent<HTMLSelectElement>) => {
    const marketScope = event.target.value as BacktestQuery['market_scope'];
    applyStrategyPreset(validationStore.draftQuery.strategy_kind, marketScope);
  }, [applyStrategyPreset, validationStore.draftQuery.strategy_kind]);

  const handleStrategyChange = useCallback((event: ChangeEvent<HTMLSelectElement>) => {
    applyStrategyPreset(event.target.value as StrategyKind, validationStore.draftQuery.market_scope);
  }, [applyStrategyPreset, validationStore.draftQuery.market_scope]);

  const updateDraftQuery = useCallback((patch: Partial<BacktestQuery>) => {
    validationStore.setDraftQuery((prev) => ({ ...prev, ...patch }));
  }, [validationStore]);

  const updatePortfolioField = useCallback((field: keyof BacktestQuery['portfolio_constraints']) => (numeric: number | null) => {
    if (numeric === null) return;
    validationStore.setDraftQuery((prev) => {
      const nextPortfolio = {
        ...prev.portfolio_constraints,
        [field]: numeric,
      };
      return {
        ...prev,
        portfolio_constraints: nextPortfolio,
        initial_cash: field === 'initial_cash' ? numeric : prev.initial_cash,
        max_positions: field === 'max_positions' ? numeric : prev.max_positions,
        max_holding_days: field === 'max_holding_days' ? numeric : prev.max_holding_days,
      };
    });
  }, [validationStore]);

  const updateStrategyParam = useCallback((name: string) => (numeric: number | null) => {
    validationStore.setDraftQuery((prev) => {
      const nextParams: Record<string, number | string | boolean | null> = {
        ...prev.strategy_params,
        [name]: numeric,
      };
      return applyStrategyParamsToQuery({
        ...prev,
        strategy_params: nextParams as BacktestQuery['strategy_params'],
      }, nextParams);
    });
  }, [validationStore]);

  const handleSave = useCallback(async () => {
    try {
      await validationStore.saveDraftToServer();
      push('success', '전략 검증 설정을 저장했습니다.', formatValidationSettingsLabel(validationStore.draftSettings, validationStore.draftQuery).join(' · '), 'settings');
    } catch {
      push('error', '설정 저장에 실패했습니다.', undefined, 'settings');
    }
  }, [push, validationStore]);

  const handleRunWalkForward = useCallback(async () => {
    setWfStatus('loading');
    setWfLastError('');
    try {
      const result = await fetchValidationWalkForward(validationStore.draftQuery, validationStore.draftSettings);
      setWfData(result);
      if (result.ok === false) {
        setWfStatus('error');
        const msg = 'Walk-forward 검증에 실패했습니다.';
        setWfLastError(msg);
        push('error', msg, undefined, 'walkforward');
      } else {
        setWfStatus('ok');
        push(
          'success',
          'Walk-forward 검증을 완료했습니다.',
          `윈도우 ${result.summary?.windows ?? 0}개 · 양호 비율 ${formatPercent(result.summary?.positive_window_ratio, 1, true)}`,
          'walkforward',
        );
      }
    } catch {
      setWfStatus('error');
      const msg = 'Walk-forward 응답을 불러오지 못했습니다.';
      setWfLastError(msg);
      push('error', msg, undefined, 'walkforward');
    }
  }, [push, validationStore.draftQuery, validationStore.draftSettings]);

  // Bug 2 fix: use /api/validation/backtest (extended metrics) instead of /api/backtest/run
  const handleRunBacktest = useCallback(async () => {
    setStatus('loading');
    setLastError('');
    try {
      const result = await fetchValidationBacktest(validationStore.draftQuery, validationStore.draftSettings);
      setData(result);
      if (result.error) {
        setStatus('error');
        setLastError(result.error);
        push('error', '전략 백테스트에 실패했습니다.', result.error, 'backtest');
      } else {
        setStatus('ok');
        push(
          'success',
          '전략 백테스트를 완료했습니다.',
          `${strategyLabel(validationStore.draftQuery.strategy_kind)} · ${marketLabel(validationStore.draftQuery.market_scope)} · ${formatCount(result.metrics?.trade_count ?? result.performance_summary?.trade_count ?? 0, '건')}`,
          'backtest',
        );
      }
    } catch {
      setStatus('error');
      const msg = '백테스트 응답을 불러오지 못했습니다.';
      setLastError(msg);
      push('error', msg, undefined, 'backtest');
    }
  }, [push, validationStore.draftQuery, validationStore.draftSettings]);

  const handleRunOptimization = useCallback(async () => {
    setOptimizationMessage('강건성 검증을 요청했습니다.');
    try {
      const response = await postJSON<{ status?: string; error?: string }>('/api/run-optimization', {
        query: validationStore.draftQuery,
        settings: validationStore.draftSettings,
      });
      if (response.data?.status === 'started' || response.data?.status === 'already_running') {
        setOptimizationRunning(true);
        push('info', '강건성 검증을 시작했습니다.', `${strategyLabel(validationStore.draftQuery.strategy_kind)} · ${validationStore.draftQuery.regime_mode}`, 'optimization');
      } else {
        push('warning', '강건성 검증 응답이 예상과 다릅니다.', response.data?.error, 'optimization');
      }
      fetchOptimizationArtifacts().catch(() => undefined);
    } catch {
      setOptimizationMessage('강건성 검증 요청에 실패했습니다.');
      push('error', '강건성 검증 요청에 실패했습니다.', undefined, 'optimization');
    }
  }, [fetchOptimizationArtifacts, push, validationStore.draftQuery, validationStore.draftSettings]);

  const [presetSaving, setPresetSaving] = useState(false);
  const handleSaveAsPreset = useCallback(async () => {
    const q = validationStore.draftQuery;
    const defaultName = `${q.strategy_kind === 'mean_reversion' ? 'Mean Reversion' : q.strategy_kind === 'defensive' ? 'Defensive' : 'Trend Following'} · ${q.market_scope.toUpperCase()} · ${q.risk_profile}`;
    const rawName = window.prompt('프리셋 이름을 입력해줘.', defaultName);
    if (!rawName) return;
    const name = rawName.trim();
    const defaultId = name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'validated_preset';
    const strategyId = window.prompt('전략 ID를 입력해줘.', defaultId);
    if (!strategyId) return;

    const metrics = displayedResult.metrics;
    const perf = displayedResult.performance_summary;
    const researchSummary = {
      backtest_return_pct: metrics?.total_return_pct ?? perf?.cagr_pct ?? null,
      max_drawdown_pct: metrics?.max_drawdown_pct ?? perf?.max_drawdown_pct ?? null,
      win_rate_pct: metrics?.win_rate_pct ?? perf?.win_rate_pct ?? null,
      sharpe: metrics?.sharpe ?? null,
      walk_forward_return_pct: null,
    };

    const market = q.market_scope === 'nasdaq' ? 'NASDAQ' : 'KOSPI';
    const universeRule = q.market_scope === 'nasdaq' ? 'sp500' : q.market_scope === 'all' ? 'multi_market' : 'kospi';
    const payload = {
      strategy_id: strategyId.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, ''),
      strategy_kind: q.strategy_kind,
      name,
      enabled: false,
      status: 'ready',
      market,
      universe_rule: universeRule,
      scan_cycle: q.market_scope === 'nasdaq' ? '15m' : '5m',
      params: { ...q.strategy_params },
      risk_limits: {
        max_positions: q.portfolio_constraints.max_positions,
        position_size_pct: 0.1,
        daily_loss_limit_pct: 0.02,
      },
      research_summary: researchSummary,
    };

    setPresetSaving(true);
    try {
      const response = await saveStrategyPreset(payload);
      if (!response.ok) {
        push('error', '프리셋 저장에 실패했습니다.', '', 'settings');
        return;
      }
      push('success', `프리셋 "${name}" 을 저장했습니다.`, '전략 관리에서 상태를 확인하고 활성화할 수 있습니다.', 'settings');
    } finally {
      setPresetSaving(false);
    }
  }, [displayedResult, push, validationStore.draftQuery]);

  const actions = useMemo<ActionBarAction[]>(() => ([
    {
      label: '설정 저장',
      tone: 'default',
      onClick: handleSave,
      disabled: validationStore.syncStatus === 'saving',
      busy: validationStore.syncStatus === 'saving',
    },
    {
      label: '백테스트 실행',
      tone: 'primary',
      onClick: handleRunBacktest,
      disabled: status === 'loading',
      busy: status === 'loading',
    },
    {
      label: 'Walk-forward 검증',
      tone: 'default',
      onClick: handleRunWalkForward,
      disabled: wfStatus === 'loading',
      busy: wfStatus === 'loading',
      busyLabel: '검증 중...',
    },
    {
      label: '강건성 검증',
      tone: 'default',
      onClick: handleRunOptimization,
      disabled: optimizationRunning,
      busy: optimizationRunning,
      busyLabel: '실행 중...',
    },
  ]), [handleRunBacktest, handleRunOptimization, handleRunWalkForward, handleSave, optimizationRunning, status, validationStore.syncStatus, wfStatus]);

  const summaryMetrics = displayedResult.performance_summary || {};
  const executionSummary = displayedResult.execution_summary || {};
  const searchContext = optimizationPayload?.meta && typeof optimizationPayload.meta === 'object'
    ? (optimizationPayload.meta as Record<string, unknown>).search_context as Record<string, unknown> | undefined
    : undefined;
  const optimizerAggregateRobustZone = optimizationPayload?.aggregate_robust_zone && typeof optimizationPayload.aggregate_robust_zone === 'object'
    ? optimizationPayload.aggregate_robust_zone as {
      summary?: string;
      parameter_bands?: Record<string, { label?: string; selected?: unknown; min?: number; max?: number }>;
    }
    : undefined;
  const initialCashCurrency = currencyCode(validationStore.draftQuery.market_scope);

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell console-page-shell" style={{ display: 'grid', gap: 16 }}>
          <ConsoleActionBar
            title="전략 검증"
            subtitle="전략 종류를 먼저 선택하고, regime/risk/portfolio 제약을 정한 뒤 전략별 파라미터를 조정합니다. Monte Carlo는 최적값 발굴기가 아니라 전략별 강건성 검증기로 취급합니다."
            lastUpdated={snapshot.fetchedAt}
            loading={loading || metadataLoading}
            errorMessage={errorMessage || lastError}
            statusItems={statusItems}
            onRefresh={onRefresh}
            actions={actions}
            logs={entries}
            onClearLogs={clear}
            settingsDirty={validationStore.unsaved}
            settingsSavedAt={validationStore.lastSavedAt}
          />

          <section className="page-section console-card-section" style={{ display: 'grid', gap: 16 }}>
            <div style={{ fontSize: 14, fontWeight: 700 }}>설정</div>
            <div className="backtest-grid">
              <label style={{ display: 'grid', gap: 6 }}>
                <span>전략</span>
                <select className="backtest-input-wrap" value={validationStore.draftQuery.strategy_kind} onChange={handleStrategyChange}>
                  <option value="trend_following">Trend Following</option>
                  <option value="mean_reversion">Mean Reversion</option>
                  <option value="defensive">Defensive</option>
                </select>
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span>Regime 모드</span>
                <select className="backtest-input-wrap" value={validationStore.draftQuery.regime_mode} onChange={(event) => updateDraftQuery({ regime_mode: event.target.value as BacktestQuery['regime_mode'] })}>
                  <option value="auto">자동</option>
                  <option value="manual">수동</option>
                </select>
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span>리스크 프로필</span>
                <select
                  className="backtest-input-wrap"
                  value={validationStore.draftQuery.risk_profile}
                  onChange={(event) => {
                    const nextRiskProfile = event.target.value as BacktestQuery['risk_profile'];
                    validationStore.setDraftQuery((prev) => syncQueryWithStrategy(
                      { ...prev, risk_profile: nextRiskProfile },
                      prev.strategy_kind,
                      prev.market_scope,
                      metadata,
                    ));
                  }}
                >
                  <option value="conservative">conservative</option>
                  <option value="balanced">balanced</option>
                  <option value="aggressive">aggressive</option>
                </select>
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span>시장</span>
                <select className="backtest-input-wrap" value={validationStore.draftQuery.market_scope} onChange={handleMarketChange}>
                  <option value="kospi">KOSPI</option>
                  <option value="nasdaq">NASDAQ</option>
                  <option value="all">KOSPI + NASDAQ</option>
                </select>
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span>백테스트 기간</span>
                <NumericInput
                  value={validationStore.draftQuery.lookback_days}
                  min={180}
                  max={1825}
                  step={30}
                  onCommit={(numeric) => {
                    if (numeric === null) return;
                    updateDraftQuery({ lookback_days: numeric });
                  }}
                />
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span>{`초기 자금 (${initialCashCurrency})`}</span>
                <NumericInput
                  value={validationStore.draftQuery.portfolio_constraints.initial_cash}
                  min={1}
                  step={1000}
                  currency={initialCashCurrency}
                  onCommit={updatePortfolioField('initial_cash')}
                />
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span>최대 포지션</span>
                <NumericInput value={validationStore.draftQuery.portfolio_constraints.max_positions} min={1} max={20} step={1} onCommit={updatePortfolioField('max_positions')} />
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span>최대 보유일</span>
                <NumericInput value={validationStore.draftQuery.portfolio_constraints.max_holding_days} min={1} max={180} step={1} onCommit={updatePortfolioField('max_holding_days')} />
              </label>
            </div>

            <div style={{ display: 'grid', gap: 10 }}>
              <div style={{ fontSize: 13, fontWeight: 700 }}>전략별 파라미터</div>
              <div className="backtest-grid">
                {editableFields.length > 0 ? editableFields.map((field) => (
                  <label key={field.name} style={{ display: 'grid', gap: 6 }}>
                    <span>{field.label || field.name}</span>
                    <NumericInput
                      value={typeof validationStore.draftQuery.strategy_params?.[String(field.name || '')] === 'number'
                        ? validationStore.draftQuery.strategy_params?.[String(field.name || '')] as number
                        : numberOrNull(String(validationStore.draftQuery.strategy_params?.[String(field.name || '')] ?? ''))}
                      min={field.min}
                      max={field.max}
                      step={field.step || 1}
                      decimals={Number(field.step || 1) < 1 ? 2 : 0}
                      allowNull
                      onCommit={updateStrategyParam(String(field.name || ''))}
                    />
                  </label>
                )) : !metadataLoading ? (
                  Object.entries(validationStore.draftQuery.strategy_params || {})
                    .filter(([, v]) => typeof v === 'number')
                    .map(([key, value]) => (
                      <label key={key} style={{ display: 'grid', gap: 6 }}>
                        <span>{key}</span>
                        <NumericInput
                          value={value as number}
                          decimals={(value as number) % 1 !== 0 ? 2 : 0}
                          allowNull
                          onCommit={updateStrategyParam(key)}
                        />
                      </label>
                    ))
                ) : null}
              </div>
            </div>

            <div style={{ display: 'grid', gap: 10 }}>
              <div style={{ fontSize: 13, fontWeight: 700 }}>검증 설정</div>
              <div className="backtest-grid">
                <label style={{ display: 'grid', gap: 6 }}>
                  <span>학습 구간 (일)</span>
                  <NumericInput
                    value={validationStore.draftSettings.trainingDays}
                    min={30}
                    max={730}
                    step={30}
                    onCommit={(v) => { if (v !== null) validationStore.setDraftSettings((prev) => ({ ...prev, trainingDays: v })); }}
                  />
                </label>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span>검증 구간 (일)</span>
                  <NumericInput
                    value={validationStore.draftSettings.validationDays}
                    min={20}
                    max={365}
                    step={20}
                    onCommit={(v) => { if (v !== null) validationStore.setDraftSettings((prev) => ({ ...prev, validationDays: v })); }}
                  />
                </label>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span>최소 거래수</span>
                  <NumericInput
                    value={validationStore.draftSettings.minTrades}
                    min={1}
                    max={200}
                    step={5}
                    onCommit={(v) => { if (v !== null) validationStore.setDraftSettings((prev) => ({ ...prev, minTrades: v })); }}
                  />
                </label>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span>Walk-forward</span>
                  <select
                    className="backtest-input-wrap"
                    value={validationStore.draftSettings.walkForward ? 'on' : 'off'}
                    onChange={(e) => validationStore.setDraftSettings((prev) => ({ ...prev, walkForward: e.target.value === 'on' }))}
                  >
                    <option value="on">사용</option>
                    <option value="off">미사용</option>
                  </select>
                </label>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span>Objective</span>
                  <select
                    className="backtest-input-wrap"
                    value={validationStore.draftSettings.objective}
                    onChange={(e) => validationStore.setDraftSettings((prev) => ({ ...prev, objective: e.target.value }))}
                  >
                    <option value="수익 우선">수익 우선</option>
                    <option value="안정성 우선">안정성 우선</option>
                    <option value="균형">균형</option>
                  </select>
                </label>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span>후보 소스</span>
                  <select
                    className="backtest-input-wrap"
                    value={validationStore.draftSettings.runtimeCandidateSourceMode}
                    onChange={(e) => validationStore.setDraftSettings((prev) => ({ ...prev, runtimeCandidateSourceMode: e.target.value as ValidationSettings['runtimeCandidateSourceMode'] }))}
                  >
                    <option value="quant_only">quant_only</option>
                    <option value="hybrid">hybrid</option>
                  </select>
                </label>
              </div>
            </div>
          </section>

          <section className="page-section console-card-section" style={{ display: 'grid', gap: 12 }}>
            <div style={{ fontSize: 14, fontWeight: 700 }}>실행 요약</div>
            <div className="console-metric-grid">
              <div><div style={{ fontSize: 12, color: 'var(--text-4)' }}>선택 전략</div><div style={{ marginTop: 6, fontWeight: 700 }}>{strategyLabel(displayedResult.strategy_kind || validationStore.draftQuery.strategy_kind)}</div></div>
              <div><div style={{ fontSize: 12, color: 'var(--text-4)' }}>Resolved 전략</div><div style={{ marginTop: 6, fontWeight: 700 }}>{strategyLabel(String(executionSummary.resolved_strategy_kind || displayedResult.resolved_strategy_kind || validationStore.draftQuery.strategy_kind))}</div></div>
              <div><div style={{ fontSize: 12, color: 'var(--text-4)' }}>Resolved Regime</div><div style={{ marginTop: 6, fontWeight: 700 }}>{String(executionSummary.resolved_regime || displayedResult.resolved_regime || validationStore.draftQuery.regime_mode)}</div></div>
              <div><div style={{ fontSize: 12, color: 'var(--text-4)' }}>Risk 프로필</div><div style={{ marginTop: 6, fontWeight: 700 }}>{displayedResult.risk_profile || validationStore.draftQuery.risk_profile}</div></div>
              <div><div style={{ fontSize: 12, color: 'var(--text-4)' }}>시장</div><div style={{ marginTop: 6, fontWeight: 700 }}>{marketLabel(validationStore.draftQuery.market_scope)}</div></div>
              <div><div style={{ fontSize: 12, color: 'var(--text-4)' }}>최근 실행</div><div style={{ marginTop: 6, fontWeight: 700 }}>{formatDateTime(displayedResult.generated_at || '') || '-'}</div></div>
            </div>
          </section>

          <section className="page-section console-card-section" style={{ display: 'grid', gap: 12 }}>
            <div style={{ fontSize: 14, fontWeight: 700 }}>성능 요약</div>
            <div className="console-metric-grid">
              <div><div style={{ fontSize: 12, color: 'var(--text-4)' }}>CAGR</div><div style={{ marginTop: 6, fontWeight: 700 }}>{formatPercent(summaryMetrics.cagr_pct, 2, true)}</div></div>
              <div><div style={{ fontSize: 12, color: 'var(--text-4)' }}>MDD</div><div style={{ marginTop: 6, fontWeight: 700 }}>{formatPercent(summaryMetrics.max_drawdown_pct, 2, true)}</div></div>
              <div><div style={{ fontSize: 12, color: 'var(--text-4)' }}>승률</div><div style={{ marginTop: 6, fontWeight: 700 }}>{formatPercent(summaryMetrics.win_rate_pct, 2, true)}</div></div>
              <div><div style={{ fontSize: 12, color: 'var(--text-4)' }}>Profit Factor</div><div style={{ marginTop: 6, fontWeight: 700 }}>{formatNumber(summaryMetrics.profit_factor, 2)}</div></div>
              <div><div style={{ fontSize: 12, color: 'var(--text-4)' }}>거래 수</div><div style={{ marginTop: 6, fontWeight: 700 }}>{formatCount(summaryMetrics.trade_count, '건')}</div></div>
              <div><div style={{ fontSize: 12, color: 'var(--text-4)' }}>총 수익</div><div style={{ marginTop: 6, fontWeight: 700 }}>{formatPercent(displayedResult.metrics?.total_return_pct, 2, true)}</div></div>
            </div>
            {status === 'ok' && !displayedResult.error && (
              <div style={{ borderTop: '1px solid var(--border)', paddingTop: 12, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <div style={{ fontSize: 12, color: 'var(--text-4)', flex: 1, minWidth: 180 }}>
                  백테스트 완료 · 이 파라미터를 전략 레지스트리에 저장하면 전략 관리에서 활성화할 수 있습니다.
                </div>
                <button
                  className="ghost-button"
                  onClick={() => { void handleSaveAsPreset(); }}
                  disabled={presetSaving}
                >
                  {presetSaving ? '저장 중...' : '이 결과로 프리셋 저장'}
                </button>
                <button
                  className="ghost-button"
                  onClick={() => { window.location.href = '/lab/strategies'; }}
                >
                  전략 프리셋으로 이동
                </button>
              </div>
            )}
          </section>

          <section className="page-section console-card-section" style={{ display: 'grid', gap: 12 }}>
            <div style={{ fontSize: 14, fontWeight: 700 }}>Walk-forward 검증 결과</div>
            {wfStatus === 'error' && (
              <div style={{ fontSize: 12, color: 'var(--tone-bad)' }}>{wfLastError}</div>
            )}
            {wfStatus === 'idle' && (
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>Walk-forward 검증 버튼을 눌러 결과를 확인하세요. 학습·검증 구간을 슬라이딩하며 OOS 신뢰도를 측정합니다.</div>
            )}
            {(wfStatus === 'ok' || wfStatus === 'loading') && (
              <>
                <div className="console-metric-grid">
                  <div><div style={{ fontSize: 12, color: 'var(--text-4)' }}>윈도우 수</div><div style={{ marginTop: 6, fontWeight: 700 }}>{formatCount(wfData.summary?.windows, '개')}</div></div>
                  <div><div style={{ fontSize: 12, color: 'var(--text-4)' }}>양호 비율</div><div style={{ marginTop: 6, fontWeight: 700 }}>{formatPercent(wfData.summary?.positive_window_ratio, 1, true)}</div></div>
                  <div><div style={{ fontSize: 12, color: 'var(--text-4)' }}>OOS 신뢰도</div><div style={{ marginTop: 6, fontWeight: 700 }}>{wfData.summary?.oos_reliability || '-'}</div></div>
                  <div><div style={{ fontSize: 12, color: 'var(--text-4)' }}>Composite Score</div><div style={{ marginTop: 6, fontWeight: 700 }}>{formatNumber(wfData.summary?.composite_score, 2)}</div></div>
                </div>
                {wfData.segments && (
                  <div style={{ display: 'grid', gap: 8 }}>
                    <div style={{ fontSize: 13, fontWeight: 700 }}>구간별 지표</div>
                    <div className="console-metric-grid">
                      {(['train', 'validation', 'oos'] as const).map((seg) => {
                        const s = wfData.segments?.[seg];
                        if (!s) return null;
                        const scorecard = s.strategy_scorecard;
                        const score = scorecard?.composite_score;
                        const components = scorecard?.components || {};
                        return (
                          <div key={seg} style={{ display: 'grid', gap: 4, padding: 10, background: 'var(--bg-soft)', borderRadius: 6 }}>
                            <div style={{ fontSize: 11, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{seg}</div>
                            {scorecard ? (
                              <>
                                <div style={{ fontSize: 12 }}>Score {formatNumber(score, 2)}</div>
                                {Object.entries(components).slice(0, 3).map(([k, v]) => (
                                  <div key={k} style={{ fontSize: 11, color: 'var(--text-3)' }}>{k}: {formatNumber(v, 2)}</div>
                                ))}
                              </>
                            ) : (
                              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>데이터 없음</div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </>
            )}
          </section>

          <section className="page-section console-data-section" style={{ padding: 0 }}>
            <div style={{ padding: 16, fontSize: 14, fontWeight: 700 }}>Input Parameter Band</div>
            <div style={{ padding: '0 16px 16px', display: 'grid', gap: 8 }}>
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>{displayedResult.parameter_band?.summary || '현재 입력 파라미터가 전략 허용 범위 안에서 어디에 있는지 보여줍니다.'}</div>
              {Object.entries(displayedResult.parameter_band?.parameter_bands || {}).length > 0 ? (
                <div className="responsive-table-desktop" style={{ overflow: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ background: 'var(--bg-soft)', textAlign: 'left' }}>
                        <th style={{ padding: 12, fontSize: 12 }}>파라미터</th>
                        <th style={{ padding: 12, fontSize: 12 }}>선택값</th>
                        <th style={{ padding: 12, fontSize: 12 }}>허용 밴드</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(displayedResult.parameter_band?.parameter_bands || {}).map(([key, band]) => (
                        <tr key={key} style={{ borderTop: '1px solid var(--border)' }}>
                          <td style={{ padding: 12, fontSize: 12 }}>{band.label || key}</td>
                          <td style={{ padding: 12, fontSize: 12 }}>{String(band.selected ?? '-')}</td>
                          <td style={{ padding: 12, fontSize: 12 }}>{`${String(band.min ?? '-')} ~ ${String(band.max ?? '-')}`}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <div style={{ padding: 12, fontSize: 12, color: 'var(--text-4)' }}>표시할 밴드가 없습니다.</div>}
            </div>
          </section>

          <section className="page-section console-data-section" style={{ padding: 0 }}>
            <div style={{ padding: 16, fontSize: 14, fontWeight: 700 }}>Regime Breakdown</div>
            <div className="responsive-table-desktop" style={{ overflow: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: 'var(--bg-soft)', textAlign: 'left' }}>
                    <th style={{ padding: 12, fontSize: 12 }}>Regime</th>
                    <th style={{ padding: 12, fontSize: 12 }}>거래 수</th>
                    <th style={{ padding: 12, fontSize: 12 }}>승률</th>
                    <th style={{ padding: 12, fontSize: 12 }}>평균 수익</th>
                    <th style={{ padding: 12, fontSize: 12 }}>Profit Factor</th>
                    <th style={{ padding: 12, fontSize: 12 }}>전략</th>
                  </tr>
                </thead>
                <tbody>
                  {(displayedResult.regime_breakdown || []).map((row) => (
                    <tr key={row.regime} style={{ borderTop: '1px solid var(--border)' }}>
                      <td style={{ padding: 12, fontSize: 12 }}>{row.regime || '-'}</td>
                      <td style={{ padding: 12, fontSize: 12 }}>{formatCount(row.trade_count, '건')}</td>
                      <td style={{ padding: 12, fontSize: 12 }}>{formatPercent(row.win_rate_pct, 2, true)}</td>
                      <td style={{ padding: 12, fontSize: 12 }}>{formatPercent(row.avg_return_pct, 2, true)}</td>
                      <td style={{ padding: 12, fontSize: 12 }}>{formatNumber(row.profit_factor, 2)}</td>
                      <td style={{ padding: 12, fontSize: 12 }}>{(row.strategy_kinds || []).join(', ') || '-'}</td>
                    </tr>
                  ))}
                  {(!displayedResult.regime_breakdown || displayedResult.regime_breakdown.length === 0) && (
                    <tr><td colSpan={6} style={{ padding: 14, fontSize: 12, color: 'var(--text-4)' }}>아직 regime별 결과가 없습니다.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section className="page-section console-card-section" style={{ display: 'grid', gap: 12 }}>
            <div style={{ fontSize: 14, fontWeight: 700 }}>취약 구간 / 실패 원인</div>
            {(displayedResult.failure_modes || []).length > 0 ? (
              <div className="console-metric-grid">
                {(displayedResult.failure_modes || []).map((row) => (
                  <div key={`${row.reason}-${row.count}`}>
                    <div style={{ fontSize: 12, color: 'var(--text-4)' }}>{row.reason || '기타'}</div>
                    <div style={{ marginTop: 6, fontWeight: 700 }}>{formatCount(row.count, '건')} · 평균 {formatPercent(row.avg_pnl_pct, 2, true)}</div>
                  </div>
                ))}
              </div>
            ) : <div style={{ fontSize: 12, color: 'var(--text-4)' }}>아직 표시할 실패 원인이 없습니다.</div>}
          </section>

          <section className="page-section console-card-section" style={{ display: 'grid', gap: 12 }}>
            <div style={{ fontSize: 14, fontWeight: 700 }}>Monte Carlo 강건성 검증</div>
            <div style={{ fontSize: 12, color: 'var(--text-4)' }}>
              {optimizationMessage || '전략별 param grid를 분리해서 robust zone 중심으로 결과를 확인합니다.'}
            </div>
            <div className="console-metric-grid">
              <div><div style={{ fontSize: 12, color: 'var(--text-4)' }}>전략</div><div style={{ marginTop: 6, fontWeight: 700 }}>{strategyLabel(String(searchContext?.strategy_kind || validationStore.draftQuery.strategy_kind))}</div></div>
              <div><div style={{ fontSize: 12, color: 'var(--text-4)' }}>상태</div><div style={{ marginTop: 6, fontWeight: 700 }}>{optimizationRunning ? '실행 중' : optimizationPayload?.status === 'ok' ? '결과 있음' : '대기'}</div></div>
              <div><div style={{ fontSize: 12, color: 'var(--text-4)' }}>Optimized Symbols</div><div style={{ marginTop: 6, fontWeight: 700 }}>{formatCount(Number((optimizationPayload?.meta as Record<string, unknown> | undefined)?.n_symbols_optimized || 0), '개')}</div></div>
              <div><div style={{ fontSize: 12, color: 'var(--text-4)' }}>Reliable</div><div style={{ marginTop: 6, fontWeight: 700 }}>{formatCount(Number((optimizationPayload?.meta as Record<string, unknown> | undefined)?.n_reliable || 0), '개')}</div></div>
            </div>
            <div style={{ display: 'grid', gap: 8 }}>
              <div style={{ fontSize: 13, fontWeight: 700 }}>Aggregate Robust Zone</div>
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>
                {optimizerAggregateRobustZone?.summary || 'optimizer 결과가 있으면 종목별 robust zone의 공통 안정 구간을 보여줍니다.'}
              </div>
              {Object.entries(optimizerAggregateRobustZone?.parameter_bands || {}).length > 0 ? (
                <div className="responsive-table-desktop" style={{ overflow: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ background: 'var(--bg-soft)', textAlign: 'left' }}>
                        <th style={{ padding: 12, fontSize: 12 }}>파라미터</th>
                        <th style={{ padding: 12, fontSize: 12 }}>대표값</th>
                        <th style={{ padding: 12, fontSize: 12 }}>안정 구간</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(optimizerAggregateRobustZone?.parameter_bands || {}).map(([key, band]) => (
                        <tr key={key} style={{ borderTop: '1px solid var(--border)' }}>
                          <td style={{ padding: 12, fontSize: 12 }}>{band.label || key}</td>
                          <td style={{ padding: 12, fontSize: 12 }}>{String(band.selected ?? '-')}</td>
                          <td style={{ padding: 12, fontSize: 12 }}>{`${String(band.min ?? '-')} ~ ${String(band.max ?? '-')}`}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <div style={{ fontSize: 12, color: 'var(--text-4)' }}>표시할 robust zone이 없습니다.</div>}
            </div>
            <div style={{ display: 'grid', gap: 8 }}>
              <div style={{ fontSize: 13, fontWeight: 700 }}>Global Parameter Patch</div>
              <div style={{ display: 'grid', gap: 6 }}>
                {Object.entries((optimizationPayload?.global_params || {}) as Record<string, unknown>).slice(0, 8).map(([key, value]) => (
                  <div key={key} style={{ fontSize: 12 }}>{key}: {String(value)}</div>
                ))}
                {Object.keys((optimizationPayload?.global_params || {}) as Record<string, unknown>).length === 0 && (
                  <div style={{ fontSize: 12, color: 'var(--text-4)' }}>아직 optimizer global params가 없습니다.</div>
                )}
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
