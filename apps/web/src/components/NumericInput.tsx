import { useCallback, useEffect, useState } from 'react';
import type { CSSProperties } from 'react';
import { formatKRW, formatNumber, formatUSD } from '../utils/format';

export interface NumericInputProps {
  value: number | null | undefined;
  onCommit: (value: number | null) => void;
  min?: number;
  max?: number;
  step?: number;
  allowNull?: boolean;
  decimals?: number;
  currency?: 'KRW' | 'USD' | null;
  className?: string;
  style?: CSSProperties;
}

function formatNumericDisplay(
  value: number | null | undefined,
  options?: { decimals?: number; currency?: 'KRW' | 'USD' | null },
) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '';
  if (options?.currency === 'USD') return formatUSD(value, false);
  if (options?.currency === 'KRW') return formatKRW(value, false);
  return formatNumber(value, options?.decimals ?? 0);
}

function formatEditingValue(value: number | null | undefined, decimals = 0) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '';
  if (decimals <= 0) return String(Math.round(value));
  return String(value);
}

export function NumericInput({
  value,
  onCommit,
  min,
  max,
  step,
  allowNull = false,
  decimals = 0,
  currency = null,
  className = 'backtest-input-wrap',
  style,
}: NumericInputProps) {
  const [focused, setFocused] = useState(false);
  const [draft, setDraft] = useState('');

  useEffect(() => {
    if (!focused) {
      setDraft(formatEditingValue(value, decimals));
    }
  }, [decimals, focused, value]);

  const commitCurrent = useCallback(() => {
    const raw = draft.replace(/,/g, '').trim();
    setFocused(false);
    if (!raw) {
      if (allowNull) {
        onCommit(null);
        setDraft('');
      } else {
        setDraft(formatEditingValue(value, decimals));
      }
      return;
    }

    const parsed = Number(raw);
    if (!Number.isFinite(parsed)) {
      setDraft(formatEditingValue(value, decimals));
      return;
    }

    let nextValue = decimals <= 0 ? Math.round(parsed) : parsed;
    if (typeof min === 'number') nextValue = Math.max(min, nextValue);
    if (typeof max === 'number') nextValue = Math.min(max, nextValue);
    onCommit(nextValue);
    setDraft(formatEditingValue(nextValue, decimals));
  }, [allowNull, decimals, draft, max, min, onCommit, value]);

  return (
    <input
      className={className}
      style={style}
      type="text"
      inputMode={decimals > 0 ? 'decimal' : 'numeric'}
      value={focused ? draft : formatNumericDisplay(value, { decimals, currency })}
      onFocus={() => {
        setFocused(true);
        setDraft(formatEditingValue(value, decimals));
      }}
      onChange={(event) => {
        const raw = event.target.value.replace(/,/g, '');
        if (raw === '' || /^-?\d*(\.\d*)?$/.test(raw)) {
          setDraft(raw);
        }
      }}
      onBlur={commitCurrent}
      onKeyDown={(event) => {
        if (event.key === 'Enter') {
          event.currentTarget.blur();
        }
      }}
      data-step={step ?? undefined}
    />
  );
}
