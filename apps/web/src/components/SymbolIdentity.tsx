import { useEffect, useState } from 'react';
import { resolveSymbolName } from '../utils/format';

interface SymbolIdentityProps {
  code?: string;
  name?: string;
  market?: string;
  align?: 'left' | 'right';
  compact?: boolean;
}

const REMOTE_NAME_CACHE = new Map<string, string>();

function cacheKey(code: string, market: string): string {
  return `${market || 'ANY'}:${code}`;
}

export function SymbolIdentity({ code, name, market, align = 'left', compact = false }: SymbolIdentityProps) {
  const normalizedCode = String(code || '').trim().toUpperCase();
  const marketLabel = String(market || '').trim().toUpperCase();
  const key = cacheKey(normalizedCode, marketLabel);
  const [remoteName, setRemoteName] = useState(() => REMOTE_NAME_CACHE.get(key) || '');
  const resolvedName = resolveSymbolName(normalizedCode, name || remoteName);
  const hasResolvedName = Boolean(resolvedName) && resolvedName.toUpperCase() !== normalizedCode;
  const wrapperClass = `symbol-identity ${align === 'right' ? 'is-right' : ''} ${compact ? 'is-compact' : ''}`.trim();
  const primaryLabel = hasResolvedName ? resolvedName : (normalizedCode || '-');
  const secondaryCodeLabel = normalizedCode;
  const secondaryMeta = hasResolvedName
    ? `${secondaryCodeLabel}${marketLabel ? ` · ${marketLabel}` : ''}`
    : (marketLabel || '-');

  useEffect(() => {
    if (!normalizedCode || hasResolvedName) return;
    const currentKey = cacheKey(normalizedCode, marketLabel);
    const cached = REMOTE_NAME_CACHE.get(currentKey);
    if (cached) {
      setRemoteName(cached);
      return;
    }
    const query = marketLabel ? `?market=${encodeURIComponent(marketLabel)}` : '';
    fetch(`/api/stock/${encodeURIComponent(normalizedCode)}${query}`, { cache: 'no-store' })
      .then((response) => (response.ok ? response.json() : null))
      .then((payload) => {
        const fetchedName = String(payload?.name || '').trim();
        if (fetchedName && fetchedName.toUpperCase() !== normalizedCode) {
          REMOTE_NAME_CACHE.set(currentKey, fetchedName);
          setRemoteName(fetchedName);
        }
      })
      .catch(() => undefined)
  }, [hasResolvedName, marketLabel, normalizedCode]);

  return (
    <div className={wrapperClass}>
      <div className="symbol-identity-name">{primaryLabel}</div>
      <div className="symbol-identity-meta">{secondaryMeta}</div>
    </div>
  );
}
