import { formatSymbol, resolveSymbolName } from '../utils/format';

interface SymbolIdentityProps {
  code?: string;
  name?: string;
  market?: string;
  align?: 'left' | 'right';
  compact?: boolean;
}

export function SymbolIdentity({ code, name, market, align = 'left', compact = false }: SymbolIdentityProps) {
  const normalizedCode = String(code || '').trim().toUpperCase();
  const resolvedName = resolveSymbolName(normalizedCode, name);
  const marketLabel = String(market || '').trim().toUpperCase();
  const wrapperClass = `symbol-identity ${align === 'right' ? 'is-right' : ''} ${compact ? 'is-compact' : ''}`.trim();

  return (
    <div className={wrapperClass}>
      <div className="symbol-identity-name">{resolvedName || normalizedCode || '-'}</div>
      <div className="symbol-identity-meta">{formatSymbol(normalizedCode, resolvedName)}{marketLabel ? ` · ${marketLabel}` : ''}</div>
    </div>
  );
}
