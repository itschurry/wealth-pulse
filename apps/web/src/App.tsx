import { useEffect, useState } from 'react';
import { UI_TEXT } from './constants/uiText';
import { useConsoleData } from './hooks/useConsoleData';
import { BacktestValidationPage } from './pages/BacktestValidationPage';
import { PaperPortfolioPage } from './pages/PaperPortfolioPage';
import { PerformancePage } from './pages/PerformancePage';
import { ReportsPage } from './pages/ReportsPage';
import { ResearchSnapshotsPage } from './pages/ResearchSnapshotsPage';
import { ScannerPage } from './pages/ScannerPage';
import { StrategiesPage } from './pages/StrategiesPage';
import { UniversePage } from './pages/UniversePage';
import { WatchlistPage } from './pages/WatchlistPage';
import { WealthPulseHomePage } from './pages/WealthPulseHomePage';
import type { AnalysisTab, LabTab, OperationsTab, TopSection } from './types/navigation';

interface RouteState {
  section: TopSection;
  operationsTab: OperationsTab;
  labTab: LabTab;
  analysisTab: AnalysisTab;
  canonicalPath: string;
}

const OPERATIONS_TABS: Array<{ id: OperationsTab; label: string; path: string; hint: string }> = [
  { id: 'overview', label: UI_TEXT.operationsTabs.overview, path: '/operations/overview', hint: '포트폴리오 · 신호 · 리스크 요약' },
  { id: 'strategies', label: UI_TEXT.operationsTabs.strategies, path: '/operations/strategies', hint: '승인/적용 전략 상태 확인' },
  { id: 'scanner', label: UI_TEXT.operationsTabs.scanner, path: '/operations/scanner', hint: '운영 스캐너와 후보군 관찰' },
  { id: 'orders', label: UI_TEXT.operationsTabs.orders, path: '/operations/orders', hint: '주문 상태와 차단 사유 확인' },
  { id: 'performance', label: UI_TEXT.operationsTabs.performance, path: '/operations/performance', hint: '운용 성과와 체결 성과 추적' },
];

const LAB_TABS: Array<{ id: LabTab; label: string; path: string; hint: string }> = [
  { id: 'validation', label: UI_TEXT.labTabs.validation, path: '/lab/validation', hint: '백테스트 · 검증 · 저장 흐름' },
  { id: 'strategies', label: UI_TEXT.labTabs.strategies, path: '/lab/strategies', hint: '프리셋 생성 · 복제 · 삭제' },
  { id: 'universe', label: UI_TEXT.labTabs.universe, path: '/lab/universe', hint: '실험용 유니버스 비교와 검토' },
];

const ANALYSIS_TABS: Array<{ id: AnalysisTab; label: string; path: string; hint: string }> = [
  { id: 'today-report', label: UI_TEXT.analysisTabs.todayReport, path: '/analysis/brief', hint: '오늘 시장 브리프와 해석' },
  { id: 'alerts', label: UI_TEXT.analysisTabs.alerts, path: '/analysis/alerts', hint: '리스크 알림과 대응 포인트' },
  { id: 'watch-decision', label: UI_TEXT.analysisTabs.watchDecision, path: '/analysis/watch-decisions', hint: '관심 시나리오 검토' },
  { id: 'watchlist', label: UI_TEXT.analysisTabs.watchlist, path: '/analysis/watchlist', hint: '관심 종목 저장과 분석' },
  { id: 'research', label: UI_TEXT.analysisTabs.research, path: '/analysis/research', hint: '리서치 스냅샷 조회' },
];

const SECTION_COPY: Record<TopSection, string> = {
  operations: '자동거래 실행, 주문 판단, 체결 추적, 장애 확인을 운영 관점으로 봅니다.',
  lab: '백테스트, 파라미터 탐색, 전략 실험, 재검증을 실험 모드에서만 수행합니다.',
  analysis: '리서치, 시장 데이터 조회, AI 인사이트를 분석 모드에서만 다룹니다.',
};

const SECTION_BADGE: Record<TopSection, string> = {
  operations: 'Execution + Monitoring + Runtime',
  lab: 'Backtest + Validation + Config',
  analysis: 'Research + Market Data + Insight',
};

