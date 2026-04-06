import { reasonCodeToKorean, reliabilityToKorean, strategyTypeToKorean } from '../constants/uiText';
import { explainSizeRecommendation, formatCount, formatDateTime, formatNumber, formatPercent, formatSymbol } from '../utils/format';
import type {
  ConsoleSnapshot,
  SignalTableRow,
  TodayReportView,
  WatchDecisionCandidate,
  WatchDecisionView,
} from '../types/consoleView';
import type { DomainSignal } from '../types/domain';

function translateReasons(reasons: string[]): string[] {
  return reasons.map((reason) => reasonCodeToKorean(reason));
}

function dedupeKeepOrder(lines: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const line of lines) {
    const normalized = line.trim();
    if (!normalized || seen.has(normalized)) continue;
    seen.add(normalized);
    out.push(normalized);
  }
  return out;
}

function sortSignalsForWatch(signals: DomainSignal[]): DomainSignal[] {
  return [...signals].sort((left, right) => {
    const evGap = Number(right.ev_metrics?.expected_value ?? Number.NEGATIVE_INFINITY)
      - Number(left.ev_metrics?.expected_value ?? Number.NEGATIVE_INFINITY);
    if (Number.isFinite(evGap) && evGap !== 0) return evGap;

    const scoreGap = Number(right.score ?? Number.NEGATIVE_INFINITY)
      - Number(left.score ?? Number.NEGATIVE_INFINITY);
    if (Number.isFinite(scoreGap) && scoreGap !== 0) return scoreGap;

    return String(left.code || '').localeCompare(String(right.code || ''));
  });
}

function buildWatchCandidate(signal: DomainSignal, index: number): WatchDecisionCandidate {
  const reasons = translateReasons(signal.reason_codes || []);
  const reliabilityRaw = String(signal.ev_metrics?.reliability || signal.validation_snapshot?.strategy_reliability || '').toLowerCase();
  const reliabilityLabel = reliabilityToKorean(reliabilityRaw) || '-';
  const strategyLabel = strategyTypeToKorean(signal.strategy_type || '');
  const sizeSummary = explainSizeRecommendation(signal.size_recommendation);
  const liquidity = String(signal.execution_realism?.liquidity_gate_status || '미확인');
  const slippage = signal.execution_realism?.slippage_bps;
  const scoreLabel = formatNumber(signal.score, 1);
  const evLabel = formatNumber(signal.ev_metrics?.expected_value, 2);
  const winRateLabel = formatPercent(signal.ev_metrics?.win_probability, 1, true);
  const primaryReason = reasons[0] || (signal.entry_allowed ? '현재 차단 사유 없음' : '차단 사유 데이터 없음');

  const chips = [
    String(signal.market || '-'),
    strategyLabel,
    scoreLabel !== '-' ? `점수 ${scoreLabel}` : '',
    evLabel !== '-' ? `EV ${evLabel}` : '',
    winRateLabel !== '-' ? `승률 ${winRateLabel}` : '',
    reliabilityLabel !== '-' ? `검증 ${reliabilityLabel}` : '',
  ].filter(Boolean).slice(0, 5);

  const secondaryDetail = signal.entry_allowed
    ? sizeSummary !== '-'
      ? `권장 수량 ${sizeSummary}`
      : `유동성 ${liquidity}${slippage === undefined ? '' : ` · 슬리피지 ${formatNumber(slippage, 2)} bps`}`
    : reasons[1]
      ? `${primaryReason} · ${reasons[1]}`
      : `차단 사유 ${primaryReason}${slippage === undefined ? '' : ` · 슬리피지 ${formatNumber(slippage, 2)} bps`}`;

  return {
    key: `${signal.market || 'market'}:${signal.code || 'signal'}:${index}`,
    symbol: formatSymbol(signal.code, signal.name),
    market: String(signal.market || '-'),
    strategyLabel,
    actionLabel: signal.entry_allowed ? '우선 검토' : '차단 사유 확인',
    actionTone: signal.entry_allowed ? 'good' : 'bad',
    scoreLabel,
    evLabel,
    reliabilityLabel,
    primaryReason,
    secondaryDetail,
    chips,
  };
}

export function buildSignalRows(snapshot: ConsoleSnapshot): SignalTableRow[] {
  const signals = snapshot.signals.signals || [];
  return signals.map((signal) => {
    const reasons = translateReasons(signal.reason_codes || []);
    return {
      signal,
      symbol: formatSymbol(signal.code, signal.name),
      statusLabel: signal.entry_allowed ? '추천' : '차단',
      reasonSummary: signal.entry_allowed ? '-' : (reasons.join(', ') || '-'),
    };
  });
}

