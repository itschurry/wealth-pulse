import { UI_TEXT } from '../constants/uiText';
import { COMPANY_CATALOG } from '../data/companyCatalog';

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

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return `${KST_DATE_TIME_FMT.format(date).replace(',', '')} KST`;
}

export function formatCount(value: number | string | null | undefined, unit: string): string {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return `- ${unit}`;
  return `${formatNumber(numeric, 0)}${unit}`;
}

function resolveSymbolName(code?: string, payloadName?: string): string {
  const normalizedCode = String(code || '').toUpperCase().trim();
  const normalizedPayloadName = String(payloadName || '').trim();
  if (normalizedPayloadName) return normalizedPayloadName;
  if (!normalizedCode) return '';
  const mapped = NAME_BY_CODE.get(normalizedCode);
  if (mapped) return mapped;
  if (!WARNED_SYMBOL_CODES.has(normalizedCode)) {
    WARNED_SYMBOL_CODES.add(normalizedCode);
    console.warn(UI_TEXT.errors.symbolNameMissing, { code: normalizedCode });
  }
  return '';
}

export function formatSymbol(code?: string, name?: string): string {
  const normalizedCode = String(code || '').toUpperCase().trim();
  const resolvedName = resolveSymbolName(normalizedCode, name);
  if (normalizedCode && resolvedName) return `${normalizedCode} ${resolvedName}`;
  if (normalizedCode) return normalizedCode;
  if (resolvedName) return resolvedName;
  return '-';
}
