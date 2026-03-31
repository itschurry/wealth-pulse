import { useSyncExternalStore } from 'react';
import { defaultBacktestQuery, loadBacktestQuery, saveBacktestQuery } from './useBacktest';
import type { BacktestQuery } from '../types';

export interface ValidationSettings {
  strategy: string;
  trainingDays: number;
  validationDays: number;
  walkForward: boolean;
  minTrades: number;
  objective: string;
}

interface ValidationStoreState {
  draftQuery: BacktestQuery;
  savedQuery: BacktestQuery;
  draftSettings: ValidationSettings;
  savedSettings: ValidationSettings;
  lastSavedAt: string;
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
    strategy: '공통 전략 엔진',
    trainingDays: 180,
    validationDays: 60,
    walkForward: true,
    minTrades: 20,
    objective: '수익 우선',
  };
}

function clampValidationSettings(raw: Partial<ValidationSettings> | null | undefined): ValidationSettings {
  const fallback = defaultValidationSettings();
  return {
    strategy: raw?.strategy || fallback.strategy,
    trainingDays: Math.max(30, Number(raw?.trainingDays) || fallback.trainingDays),
    validationDays: Math.max(20, Number(raw?.validationDays) || fallback.validationDays),
    walkForward: typeof raw?.walkForward === 'boolean' ? raw.walkForward : fallback.walkForward,
    minTrades: Math.max(1, Number(raw?.minTrades) || fallback.minTrades),
    objective: raw?.objective || fallback.objective,
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
    };
  }

  const draftQuery = loadBacktestQuery();
  const savedQuery = readJson<BacktestQuery>(SAVED_QUERY_KEY) || draftQuery;
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

export function useValidationSettingsStore() {
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  const unsaved = !isSame(snapshot.draftQuery, snapshot.savedQuery) || !isSame(snapshot.draftSettings, snapshot.savedSettings);

  return {
    ...snapshot,
    unsaved,
    setDraftQuery(next: BacktestQuery | ((current: BacktestQuery) => BacktestQuery)) {
      storeState = {
        ...storeState,
        draftQuery: typeof next === 'function' ? next(storeState.draftQuery) : next,
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
    saveDraft() {
      storeState = {
        ...storeState,
        savedQuery: storeState.draftQuery,
        savedSettings: storeState.draftSettings,
        lastSavedAt: new Date().toISOString(),
      };
      persistSaved(storeState);
      persistDraft(storeState);
      emit();
      return storeState.lastSavedAt;
    },
    resetDraft() {
      const defaultQuery = defaultBacktestQuery(storeState.draftQuery.market_scope);
      storeState = {
        ...storeState,
        draftQuery: defaultQuery,
        draftSettings: defaultValidationSettings(),
      };
      persistDraft(storeState);
      emit();
    },
  };
}

export function formatValidationSettingsLabel(settings: ValidationSettings, query: BacktestQuery): string[] {
  return [
    `${query.market_scope === 'kospi' ? 'KOSPI' : query.market_scope === 'nasdaq' ? 'NASDAQ' : 'KOSPI+NASDAQ'} · 기간 ${query.lookback_days}일`,
    `${settings.strategy} · 학습 ${settings.trainingDays}일 / 검증 ${settings.validationDays}일`,
    `${settings.walkForward ? 'Walk-forward 사용' : 'Walk-forward 미사용'} · 최소 거래수 ${settings.minTrades}건 · ${settings.objective}`,
  ];
}
