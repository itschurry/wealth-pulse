import { renderTextWithLinks } from '../utils/linkify';

interface Props {
  summaryLines: string[];
  generatedAt?: string;
  onRefresh: () => void;
}

const OFF_SESSION_HOURS = [6, 9, 12, 15, 18, 21];

function getZonedTimeParts(timeZone: string, now: Date) {
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
    hour,
    minute,
    minutes: hour * 60 + minute,
  };
}

function isWeekday(weekday: string) {
  return weekday !== 'Sat' && weekday !== 'Sun';
}

function isKoreaSessionSlot(now: Date) {
  const zoned = getZonedTimeParts('Asia/Seoul', now);
  return isWeekday(zoned.weekday) && zoned.minutes >= 9 * 60 && zoned.minutes <= 15 * 60 + 30 && (zoned.minutes - 9 * 60) % 30 === 0;
}

function isUsSessionSlot(now: Date) {
  const zoned = getZonedTimeParts('America/New_York', now);
  return isWeekday(zoned.weekday) && zoned.minutes >= 9 * 60 + 30 && zoned.minutes <= 16 * 60 && (zoned.minutes - (9 * 60 + 30)) % 30 === 0;
}

function isOffSessionSlot(now: Date) {
  const zoned = getZonedTimeParts('Asia/Seoul', now);
  return zoned.minute === 0 && OFF_SESSION_HOURS.includes(zoned.hour);
}

function isReportScheduleSlot(now: Date) {
  return isOffSessionSlot(now) || isKoreaSessionSlot(now) || isUsSessionSlot(now);
}

function getNextScheduleLabel(now = new Date()) {
  const next = new Date(now);
  next.setSeconds(0, 0);
  next.setMinutes(next.getMinutes() + 1);

  for (let i = 0; i < 60 * 24 * 8; i += 1) {
    if (isReportScheduleSlot(next)) {
      return next.toLocaleString('ko-KR', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      });
    }
    next.setMinutes(next.getMinutes() + 1);
  }

  return '계산 중';
}

export function SummaryBar({ summaryLines, generatedAt, onRefresh }: Props) {
  const lines = summaryLines.length > 0
    ? summaryLines
    : ['핵심 요약을 준비하는 중입니다.', '시장 신호를 모으는 중입니다.', '리포트 본문이 곧 정리됩니다.'];

  return (
    <div className="summary-shell">
      <div className="summary-head">
        <div>
          <div className="summary-title">Opening Brief</div>
          <div className="summary-meta">
            리포트 생성 {generatedAt || '데이터 없음'} · 다음 자동 생성 {getNextScheduleLabel()}
          </div>
        </div>
        <button className="ghost-button" onClick={onRefresh} title="최신 리포트 다시 불러오기">
          최신 리포트 불러오기
        </button>
      </div>

      <div className="summary-grid">
        {lines.slice(0, 3).map((line, i) => (
          <div key={i} className={`summary-card ${i === 0 ? 'primary' : ''}`}>
            <div className="summary-card-topline">
              <span className="summary-index">{i + 1}</span>
              <span className="summary-step-label">{i === 0 ? '시장 요지' : i === 1 ? '핵심 이슈' : '행동 포인트'}</span>
            </div>
            <div className="summary-copy">{renderTextWithLinks(line)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
