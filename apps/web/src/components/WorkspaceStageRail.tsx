interface WorkspaceStageRailProps {
  current: 'validation' | 'watchlist' | 'scanner' | 'research' | 'orders';
}

const STAGES: Array<{ key: WorkspaceStageRailProps['current']; label: string; hint: string }> = [
  { key: 'validation', label: '설정 검증', hint: '전략·리스크·백테스트 기준' },
  { key: 'watchlist', label: '관심 종목', hint: '편집·저장·분석 실행' },
  { key: 'scanner', label: '스캐너', hint: '후보 생성과 필터링' },
  { key: 'research', label: '리서치', hint: 'Hanna 스냅샷과 근거' },
  { key: 'orders', label: '주문/리스크', hint: '판단·차단·주문 결과' },
];

export function WorkspaceStageRail({ current }: WorkspaceStageRailProps) {
  return (
    <div className="workspace-stage-rail" aria-label="운영 흐름">
      {STAGES.map((stage, index) => {
        const active = stage.key === current;
        return (
          <div key={stage.key} className={`workspace-stage-chip ${active ? 'is-active' : ''}`.trim()}>
            <span className="workspace-stage-index">{String(index + 1).padStart(2, '0')}</span>
            <span className="workspace-stage-texts">
              <span className="workspace-stage-label">{stage.label}</span>
              <span className="workspace-stage-hint">{stage.hint}</span>
            </span>
          </div>
        );
      })}
    </div>
  );
}
