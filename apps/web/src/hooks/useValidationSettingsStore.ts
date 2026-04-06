import { useSyncExternalStore } from 'react';
import { fetchValidationSettings, resetValidationSettings, saveValidationSettings } from '../api/domain';
import { defaultBacktestQuery, loadBacktestQuery, saveBacktestQuery } from './useBacktest';
import type { BacktestQuery } from '../types';
import type { PersistedValidationSettingsResponse } from '../types/domain';

export type RuntimeCandidateSourceMode = 'quant_only' | 'hybrid';

export interface ValidationSettings {
  strategy: string;
  trainingDays: number;
  validationDays: number;
  walkForward: boolean;
  minTrades: number;
  objective: string;
  runtimeCandidateSourceMode: RuntimeCandidateSourceMode;
}

interface ValidationStoreState {
  draftQuery: BacktestQuery;
  savedQuery: BacktestQuery;
  draftSettings: ValidationSettings;
  savedSettings: ValidationSettings;
  lastSavedAt: string;
  syncStatus: 'idle' | 'loading' | 'saving' | 'resetting' | 'ready' | 'error';
  syncMessage: string;
  serverLoaded: boolean;
}

const SAVED_SETTINGS_KEY = 'console_validation_settings_v1';
const DRAFT_SETTINGS_KEY = 'console_validation_settings_draft_v1';
const SAVED_QUERY_KEY = 'console_validation_saved_query_v1';
const META_KEY = 'console_validation_settings_meta_v1';

const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}

function defaultValidationSettings(): ValidationSettings {
  return {
    strategy: '퀀트 전략 엔진',
    trainingDays: 180,
    validationDays: 60,
    walkForward: true,
    minTrades: 20,
    objective: '수익 우선',
    runtimeCandidateSourceMode: 'quant_only',
  };
}

function clampValidationSettings(raw: Partial<ValidationSettings> | null | undefined): ValidationSettings {
  const fallback = defaultValidationSettings();
  const runtimeCandidateSourceMode = raw?.runtimeCandidateSourceMode === 'hybrid'
    || raw?.runtimeCandidateSourceMode === 'quant_only'
    ? raw.runtimeCandidateSourceMode
    : raw && 'runtime_candidate_source_mode' in raw
      && ((raw as Partial<Record<'runtime_candidate_source_mode', unknown>>).runtime_candidate_source_mode === 'hybrid'
        || (raw as Partial<Record<'runtime_candidate_source_mode', unknown>>).runtime_candidate_source_mode === 'quant_only')
      ? ((raw as Partial<Record<'runtime_candidate_source_mode', RuntimeCandidateSourceMode>>).runtime_candidate_source_mode as RuntimeCandidateSourceMode)
      : fallback.runtimeCandidateSourceMode;
  return {
    strategy: raw?.strategy || fallback.strategy,
    trainingDays: Math.max(30, Number(raw?.trainingDays) || fallback.trainingDays),
    validationDays: Math.max(20, Number(raw?.validationDays) || fallback.validationDays),
    walkForward: typeof raw?.walkForward === 'boolean' ? raw.walkForward : fallback.walkForward,
    minTrades: Math.max(1, Number(raw?.minTrades) || fallback.minTrades),
    objective: raw?.objective || fallback.objective,
    runtimeCandidateSourceMode,
  };
}

function readJson<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

