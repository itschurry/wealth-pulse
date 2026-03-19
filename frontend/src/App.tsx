import { useEffect, useState } from 'react';
import type { TabId } from './types';
import { Header } from './components/Header';
import { SummaryBar } from './components/SummaryBar';
import { TabBar } from './components/TabBar';
import { AssistantTab } from './components/AssistantTab';
import { MarketTab } from './components/MarketTab';
import { WatchlistTab } from './components/WatchlistTab';
import { AnalysisTab } from './components/AnalysisTab';
import { RecommendationTab } from './components/RecommendationTab';
import { BacktestPage } from './components/BacktestPage';
import { useAnalysis } from './hooks/useAnalysis';

type RouteId = 'dashboard' | 'backtest';

function readRoute(): RouteId {
  return location.pathname.startsWith('/backtest') ? 'backtest' : 'dashboard';
}

function readTab(): TabId {
  const hash = location.hash.replace('#', '') as TabId;
  return ['assistant', 'market', 'holdings', 'analysis', 'recommendations'].includes(hash) ? hash : 'analysis';
}

function DashboardPage({ onOpenBacktest }: { onOpenBacktest: () => void }) {
  const [activeTab, setActiveTab] = useState<TabId>(readTab);
  const { data: analysis, status: analysisStatus, refresh: refreshAnalysis } = useAnalysis();

  useEffect(() => {
    const handlePopState = () => {
      setActiveTab(readTab());
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  function handleTabChange(tab: TabId) {
    setActiveTab(tab);
    history.replaceState(null, '', '/#' + tab);
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
        <TabBar activeTab={activeTab} onChange={handleTabChange} onOpenBacktest={onOpenBacktest} />
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

export default function App() {
  const [route, setRoute] = useState<RouteId>(readRoute);

  function navigateToDashboard(tab?: TabId) {
    history.pushState(null, '', tab ? `/#${tab}` : '/');
    setRoute('dashboard');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function navigateToBacktest() {
    history.pushState(null, '', '/backtest');
    setRoute('backtest');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  useEffect(() => {
    const handlePopState = () => {
      setRoute(readRoute());
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  if (route === 'backtest') {
    return <BacktestPage onBack={() => navigateToDashboard('analysis')} />;
  }

  return <DashboardPage onOpenBacktest={navigateToBacktest} />;
}
