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
    : ['AI 분석 요약을 불러오는 중...', '', ''];
  const nextSchedule = getNextScheduleLabel();

  return (
    <div style={{
      background: 'linear-gradient(135deg, #0a1628 0%, #111f38 50%, #0a1628 100%)',
      borderBottom: '1px solid rgba(255,255,255,.06)',
      padding: '16px 24px',
    }}>
      {/* Shimmer top line */}
      <div className="shimmer-line" style={{
        height: 2,
        background: 'linear-gradient(90deg, transparent, rgba(59,130,246,.6), transparent)',
        marginBottom: 14,
        borderRadius: 1,
      }} />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {lines.slice(0, 3).map((line, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
              <span style={{
                flexShrink: 0,
                width: 22, height: 22,
                borderRadius: '50%',
                background: 'rgba(59,130,246,.2)',
                border: '1px solid rgba(59,130,246,.4)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 11, fontWeight: 700, color: '#93c5fd',
              }}>{i + 1}</span>
              <span style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.5 }}>{line}</span>
            </div>
          ))}
          <div style={{ fontSize: 11, color: 'var(--text-4)', marginLeft: 32, marginTop: 2 }}>오늘 판단 전에 먼저 봐야 할 3가지 신호</div>
          <div style={{ fontSize: 11, color: 'var(--text-4)', marginLeft: 32 }}>
            리포트 생성: {generatedAt || '데이터 없음'}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-4)', marginLeft: 32 }}>
            다음 자동 생성(스케줄러 기준): {nextSchedule}
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 8, flexShrink: 0 }}>
          <span style={{ fontSize: 11, color: 'var(--text-4)' }}>읽기 모드</span>
          <button
            onClick={onRefresh}
            style={{
              background: 'rgba(59,130,246,.12)',
              border: '1px solid rgba(59,130,246,.3)',
              borderRadius: 8,
              color: '#93c5fd',
              cursor: 'pointer',
              fontSize: 16,
              padding: '4px 10px',
              transition: 'background .2s',
            }}
            title="최신 리포트 다시 불러오기"
          >↻</button>
        </div>
      </div>
    </div>
  );
}
