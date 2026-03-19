import { useCallback, useMemo } from 'react';
import type {
  RecommendationItem,
  RecommendationsData,
  TodayPickItem,
  TodayPicksData,
  WatchlistActionItem,
  WatchlistActionsData,
  WatchlistItem,
} from '../types';
import { useRecommendations } from './useRecommendations';
import { useTodayPicks } from './useTodayPicks';
import { useWatchlistActions } from './useWatchlistActions';

type UnifiedScoreSource = 'watchlist' | 'blended' | 'today_pick' | 'recommendation';

export interface UnifiedScoreEntry {
  score: number;
  signal?: string;
  source: UnifiedScoreSource;
}

interface ScoreSeed {
  pick_score?: number;
  pick_signal?: string;
  recommendation_score?: number;
  recommendation_signal?: string;
  watchlist_score?: number;
  watchlist_signal?: string;
}

function normalizeCode(value?: string) {
  return (value || '').split('.')[0].trim().toUpperCase();
}

function normalizeName(value?: string) {
  return (value || '').trim().toLowerCase();
}

function buildKeys(code?: string, name?: string) {
  const keys: string[] = [];
  const normalizedCode = normalizeCode(code);
  const normalizedName = normalizeName(name);
  if (normalizedCode) keys.push(`code:${normalizedCode}`);
  if (normalizedName) keys.push(`name:${normalizedName}`);
  return keys;
}

function upsertSeed(seedMap: Map<string, ScoreSeed>, item: { code?: string; name?: string }, patch: Partial<ScoreSeed>) {
  for (const key of buildKeys(item.code, item.name)) {
    seedMap.set(key, {
      ...(seedMap.get(key) || {}),
      ...patch,
    });
  }
}

function roundScore(value: number) {
  return Math.round(Math.max(20, Math.min(95, value)) * 10) / 10;
}

function buildUnifiedEntry(seed: ScoreSeed): UnifiedScoreEntry | null {
  if (typeof seed.watchlist_score === 'number') {
    return {
      score: roundScore(seed.watchlist_score),
      signal: seed.watchlist_signal,
      source: 'watchlist',
    };
  }

  if (typeof seed.pick_score === 'number' && typeof seed.recommendation_score === 'number') {
    const score = 50 + (seed.pick_score - 50) * 0.55 + (seed.recommendation_score - 50) * 0.35;
    return {
      score: roundScore(score),
      signal: seed.pick_signal || seed.recommendation_signal,
      source: 'blended',
    };
  }

  if (typeof seed.pick_score === 'number') {
    return {
      score: roundScore(seed.pick_score),
      signal: seed.pick_signal,
      source: 'today_pick',
    };
  }

  if (typeof seed.recommendation_score === 'number') {
    return {
      score: roundScore(seed.recommendation_score),
      signal: seed.recommendation_signal,
      source: 'recommendation',
    };
  }

  return null;
}

function buildUnifiedScoreMap(
  todayPicks: TodayPicksData,
  recommendations: RecommendationsData,
  watchlistActions: WatchlistActionsData,
) {
  const seedMap = new Map<string, ScoreSeed>();

  for (const item of todayPicks.picks || []) {
    upsertSeed(seedMap, item, {
      pick_score: item.score,
      pick_signal: item.signal,
    });
  }

  for (const item of recommendations.recommendations || []) {
    upsertSeed(seedMap, { code: item.ticker, name: item.name }, {
      recommendation_score: item.score,
      recommendation_signal: item.signal,
    });
  }

  for (const item of watchlistActions.actions || []) {
    upsertSeed(seedMap, item, {
      watchlist_score: item.score,
      watchlist_signal: item.signal,
    });
  }

  const scoreMap = new Map<string, UnifiedScoreEntry>();
  for (const [key, seed] of seedMap.entries()) {
    const entry = buildUnifiedEntry(seed);
    if (entry) scoreMap.set(key, entry);
  }
  return scoreMap;
}

function findUnifiedScore(
  scoreMap: Map<string, UnifiedScoreEntry>,
  item: { code?: string; name?: string },
) {
  for (const key of buildKeys(item.code, item.name)) {
    const entry = scoreMap.get(key);
    if (entry) return entry;
  }
  return undefined;
}

export function applyUnifiedScore<T extends { score: number; signal?: string; code?: string; name?: string }>(
  item: T,
  scoreMap: Map<string, UnifiedScoreEntry>,
) {
  const unified = findUnifiedScore(scoreMap, item);
  if (!unified) return item;
  return {
    ...item,
    score: unified.score,
    signal: unified.signal || item.signal,
  };
}

export function useUnifiedScores(watchlistItems: WatchlistItem[]) {
  const todayPicks = useTodayPicks();
  const recommendations = useRecommendations();
  const watchlistActions = useWatchlistActions(watchlistItems);

  const scoreMap = useMemo(
    () => buildUnifiedScoreMap(todayPicks.data, recommendations.data, watchlistActions.data),
    [todayPicks.data, recommendations.data, watchlistActions.data],
  );

  const getUnifiedScore = useCallback(
    (item: { code?: string; name?: string }) => findUnifiedScore(scoreMap, item),
    [scoreMap],
  );

  const applyToPick = useCallback(
    (item: TodayPickItem) => applyUnifiedScore(item, scoreMap),
    [scoreMap],
  );

  const applyToRecommendation = useCallback(
    (item: RecommendationItem) => applyUnifiedScore({ ...item, code: item.ticker }, scoreMap),
    [scoreMap],
  );

  const applyToWatchlistAction = useCallback(
    (item: WatchlistActionItem) => applyUnifiedScore(item, scoreMap),
    [scoreMap],
  );

  const refresh = useCallback(() => {
    todayPicks.refresh();
    recommendations.refresh();
    watchlistActions.refresh();
  }, [todayPicks, recommendations, watchlistActions]);

  return {
    scoreMap,
    getUnifiedScore,
    applyToPick,
    applyToRecommendation,
    applyToWatchlistAction,
    todayPicks,
    recommendations,
    watchlistActions,
    refresh,
  };
}
