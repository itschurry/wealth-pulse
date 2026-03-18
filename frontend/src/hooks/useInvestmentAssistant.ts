import { useCallback, useEffect, useMemo, useState } from 'react';
import { CANDIDATE_EXCLUDES, COMPANY_CATALOG } from '../data/companyCatalog';
import type { AssistantRiskSignal, AutoRecommendedItem, RecommendedWatchlistItem } from '../types';
import { useAnalysis } from './useAnalysis';
import { useWatchlist } from './useWatchlist';

const KEYWORD_SIGNALS = {
  positive: ['상승', '강세', '급등', '매수', '추천', '우호', '개선', '성장', '상향', '돌파', '신고가', '긍정', '전망', '주목', '기회', '매력'],
  negative: ['하락', '약세', '급락', '매도', '부정', '악화', '약화', '조정', '하향', '저점', '우려', '위험', '주의'],
};

const RISK_RULES: Array<{ title: string; detail: string; keywords: string[]; level: 'high' | 'medium' }> = [
  {
    title: '금리 이벤트 변동성',
    detail: '연준, FOMC, 금리 결정 전후에는 성장주와 환율 민감 자산의 변동성이 커질 수 있습니다.',
    keywords: ['fomc', '연준', '금리', 'fed'],
    level: 'high',
  },
  {
    title: '유가와 지정학 리스크',
    detail: '중동, 유가, 호르무즈 관련 뉴스는 항공과 물류, 인플레이션 기대에 직접적인 영향을 줍니다.',
    keywords: ['유가', '중동', '호르무즈', '이란', 'oil'],
    level: 'high',
  },
  {
    title: '환율 민감도 확대',
    detail: '원달러와 달러 흐름은 외국인 수급과 대형 수출주 심리에 영향을 줄 수 있습니다.',
    keywords: ['환율', '원달러', '달러', 'usd/krw'],
    level: 'medium',
  },
  {
    title: '가상자산 규제 변수',
    detail: '스테이블코인, SEC, 코인 규제 관련 이슈는 성장주 심리와 함께 흔들릴 수 있습니다.',
    keywords: ['스테이블코인', 'sec', '코인', '가상자산', '비트코인'],
    level: 'medium',
  },
];

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function countPatternMatches(text: string, pattern: string) {
  const escapedPattern = escapeRegExp(pattern);
  const asciiOnly = /^[A-Za-z0-9]+$/.test(pattern);
  const regex = asciiOnly
    ? new RegExp(`(^|[^A-Za-z0-9])${escapedPattern}(?=[^A-Za-z0-9]|$)`, 'gi')
    : new RegExp(escapedPattern, 'g');

  return text.match(regex)?.length ?? 0;
}

function normalizeText(value: string) {
  return value.toLowerCase().replace(/\s+/g, ' ').trim();
}

function normalizeKey(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9가-힣]/g, '');
}

function extractTextFromHtml(html: string) {
  if (!html.trim()) return '';

  if (typeof DOMParser !== 'undefined') {
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    return doc.body.textContent?.replace(/\s+/g, ' ').trim() || '';
  }

  return html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
}

function splitIntoSegments(text: string) {
  return text
    .split(/(?<=[.!?。]|다\.|요\.|니다\.)\s+|\n+/)
    .map((segment) => segment.trim())
    .filter(Boolean);
}

function getCompanyContext(analysisText: string, aliases: string[]) {
  const segments = splitIntoSegments(analysisText);
  const loweredAliases = aliases.map((alias) => alias.toLowerCase());
  const matchedSegments = segments.filter((segment) => {
    const loweredSegment = segment.toLowerCase();
    return loweredAliases.some((alias) => countPatternMatches(loweredSegment, alias) > 0);
  });
  const contextSegments = matchedSegments.length ? matchedSegments : segments.slice(0, 2);
  const contextText = contextSegments.join(' ');
  const loweredContext = contextText.toLowerCase();
  const mentionCount = loweredAliases.reduce((total, alias) => total + countPatternMatches(loweredContext, alias), 0);
  const positiveCount = KEYWORD_SIGNALS.positive.reduce((total, keyword) => total + countPatternMatches(loweredContext, keyword), 0);
  const negativeCount = KEYWORD_SIGNALS.negative.reduce((total, keyword) => total + countPatternMatches(loweredContext, keyword), 0);

  return {
    matchedSegments: contextSegments,
    mentionCount: Math.max(1, mentionCount),
    positiveCount,
    negativeCount,
  };
}

function findCompanyMatches(text: string) {
  return COMPANY_CATALOG.map((company) => {
    const count = company.aliases.reduce((total, alias) => total + countPatternMatches(text, alias.toLowerCase()), 0);
    return {
      ...company,
      count,
    };
  }).filter((company) => company.count > 0);
}