function readNumber(value: unknown, fallback: number) {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function readNullableNumber(value: unknown, fallback: number | null | undefined) {
  if (value === null) return null;
  return typeof value === 'number' && Number.isFinite(value) ? value : (fallback ?? null);
}

function clampBacktestQuery(raw: Partial<BacktestQuery> | null | undefined): BacktestQuery {
  const marketScope = raw?.market_scope === 'nasdaq'
    ? 'nasdaq'
    : raw?.market_scope === 'all'
      ? 'all'
      : 'kospi';
  const strategyKind = raw?.strategy_kind === 'mean_reversion'
    ? 'mean_reversion'
    : raw?.strategy_kind === 'defensive'
      ? 'defensive'
      : 'trend_following';
  const riskProfile = raw?.risk_profile === 'conservative'
    ? 'conservative'
    : raw?.risk_profile === 'aggressive'
      ? 'aggressive'
      : 'balanced';
  const preset = defaultBacktestQuery(marketScope, strategyKind, riskProfile);
  const portfolioRaw = raw?.portfolio_constraints && typeof raw.portfolio_constraints === 'object'
    ? raw.portfolio_constraints
    : {};
  const strategyParamsRaw = (raw?.strategy_params && typeof raw.strategy_params === 'object'
    ? raw.strategy_params
    : preset.strategy_params) as Record<string, unknown>;
  return {
    market_scope: marketScope,
    lookback_days: Math.max(180, readNumber(raw?.lookback_days, preset.lookback_days)),
    strategy_kind: strategyKind,
    regime_mode: raw?.regime_mode === 'manual' ? 'manual' : 'auto',
    risk_profile: riskProfile,
    portfolio_constraints: {
      market_scope: marketScope,
      initial_cash: Math.max(1, readNumber((portfolioRaw as Partial<BacktestQuery['portfolio_constraints']>).initial_cash, preset.portfolio_constraints.initial_cash)),
      max_positions: Math.max(1, readNumber((portfolioRaw as Partial<BacktestQuery['portfolio_constraints']>).max_positions, preset.portfolio_constraints.max_positions)),
      max_holding_days: Math.max(1, readNumber((portfolioRaw as Partial<BacktestQuery['portfolio_constraints']>).max_holding_days, preset.portfolio_constraints.max_holding_days)),
    },
    strategy_params: strategyParamsRaw as Record<string, number | string | boolean | null>,
    initial_cash: Math.max(1, readNumber(raw?.initial_cash, preset.initial_cash)),
    max_positions: Math.max(1, readNumber(raw?.max_positions, preset.max_positions)),
    max_holding_days: Math.max(1, readNumber(raw?.max_holding_days, preset.max_holding_days)),
    rsi_min: readNumber(raw?.rsi_min, Number(strategyParamsRaw.rsi_min ?? preset.rsi_min)),
    rsi_max: readNumber(raw?.rsi_max, Number(strategyParamsRaw.rsi_max ?? preset.rsi_max)),
    volume_ratio_min: Math.max(0, readNumber(raw?.volume_ratio_min, Number(strategyParamsRaw.volume_ratio_min ?? preset.volume_ratio_min))),
    stop_loss_pct: readNullableNumber(raw?.stop_loss_pct, readNullableNumber(strategyParamsRaw.stop_loss_pct, preset.stop_loss_pct)),
    take_profit_pct: readNullableNumber(raw?.take_profit_pct, readNullableNumber(strategyParamsRaw.take_profit_pct, preset.take_profit_pct)),
    adx_min: readNullableNumber(raw?.adx_min, readNullableNumber(strategyParamsRaw.adx_min, preset.adx_min)),
    mfi_min: readNullableNumber(raw?.mfi_min, readNullableNumber(strategyParamsRaw.mfi_min, preset.mfi_min)),
    mfi_max: readNullableNumber(raw?.mfi_max, readNullableNumber(strategyParamsRaw.mfi_max, preset.mfi_max)),
    bb_pct_min: readNullableNumber(raw?.bb_pct_min, readNullableNumber(strategyParamsRaw.bb_pct_min, preset.bb_pct_min)),
    bb_pct_max: readNullableNumber(raw?.bb_pct_max, readNullableNumber(strategyParamsRaw.bb_pct_max, preset.bb_pct_max)),
    stoch_k_min: readNullableNumber(raw?.stoch_k_min, readNullableNumber(strategyParamsRaw.stoch_k_min, preset.stoch_k_min)),
    stoch_k_max: readNullableNumber(raw?.stoch_k_max, readNullableNumber(strategyParamsRaw.stoch_k_max, preset.stoch_k_max)),
  };
}

function persistDraft(state: ValidationStoreState) {
  saveBacktestQuery(state.draftQuery);
  localStorage.setItem(DRAFT_SETTINGS_KEY, JSON.stringify(state.draftSettings));
}

function persistSaved(state: ValidationStoreState) {
  localStorage.setItem(SAVED_SETTINGS_KEY, JSON.stringify(state.savedSettings));
  localStorage.setItem(SAVED_QUERY_KEY, JSON.stringify(state.savedQuery));
  localStorage.setItem(META_KEY, JSON.stringify({ lastSavedAt: state.lastSavedAt }));
}

function readMetaSavedAt(): string {
  const meta = readJson<{ lastSavedAt?: string }>(META_KEY);
  return meta?.lastSavedAt || '';
}

function hydrateState(): ValidationStoreState {
  if (typeof window === 'undefined') {
    const query = defaultBacktestQuery();
    const settings = defaultValidationSettings();
    return {
      draftQuery: query,
      savedQuery: query,
      draftSettings: settings,
      savedSettings: settings,
      lastSavedAt: '',
      syncStatus: 'idle',
      syncMessage: '',
      serverLoaded: false,
    };
  }

  const draftQuery = loadBacktestQuery();
  const savedQuery = clampBacktestQuery(readJson<Partial<BacktestQuery>>(SAVED_QUERY_KEY) || draftQuery);
  const savedSettings = clampValidationSettings(readJson<Partial<ValidationSettings>>(SAVED_SETTINGS_KEY));
  const draftSettings = clampValidationSettings(
    readJson<Partial<ValidationSettings>>(DRAFT_SETTINGS_KEY)
      || readJson<Partial<ValidationSettings>>(SAVED_SETTINGS_KEY),
  );

  return {
    draftQuery,
    savedQuery,
    draftSettings,
    savedSettings,
    lastSavedAt: readMetaSavedAt(),
    syncStatus: 'idle',
    syncMessage: '',
    serverLoaded: false,
  };
}

let storeState = hydrateState();

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot() {
  return storeState;
}

function isSame<T>(left: T, right: T): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function hasUnsavedDraft(state: ValidationStoreState): boolean {
  return !isSame(state.draftQuery, state.savedQuery) || !isSame(state.draftSettings, state.savedSettings);
}

function normalizeServerPayload(payload: PersistedValidationSettingsResponse | null | undefined) {
  return {
    query: clampBacktestQuery((payload?.query || null) as Partial<BacktestQuery> | null),
    settings: clampValidationSettings((payload?.settings || null) as Partial<ValidationSettings> | null),
    savedAt: payload?.saved_at || '',
  };
}

function applyServerPayload(payload: PersistedValidationSettingsResponse | null | undefined, options?: { replaceDraft?: boolean }) {
  const normalized = normalizeServerPayload(payload);
  storeState = {
    ...storeState,
    savedQuery: normalized.query,
    savedSettings: normalized.settings,
    lastSavedAt: normalized.savedAt,
    syncStatus: 'ready',
    syncMessage: normalized.savedAt ? '서버 저장값을 동기화했습니다.' : '서버 기본값을 동기화했습니다.',
    serverLoaded: true,
    ...(options?.replaceDraft ? {
      draftQuery: normalized.query,
      draftSettings: normalized.settings,
    } : {}),
  };
  persistSaved(storeState);
  if (options?.replaceDraft) {
    persistDraft(storeState);
  }
  emit();
  return storeState;
}

export function useValidationSettingsStore() {
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  const unsaved = hasUnsavedDraft(snapshot);

  return {
    ...snapshot,
    unsaved,
    setDraftQuery(next: BacktestQuery | ((current: BacktestQuery) => BacktestQuery)) {
      storeState = {
        ...storeState,
        draftQuery: clampBacktestQuery(typeof next === 'function' ? next(storeState.draftQuery) : next),
      };
      persistDraft(storeState);
      emit();
    },
    setDraftSettings(next: ValidationSettings | ((current: ValidationSettings) => ValidationSettings)) {
      storeState = {
        ...storeState,
        draftSettings: clampValidationSettings(typeof next === 'function' ? next(storeState.draftSettings) : next),
      };
      persistDraft(storeState);
      emit();
    },
    async loadSavedFromServer(options?: { forceDraft?: boolean }) {
      const replaceDraft = options?.forceDraft || !hasUnsavedDraft(storeState);
      storeState = {
        ...storeState,
        syncStatus: 'loading',
        syncMessage: '서버 저장값을 불러오는 중입니다.',
      };
      emit();
      try {
        const payload = await fetchValidationSettings();
        return applyServerPayload(payload, { replaceDraft });
      } catch (error) {
        storeState = {
          ...storeState,
          syncStatus: 'error',
          syncMessage: '서버 저장값을 불러오지 못했습니다.',
        };
        emit();
        throw error;
      }
    },
    async saveDraftToServer() {
      storeState = {
        ...storeState,
        syncStatus: 'saving',
        syncMessage: '현재 초안을 서버에 저장하는 중입니다.',
      };
      emit();
      try {
        const payload = await saveValidationSettings(storeState.draftQuery, storeState.draftSettings);
        applyServerPayload(payload, { replaceDraft: true });
        return storeState.lastSavedAt;
      } catch (error) {
        storeState = {
          ...storeState,
          syncStatus: 'error',
          syncMessage: '서버 저장에 실패했습니다.',
        };
        emit();
        throw error;
      }
    },
    loadSavedIntoDraft() {
      storeState = {
        ...storeState,
        draftQuery: storeState.savedQuery,
        draftSettings: storeState.savedSettings,
        syncStatus: 'ready',
        syncMessage: '서버 저장값을 초안으로 불러왔습니다.',
      };
      persistDraft(storeState);
      emit();
    },
    async resetSavedToServer() {
      storeState = {
        ...storeState,
        syncStatus: 'resetting',
        syncMessage: '서버 저장값을 기본값으로 초기화하는 중입니다.',
      };
      emit();
      try {
        const payload = await resetValidationSettings();
        applyServerPayload(payload, { replaceDraft: true });
        return storeState.lastSavedAt;
      } catch (error) {
        storeState = {
          ...storeState,
          syncStatus: 'error',
          syncMessage: '서버 저장값 초기화에 실패했습니다.',
        };
        emit();
        throw error;
      }
    },
  };
}

export function formatValidationSettingsLabel(settings: ValidationSettings, query: BacktestQuery): string[] {
  const strategyLabel = query.strategy_kind === 'mean_reversion'
    ? 'Mean Reversion'
    : query.strategy_kind === 'defensive'
      ? 'Defensive'
      : 'Trend Following';
  return [
    `${query.market_scope === 'kospi' ? 'KOSPI' : query.market_scope === 'nasdaq' ? 'NASDAQ' : 'KOSPI+NASDAQ'} · 탐색 기간 ${query.lookback_days}일`,
    `${strategyLabel} · regime ${query.regime_mode} · risk ${query.risk_profile}`,
    `${settings.strategy} · 검증 ${settings.validationDays}일${settings.trainingDays ? ` · UI 설정 학습 구간 ${settings.trainingDays}일` : ''}`,
    `${settings.walkForward ? 'Walk-forward 사용' : 'Walk-forward 미사용'} · 최소 거래수 ${settings.minTrades}건 · ${settings.objective}`,
    `실행 후보 소스 ${settings.runtimeCandidateSourceMode === 'quant_only' ? 'quant_only · 퀀트 검증 후보만 사용' : 'hybrid · 퀀트/리서치 분리 후 합집합 사용'}`,
  ];
}