function classifyMode(snapshot: ConsoleSnapshot): Pick<WatchDecisionView, 'mode' | 'rationale' | 'stanceTitle' | 'stanceSummary'> {
  const riskLevel = String(snapshot.engine.allocator?.risk_level || snapshot.portfolio.risk_level || '');
  const guardAllowed = Boolean(snapshot.engine.risk_guard_state?.entry_allowed);
  const oosReliabilityRaw = String(snapshot.validation.summary?.oos_reliability || '').toLowerCase();
  const oosReliabilityLabel = reliabilityToKorean(oosReliabilityRaw);
  const signals = snapshot.signals.signals || [];
  const allowedCount = signals.filter((item) => item.entry_allowed).length;
  const allowRatio = signals.length > 0 ? allowedCount / signals.length : 0;

  if (!guardAllowed || riskLevel === '높음' || oosReliabilityRaw === 'low') {
    return {
      mode: '관망',
      stanceTitle: '신규 진입보다 방어 우선',
      stanceSummary: '이 탭은 매수 확정 화면이 아니라 오늘 무엇을 계속 볼지 정리하는 관찰 보드로 쓰는 편이 맞습니다. 차단 사유 해소 전까지는 허용 후보보다 리스크 관리가 먼저입니다.',
      rationale: [
        `리스크 가드 또는 검증 신뢰도(${oosReliabilityLabel}) 조건이 보수 구간입니다.`,
        '신규 진입보다 기존 포지션 방어와 손실 제한을 우선합니다.',
      ],
    };
  }
  if (riskLevel === '중간' || allowRatio < 0.35) {
    return {
      mode: '선별',
      stanceTitle: '허용 후보를 좁게 선별',
      stanceSummary: '관심 시나리오는 많이 보는 탭이 아니라 상위 후보만 추리는 필터 탭으로 보는 편이 낫습니다. 허용 후보와 막힌 후보를 섞지 말고 분리해서 읽으면 됩니다.',
      rationale: [
        '허용 신호 비율이 낮아 상위 EV 신호만 선별 진입합니다.',
        '유동성/리스크 제한 사유가 없는 종목 위주로 좁게 대응합니다.',
      ],
    };
  }
  if (riskLevel === '낮음' && oosReliabilityRaw === 'high' && allowRatio >= 0.6) {
    return {
      mode: '공격',
      stanceTitle: '허용 후보 빠르게 검토 가능',
      stanceSummary: '공격 모드여도 이 화면의 역할은 우선순위 정리입니다. 상위 허용 후보를 먼저 보고, 막힌 후보는 왜 빠졌는지만 짧게 확인하면 충분합니다.',
      rationale: [
        '시장 위험도와 OOS 신뢰도가 양호해 적극 운용 가능한 구간입니다.',
        '단, 일일 손실 한도와 섹터 익스포저 캡은 동일하게 준수합니다.',
      ],
    };
  }
  return {
    mode: '축소',
    stanceTitle: '포지션 크기 보수적으로 유지',
    stanceSummary: '완전 관망은 아니지만 확대 근거도 강하지 않습니다. 허용 후보는 검토하되, 수량과 유동성 조건이 맞는 종목만 남기는 용도로 보면 됩니다.',
    rationale: [
      '중립 구간으로 포지션 크기를 보수적으로 조절합니다.',
      '신규 진입은 EV 우위가 뚜렷한 신호에 제한합니다.',
    ],
  };
}