function toRouteState(pathname: string): RouteState {
  const path = pathname.toLowerCase();
  const normalize = (nextPath: string): RouteState => toRouteState(nextPath);

  const legacyRedirects: Record<string, string> = {
    '/': '/operations/overview',
    '/home': '/operations/overview',
    '/dashboard': '/operations/overview',
    '/overview': '/operations/overview',
    '/console/strategies': '/operations/strategies',
    '/console/scanner': '/operations/scanner',
    '/console/orders': '/operations/orders',
    '/console/performance': '/operations/performance',
    '/console/watchlist': '/analysis/watchlist',
    '/console/research': '/analysis/research',
    '/console/validation': '/lab/validation',
    '/console/validation-lab': '/lab/validation',
    '/console/universe': '/lab/universe',
    '/reports': '/analysis/brief',
    '/reports/today-report': '/analysis/brief',
    '/reports/today': '/analysis/brief',
    '/reports/recommendations': '/analysis/brief',
    '/reports/today-recommendations': '/analysis/brief',
    '/reports/alerts': '/analysis/alerts',
    '/reports/watch-decision': '/analysis/watch-decisions',
    '/reports/action-board': '/analysis/alerts',
    '/signals': '/operations/scanner',
    '/paper': '/operations/orders',
    '/backtest': '/lab/validation',
  };
  if (legacyRedirects[path]) return normalize(legacyRedirects[path]);

  if (path.startsWith('/operations/')) {
    const segment = path.replace('/operations/', '');
    const found = OPERATIONS_TABS.find((tab) => tab.id === segment);
    if (found) {
      return {
        section: 'operations',
        operationsTab: found.id,
        labTab: 'validation',
        analysisTab: 'today-report',
        canonicalPath: found.path,
      };
    }
    return normalize('/operations/overview');
  }

  if (path.startsWith('/lab/')) {
    const segment = path.replace('/lab/', '');
    const found = LAB_TABS.find((tab) => tab.id === segment);
    if (found) {
      return {
        section: 'lab',
        operationsTab: 'overview',
        labTab: found.id,
        analysisTab: 'today-report',
        canonicalPath: found.path,
      };
    }
    return normalize('/lab/validation');
  }

  if (path.startsWith('/analysis/')) {
    const segment = path.replace('/analysis/', '');
    const normalizedSegment = segment === 'brief'
      ? 'today-report'
      : segment === 'watch-decisions'
        ? 'watch-decision'
        : segment;
    const found = ANALYSIS_TABS.find((tab) => tab.id === normalizedSegment);
    if (found) {
      return {
        section: 'analysis',
        operationsTab: 'overview',
        labTab: 'validation',
        analysisTab: found.id,
        canonicalPath: found.path,
      };
    }
    return normalize('/analysis/brief');
  }

  return normalize('/operations/overview');
}

function pushPath(path: string) {
  history.pushState(null, '', path);
}

function replacePath(path: string) {
  history.replaceState(null, '', path);
}

