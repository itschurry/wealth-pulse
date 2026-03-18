import type { TabId } from '../types';

interface Props {
  activeTab: TabId;
  onChange: (tab: TabId) => void;
}

const TABS: { id: TabId; label: string }[] = [
  { id: 'analysis', label: '📰 오늘 리포트' },
  { id: 'assistant', label: '🧭 의사결정 보드' },
  { id: 'market', label: '📈 실시간 참고' },
  { id: 'holdings', label: '⭐ 관심 종목' },
  { id: 'recommendations', label: '🎯 추천 허브' },
];

export function TabBar({ activeTab, onChange }: Props) {
  return (
    <div style={{
      position: 'sticky',
      top: 0,
      zIndex: 100,
      background: 'var(--card-bg)',
      borderBottom: '1px solid var(--border)',
      display: 'flex',
    }}>
      {TABS.map(tab => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          style={{
            flex: 1,
            padding: '14px 8px',
            background: 'none',
            border: 'none',
            borderBottom: activeTab === tab.id ? '2px solid #3b82f6' : '2px solid transparent',
            color: activeTab === tab.id ? '#f0f4ff' : 'var(--text-3)',
            cursor: 'pointer',
            fontSize: 13,
            fontWeight: activeTab === tab.id ? 700 : 400,
            fontFamily: 'inherit',
            transition: 'all .2s',
          }}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
