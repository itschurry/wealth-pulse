import { reasonCodeToKorean, reliabilityToKorean } from '../constants/uiText';
import { formatCount, formatDateTime, formatSymbol } from '../utils/format';
import type {
  ActionBoardView,
  ConsoleSnapshot,
  SignalTableRow,
  TodayReportView,
  WatchDecisionView,
} from '../types/consoleView';

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

function classifyMode(snapshot: ConsoleSnapshot): WatchDecisionView {
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
      rationale: [
        `리스크 가드 또는 검증 신뢰도(${oosReliabilityLabel}) 조건이 보수 구간입니다.`,
        '신규 진입보다 기존 포지션 방어와 손실 제한을 우선합니다.',
      ],
    };
  }
  if (riskLevel === '중간' || allowRatio < 0.35) {
    return {
      mode: '선별',
      rationale: [
        '허용 신호 비율이 낮아 상위 EV 신호만 선별 진입합니다.',
        '유동성/리스크 제한 사유가 없는 종목 위주로 좁게 대응합니다.',
      ],
    };
  }
  if (riskLevel === '낮음' && oosReliabilityRaw === 'high' && allowRatio >= 0.6) {
    return {
      mode: '공격',
      rationale: [
        '시장 위험도와 OOS 신뢰도가 양호해 적극 운용 가능한 구간입니다.',
        '단, 일일 손실 한도와 섹터 익스포저 캡은 동일하게 준수합니다.',
      ],
    };
  }
  return {
    mode: '축소',
    rationale: [
      '중립 구간으로 포지션 크기를 보수적으로 조절합니다.',
      '신규 진입은 EV 우위가 뚜렷한 신호에 제한합니다.',
    ],
  };
}

export function buildTodayReportView(snapshot: ConsoleSnapshot): TodayReportView {
  const analysisLines = (snapshot.reports.analysis?.summary_lines || [])
    .map((line) => line.trim())
    .filter(Boolean);
  const hasReportContent = analysisLines.length > 0 || Boolean(snapshot.reports.generated_at);
  const summaryFallback = [
    '거시/수급 지표 변화를 기준으로 시장 위험도를 점검합니다.',
    '리스크 가드 상태와 허용 신호 비율을 함께 확인합니다.',
    '신규 진입은 EV와 유동성 조건을 동시에 충족한 종목만 고려합니다.',
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
      detail: `리포트 생성 시각 ${formatDateTime(snapshot.reports.generated_at || snapshot.fetchedAt)} / 데이터 기준 시각 ${formatDateTime(snapshot.fetchedAt)}`,
      tone: 'neutral',
    },
  ];

  return {
    generatedAt: snapshot.reports.generated_at || snapshot.fetchedAt,
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

export function buildActionBoardView(snapshot: ConsoleSnapshot): ActionBoardView {
  const watch = classifyMode(snapshot);
  const guardAllowed = Boolean(snapshot.engine.risk_guard_state?.entry_allowed);
  const oosReliabilityRaw = String(snapshot.validation.summary?.oos_reliability || '').toLowerCase();
  const oosReliability = reliabilityToKorean(oosReliabilityRaw);
  const entryAllowedCount = Number(snapshot.engine.allocator?.entry_allowed_count || 0);
  const blockedCount = Number(snapshot.engine.allocator?.blocked_count || 0);

  return {
    rules: [
      `오늘 전략 포인트: ${watch.mode}`,
      '손절/손실 한도 규칙을 우선 적용합니다.',
      '차단 사유가 없는 신호만 진입 후보로 사용합니다.',
    ],
    checklist: [
      {
        label: '리스크 가드 상태 확인',
        done: guardAllowed,
        detail: guardAllowed ? '신규 진입 가능 상태입니다.' : '리스크 가드로 신규 진입이 제한됩니다.',
      },
      {
        label: 'OOS 신뢰도 확인',
        done: oosReliabilityRaw !== 'low',
        detail: oosReliability ? `현재 OOS 신뢰도: ${oosReliability}` : 'OOS 신뢰도 데이터가 없습니다.',
      },
      {
        label: '신규 진입 허용 여부 확인',
        done: entryAllowedCount > 0,
        detail: `허용 ${formatCount(entryAllowedCount, '건')} / 차단 ${formatCount(blockedCount, '건')}`,
      },
      {
        label: '차단 사유 점검',
        done: blockedCount === 0,
        detail: blockedCount === 0 ? '차단 신호가 없습니다.' : '차단 사유를 확인하고 진입 제외 대상을 정리하세요.',
      },
    ],
  };
}

export function buildWatchDecisionView(snapshot: ConsoleSnapshot): WatchDecisionView {
  return classifyMode(snapshot);
}