export default function App() {
  const [route, setRoute] = useState<RouteState>(() => toRouteState(location.pathname));
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const { snapshot, loading, hasError, errorMessage, refresh } = useConsoleData(route);
  const activeOperationsTab = OPERATIONS_TABS.find((tab) => tab.id === route.operationsTab);
  const activeLabTab = LAB_TABS.find((tab) => tab.id === route.labTab);
  const activeAnalysisTab = ANALYSIS_TABS.find((tab) => tab.id === route.analysisTab);
  const activeLabel = route.section === 'operations'
    ? activeOperationsTab?.label || UI_TEXT.operationsTabs.overview
    : route.section === 'lab'
      ? activeLabTab?.label || UI_TEXT.labTabs.validation
      : activeAnalysisTab?.label || UI_TEXT.analysisTabs.todayReport;

  useEffect(() => {
    const initial = toRouteState(location.pathname);
    setRoute(initial);
    if (location.pathname !== initial.canonicalPath) {
      replacePath(initial.canonicalPath);
    }

    const handlePopState = () => {
      const next = toRouteState(location.pathname);
      setRoute(next);
      setMobileNavOpen(false);
      if (location.pathname !== next.canonicalPath) {
        replacePath(next.canonicalPath);
      }
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  function moveToSection(section: TopSection) {
    const targetPath = section === 'operations'
      ? '/operations/overview'
      : section === 'lab'
        ? '/lab/validation'
        : '/analysis/brief';
    const next = toRouteState(targetPath);
    pushPath(next.canonicalPath);
    setRoute(next);
    setMobileNavOpen(false);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function moveToOperationsTab(tab: OperationsTab) {
    const target = OPERATIONS_TABS.find((item) => item.id === tab);
    if (!target) return;
    const next = toRouteState(target.path);
    pushPath(next.canonicalPath);
    setRoute(next);
    setMobileNavOpen(false);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function moveToLabTab(tab: LabTab) {
    const target = LAB_TABS.find((item) => item.id === tab);
    if (!target) return;
    const next = toRouteState(target.path);
    pushPath(next.canonicalPath);
    setRoute(next);
    setMobileNavOpen(false);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function moveToAnalysisTab(tab: AnalysisTab) {
    const target = ANALYSIS_TABS.find((item) => item.id === tab);
    if (!target) return;
    const next = toRouteState(target.path);
    pushPath(next.canonicalPath);
    setRoute(next);
    setMobileNavOpen(false);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  const sharedProps = {
    snapshot,
    loading,
    errorMessage: hasError ? errorMessage : '',
    onRefresh: refresh,
  };

  return (
    <div className={`app-layout ${mobileNavOpen ? 'is-nav-open' : ''}`}>
      <button
        className="app-mobile-nav-toggle"
        type="button"
        aria-label={mobileNavOpen ? '사이드 메뉴 닫기' : '사이드 메뉴 열기'}
        onClick={() => setMobileNavOpen((prev) => !prev)}
      >
        <span />
        <span />
        <span />
      </button>

      <button
        className="app-mobile-nav-backdrop"
        type="button"
        aria-hidden={!mobileNavOpen}
        onClick={() => setMobileNavOpen(false)}
      />

      <aside className="app-sidebar" aria-label="Workspace navigation">
        <div className="app-sidebar-brand">
          <div className="app-sidebar-kicker">WealthPulse</div>
          <div className="app-sidebar-title">Operator Workspace</div>
          <div className="app-sidebar-copy">{SECTION_COPY[route.section]}</div>
        </div>

        <div className="app-sidebar-group">
          <div className="app-sidebar-group-label">Modes</div>
          <button
            onClick={() => moveToSection('operations')}
            className={`app-nav-button ${route.section === 'operations' ? 'active' : ''}`}
            aria-current={route.section === 'operations' ? 'page' : undefined}
          >
            <span className="app-nav-step">01</span>
            <span className="app-nav-label-wrap">
              <span className="app-nav-label">{UI_TEXT.topTabs.operations}</span>
              <span className="app-nav-help">자동거래 실행 · 주문 관제</span>
            </span>
          </button>
          <button
            onClick={() => moveToSection('lab')}
            className={`app-nav-button ${route.section === 'lab' ? 'active' : ''}`}
            aria-current={route.section === 'lab' ? 'page' : undefined}
          >
            <span className="app-nav-step">02</span>
            <span className="app-nav-label-wrap">
              <span className="app-nav-label">{UI_TEXT.topTabs.lab}</span>
              <span className="app-nav-help">백테스트 · 검증 · 승인 준비</span>
            </span>
          </button>
          <button
            onClick={() => moveToSection('analysis')}
            className={`app-nav-button ${route.section === 'analysis' ? 'active' : ''}`}
            aria-current={route.section === 'analysis' ? 'page' : undefined}
          >
            <span className="app-nav-step">03</span>
            <span className="app-nav-label-wrap">
              <span className="app-nav-label">{UI_TEXT.topTabs.analysis}</span>
              <span className="app-nav-help">리서치 · 시장 데이터 · 인사이트</span>
            </span>
          </button>
        </div>

        <div className="app-sidebar-group">
          <div className="app-sidebar-group-label">
            {route.section === 'operations' ? 'Operations Views' : route.section === 'lab' ? 'Lab Views' : 'Analysis Views'}
          </div>
          {route.section === 'operations' && OPERATIONS_TABS.map((tab, index) => (
            <button
              key={tab.id}
              onClick={() => moveToOperationsTab(tab.id)}
              className={`app-nav-button is-sub ${route.operationsTab === tab.id ? 'active' : ''}`}
              aria-current={route.operationsTab === tab.id ? 'page' : undefined}
            >
              <span className="app-nav-step">{String(index + 1).padStart(2, '0')}</span>
              <span className="app-nav-label-wrap">
                <span className="app-nav-label">{tab.label}</span>
                <span className="app-nav-help">{tab.hint}</span>
              </span>
            </button>
          ))}
          {route.section === 'lab' && LAB_TABS.map((tab, index) => (
            <button
              key={tab.id}
              onClick={() => moveToLabTab(tab.id)}
              className={`app-nav-button is-sub ${route.labTab === tab.id ? 'active' : ''}`}
              aria-current={route.labTab === tab.id ? 'page' : undefined}
            >
              <span className="app-nav-step">{String(index + 1).padStart(2, '0')}</span>
              <span className="app-nav-label-wrap">
                <span className="app-nav-label">{tab.label}</span>
                <span className="app-nav-help">{tab.hint}</span>
              </span>
            </button>
          ))}
          {route.section === 'analysis' && ANALYSIS_TABS.map((tab, index) => (
            <button
              key={tab.id}
              onClick={() => moveToAnalysisTab(tab.id)}
              className={`app-nav-button is-sub ${route.analysisTab === tab.id ? 'active' : ''}`}
              aria-current={route.analysisTab === tab.id ? 'page' : undefined}
            >
              <span className="app-nav-step">{String(index + 1).padStart(2, '0')}</span>
              <span className="app-nav-label-wrap">
                <span className="app-nav-label">{tab.label}</span>
                <span className="app-nav-help">{tab.hint}</span>
              </span>
            </button>
          ))}
        </div>

        <div className="app-sidebar-foot">
          <span className={`app-chrome-pill ${loading ? 'is-live' : ''}`}>{loading ? 'Syncing' : 'Ready'}</span>
          <span className="app-chrome-pill">{SECTION_BADGE[route.section]}</span>
        </div>
      </aside>

      <main className="app-main">
        <header className="app-main-header">
          <div>
            <div className="app-main-kicker">Current Mode</div>
            <h1 className="app-main-title">{activeLabel}</h1>
            <div className="app-main-copy">{SECTION_COPY[route.section]}</div>
          </div>
        </header>

        <div className="app-main-content">
          {route.section === 'operations' && route.operationsTab === 'overview' && (
            <WealthPulseHomePage
              {...sharedProps}
              onGoLab={() => moveToSection('lab')}
              onGoAnalysis={() => moveToSection('analysis')}
            />
          )}
          {route.section === 'operations' && route.operationsTab === 'strategies' && <StrategiesPage {...sharedProps} mode="operations" />}
          {route.section === 'operations' && route.operationsTab === 'scanner' && <ScannerPage {...sharedProps} />}
          {route.section === 'operations' && route.operationsTab === 'orders' && <PaperPortfolioPage {...sharedProps} />}
          {route.section === 'operations' && route.operationsTab === 'performance' && <PerformancePage {...sharedProps} />}

          {route.section === 'lab' && route.labTab === 'validation' && <BacktestValidationPage {...sharedProps} />}
          {route.section === 'lab' && route.labTab === 'strategies' && <StrategiesPage {...sharedProps} mode="lab" />}
          {route.section === 'lab' && route.labTab === 'universe' && <UniversePage {...sharedProps} />}

          {route.section === 'analysis' && ['today-report', 'alerts', 'watch-decision'].includes(route.analysisTab) && (
            <ReportsPage
              {...sharedProps}
              reportTab={route.analysisTab as 'today-report' | 'alerts' | 'watch-decision'}
            />
          )}
          {route.section === 'analysis' && route.analysisTab === 'watchlist' && <WatchlistPage {...sharedProps} />}
          {route.section === 'analysis' && route.analysisTab === 'research' && <ResearchSnapshotsPage {...sharedProps} />}
        </div>
      </main>
    </div>
  );
}
