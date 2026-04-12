import { UI_TEXT } from '../constants/uiText';
import { COMPANY_CATALOG } from '../data/companyCatalog';
import type { SizeRecommendation } from '../types/domain';

const KRW_DECIMAL_FMT = new Intl.NumberFormat('ko-KR', {
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

const USD_DECIMAL_FMT = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const KST_DATE_TIME_FMT = new Intl.DateTimeFormat('sv-SE', {
  timeZone: 'Asia/Seoul',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
});

const NAME_BY_CODE = new Map<string, string>();
for (const entry of COMPANY_CATALOG) {
  if (!entry.code) continue;
  NAME_BY_CODE.set(entry.code.toUpperCase(), entry.name);
}

const WARNED_SYMBOL_CODES = new Set<string>();

export function formatNumber(value: number | string | null | undefined, decimals = 0): string {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return '-';
  return numeric.toLocaleString('ko-KR', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function formatPercent(value: number | null | undefined, decimals = 2, ratio = false): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '-';
  const pctValue = ratio ? value * 100 : value;
  return `${formatNumber(pctValue, decimals)}%`;
}

export function formatKRW(value: number | null | undefined, withSuffix = false): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '-';
  const body = KRW_DECIMAL_FMT.format(value);
  return withSuffix ? `${body}원` : body;
}

export function formatUSD(value: number | null | undefined, withPrefix = false): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '-';
  const body = USD_DECIMAL_FMT.format(value);
  return withPrefix ? `$${body}` : body;
}

export function formatUSDWithKRW(usdValue: number | null | undefined, krwValue: number | null | undefined): string {
  const usdText = formatUSD(usdValue, true);
  const krwText = formatKRW(krwValue, true);
  if (usdText === '-') return krwText;
  if (krwText === '-') return usdText;
  return `${usdText} (${krwText})`;
}

export function formatLocalAmountWithKRW(
  localValue: number | null | undefined,
  krwValue: number | null | undefined,
  currency: 'KRW' | 'USD',
): string {
  if (currency === 'USD') return formatUSDWithKRW(localValue, krwValue);
  return formatKRW(krwValue ?? localValue, true);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return `${KST_DATE_TIME_FMT.format(date).replace(',', '')} KST`;
}

export function formatRelativeAge(value: string | null | undefined): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';

  const diffMs = Date.now() - date.getTime();
  const isFuture = diffMs < 0;
  const absMs = Math.abs(diffMs);
  const absSeconds = Math.round(absMs / 1000);

  if (absSeconds < 45) return isFuture ? '곧' : '방금';
  if (absSeconds < 3600) {
    const minutes = Math.round(absSeconds / 60);
    return `${minutes}분 ${isFuture ? '후' : '전'}`;
  }
  if (absSeconds < 86400) {
    const hours = Math.round(absSeconds / 3600);
    return `${hours}시간 ${isFuture ? '후' : '전'}`;
  }
  const days = Math.round(absSeconds / 86400);
  return `${days}일 ${isFuture ? '후' : '전'}`;
}

export function formatDateTimeWithAge(value: string | null | undefined): string {
  const formatted = formatDateTime(value);
  const age = formatRelativeAge(value);
  if (formatted === '-') return '-';
  if (age === '-') return formatted;
  return `${formatted} · ${age}`;
}

export function formatCount(value: number | string | null | undefined, unit: string): string {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return `- ${unit}`;
  return `${formatNumber(numeric, 0)}${unit}`;
}

export function resolveSymbolName(code?: string, payloadName?: string): string {
  const normalizedCode = String(code || '').toUpperCase().trim();
  const normalizedPayloadName = String(payloadName || '').trim();
  if (normalizedPayloadName && normalizedPayloadName.toUpperCase() !== normalizedCode) return normalizedPayloadName;
  if (!normalizedCode) return normalizedPayloadName;
  const mapped = NAME_BY_CODE.get(normalizedCode);
  if (mapped) return mapped;
  if (normalizedPayloadName) return normalizedPayloadName;
  if (!WARNED_SYMBOL_CODES.has(normalizedCode)) {
    WARNED_SYMBOL_CODES.add(normalizedCode);
    console.warn(UI_TEXT.errors.symbolNameMissing, { code: normalizedCode });
  }
  return '';
}

export function formatSymbolLabel(code?: string, name?: string, separator = ' · '): string {
  const normalizedCode = String(code || '').toUpperCase().trim();
  const resolvedName = resolveSymbolName(normalizedCode, name);
  if (normalizedCode && resolvedName) return `${normalizedCode}${separator}${resolvedName}`;
  if (normalizedCode) return normalizedCode;
  if (resolvedName) return resolvedName;
  return '-';
}

export function formatSymbol(code?: string, name?: string): string {
  return formatSymbolLabel(code, name, ' ');
}

