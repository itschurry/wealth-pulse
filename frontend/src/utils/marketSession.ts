export type MarketBucket = 'domestic' | 'us' | 'other';
export type SessionTone = 'live' | 'idle';

interface MarketSessionWindow {
  key: 'domestic' | 'us';
  label: string;
  marketsLabel: string;
  timeZone: string;
  openMinutes: number;
  closeMinutes: number;
  scheduleLabel: string;
}

export interface MarketSessionInfo {
  key: 'domestic' | 'us';
  label: string;
  marketsLabel: string;
  scheduleLabel: string;
  statusLabel: string;
  isOpen: boolean;
  tone: SessionTone;
}

const SESSION_WINDOWS: MarketSessionWindow[] = [
  {
    key: 'domestic',
    label: '국내장',
    marketsLabel: 'KOSPI · KOSDAQ',
    timeZone: 'Asia/Seoul',
    openMinutes: 9 * 60,
    closeMinutes: 15 * 60 + 30,
    scheduleLabel: 'KST 09:00-15:30',
  },
  {
    key: 'us',
    label: '미국장',
    marketsLabel: 'NASDAQ · NYSE',
    timeZone: 'America/New_York',
    openMinutes: 9 * 60 + 30,
    closeMinutes: 16 * 60,
    scheduleLabel: 'ET 09:30-16:00',
  },
];

function getZonedTimeParts(timeZone: string, now = new Date()) {
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone,
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });

  const parts = formatter.formatToParts(now);
  const weekday = parts.find((part) => part.type === 'weekday')?.value || 'Mon';
  const hour = Number(parts.find((part) => part.type === 'hour')?.value || 0);
  const minute = Number(parts.find((part) => part.type === 'minute')?.value || 0);

  return {
    weekday,
    minutes: hour * 60 + minute,
  };
}

function getSessionStatus(window: MarketSessionWindow, now = new Date()) {
  const zoned = getZonedTimeParts(window.timeZone, now);
  const isWeekend = zoned.weekday === 'Sat' || zoned.weekday === 'Sun';

  if (isWeekend) {
    return { statusLabel: '휴장', isOpen: false, tone: 'idle' as const };
  }

  if (zoned.minutes < window.openMinutes) {
    return { statusLabel: '개장 전', isOpen: false, tone: 'idle' as const };
  }

  if (zoned.minutes < window.closeMinutes) {
    return { statusLabel: '정규장 진행 중', isOpen: true, tone: 'live' as const };
  }

  return { statusLabel: '장 마감', isOpen: false, tone: 'idle' as const };
}

export function getMarketBucket(market?: string): MarketBucket {
  const normalized = (market || '').trim().toUpperCase();

  if (['KOSPI', 'KOSDAQ', 'KONEX', 'KRX'].includes(normalized)) {
    return 'domestic';
  }

  if (['NASDAQ', 'NYSE', 'AMEX', 'US', 'USA'].includes(normalized)) {
    return 'us';
  }

  return 'other';
}

export function getMarketSessions(now = new Date()): Record<'domestic' | 'us', MarketSessionInfo> {
  return SESSION_WINDOWS.reduce((acc, window) => {
    const status = getSessionStatus(window, now);
    acc[window.key] = {
      key: window.key,
      label: window.label,
      marketsLabel: window.marketsLabel,
      scheduleLabel: window.scheduleLabel,
      statusLabel: status.statusLabel,
      isOpen: status.isOpen,
      tone: status.tone,
    };
    return acc;
  }, {} as Record<'domestic' | 'us', MarketSessionInfo>);
}

export function getPreferredMarketOrder(now = new Date()): MarketBucket[] {
  const sessions = getMarketSessions(now);

  if (sessions.domestic.isOpen) {
    return ['domestic', 'us', 'other'];
  }

  if (sessions.us.isOpen) {
    return ['us', 'domestic', 'other'];
  }

  return ['domestic', 'us', 'other'];
}

export function getMarketSectionLabel(bucket: MarketBucket) {
  if (bucket === 'domestic') return '국내장';
  if (bucket === 'us') return '미국장';
  return '기타 종목';
}

export function getMarketSectionCaption(bucket: MarketBucket) {
  if (bucket === 'domestic') return 'KOSPI · KOSDAQ';
  if (bucket === 'us') return 'NASDAQ · NYSE';
  return '기타 시장';
}
