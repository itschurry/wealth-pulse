interface Props {
  reportDate: string;
  generatedAt?: string;
  headline?: string;
}

export function Header({ reportDate, generatedAt, headline }: Props) {
  return (
    <div className="hero-banner">
      <div className="hero-grid">
        <div>
          <div className="hero-eyebrow">Daily Market Brief</div>
          <div className="hero-title">판단은 짧게, 근거는 깊게.</div>
          <div className="hero-subtitle">
            매일 쏟아지는 뉴스와 시장 신호를 한 장의 브리핑으로 정리하고,
            오늘 바로 확인해야 할 리스크와 행동 포인트까지 이어주는 투자 도우미입니다.
          </div>
          <div className="hero-chip-row">
            <span className="hero-chip">{reportDate}</span>
            <span className="hero-chip">{generatedAt || '생성 시각 확인 중'}</span>
          </div>
        </div>

        <div className="hero-sidecard">
          <div className="hero-sidecard-label">오늘의 첫 문장</div>
          <div className="hero-sidecard-value">Morning Thesis</div>
          <div className="hero-sidecard-copy">
            {headline || '오늘 시장의 핵심 요약을 불러오는 중입니다.'}
          </div>
        </div>
      </div>
    </div>
  );
}
