import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ChangeEvent } from 'react';
import { getJSON, postJSON } from '../api/client';
import {
  applyQuantOpsRuntime,
  fetchQuantOpsWorkflow,
  fetchStrategyMetadata,
  fetchValidationBacktest,
  fetchValidationWalkForward,
  revalidateQuantOpsCandidate,
  saveQuantOpsCandidate,
  saveStrategyPreset,
} from '../api/domain';
import { ConsoleActionBar } from '../components/ConsoleActionBar';
import { NumericInput } from '../components/NumericInput';
import { FreshnessBadge, GradeBadge } from '../components/QualityBadge';
import { reasonCodeToKorean, providerSourceToKorean } from '../constants/uiText';
import { defaultBacktestQuery } from '../hooks/useBacktest';
import { useConsoleLogs } from '../hooks/useConsoleLogs';
import {
  formatValidationSettingsLabel,
  useValidationSettingsStore,
} from '../hooks/useValidationSettingsStore';
import { VALIDATION_TRANSFER_STORAGE_KEY } from '../lib/validationConfigStorage';
import type { BacktestData, BacktestQuery, StrategyKind } from '../types';
import type {
  QuantOpsCandidatePayload,
  QuantOpsCandidateStatePayload,
  QuantOpsRuntimeApplyPayload,
  QuantOpsWorkflowResponse,
  StrategyRegistryItem,
  ValidationResponse,
} from '../types/domain';
import type { ActionBarAction, ConsoleSnapshot } from '../types/consoleView';
import type { StrategiesMetadataResponse } from '../types/domain';
import { strategyTypeToKorean, riskProfileToKorean, reliabilityToKorean } from '../constants/uiText';
import { formatCount, formatDateTime, formatNumber, formatPercent } from '../utils/format';

interface BacktestValidationPageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
}