function extractSearchCandidates(text: string) {
  const candidates = new Set<string>();
  const regexes = [
    /([가-힣A-Za-z]+(?:전자|지주|금융|은행|화학|텔레콤|통신|에너지|모비스|제약|바이오로직스|바이오|게임즈|건설|항공|증권|카드|전력|이노베이션|생명|화재|소프트|로보틱스|홀딩스))/g,
    /\b([A-Z]{2,5})\b/g,
    /([가-힣]{2,10})\s*항공/g,
  ];

  regexes.forEach((regex) => {
    for (const match of text.matchAll(regex)) {
      const value = (match[1] || match[0] || '').trim();
      if (!value) continue;
      const normalized = normalizeText(value);
      if (normalized.length < 2 || CANDIDATE_EXCLUDES.has(normalized)) continue;
      candidates.add(value);
    }
  });

  return [...candidates].slice(0, 12);
}

function buildAutoRecommendation(params: {
  name: string;
  code?: string;
  market?: string;
  aliases: string[];
  analysisText: string;
  source: 'catalog' | 'search';
  mentionLabel?: string;
}): AutoRecommendedItem {
  const context = getCompanyContext(params.analysisText, params.aliases);
  let baseScore = 54 + context.mentionCount * 4;
  const sentiment = context.positiveCount - context.negativeCount;
  baseScore = Math.min(100, Math.max(30, baseScore + sentiment * 6));

  let signal = '중립';
  if (baseScore >= 74) signal = '강력추천';
  else if (baseScore >= 66) signal = '추천';
  else if (baseScore < 54) signal = '회피';

  const reasons: string[] = [];
  if (context.positiveCount > 0) reasons.push(`긍정 문맥 ${context.positiveCount}건`);
  if (context.negativeCount > 0) reasons.push(`부정 문맥 ${context.negativeCount}건`);
  if (context.mentionCount > 0) reasons.push(`관련 문장 ${context.matchedSegments.length}개, 언급 ${context.mentionCount}회`);
  if (params.mentionLabel) reasons.push(`${params.mentionLabel} 기준으로 종목 식별`);
  if (!reasons.length) reasons.push('관련 문맥을 기반으로 종목 식별');

  return {
    name: params.name,
    code: params.code,
    market: params.market,
    score: Math.round(baseScore),
    confidence: Math.min(100, Math.round(50 + Math.abs(sentiment) * 12 + context.matchedSegments.length * 8)),
    signal,
    reasons,
    evidence: context.matchedSegments.slice(0, 2),
    isAuto: true,
    source: params.source,
  };
}

function calculateWatchlistScore(item: { code: string; name: string; market: string; price?: number; change_pct?: number }, analysisText: string): RecommendedWatchlistItem {
  const context = getCompanyContext(analysisText, [item.name, item.code]);
  const positiveCount = context.positiveCount;
  const negativeCount = context.negativeCount;

  let baseScore = 60;
  const sentiment = positiveCount - negativeCount;
  baseScore = Math.min(100, Math.max(30, baseScore + sentiment * 3));

  if (item.change_pct !== undefined) {
    if (item.change_pct > 1.5) baseScore += 5;
    if (item.change_pct < -1.5) baseScore -= 5;
  }

  const confidence = Math.min(100, Math.round(60 + Math.abs(sentiment) * 8 + context.matchedSegments.length * 5));

  let signal = '중립';
  if (baseScore >= 72) signal = '강력추천';
  else if (baseScore >= 65) signal = '추천';
  else if (baseScore >= 55) signal = '중립';
  else signal = '회피';

  const reasons: string[] = [];
  if (positiveCount > 0) reasons.push(`긍정 신호 ${positiveCount}건`);
  if (negativeCount > 0) reasons.push(`부정 신호 ${negativeCount}건`);
  if (context.matchedSegments.length > 0) reasons.push(`관련 문장 ${context.matchedSegments.length}개`);
  if (item.change_pct && Math.abs(item.change_pct) > 1) reasons.push(`당일 ${item.change_pct > 0 ? '상승' : '하락'} ${Math.abs(item.change_pct)}%`);
  if (!reasons.length) reasons.push('중립적 시장 상황');

  let riskLevel = '낮음';
  if (Math.abs(item.change_pct || 0) > 2) riskLevel = '높음';
  else if (Math.abs(item.change_pct || 0) > 1) riskLevel = '중간';

  return {
    ...item,
    score: Math.round(baseScore),
    confidence,
    signal,
    reasons,
    riskLevel,
    evidence: context.matchedSegments.slice(0, 2),
  };
}

