import type { TabId } from '../types';

interface Props {
  activeTab: TabId;
  onChange: (tab: TabId) => void;
  onOpenBacktest: () => void;
}

const TABS: { id: TabId; label: string; help: string }[] = [
  { id: 'analysis', label: '오늘 리포트', help: '시장 맥락 읽기' },
  { id: 'assistant', label: '액션 보드', help: '오늘 할 일 정리' },
  { id: 'recommendations', label: '오늘의 추천', help: '뉴스 기반 아이디어' },
  { id: 'holdings', label: '관심종목 판단', help: '매수·매도 시그널' },
  { id: 'market', label: '실시간 참고', help: '보조 지표 확인' },
];

export function TabBar({ activeTab, onChange, onOpenBacktest }: Props) {
  return (
    <div className="tab-shell">
      <div className="tab-shell-row">
        <div className="tab-strip">
          {TABS.map((tab, index) => (
            <button
              key={tab.id}
              onClick={() => onChange(tab.id)}
              className={`tab-button ${activeTab === tab.id ? 'active' : ''}`}
            >
              <span className="tab-step">{String(index + 1).padStart(2, '0')}</span>
              <span className="tab-label">{tab.label}</span>
              <span className="tab-help">{tab.help}</span>
            </button>
          ))}
        </div>
        <button className="tab-launch-button" onClick={onOpenBacktest}>
          <span className="tab-label">백테스트 실험실</span>
          <span className="tab-help">설정 조절 · 전략 검증</span>
        </button>
      </div>
    </div>
  );
}
