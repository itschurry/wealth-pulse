export type ScoreTone = 'good' | 'neutral' | 'bad';

export interface StrategyScorecardView {
  compositeScore: number | null;
  components: Record<string, number>;
  tailRisk: Record<string, number>;
}

export interface ScorecardComponentRow {
  key: string;
  label: string;
  value: number;
  tone: ScoreTone;
}

export interface TailRiskRow {
  key: string;
  label: string;
  value: number;
  tone: ScoreTone;
}

const COMPONENT_LABELS: Record<string, string> = {
  sharpe_component: '리스크 조정 수익',
  return_component: '기대 수익',
  win_rate_component: '승률',
  sample_component: '표본 수',
  drawdown_component: '낙폭 관리',
  tail_component: '테일 리스크',
  total_score: '총점',
};

const COMPONENT_ORDER = [
  'sharpe_component',
  'return_component',
  'win_rate_component',
  'sample_component',
  'drawdown_component',
  'tail_component',
];

function toNumber(value: unknown): number | null {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function toNumberRecord(value: unknown): Record<string, number> {
  if (!value || typeof value !== 'object') return {};
  const out: Record<string, number> = {};
  Object.entries(value as Record<string, unknown>).forEach(([key, raw]) => {
    const numeric = toNumber(raw);
    if (numeric !== null) out[key] = numeric;
  });
  return out;
}

function readTailRisk(source: Record<string, unknown>): Record<string, number> {
  return toNumberRecord(source.tail_risk ?? source.tailRisk);
}

function readComponents(source: Record<string, unknown>): Record<string, number> {
  return toNumberRecord(source.components ?? source.score_components ?? source.scoreComponents);
}

export function extractStrategyScorecard(source: unknown): StrategyScorecardView | null {
  if (!source || typeof source !== 'object') return null;
  const raw = source as Record<string, unknown>;
  const components = readComponents(raw);
  const tailRisk = readTailRisk(raw);
  const compositeScore = toNumber(raw.composite_score ?? raw.compositeScore ?? components.total_score);

  const hasData = compositeScore !== null || Object.keys(components).length > 0 || Object.keys(tailRisk).length > 0;
  if (!hasData) return null;

  return {
    compositeScore,
    components,
    tailRisk,
  };
}

function toneFromComponent(value: number): ScoreTone {
  if (value >= 4) return 'good';
  if (value <= -4) return 'bad';
  return 'neutral';
}

function toneFromTailRisk(key: string, value: number): ScoreTone {
  if (key === 'loss_rate_pct') {
    if (value >= 55) return 'bad';
    if (value >= 45) return 'neutral';
    return 'good';
  }
  if (key === 'expected_shortfall_5_pct') {
    if (value <= -14) return 'bad';
    if (value <= -8) return 'neutral';
    return 'good';
  }
  if (key === 'return_p05_pct') {
    if (value <= -10) return 'bad';
    if (value <= -6) return 'neutral';
    return 'good';
  }
  if (key === 'worst_case_return_pct') {
    if (value <= -18) return 'bad';
    if (value <= -12) return 'neutral';
    return 'good';
  }
  if (key === 'return_p01_pct') {
    if (value <= -14) return 'bad';
    if (value <= -9) return 'neutral';
    return 'good';
  }
  return 'neutral';
}

export function describeScoreDecision(scorecard: StrategyScorecardView | null): {
  label: string;
  tone: ScoreTone;
  detail: string;
} {
  if (!scorecard || scorecard.compositeScore === null) {
    return {
      label: '점수 미확정',
      tone: 'neutral',
      detail: '백테스트/최적화 결과가 더 쌓이면 투입 판단을 고정할 수 있습니다.',
    };
  }

  const tailRows = buildTailRiskRows(scorecard);
  const tailBad = tailRows.some((item) => item.tone === 'bad');
  const score = scorecard.compositeScore;

  if (!tailBad && score >= 48) {
    return {
      label: '투입 후보',
      tone: 'good',
      detail: '점수와 꼬리손실이 모두 양호합니다. 소규모부터 검증 가능한 구간입니다.',
    };
  }
  if (tailBad || score < 24) {
    return {
      label: '재검증 필요',
      tone: 'bad',
      detail: '손실 꼬리나 점수 하단이 걸립니다. 파라미터/기간 재검증이 우선입니다.',
    };
  }
  return {
    label: '조건부 운영',
    tone: 'neutral',
    detail: '진입 수를 줄이고 tail-risk 경계값을 같이 보면서 운영해야 합니다.',
  };
}

export function buildScoreComponentRows(scorecard: StrategyScorecardView | null): ScorecardComponentRow[] {
  if (!scorecard) return [];
  return COMPONENT_ORDER
    .map((key) => {
      const value = toNumber(scorecard.components[key]);
      if (value === null) return null;
      return {
        key,
        label: COMPONENT_LABELS[key] || key,
        value,
        tone: toneFromComponent(value),
      } satisfies ScorecardComponentRow;
    })
    .filter((item): item is ScorecardComponentRow => Boolean(item));
}

export function buildTailRiskRows(scorecard: StrategyScorecardView | null): TailRiskRow[] {
  if (!scorecard) return [];
  const keys = ['return_p05_pct', 'expected_shortfall_5_pct', 'worst_case_return_pct', 'loss_rate_pct'];
  const labels: Record<string, string> = {
    return_p05_pct: 'P05 수익률',
    expected_shortfall_5_pct: 'ES 5%',
    worst_case_return_pct: '최악 손실',
    loss_rate_pct: '손실 비중',
  };
  return keys
    .map((key) => {
      const value = toNumber(scorecard.tailRisk[key]);
      if (value === null) return null;
      return {
        key,
        label: labels[key] || key,
        value,
        tone: toneFromTailRisk(key, value),
      } satisfies TailRiskRow;
    })
    .filter((item): item is TailRiskRow => Boolean(item));
}

export function strongestComponents(scorecard: StrategyScorecardView | null): ScorecardComponentRow[] {
  return buildScoreComponentRows(scorecard)
    .filter((item) => item.key !== 'total_score')
    .sort((left, right) => right.value - left.value)
    .slice(0, 2);
}

export function weakestComponents(scorecard: StrategyScorecardView | null): ScorecardComponentRow[] {
  return buildScoreComponentRows(scorecard)
    .filter((item) => item.key !== 'total_score')
    .sort((left, right) => left.value - right.value)
    .slice(0, 2);
}

export function tailRiskHeadline(scorecard: StrategyScorecardView | null): {
  label: string;
  tone: ScoreTone;
  detail: string;
} {
  const rows = buildTailRiskRows(scorecard);
  if (rows.length === 0) {
    return {
      label: '테일 데이터 없음',
      tone: 'neutral',
      detail: '손실 꼬리 지표가 아직 계산되지 않았습니다.',
    };
  }

  if (rows.some((item) => item.tone === 'bad')) {
    return {
      label: '꼬리손실 경계',
      tone: 'bad',
      detail: '급락 구간에서 손실이 커질 수 있어 포지션 수와 초기 진입 크기를 줄여야 합니다.',
    };
  }
  if (rows.some((item) => item.tone === 'neutral')) {
    return {
      label: '꼬리손실 보통',
      tone: 'neutral',
      detail: '수익 기회는 있지만 이벤트 구간에서는 방어 우선으로 보는 편이 안전합니다.',
    };
  }
  return {
    label: '꼬리손실 안정',
    tone: 'good',
    detail: '현재 기준에서는 손실 꼬리가 비교적 얕은 편입니다.',
  };
}