function buildCatalogRecommendations(analysisText: string) {
  const textLower = analysisText.toLowerCase();
  const detectedCompanies = findCompanyMatches(textLower);
  return detectedCompanies
    .map((company) => buildAutoRecommendation({
      name: company.name,
      code: company.code,
      market: company.market,
      aliases: company.aliases,
      analysisText,
      source: 'catalog',
    }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 10);
}

async function resolveDynamicCompanies(analysisText: string, baseMatches: AutoRecommendedItem[]): Promise<AutoRecommendedItem[]> {
  const existingKeys = new Set(baseMatches.flatMap((item) => [normalizeKey(item.name), item.code ? normalizeKey(item.code) : '']));
  const candidates = extractSearchCandidates(analysisText).filter((candidate) => !existingKeys.has(normalizeKey(candidate)));

  if (!candidates.length) return [];

  const resolved: Array<AutoRecommendedItem | null> = await Promise.all(candidates.map(async (candidate) => {
    try {
      const res = await fetch(`/api/stock-search?q=${encodeURIComponent(candidate)}`, { cache: 'no-store' });
      const data = await res.json();
      const results = Array.isArray(data.results) ? data.results : [];
      const candidateKey = normalizeKey(candidate);
      const match = results.find((result: { name: string; code: string; market: string }) => {
        const resultNameKey = normalizeKey(result.name);
        return resultNameKey === candidateKey || resultNameKey.includes(candidateKey) || candidateKey.includes(resultNameKey);
      });

      if (!match) return null;

      const dedupeKey = normalizeKey(match.code || match.name);
      if (existingKeys.has(dedupeKey)) return null;
      existingKeys.add(dedupeKey);

      return buildAutoRecommendation({
        name: match.name,
        code: match.code,
        market: match.market,
        aliases: [candidate, match.name],
        analysisText,
        source: 'search',
        mentionLabel: candidate,
      });
    } catch {
      return null;
    }
  }));

  return resolved.filter((item): item is AutoRecommendedItem => item !== null);
}

function buildRiskSignals(analysisText: string): AssistantRiskSignal[] {
  const lowered = analysisText.toLowerCase();
  return RISK_RULES.filter((rule) => rule.keywords.some((keyword) => lowered.includes(keyword.toLowerCase())))
    .slice(0, 3)
    .map((rule) => ({ title: rule.title, detail: rule.detail, level: rule.level }));
}

export function useInvestmentAssistant() {
  const { items: watchlist, add: addWatchlist, refreshPrices } = useWatchlist();
  const { data: analysisData, status: analysisStatus, refresh: refreshAnalysis } = useAnalysis();
  const [autoRecommendations, setAutoRecommendations] = useState<AutoRecommendedItem[]>([]);
  const [autoLoading, setAutoLoading] = useState(false);
  const [addingCode, setAddingCode] = useState<string | null>(null);

  const analysisText = useMemo(() => {
    const summaryText = (analysisData.summary_lines || []).join(' ');
    const bodyText = extractTextFromHtml(analysisData.analysis_html || '');
    return [summaryText, bodyText].filter(Boolean).join(' ');
  }, [analysisData.summary_lines, analysisData.analysis_html]);

  const watchlistRecommendations = useMemo(
    () => watchlist.map((item) => calculateWatchlistScore(item, analysisText.toLowerCase())),
    [watchlist, analysisText],
  );

  const watchlistCodes = useMemo(() => new Set(watchlist.map((item) => item.code)), [watchlist]);
  const riskSignals = useMemo(() => buildRiskSignals(analysisText), [analysisText]);

  useEffect(() => {
    let cancelled = false;

    async function buildRecommendations() {
      if (!analysisText.trim()) {
        setAutoRecommendations([]);
        return;
      }

      setAutoLoading(true);
      const baseMatches = buildCatalogRecommendations(analysisText);
      const dynamicMatches = await resolveDynamicCompanies(analysisText, baseMatches);
      const merged = [...baseMatches, ...dynamicMatches]
        .sort((a, b) => b.score - a.score)
        .slice(0, 12);

      if (!cancelled) {
        setAutoRecommendations(merged);
        setAutoLoading(false);
      }
    }

    buildRecommendations().catch(() => {
      if (!cancelled) {
        setAutoRecommendations(buildCatalogRecommendations(analysisText));
        setAutoLoading(false);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [analysisText]);

  const refreshAll = useCallback(() => {
    refreshAnalysis();
    refreshPrices();
  }, [refreshAnalysis, refreshPrices]);

  const addRecommendation = useCallback(async (item: AutoRecommendedItem) => {
    if (!item.code || watchlistCodes.has(item.code)) return;

    try {
      setAddingCode(item.code);
      await addWatchlist(item.code, item.name, item.market || '');
    } finally {
      setAddingCode(null);
    }
  }, [addWatchlist, watchlistCodes]);

  return {
    analysisData,
    analysisStatus,
    analysisText,
    watchlist,
    watchlistRecommendations,
    autoRecommendations,
    autoLoading,
    watchlistCodes,
    riskSignals,
    addingCode,
    addRecommendation,
    refreshAll,
  };
}