export function buildTodayReportView(snapshot: ConsoleSnapshot): TodayReportView {
  const rawBriefLines = [
    ...(snapshot.reports.summary_lines || []),
    ...(snapshot.reports.brief?.summary_lines || []),
    ...(snapshot.reports.analysis?.summary_lines || []),
  ];
  const analysisLines = rawBriefLines
    .map((line) => line.trim())
    .filter(Boolean);
  const reportGeneratedAt = snapshot.reports.brief?.generated_at || snapshot.reports.generated_at;
  const hasReportContent = analysisLines.length > 0 || Boolean(reportGeneratedAt);
  const summaryFallback = [
    '거시/수급 지표 변화를 기준으로 시장 위험도를 점검합니다.',
    '리스크 가드 상태와 허용 신호 비율을 함께 확인합니다.',
    '후보는 Layer B quant를 기준으로 보고, Layer C research는 보조 판단과 경고 코드로만 해석합니다.',
  ];
  const summaryLines = dedupeKeepOrder([...analysisLines, ...summaryFallback]).slice(0, 5);

  const guardReasons = translateReasons(snapshot.engine.risk_guard_state?.reasons || []);
  const blockedReasons = translateReasons(
    (snapshot.signals.signals || []).flatMap((signal) => signal.entry_allowed ? [] : (signal.reason_codes || [])),
  );
  const allocator = snapshot.engine.allocator || {};
  const running = Boolean(snapshot.engine.execution?.state?.running);
  const guardAllowed = Boolean(snapshot.engine.risk_guard_state?.entry_allowed);
  const allowedCount = Number(allocator.entry_allowed_count || 0);
  const blockedCount = Number(allocator.blocked_count || 0);
  const decision = classifyMode(snapshot);

  const watchPoints = dedupeKeepOrder([
    ...guardReasons,
    ...blockedReasons,
    '장초/이벤트 구간에서는 체결 슬리피지 확대 가능성에 유의합니다.',
    '연속 손실 구간에서는 신규 진입보다 기존 포지션 방어를 우선합니다.',
    '유동성 정보가 부족한 신호는 자동으로 제외될 수 있습니다.',
  ]).slice(0, 5);

  const judgmentLines = dedupeKeepOrder([
    ...decision.rationale,
    guardAllowed
      ? `현재 신규 진입은 가능합니다. 신호 화면에서 허용 ${formatCount(allowedCount, '건')}을 우선 확인하세요.`
      : '현재 신규 진입은 제한됩니다. 리스크 가드 사유를 먼저 해소하거나 관망 비중을 유지하세요.',
    blockedCount > 0
      ? `차단 신호 ${formatCount(blockedCount, '건')}은 사유를 확인한 뒤 제외 대상으로 유지합니다.`
      : '현재 차단 신호가 많지 않아 허용 신호 중심으로 판단해도 됩니다.',
  ]).slice(0, 3);

  const actionItems: TodayReportView['actionItems'] = [
    {
      label: '오늘 해야 할 일',
      detail: guardAllowed && allowedCount > 0
        ? `허용 신호 ${formatCount(allowedCount, '건')}을 신호 화면에서 우선 점검하세요.`
        : '신규 진입보다 기존 포지션과 리스크 가드 상태를 먼저 점검하세요.',
      tone: guardAllowed && allowedCount > 0 ? 'good' : 'bad',
    },
    {
      label: '주의할 점',
      detail: guardReasons[0] || blockedReasons[0] || '차단 사유가 없더라도 손실 한도와 익스포저 캡은 그대로 유지합니다.',
      tone: guardReasons.length > 0 || blockedReasons.length > 0 ? 'bad' : 'neutral',
    },
    {
      label: '확인 기준',
      detail: `리포트 생성 시각 ${formatDateTime(reportGeneratedAt || snapshot.fetchedAt)} / 데이터 기준 시각 ${formatDateTime(snapshot.fetchedAt)}`,
      tone: 'neutral',
    },
  ];

  return {
    generatedAt: reportGeneratedAt || snapshot.fetchedAt,
    dataAsOf: snapshot.fetchedAt,
    statusItems: [
      {
        label: '엔진 상태',
        value: running ? '실행 중' : '중지',
        tone: running ? 'good' : 'bad',
      },
      {
        label: '신규 진입 가능',
        value: guardAllowed ? '가능' : '제한',
        tone: guardAllowed ? 'good' : 'bad',
      },
      {
        label: '장세 / 위험도',
        value: `${allocator.regime || snapshot.signals.regime || '-'} / ${allocator.risk_level || snapshot.signals.risk_level || '-'}`,
        tone: 'neutral',
      },
      {
        label: '허용 / 차단 신호',
        value: `${formatCount(allowedCount, '건')} / ${formatCount(blockedCount, '건')}`,
        tone: 'neutral',
      },
    ],
    summaryLines,
    judgmentTitle: decision.mode,
    judgmentLines,
    actionItems,
    watchPoints,
    hasReportContent,
  };
}

export function buildWatchDecisionView(snapshot: ConsoleSnapshot): WatchDecisionView {
  const signals = snapshot.signals.signals || [];
  const decision = classifyMode(snapshot);
  const allowedSignals = sortSignalsForWatch(signals.filter((signal) => signal.entry_allowed));
  const blockedSignals = sortSignalsForWatch(signals.filter((signal) => !signal.entry_allowed));
  const repeatedBlockedReasons = dedupeKeepOrder(
    blockedSignals.flatMap((signal) => translateReasons(signal.reason_codes || [])),
  ).slice(0, 3);

  const focusCandidates = allowedSignals.slice(0, 3).map((signal, index) => buildWatchCandidate(signal, index));
  const blockedCandidates = blockedSignals.slice(0, 3).map((signal, index) => buildWatchCandidate(signal, index));

  const researchQueue = dedupeKeepOrder([
    ...decision.rationale,
    focusCandidates[0]
      ? `${focusCandidates[0].symbol} 등 허용 후보는 EV·승률·권장 수량이 같이 버티는지부터 확인합니다.`
      : '현재 허용 후보가 적어 관심 시나리오는 관찰/보류 중심으로 읽는 편이 안전합니다.',
    blockedCandidates[0]
      ? `${blockedCandidates[0].symbol} 등 막힌 후보는 ${blockedCandidates[0].primaryReason} 해소 전까지 관찰 전용으로 둡니다.`
      : '강하게 막힌 후보가 적어 오늘은 허용 후보 우선순위 정리에 집중하면 됩니다.',
    repeatedBlockedReasons.length > 0
      ? `반복 차단 사유: ${repeatedBlockedReasons.join(' · ')}`
      : '',
  ]).slice(0, 5);

  return {
    ...decision,
    allowedCount: allowedSignals.length,
    blockedCount: blockedSignals.length,
    focusCandidates,
    blockedCandidates,
    researchQueue,
  };
}
