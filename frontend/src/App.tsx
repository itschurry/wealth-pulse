import { useState } from 'react';
import type { TabId } from './types';
import { Header } from './components/Header';
import { SummaryBar } from './components/SummaryBar';
import { TabBar } from './components/TabBar';
import { AssistantTab } from './components/AssistantTab';
import { MarketTab } from './components/MarketTab';
import { WatchlistTab } from './components/WatchlistTab';
import { AnalysisTab } from './components/AnalysisTab';
import { RecommendationTab } from './components/RecommendationTab';
import { useAnalysis } from './hooks/useAnalysis';

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>(() => {
    const hash = location.hash.replace('#', '') as TabId;
    return ['assistant', 'market', 'holdings', 'analysis', 'recommendations'].includes(hash) ? hash : 'analysis';
  });
  const { data: analysis, status: analysisStatus, refresh: refreshAnalysis } = useAnalysis();

  function handleTabChange(tab: TabId) {
    setActiveTab(tab);
    history.replaceState(null, '', '#' + tab);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  const today = new Date().toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric' });

  return (
    <div className="app-shell">
      <div className="page-frame">
        <Header
          reportDate={today}
          generatedAt={analysis.generated_at}
          headline={analysis.summary_lines?.[0]}
        />
        <SummaryBar
          summaryLines={analysis.summary_lines || []}
          generatedAt={analysis.generated_at}
          onRefresh={refreshAnalysis}
        />
        <TabBar activeTab={activeTab} onChange={handleTabChange} />
        <div className="content-shell">
          {activeTab === 'assistant' && <AssistantTab />}
          {activeTab === 'market' && <MarketTab />}
          {activeTab === 'holdings' && <WatchlistTab />}
          {activeTab === 'analysis' && (
            <AnalysisTab
              data={analysis}
              status={analysisStatus}
              onRefresh={refreshAnalysis}
            />
          )}
          {activeTab === 'recommendations' && (
            <RecommendationTab
              onRefresh={refreshAnalysis}
            />
          )}
        </div>
      </div>
    </div>
  );
}
