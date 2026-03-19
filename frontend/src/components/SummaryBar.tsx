interface Props {
  summaryLines: string[];
  generatedAt?: string;
  onRefresh: () => void;
}

function getNextScheduleLabel(now = new Date()) {
  const slots = [6, 9, 12, 15, 18, 21];
  const next = new Date(now);
  next.setSeconds(0, 0);

  const currentHour = now.getHours();
  const currentMinute = now.getMinutes();
  const targetHour = slots.find((hour) => hour > currentHour || (hour === currentHour && currentMinute === 0));

  if (targetHour !== undefined) {
    next.setHours(targetHour, 0, 0, 0);
  } else {
    next.setDate(next.getDate() + 1);
    next.setHours(slots[0], 0, 0, 0);
  }

  return next.toLocaleString('ko-KR', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function SummaryBar({ summaryLines, generatedAt, onRefresh }: Props) {
  const lines = summaryLines.length > 0
    ? summaryLines
    : ['핵심 요약을 준비하는 중입니다.', '시장 신호를 모으는 중입니다.', '리포트 본문이 곧 정리됩니다.'];

  return (
    <div className="summary-shell">
      <div className="summary-head">
        <div>
          <div className="summary-title">Quick Brief</div>
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
          <div key={i} className="summary-card">
            <span className="summary-index">{i + 1}</span>
            <div className="summary-copy">{line}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