function strategyLabel(strategyKind: string | undefined) {
  return strategyTypeToKorean(String(strategyKind || 'trend_following'));
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

function quantOpsStateLabel(state?: QuantOpsCandidateStatePayload | null) {
  if (!state) return '없음';
  if (state.status === 'active') return '활성';
  if (state.status === 'stale') return '지연';
  if (state.status === 'missing') return '없음';
  return state.status || '알 수 없음';
}

function quantOpsCandidateSummary(candidate?: QuantOpsCandidatePayload | null) {
  if (!candidate) return '후보 없음';
  const decision = candidate.decision?.label || candidate.decision?.status || '-';
  const reliability = reliabilityToKorean(String(candidate.metrics?.reliability || '-'));
  const trades = formatCount(candidate.metrics?.trade_count, '건');
  return `${decision} · 신뢰도 ${reliability} · 거래 ${trades}`;
}

function quantOpsRuntimeSummary(runtimeApply?: QuantOpsRuntimeApplyPayload | null) {
  if (!runtimeApply?.available) return '미반영';
  const sourceMode = runtimeApply.runtime_candidate_source_mode === 'runtime_candidates' ? '런타임 후보' : String(runtimeApply.runtime_candidate_source_mode || '-');
  const applyStatus = String(runtimeApply.status || '').toLowerCase() === 'applied' ? '반영됨' : (runtimeApply.status || '반영됨');
  const engineState = String(runtimeApply.engine_state || '').toLowerCase() === 'stopped' ? '중지' : (runtimeApply.engine_state || '-');
  return `${applyStatus} · ${sourceMode} · 엔진 ${engineState}`;
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
  const [quantOpsWorkflow, setQuantOpsWorkflow] = useState<QuantOpsWorkflowResponse | null>(null);
  const [quantOpsLoading, setQuantOpsLoading] = useState(false);
  const [quantOpsBusyAction, setQuantOpsBusyAction] = useState<'revalidate' | 'save' | 'apply' | null>(null);

  // Bug 1 fix: read transfer payload immediately on mount before any effects run,
  // then apply once metadata is available to avoid the race condition where
  // the effect ran with null metadata and cleared the localStorage key.
  const transferRef = useRef<StrategyRegistryItem | null>(null);
  const transferApplied = useRef(false);
  const settingsLoadStarted = useRef(false);
  if (transferRef.current === null && !transferApplied.current) {
    const raw = localStorage.getItem(VALIDATION_TRANSFER_STORAGE_KEY);
    if (raw) {
      localStorage.removeItem(VALIDATION_TRANSFER_STORAGE_KEY);
      try { transferRef.current = JSON.parse(raw) as StrategyRegistryItem; } catch { /* ignore */ }
    }
  }

  useEffect(() => {
    let cancelled = false;
    async function loadMetadata() {
      setMetadataLoading(true);
      try {
        const payload = await fetchStrategyMetadata();
        if (!cancelled) {
          setMetadata(payload.ok === false ? null : payload);
        }
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
    if (validationStore.serverLoaded || settingsLoadStarted.current) return;
    settingsLoadStarted.current = true;
    validationStore.loadSavedFromServer().catch(() => {
      settingsLoadStarted.current = false;
      return undefined;
    });
  }, [validationStore.serverLoaded, validationStore]);

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

  const loadQuantOpsWorkflow = useCallback(async () => {
    setQuantOpsLoading(true);
    try {
      const payload = await fetchQuantOpsWorkflow();
      if (payload.ok === false) {
        throw new Error(payload.error || '운영 워크플로우를 불러오지 못했습니다.');
      }
      setQuantOpsWorkflow(payload);
    } catch {
      setQuantOpsWorkflow(null);
    } finally {
      setQuantOpsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOptimizationArtifacts().catch(() => undefined);
  }, [fetchOptimizationArtifacts]);

  useEffect(() => {
    loadQuantOpsWorkflow().catch(() => undefined);
  }, [loadQuantOpsWorkflow]);

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
    { label: '장세', value: validationStore.draftQuery.regime_mode === 'auto' ? '자동' : '수동', tone: 'neutral' as const },
    { label: '리스크', value: riskProfileToKorean(validationStore.draftQuery.risk_profile), tone: 'neutral' as const },
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

  const handleReset = useCallback(async () => {
    try {
      await validationStore.resetSavedToServer();
      push('warning', '검증 설정을 기본값으로 초기화했습니다.', undefined, 'settings');
    } catch {
      push('error', '설정 초기화에 실패했습니다.', undefined, 'settings');
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
        const msg = '워크포워드 검증에 실패했습니다.';
        setWfLastError(msg);
        push('error', msg, undefined, 'walkforward');
      } else {
        setWfStatus('ok');
        push(
          'success',
          '워크포워드 검증을 완료했습니다.',
          `윈도우 ${result.summary?.windows ?? 0}개 · 양호 비율 ${formatPercent(result.summary?.positive_window_ratio, 1, true)}`,
          'walkforward',
        );
      }
    } catch {
      setWfStatus('error');
      const msg = '워크포워드 응답을 불러오지 못했습니다.';
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

  const handleQuantOpsRevalidate = useCallback(async () => {
    setQuantOpsBusyAction('revalidate');
    try {
      const response = await revalidateQuantOpsCandidate(validationStore.draftQuery, validationStore.draftSettings);
      const payload = response.data;
      if (!response.ok || payload.ok === false) {
        push('error', '운영 후보 재검증에 실패했습니다.', payload.error || response.error?.message, 'quant-ops');
      } else {
        setQuantOpsWorkflow(payload.workflow || null);
        push('success', '운영 후보를 재검증했습니다.', quantOpsCandidateSummary(payload.candidate), 'quant-ops');
      }
    } catch {
      push('error', '운영 후보 재검증 요청에 실패했습니다.', undefined, 'quant-ops');
    } finally {
      setQuantOpsBusyAction(null);
      loadQuantOpsWorkflow().catch(() => undefined);
    }
  }, [loadQuantOpsWorkflow, push, validationStore.draftQuery, validationStore.draftSettings]);

  const handleQuantOpsSave = useCallback(async () => {
    const candidateId = quantOpsWorkflow?.latest_candidate?.id;
    if (!candidateId) {
      push('warning', '저장할 최신 운영 후보가 없습니다.', undefined, 'quant-ops');
      return;
    }
    setQuantOpsBusyAction('save');
    try {
      const response = await saveQuantOpsCandidate(candidateId);
      const payload = response.data;
      if (!response.ok || payload.ok === false) {
        push('error', '운영 후보 저장에 실패했습니다.', payload.error || response.error?.message, 'quant-ops');
      } else {
        setQuantOpsWorkflow(payload.workflow || null);
        push('success', '운영 후보를 저장했습니다.', quantOpsCandidateSummary(payload.candidate), 'quant-ops');
      }
    } catch {
      push('error', '운영 후보 저장 요청에 실패했습니다.', undefined, 'quant-ops');
    } finally {
      setQuantOpsBusyAction(null);
      loadQuantOpsWorkflow().catch(() => undefined);
    }
  }, [loadQuantOpsWorkflow, push, quantOpsWorkflow?.latest_candidate?.id]);

  const handleQuantOpsApply = useCallback(async () => {
    const candidateId = quantOpsWorkflow?.saved_candidate?.id;
    if (!candidateId) {
      push('warning', '런타임에 반영할 저장 후보가 없습니다.', undefined, 'quant-ops');
      return;
    }
    setQuantOpsBusyAction('apply');
    try {
      const response = await applyQuantOpsRuntime(candidateId);
      const payload = response.data;
      if (!response.ok || payload.ok === false) {
        push('error', '런타임 반영에 실패했습니다.', payload.error || response.error?.message, 'quant-ops');
      } else {
        setQuantOpsWorkflow(payload.workflow || null);
        push('success', '저장 후보를 런타임에 반영했습니다.', quantOpsRuntimeSummary(payload.runtime_apply), 'quant-ops');
      }
    } catch {
      push('error', '런타임 반영 요청에 실패했습니다.', undefined, 'quant-ops');
    } finally {
      setQuantOpsBusyAction(null);
      loadQuantOpsWorkflow().catch(() => undefined);
    }
  }, [loadQuantOpsWorkflow, push, quantOpsWorkflow?.saved_candidate?.id]);

  const [presetSaving, setPresetSaving] = useState(false);
  const handleSaveAsPreset = useCallback(async () => {
    const q = validationStore.draftQuery;
    const defaultName = `${strategyLabel(q.strategy_kind)} · ${q.market_scope.toUpperCase()} · ${riskProfileToKorean(q.risk_profile)}`;
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
      scan_cycle: '5m',
      params: { ...q.strategy_params, risk_profile: q.risk_profile },
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
      label: '워크포워드 검증',
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
    {
      label: '운영후보 재검증',
      tone: 'default',
      onClick: handleQuantOpsRevalidate,
      disabled: quantOpsBusyAction !== null,
      busy: quantOpsBusyAction === 'revalidate',
      busyLabel: '재검증 중...',
    },
    {
      label: '설정 초기화',
      tone: 'danger' as const,
      onClick: handleReset,
      busy: validationStore.syncStatus === 'resetting',
      busyLabel: '초기화 중...',
      confirmTitle: '검증 설정을 초기화하시겠습니까?',
      confirmMessage: '저장된 설정과 현재 초안이 모두 기본값으로 돌아갑니다.',
    },
  ]), [handleQuantOpsRevalidate, handleReset, handleRunBacktest, handleRunOptimization, handleRunWalkForward, handleSave, optimizationRunning, quantOpsBusyAction, status, validationStore.syncStatus, wfStatus]);

  const summaryMetrics = displayedResult.performance_summary || {};
  const executionSummary = displayedResult.execution_summary || {};
  const positionSizingMeta = executionSummary.position_sizing_meta || displayedResult.position_sizing_meta || displayedResult.config?.position_sizing_meta;
  const positionSizingMode = String(positionSizingMeta?.label || positionSizingMeta?.mode || executionSummary.position_sizing || displayedResult.position_sizing || displayedResult.config?.position_sizing || '-');
  const positionSizingRisk = positionSizingMeta?.risk_per_trade_pct ?? executionSummary.risk_per_trade_pct ?? displayedResult.risk_per_trade_pct ?? displayedResult.config?.risk_per_trade_pct;
  const positionSizingNote = positionSizingMeta?.comparison_note || '';
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
  const latestCandidate = quantOpsWorkflow?.latest_candidate;
  const latestCandidateState = quantOpsWorkflow?.latest_candidate_state;
  const savedCandidate = quantOpsWorkflow?.saved_candidate;
  const savedCandidateState = quantOpsWorkflow?.saved_candidate_state;
  const runtimeApply = quantOpsWorkflow?.runtime_apply;

  return (
    <div className="app-shell">
      <div className="page-frame">
        <div className="content-shell console-page-shell" style={{ display: 'grid', gap: 16 }}>
          <ConsoleActionBar
            title="전략 검증"
            subtitle="전략 종류를 먼저 선택하고, 장세 모드/리스크/포트폴리오 제약을 정한 뒤 전략별 파라미터를 조정합니다. 몬테카를로는 최적값 발굴기가 아니라 전략별 강건성 검증기로 취급합니다."
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
            <div style={{ fontSize: 17, fontWeight: 700 }}>설정</div>
            <div className="backtest-grid">
              <label style={{ display: 'grid', gap: 6 }}>
                <span>전략</span>
                <select className="backtest-input-wrap" value={validationStore.draftQuery.strategy_kind} onChange={handleStrategyChange}>
                  <option value="trend_following">추세 추종</option>
                  <option value="mean_reversion">평균 회귀</option>
                  <option value="defensive">방어형</option>
                </select>
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span>장세 모드</span>
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
                  <option value="conservative">보수형</option>
                  <option value="balanced">균형형</option>
                  <option value="aggressive">공격형</option>
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
              <div style={{ fontSize: 16, fontWeight: 700 }}>전략별 파라미터</div>
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
              <div style={{ fontSize: 16, fontWeight: 700 }}>검증 설정</div>
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
                  <span>워크포워드</span>
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
                  <span>목표</span>
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
              </div>
            </div>
          </section>

          <section className="page-section console-card-section" style={{ display: 'grid', gap: 12 }}>
            <div style={{ fontSize: 17, fontWeight: 700 }}>실행 요약</div>
            <div className="console-metric-grid">
              <div><div style={{ fontSize: 15, color: 'var(--text-4)' }}>선택 전략</div><div style={{ marginTop: 6, fontWeight: 700 }}>{strategyLabel(displayedResult.strategy_kind || validationStore.draftQuery.strategy_kind)}</div></div>
              <div><div style={{ fontSize: 15, color: 'var(--text-4)' }}>확정 전략</div><div style={{ marginTop: 6, fontWeight: 700 }}>{strategyLabel(String(executionSummary.resolved_strategy_kind || displayedResult.resolved_strategy_kind || validationStore.draftQuery.strategy_kind))}</div></div>
              <div><div style={{ fontSize: 15, color: 'var(--text-4)' }}>확정 장세</div><div style={{ marginTop: 6, fontWeight: 700 }}>{String(executionSummary.resolved_regime || displayedResult.resolved_regime || validationStore.draftQuery.regime_mode)}</div></div>
              <div><div style={{ fontSize: 15, color: 'var(--text-4)' }}>리스크 프로필</div><div style={{ marginTop: 6, fontWeight: 700 }}>{riskProfileToKorean(displayedResult.risk_profile || validationStore.draftQuery.risk_profile)}</div></div>
              <div><div style={{ fontSize: 15, color: 'var(--text-4)' }}>포지션 사이징</div><div style={{ marginTop: 6, fontWeight: 700 }}>{positionSizingMode}</div></div>
              <div><div style={{ fontSize: 15, color: 'var(--text-4)' }}>거래당 위험예산</div><div style={{ marginTop: 6, fontWeight: 700 }}>{formatPercent(positionSizingRisk, 2)}</div></div>
              <div><div style={{ fontSize: 15, color: 'var(--text-4)' }}>시장</div><div style={{ marginTop: 6, fontWeight: 700 }}>{marketLabel(validationStore.draftQuery.market_scope)}</div></div>
              <div><div style={{ fontSize: 15, color: 'var(--text-4)' }}>최근 실행</div><div style={{ marginTop: 6, fontWeight: 700 }}>{formatDateTime(displayedResult.generated_at || '') || '-'}</div></div>
            </div>
            {positionSizingNote && (
              <div style={{ fontSize: 14, color: 'var(--text-4)', borderTop: '1px solid var(--border)', paddingTop: 10 }}>
                {positionSizingNote}
              </div>
            )}
          </section>

          <section className="page-section console-card-section" style={{ display: 'grid', gap: 12 }}>
            <div style={{ fontSize: 17, fontWeight: 700 }}>성능 요약</div>
            <div className="console-metric-grid">
              <div><div style={{ fontSize: 15, color: 'var(--text-4)' }}>연환산 수익률</div><div style={{ marginTop: 6, fontWeight: 700 }}>{formatPercent(summaryMetrics.cagr_pct, 2)}</div></div>
              <div><div style={{ fontSize: 15, color: 'var(--text-4)' }}>MDD</div><div style={{ marginTop: 6, fontWeight: 700 }}>{formatPercent(summaryMetrics.max_drawdown_pct, 2)}</div></div>
              <div><div style={{ fontSize: 15, color: 'var(--text-4)' }}>승률</div><div style={{ marginTop: 6, fontWeight: 700 }}>{formatPercent(summaryMetrics.win_rate_pct, 2)}</div></div>
              <div><div style={{ fontSize: 15, color: 'var(--text-4)' }}>손익비</div><div style={{ marginTop: 6, fontWeight: 700 }}>{formatNumber(summaryMetrics.profit_factor, 2)}</div></div>
              <div><div style={{ fontSize: 15, color: 'var(--text-4)' }}>거래 수</div><div style={{ marginTop: 6, fontWeight: 700 }}>{formatCount(summaryMetrics.trade_count, '건')}</div></div>
              <div><div style={{ fontSize: 15, color: 'var(--text-4)' }}>총 수익</div><div style={{ marginTop: 6, fontWeight: 700 }}>{formatPercent(displayedResult.metrics?.total_return_pct, 2)}</div></div>
            </div>
            {status === 'ok' && !displayedResult.error && (
              <div style={{ borderTop: '1px solid var(--border)', paddingTop: 12, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <div style={{ fontSize: 15, color: 'var(--text-4)', flex: 1, minWidth: 180 }}>
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
            <div style={{ fontSize: 17, fontWeight: 700 }}>워크포워드 검증 결과</div>
            {wfStatus === 'error' && (
              <div style={{ fontSize: 15, color: 'var(--tone-bad)' }}>{wfLastError}</div>
            )}
            {wfStatus === 'idle' && (
              <div style={{ fontSize: 15, color: 'var(--text-4)' }}>워크포워드 검증 버튼을 눌러 결과를 확인하세요. 학습·검증 구간을 슬라이딩하며 OOS 신뢰도를 측정합니다.</div>
            )}
            {(wfStatus === 'ok' || wfStatus === 'loading') && (
              <>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <FreshnessBadge value={String(wfData.freshness || 'missing')} />
                  <GradeBadge value={String(wfData.validation?.grade || '-')} />
                  {wfData.validation?.reason ? <span className="inline-badge">{reasonCodeToKorean(String(wfData.validation.reason))}</span> : null}
                  {wfData.source ? <span className="inline-badge">출처 {providerSourceToKorean(String(wfData.source))}</span> : null}
                </div>
                {wfData.validation?.exclusion_reason ? (
                  <div style={{ fontSize: 15, color: 'var(--tone-bad)' }}>검증 숫자는 신뢰도 부족 상태야: {String(wfData.validation.exclusion_reason)}</div>
                ) : null}
                <div className="console-metric-grid">
                  <div><div style={{ fontSize: 15, color: 'var(--text-4)' }}>윈도우 수</div><div style={{ marginTop: 6, fontWeight: 700 }}>{formatCount(wfData.summary?.windows, '개')}</div></div>
                  <div><div style={{ fontSize: 15, color: 'var(--text-4)' }}>양호 비율</div><div style={{ marginTop: 6, fontWeight: 700 }}>{formatPercent(wfData.summary?.positive_window_ratio, 1, true)}</div></div>
                  <div><div style={{ fontSize: 15, color: 'var(--text-4)' }}>OOS 신뢰도</div><div style={{ marginTop: 6, fontWeight: 700 }}>{wfData.summary?.oos_reliability || '-'}</div></div>
                  <div><div style={{ fontSize: 15, color: 'var(--text-4)' }}>Composite Score</div><div style={{ marginTop: 6, fontWeight: 700 }}>{formatNumber(wfData.summary?.composite_score, 2)}</div></div>
                </div>
                {wfData.segments && (
                  <div style={{ display: 'grid', gap: 8 }}>
                    <div style={{ fontSize: 16, fontWeight: 700 }}>구간별 지표</div>
                    <div className="console-metric-grid">
                      {(['train', 'validation', 'oos'] as const).map((seg) => {
                        const s = wfData.segments?.[seg];
                        if (!s) return null;
                        const scorecard = s.strategy_scorecard;
                        const score = scorecard?.composite_score;
                        const components = scorecard?.components || {};
                        return (
                          <div key={seg} style={{ display: 'grid', gap: 4, padding: 10, background: 'var(--bg-soft)', borderRadius: 6 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                              <div style={{ fontSize: 14, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{seg}</div>
                              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                                <FreshnessBadge value={String(s.freshness || 'missing')} />
                                <GradeBadge value={String(s.validation?.grade || '-')} />
                              </div>
                            </div>
                            {s.validation?.reason ? <div style={{ fontSize: 14, color: 'var(--text-3)' }}>{reasonCodeToKorean(String(s.validation.reason))}</div> : null}
                            {scorecard ? (
                              <>
                                <div style={{ fontSize: 15 }}>Score {formatNumber(score, 2)}</div>
                                {Object.entries(components).slice(0, 3).map(([k, v]) => (
                                  <div key={k} style={{ fontSize: 14, color: 'var(--text-3)' }}>{k}: {formatNumber(v, 2)}</div>
                                ))}
                              </>
                            ) : (
                              <div style={{ fontSize: 15, color: 'var(--text-4)' }}>데이터 없음</div>
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
            <div style={{ padding: 16, fontSize: 17, fontWeight: 700 }}>입력 파라미터 구간</div>
            <div style={{ padding: '0 16px 16px', display: 'grid', gap: 8 }}>
              <div style={{ fontSize: 15, color: 'var(--text-4)' }}>{displayedResult.parameter_band?.summary || '현재 입력 파라미터가 전략 허용 범위 안에서 어디에 있는지 보여줍니다.'}</div>
              {Object.entries(displayedResult.parameter_band?.parameter_bands || {}).length > 0 ? (
                <div className="responsive-table-desktop" style={{ overflow: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ background: 'var(--bg-soft)', textAlign: 'left' }}>
                        <th style={{ padding: 12, fontSize: 15 }}>파라미터</th>
                        <th style={{ padding: 12, fontSize: 15 }}>선택값</th>
                        <th style={{ padding: 12, fontSize: 15 }}>허용 밴드</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(displayedResult.parameter_band?.parameter_bands || {}).map(([key, band]) => (
                        <tr key={key} style={{ borderTop: '1px solid var(--border)' }}>
                          <td style={{ padding: 12, fontSize: 15 }}>{band.label || key}</td>
                          <td style={{ padding: 12, fontSize: 15 }}>{String(band.selected ?? '-')}</td>
                          <td style={{ padding: 12, fontSize: 15 }}>{`${String(band.min ?? '-')} ~ ${String(band.max ?? '-')}`}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <div style={{ padding: 12, fontSize: 15, color: 'var(--text-4)' }}>표시할 밴드가 없습니다.</div>}
            </div>
          </section>

          <section className="page-section console-data-section" style={{ padding: 0 }}>
            <div style={{ padding: 16, fontSize: 17, fontWeight: 700 }}>장세별 분해</div>
            <div className="responsive-table-desktop" style={{ overflow: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: 'var(--bg-soft)', textAlign: 'left' }}>
                    <th style={{ padding: 12, fontSize: 15 }}>장세</th>
                    <th style={{ padding: 12, fontSize: 15 }}>거래 수</th>
                    <th style={{ padding: 12, fontSize: 15 }}>승률</th>
                    <th style={{ padding: 12, fontSize: 15 }}>평균 수익</th>
                    <th style={{ padding: 12, fontSize: 15 }}>손익비</th>
                    <th style={{ padding: 12, fontSize: 15 }}>전략</th>
                  </tr>
                </thead>
                <tbody>
                  {(displayedResult.regime_breakdown || []).map((row) => (
                    <tr key={row.regime} style={{ borderTop: '1px solid var(--border)' }}>
                      <td style={{ padding: 12, fontSize: 15 }}>{row.regime || '-'}</td>
                      <td style={{ padding: 12, fontSize: 15 }}>{formatCount(row.trade_count, '건')}</td>
                      <td style={{ padding: 12, fontSize: 15 }}>{formatPercent(row.win_rate_pct, 2)}</td>
                      <td style={{ padding: 12, fontSize: 15 }}>{formatPercent(row.avg_return_pct, 2)}</td>
                      <td style={{ padding: 12, fontSize: 15 }}>{formatNumber(row.profit_factor, 2)}</td>
                      <td style={{ padding: 12, fontSize: 15 }}>{(row.strategy_kinds || []).join(', ') || '-'}</td>
                    </tr>
                  ))}
                  {(!displayedResult.regime_breakdown || displayedResult.regime_breakdown.length === 0) && (
                    <tr><td colSpan={6} style={{ padding: 14, fontSize: 15, color: 'var(--text-4)' }}>아직 장세별 결과가 없습니다.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section className="page-section console-card-section" style={{ display: 'grid', gap: 12 }}>
            <div style={{ fontSize: 17, fontWeight: 700 }}>취약 구간 / 실패 원인</div>
            {(displayedResult.failure_modes || []).length > 0 ? (
              <div className="console-metric-grid">
                {(displayedResult.failure_modes || []).map((row) => (
                  <div key={`${row.reason}-${row.count}`}>
                    <div style={{ fontSize: 15, color: 'var(--text-4)' }}>{row.reason || '기타'}</div>
                    <div style={{ marginTop: 6, fontWeight: 700 }}>{formatCount(row.count, '건')} · 평균 {formatPercent(row.avg_pnl_pct, 2)}</div>
                  </div>
                ))}
              </div>
            ) : <div style={{ fontSize: 15, color: 'var(--text-4)' }}>아직 표시할 실패 원인이 없습니다.</div>}
          </section>

          <section className="page-section console-card-section" style={{ display: 'grid', gap: 12 }}>
            <div style={{ fontSize: 17, fontWeight: 700 }}>몬테카를로 강건성 검증</div>
            <div style={{ fontSize: 15, color: 'var(--text-4)' }}>
              {optimizationMessage || '전략별 파라미터 격자를 분리해서 안정 구간 중심으로 결과를 확인합니다.'}
            </div>
            <div className="console-metric-grid">
              <div><div style={{ fontSize: 15, color: 'var(--text-4)' }}>전략</div><div style={{ marginTop: 6, fontWeight: 700 }}>{strategyLabel(String(searchContext?.strategy_kind || validationStore.draftQuery.strategy_kind))}</div></div>
              <div><div style={{ fontSize: 15, color: 'var(--text-4)' }}>상태</div><div style={{ marginTop: 6, fontWeight: 700 }}>{optimizationRunning ? '실행 중' : optimizationPayload?.status === 'ok' ? '결과 있음' : '대기'}</div></div>
              <div><div style={{ fontSize: 15, color: 'var(--text-4)' }}>최적화 종목 수</div><div style={{ marginTop: 6, fontWeight: 700 }}>{formatCount(Number((optimizationPayload?.meta as Record<string, unknown> | undefined)?.n_symbols_optimized || 0), '개')}</div></div>
              <div><div style={{ fontSize: 15, color: 'var(--text-4)' }}>신뢰 통과</div><div style={{ marginTop: 6, fontWeight: 700 }}>{formatCount(Number((optimizationPayload?.meta as Record<string, unknown> | undefined)?.n_reliable || 0), '개')}</div></div>
            </div>
            <div style={{ display: 'grid', gap: 8 }}>
              <div style={{ fontSize: 16, fontWeight: 700 }}>공통 안정 구간</div>
              <div style={{ fontSize: 15, color: 'var(--text-4)' }}>
                {optimizerAggregateRobustZone?.summary || '최적화 결과가 있으면 종목별 안정 구간의 공통 영역을 보여줍니다.'}
              </div>
              {Object.entries(optimizerAggregateRobustZone?.parameter_bands || {}).length > 0 ? (
                <div className="responsive-table-desktop" style={{ overflow: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ background: 'var(--bg-soft)', textAlign: 'left' }}>
                        <th style={{ padding: 12, fontSize: 15 }}>파라미터</th>
                        <th style={{ padding: 12, fontSize: 15 }}>대표값</th>
                        <th style={{ padding: 12, fontSize: 15 }}>안정 구간</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(optimizerAggregateRobustZone?.parameter_bands || {}).map(([key, band]) => (
                        <tr key={key} style={{ borderTop: '1px solid var(--border)' }}>
                          <td style={{ padding: 12, fontSize: 15 }}>{band.label || key}</td>
                          <td style={{ padding: 12, fontSize: 15 }}>{String(band.selected ?? '-')}</td>
                          <td style={{ padding: 12, fontSize: 15 }}>{`${String(band.min ?? '-')} ~ ${String(band.max ?? '-')}`}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <div style={{ fontSize: 15, color: 'var(--text-4)' }}>표시할 안정 구간이 없습니다.</div>}
            </div>
            <div style={{ display: 'grid', gap: 8 }}>
              <div style={{ fontSize: 16, fontWeight: 700 }}>전역 파라미터 패치</div>
              <div style={{ display: 'grid', gap: 6 }}>
                {Object.entries((optimizationPayload?.global_params || {}) as Record<string, unknown>).slice(0, 8).map(([key, value]) => (
                  <div key={key} style={{ fontSize: 15 }}>{key}: {String(value)}</div>
                ))}
                {Object.keys((optimizationPayload?.global_params || {}) as Record<string, unknown>).length === 0 && (
                  <div style={{ fontSize: 15, color: 'var(--text-4)' }}>아직 최적화 전역 파라미터가 없습니다.</div>
                )}
              </div>
            </div>
          </section>

          <section className="page-section console-card-section" style={{ display: 'grid', gap: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
              <div>
                <div style={{ fontSize: 17, fontWeight: 700 }}>운영 반영 워크플로우</div>
                <div style={{ marginTop: 4, fontSize: 15, color: 'var(--text-4)' }}>
                  검증 랩 결과를 최신 후보 → 저장 후보 → 런타임 반영 순서로 넘겨야 실제 엔진에 반영됩니다.
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button className="ghost-button" onClick={() => { void handleQuantOpsRevalidate(); }} disabled={quantOpsBusyAction !== null}>
                  {quantOpsBusyAction === 'revalidate' ? '재검증 중...' : '현재 설정으로 재검증'}
                </button>
                <button
                  className="ghost-button"
                  onClick={() => { void handleQuantOpsSave(); }}
                  disabled={quantOpsBusyAction !== null || !latestCandidate || latestCandidate?.guardrails?.can_save === false}
                  title={!latestCandidate ? '최신 후보가 없어서 저장할 수 없습니다.' : latestCandidate?.guardrails?.can_save === false ? (latestCandidate.guardrails?.reasons || []).join(', ') : ''}
                >
                  {quantOpsBusyAction === 'save' ? '저장 중...' : '최신 후보 저장'}
                </button>
                <button
                  className="ghost-button"
                  onClick={() => { void handleQuantOpsApply(); }}
                  disabled={quantOpsBusyAction !== null || !savedCandidate || savedCandidate?.guardrails?.can_apply === false}
                  title={!savedCandidate ? '저장 후보가 없어서 반영할 수 없습니다.' : savedCandidate?.guardrails?.can_apply === false ? (savedCandidate.guardrails?.reasons || []).join(', ') : ''}
                >
                  {quantOpsBusyAction === 'apply' ? '반영 중...' : '저장 후보 런타임 반영'}
                </button>
              </div>
            </div>

            <div className="console-metric-grid">
              <div>
                <div style={{ fontSize: 15, color: 'var(--text-4)' }}>탐색 결과</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{quantOpsWorkflow?.search_result?.available ? '있음' : '없음'}</div>
                <div style={{ marginTop: 4, fontSize: 15, color: 'var(--text-4)' }}>{quantOpsWorkflow?.search_result?.version || '-'}</div>
              </div>
              <div>
                <div style={{ fontSize: 15, color: 'var(--text-4)' }}>최신 후보</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{latestCandidate?.id || '-'}</div>
                <div style={{ marginTop: 4, fontSize: 15, color: 'var(--text-4)' }}>{quantOpsStateLabel(latestCandidateState)}</div>
              </div>
              <div>
                <div style={{ fontSize: 15, color: 'var(--text-4)' }}>저장 후보</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{savedCandidate?.id || '-'}</div>
                <div style={{ marginTop: 4, fontSize: 15, color: 'var(--text-4)' }}>{quantOpsStateLabel(savedCandidateState)}</div>
              </div>
              <div>
                <div style={{ fontSize: 15, color: 'var(--text-4)' }}>Runtime 반영</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{runtimeApply?.candidate_id || '-'}</div>
                <div style={{ marginTop: 4, fontSize: 15, color: 'var(--text-4)' }}>{quantOpsRuntimeSummary(runtimeApply)}</div>
              </div>
            </div>

            <div style={{ display: 'grid', gap: 10 }}>
              <div style={{ padding: 12, background: 'var(--bg-soft)', borderRadius: 8, display: 'grid', gap: 6 }}>
                <div style={{ fontSize: 15, color: 'var(--text-4)' }}>최신 후보</div>
                <div style={{ fontWeight: 700 }}>{quantOpsCandidateSummary(latestCandidate)}</div>
                <div style={{ fontSize: 15, color: 'var(--text-4)' }}>{latestCandidate?.decision?.summary || (latestCandidateState?.reasons || []).join(', ') || '-'}</div>
              </div>
              <div style={{ padding: 12, background: 'var(--bg-soft)', borderRadius: 8, display: 'grid', gap: 6 }}>
                <div style={{ fontSize: 15, color: 'var(--text-4)' }}>저장 후보</div>
                <div style={{ fontWeight: 700 }}>{quantOpsCandidateSummary(savedCandidate)}</div>
                <div style={{ fontSize: 15, color: 'var(--text-4)' }}>{savedCandidateState?.reasons?.length ? savedCandidateState.reasons.join(', ') : savedCandidate?.save_note || '-'}</div>
              </div>
              <div style={{ padding: 12, background: 'var(--bg-soft)', borderRadius: 8, display: 'grid', gap: 6 }}>
                <div style={{ fontSize: 15, color: 'var(--text-4)' }}>런타임 반영</div>
                <div style={{ fontWeight: 700 }}>{quantOpsRuntimeSummary(runtimeApply)}</div>
                <div style={{ fontSize: 15, color: 'var(--text-4)' }}>
                  반영 시각 {formatDateTime(runtimeApply?.applied_at || '') || '-'} · 다음 실행 {formatDateTime(runtimeApply?.next_run_at || '') || '-'}
                </div>
              </div>
            </div>

            {quantOpsWorkflow?.notes?.length ? (
              <div style={{ display: 'grid', gap: 4 }}>
                {quantOpsWorkflow.notes.map((note) => (
                  <div key={note} style={{ fontSize: 15, color: 'var(--text-4)' }}>- {note}</div>
                ))}
              </div>
            ) : quantOpsLoading ? (
              <div style={{ fontSize: 15, color: 'var(--text-4)' }}>quant-ops workflow 로딩 중...</div>
            ) : null}
          </section>
        </div>
      </div>
    </div>
  );
}
