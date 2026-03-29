import type { ReactNode } from 'react';

const URL_PATTERN = /(https?:\/\/[^\s<>()]+[^\s<>().,;:!?"'])/g;

export function formatLinkLabel(url: string): string {
  try {
    const { hostname } = new URL(url);
    const normalized = hostname.replace(/^www\./i, '').trim();
    return normalized || '링크 열기';
  } catch {
    return '링크 열기';
  }
}

export function renderTextWithLinks(text: string): ReactNode[] {
  if (!text) return [text];

  const parts = text.split(URL_PATTERN);
  return parts.filter(Boolean).map((part, index) => {
    if (!part.match(URL_PATTERN)) {
      return part;
    }

    return (
      <a
        className="inline-link"
        key={`${part}-${index}`}
        href={part}
        target="_blank"
        rel="noreferrer"
      >
        {formatLinkLabel(part)}
      </a>
    );
  });
}