export function explainOrderFailureReason(reason: string | null | undefined): string {
  const normalized = String(reason || '').trim();
  if (!normalized) return '-';

  const normalizedUpper = normalized.toUpperCase();
  const normalizedLower = normalized.toLowerCase();

  const reasonGuide: Record<string, string> = {
    quote_stale: '시세가 오래돼 주문을 막았습니다. 가격 갱신 후 자동 재시도합니다.',
    liquidity_guard_blocked: '유동성 가드에서 주문을 막았습니다. 유동성/스프레드 조건이 완화되어야 합니다.',
    BUY_FAILED: '매수 주문 처리 중 브로커/엔진 단계 오류입니다. 잔액/유동성/호가를 다시 확인하세요.',
    SELL_FAILED: '매도 주문 처리 중 브로커/엔진 단계 오류입니다. 잔액/호가/포지션 상태를 다시 확인하세요.',
    insufficient_cash: '현금이 부족해 주문 수량이 부족합니다. 진입 수량을 낮추거나 현금 기반 한도를 확인하세요.',
    account_unavailable: '계좌 스냅샷이 비어 있어 주문 경로 추적이 제한됩니다. 계좌 조회를 새로고침하세요.',
    liquidity_unknown: '유동성 정보가 없어 주문이 보류되었습니다. 시장 데이터 수신 시 재평가가 필요합니다.',
    daily_loss_limit_reached: '일일 손실 한도가 도달해 신규 진입이 차단되었습니다.',
    LOSS_STREAK_COOLDOWN: '연속 손실 쿨다운 구간입니다. 일정 시간 이후 자동 해제됩니다.',
    MAX_POSITIONS_REACHED: '시장별 최대 포지션 수에 도달해 신규 진입을 차단했습니다.',
    POSITION_SIZE_LIMIT_EXCEEDED: '수량 계산 한도로 추천 수량이 0이 되어 주문하지 않습니다.',
    SIZE_LIMIT_REACHED: '수량 계산 한도로 인해 주문을 하지 못했습니다.',
    size_zero: '권장 수량이 0주로 계산되었습니다.',
    max_positions_reached: '시장 최대 보유 수 한도에 따라 주문이 보류됩니다.',
    duplicate_position: '동일 종목 중복 진입 시도는 차단됩니다.',
    market_closed: '시장 휴장/장마감 상태입니다.',
    risk_veto: '리스크 가드에서 주문을 차단했습니다.',
    risk_guard_blocked: '리스크 가드에서 주문을 차단했습니다.',
    RISK_GUARD_BLOCKED: '리스크 가드에서 주문을 차단했습니다.',
    screened: '리스크/평가 단계에서 선별되지 않아 주문이 전송되지 않았습니다.',
    invalid_unit_price: '현재가 계산값이 유효하지 않아 주문을 생성하지 못했습니다.',
    liqidity_too_low: '유동성 부족으로 주문 판단을 보류했습니다.',
    spread_too_wide: '호가 스프레드가 크고 체결 안정성이 낮아 주문을 보류했습니다.',
  };

  if (reasonGuide[normalized]) return reasonGuide[normalized];
  if (reasonGuide[normalizedLower]) return reasonGuide[normalizedLower];
  if (reasonGuide[normalizedUpper]) return reasonGuide[normalizedUpper];

  if (normalizedLower.startsWith('technicals_error')) {
    return '기술 지표 수집/분석 오류로 판단이 중단되었습니다.';
  }

  if (normalized === 'quote_stale') return '시세가 오래돼 주문을 막았습니다.';
  if (normalized === 'liquidity_guard_blocked') return '유동성 가드가 주문을 차단했습니다.';
  if (normalized === 'buy_failed') return '매수 주문 처리에 실패했습니다.';
  if (normalized === 'sell_failed') return '매도 주문 처리에 실패했습니다.';
  if (normalized.includes('현금이 부족')) return `${normalized} · 동일 조건 반복 시 자동 재시도보다 수량/예산 조정이 먼저입니다.`;
  return normalized;
}

export function explainSizeRecommendation(sizeRecommendation: SizeRecommendation | null | undefined): string {
  if (!sizeRecommendation) return '-';
  const quantity = Number(sizeRecommendation.quantity || 0);
  if (quantity > 0) {
    const parts = [formatCount(quantity, '주')];
    if (Number.isFinite(Number(sizeRecommendation.risk_budget_krw))) {
      parts.push(`리스크 예산 ${formatKRW(Number(sizeRecommendation.risk_budget_krw), true)}`);
    }
    return parts.join(' · ');
  }

  const reason = String(sizeRecommendation.reason || '').trim();
  if (reason === 'account_unavailable') return '계좌 스냅샷이 없어 수량 계산을 못했습니다.';
  if (reason === 'invalid_unit_price') return '현재가가 유효하지 않아 수량 계산을 중단했습니다.';
  if (reason === 'exposure_or_cash_limit') {
    const blockers: string[] = [];
    if (Number(sizeRecommendation.qty_by_cash ?? -1) === 0) blockers.push('현금 기준 0주');
    if (Number(sizeRecommendation.qty_by_caps ?? -1) === 0) blockers.push('노출 한도 기준 0주');
    if (Number(sizeRecommendation.qty_by_risk ?? -1) === 0) blockers.push('리스크 예산 기준 0주');
    return blockers.length > 0 ? blockers.join(' · ') : '현금 또는 노출 한도 때문에 0주입니다.';
  }
  if (reason === 'size_zero') return '권장 수량이 0주로 계산됐습니다.';
  return reason || '권장 수량을 계산하지 못했습니다.';
}
