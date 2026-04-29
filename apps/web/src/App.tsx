import { useEffect, useState } from 'react';
import { UI_TEXT } from './constants/uiText';
import { useConsoleData } from './hooks/useConsoleData';
import { FEATURE_FLAGS } from './lib/featureFlags';
import { AgentDashboardPage } from './pages/AgentDashboardPage';
import { BacktestValidationPage } from './pages/BacktestValidationPage';
import { PaperPortfolioPage } from './pages/PaperPortfolioPage';
import { PerformancePage } from './pages/PerformancePage';
import { ReportsPage } from './pages/ReportsPage';
import { CandidateResearchPage } from './pages/CandidateResearchPage';
import { ScannerPage } from './pages/ScannerPage';
import { StrategiesPage } from './pages/StrategiesPage';
import { UniversePage } from './pages/UniversePage';
import { WatchlistPage } from './pages/WatchlistPage';
import { WealthPulseHomePage } from './pages/WealthPulseHomePage';
import type { DashboardTab, LabTab, ResearchTab, WorkspacePage } from './types/navigation';

function formatKstClock(date: Date): string {
  return new Intl.DateTimeFormat('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: 'Asia/Seoul',
  }).format(date);
}

interface RouteState {
  page: WorkspacePage;
  dashboardTab: DashboardTab;
  labTab: LabTab;
  researchTab: ResearchTab;
  canonicalPath: string;
  search: string;
}

const WORKSPACE_PAGES: Array<{ id: WorkspacePage; label: string; path: string; hint: string }> = [
  { id: 'operations-dashboard', label: '운영 대시보드', path: '/operations-dashboard', hint: '운영 개요 · 스캐너 · 시나리오 · 성과' },
  { id: 'research-ai', label: '리서치/AI', path: '/research-ai', hint: '현재 후보 리서치 조회' },
  { id: 'agent-dashboard', label: 'Agent 관제', path: '/agent-dashboard', hint: 'Agent Run · Risk Gate · Paper 주문 감사' },
  { id: 'orders-execution', label: '주문/체결', path: '/orders-execution', hint: '주문 상태 · 차단 사유 · 포지션' },
  { id: 'lab', label: '실험실(Lab)', path: '/lab/validation', hint: '백테스트 · 탐색 · 재검증' },
  { id: 'watchlist', label: UI_TEXT.analysisTabs.watchlist, path: '/watchlist', hint: '관심 종목 저장과 분석' },
];

const DASHBOARD_TABS: Array<{ id: DashboardTab; label: string; path: string; hint: string }> = [
  { id: 'overview', label: UI_TEXT.operationsTabs.overview, path: '/operations-dashboard', hint: '브리프와 리스크를 합친 운영 첫 화면' },
  { id: 'scanner', label: UI_TEXT.operationsTabs.scanner, path: '/operations-dashboard/scanner', hint: '장중 후보와 차단 사유 관찰' },
  { id: 'watch-decision', label: UI_TEXT.operationsTabs.watchDecision, path: '/operations-dashboard/watch-decision', hint: '관심 시나리오 검토' },
  { id: 'performance', label: UI_TEXT.operationsTabs.performance, path: '/operations-dashboard/performance', hint: '체결/운용 성과 추적' },
];

const LAB_TABS: Array<{ id: LabTab; label: string; path: string; hint: string }> = [
  { id: 'validation', label: UI_TEXT.labTabs.validation, path: '/lab/validation', hint: '백테스트 · 검증 · 재검증' },
  { id: 'strategies', label: UI_TEXT.labTabs.strategies, path: '/lab/strategies', hint: '실험용 프리셋 생성 · 복제 · 삭제' },
  { id: 'universe', label: UI_TEXT.labTabs.universe, path: '/lab/universe', hint: '실험용 유니버스 비교' },
];

const RESEARCH_TABS: Array<{ id: ResearchTab; label: string; path: string; hint: string }> = [
  { id: 'research', label: UI_TEXT.analysisTabs.research, path: '/research-ai', hint: '현재 후보 리서치 조회' },
];

const PAGE_COPY: Record<WorkspacePage, string> = {
  'operations-dashboard': '운영자가 자동거래 파이프라인, 브리프, 리스크를 한 화면에서 판단하는 관제 홈입니다.',
  'orders-execution': '주문 흐름, 차단 사유, 체결 상태를 운영 관점에서 추적합니다.',
  'agent-dashboard': 'Hermes 판단, Risk Gate, Paper 주문 감사를 한 곳에서 확인하는 자동거래 관제 화면입니다.',
  lab: '백테스트, 탐색, 검증, 프리셋 실험은 이 영역에서만 수행합니다.',
  watchlist: '관심 종목 저장, 편집, 분석을 실행 화면과 분리해 관리합니다.',
  'research-ai': '현재 스캐너 후보에 붙은 리서치 상태와 생성 이력을 따로 추적합니다.',
};

function normalizeSearch(search = ''): string {
  if (!search) return '';
  return search.startsWith('?') ? search : `?${search}`;
}

function buildUrl(path: string, search = ''): string {
  return `${path}${normalizeSearch(search)}`;
}

function defaultRouteState(search = ''): RouteState {
  return {
    page: 'operations-dashboard',
    dashboardTab: 'overview',
    labTab: 'validation',
    researchTab: 'research',
    canonicalPath: '/operations-dashboard',
    search: normalizeSearch(search),
  };
}

function withDefaults(partial: Partial<RouteState> & Pick<RouteState, 'page' | 'canonicalPath'>, search = ''): RouteState {
  return {
    dashboardTab: 'overview',
    labTab: 'validation',
    researchTab: 'research',
    search: normalizeSearch(search),
    ...partial,
  };
}

function toRouteState(pathname: string, search = ''): RouteState {
  const path = pathname.toLowerCase();
  const normalizedSearch = normalizeSearch(search);
  const normalize = (nextPath: string): RouteState => toRouteState(nextPath, normalizedSearch);

  const legacyRedirects: Record<string, string> = {
    '/': '/operations-dashboard',
    '/home': '/operations-dashboard',
    '/dashboard': '/operations-dashboard',
    '/overview': '/operations-dashboard',
    '/operations/overview': '/operations-dashboard',
    '/operations/scanner': '/operations-dashboard/scanner',
    '/operations/brief': '/operations-dashboard',
    '/operations/alerts': '/operations-dashboard',
    '/operations/watch-decision': '/operations-dashboard/watch-decision',
    '/operations/performance': '/operations-dashboard/performance',
    '/operations/orders': '/orders-execution',
    '/strategy-operations': '/lab/strategies',
    '/operations/strategies': '/lab/strategies',
    '/console/strategies': '/lab/strategies',
    '/console/scanner': '/operations-dashboard/scanner',
    '/console/orders': '/orders-execution',
    '/console/agent': '/agent-dashboard',
    '/agent': '/agent-dashboard',
    '/agent-runs': '/agent-dashboard',
    '/console/performance': '/operations-dashboard/performance',
    '/console/watchlist': '/watchlist',
    '/console/research': '/research-ai',
    '/console/validation': '/lab/validation',
    '/console/validation-lab': '/lab/validation',
    '/console/universe': '/lab/universe',
    '/reports': '/operations-dashboard',
    '/reports/today-report': '/operations-dashboard',
    '/reports/today': '/operations-dashboard',
    '/reports/recommendations': '/operations-dashboard',
    '/reports/today-recommendations': '/operations-dashboard',
    '/reports/alerts': '/operations-dashboard',
    '/reports/watch-decision': '/operations-dashboard/watch-decision',
    '/reports/action-board': '/operations-dashboard',
    '/analysis/brief': '/operations-dashboard',
    '/analysis/alerts': '/operations-dashboard',
    '/analysis/watch-decisions': '/operations-dashboard/watch-decision',
    '/analysis/watchlist': '/watchlist',
    '/analysis/research': '/research-ai',
    '/research-ai/brief': '/operations-dashboard',
    '/research-ai/alerts': '/operations-dashboard',
    '/research-ai/watch-decisions': '/operations-dashboard/watch-decision',
    '/research-ai/watchlist': '/watchlist',
    '/research-ai/research': '/research-ai',
    '/signals': '/operations-dashboard/scanner',
    '/paper': '/orders-execution',
    '/backtest': '/lab/validation',
    '/settings': '/lab/validation',
  };
  if (legacyRedirects[path]) return normalize(legacyRedirects[path]);

  if (path === '/operations-dashboard' || path === '/operations-dashboard/') {
    return withDefaults({ page: 'operations-dashboard', dashboardTab: 'overview', canonicalPath: '/operations-dashboard' }, normalizedSearch);
  }
  if (path === '/operations-dashboard/scanner') {
    return withDefaults({ page: 'operations-dashboard', dashboardTab: 'scanner', canonicalPath: '/operations-dashboard/scanner' }, normalizedSearch);
  }
  if (path === '/operations-dashboard/performance') {
    return withDefaults({ page: 'operations-dashboard', dashboardTab: 'performance', canonicalPath: '/operations-dashboard/performance' }, normalizedSearch);
  }
  if (path === '/operations-dashboard/watch-decision') {
    return withDefaults({ page: 'operations-dashboard', dashboardTab: 'watch-decision', canonicalPath: '/operations-dashboard/watch-decision' }, normalizedSearch);
  }
  if (path === '/orders-execution') {
    return withDefaults({ page: 'orders-execution', canonicalPath: '/orders-execution' }, normalizedSearch);
  }
  if (path === '/agent-dashboard') {
    return withDefaults({ page: 'agent-dashboard', canonicalPath: '/agent-dashboard' }, normalizedSearch);
  }
  if (path === '/watchlist') {
    return withDefaults({ page: 'watchlist', canonicalPath: '/watchlist' }, normalizedSearch);
  }
  if (path.startsWith('/lab/')) {
    const segment = path.replace('/lab/', '');
    const found = LAB_TABS.find((tab) => tab.id === segment);
    if (found) {
      return withDefaults({ page: 'lab', labTab: found.id, canonicalPath: found.path }, normalizedSearch);
    }
    return normalize('/lab/validation');
  }
  if (path === '/research-ai' || path === '/research-ai/') {
    return withDefaults({ page: 'research-ai', researchTab: 'research', canonicalPath: '/research-ai' }, normalizedSearch);
  }
  return defaultRouteState(normalizedSearch);
}

function pushPath(path: string, search = '') {
  history.pushState(null, '', buildUrl(path, search));
}

function replacePath(path: string, search = '') {
  history.replaceState(null, '', buildUrl(path, search));
}

export default function App() {
  const [route, setRoute] = useState<RouteState>(() => toRouteState(location.pathname, location.search));
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [clockText, setClockText] = useState(() => formatKstClock(new Date()));
  const { snapshot, loading, hasError, errorMessage, refresh } = useConsoleData(route);
  const activePage = WORKSPACE_PAGES.find((page) => page.id === route.page) || WORKSPACE_PAGES[0];
  const activeDashboardTab = DASHBOARD_TABS.find((tab) => tab.id === route.dashboardTab);
  const activeLabTab = LAB_TABS.find((tab) => tab.id === route.labTab);
  const activeResearchTab = RESEARCH_TABS.find((tab) => tab.id === route.researchTab);
  const activeLabel = route.page === 'operations-dashboard'
    ? activeDashboardTab?.label || activePage.label
    : route.page === 'lab'
      ? activeLabTab?.label || activePage.label
      : route.page === 'research-ai'
        ? activeResearchTab?.label || activePage.label
        : activePage.label;
  const activeHint = route.page === 'operations-dashboard'
    ? activeDashboardTab?.hint || activePage.hint
    : route.page === 'lab'
      ? activeLabTab?.hint || activePage.hint
      : route.page === 'research-ai'
        ? activeResearchTab?.hint || activePage.hint
        : activePage.hint;

  useEffect(() => {
    const initial = toRouteState(location.pathname, location.search);
    setRoute(initial);
    if (location.pathname !== initial.canonicalPath) {
      replacePath(initial.canonicalPath, initial.search);
    }

    const handlePopState = () => {
      const next = toRouteState(location.pathname, location.search);
      setRoute(next);
      setMobileNavOpen(false);
      if (location.pathname !== next.canonicalPath) {
        replacePath(next.canonicalPath, next.search);
      }
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setClockText(formatKstClock(new Date()));
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  function navigateTo(targetPath: string) {
    const next = toRouteState(targetPath, route.search);
    pushPath(next.canonicalPath, next.search);
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

      <aside className="app-sidebar" aria-label="작업 공간 탐색">
        <div className="app-sidebar-brand">
          <div className="app-sidebar-brand-row">
            <div>
              <div className="app-sidebar-kicker">WealthPulse</div>
              <div className="app-sidebar-title">운영 작업 공간</div>
            </div>
            <div className="app-sidebar-meta">
              <span className="app-live-pill">LIVE</span>
              <span className="app-sidebar-clock">{clockText}</span>
            </div>
          </div>
          <div className="app-sidebar-copy">{PAGE_COPY[route.page]}</div>
        </div>

        <div className="app-sidebar-group">
          <div className="app-sidebar-group-label">작업 공간</div>
          {WORKSPACE_PAGES.map((page, index) => (
            <button
              key={page.id}
              onClick={() => navigateTo(page.path)}
              className={`app-nav-button ${route.page === page.id ? 'active' : ''}`}
              aria-current={route.page === page.id ? 'page' : undefined}
            >
              <span className="app-nav-step">{String(index + 1).padStart(2, '0')}</span>
              <span className="app-nav-label-wrap">
                <span className="app-nav-label">{page.label}</span>
                {route.page === page.id ? <span className="app-nav-help">{page.hint}</span> : null}
              </span>
            </button>
          ))}
        </div>

        {(route.page === 'operations-dashboard' || route.page === 'lab') && (
          <div className="app-sidebar-group">
            <div className="app-sidebar-group-label">
              {route.page === 'operations-dashboard' ? '운영 보조 화면' : '실험 화면'}
            </div>
            {route.page === 'operations-dashboard' && DASHBOARD_TABS.map((tab, index) => (
              <button
                key={tab.id}
                onClick={() => navigateTo(tab.path)}
                className={`app-nav-button is-sub ${route.dashboardTab === tab.id ? 'active' : ''}`}
                aria-current={route.dashboardTab === tab.id ? 'page' : undefined}
              >
                <span className="app-nav-step">{String(index + 1).padStart(2, '0')}</span>
                <span className="app-nav-label-wrap">
                  <span className="app-nav-label">{tab.label}</span>
                  {route.dashboardTab === tab.id ? <span className="app-nav-help">{tab.hint}</span> : null}
                </span>
              </button>
            ))}
            {route.page === 'lab' && LAB_TABS.map((tab, index) => (
              <button
                key={tab.id}
                onClick={() => navigateTo(tab.path)}
                className={`app-nav-button is-sub ${route.labTab === tab.id ? 'active' : ''}`}
                aria-current={route.labTab === tab.id ? 'page' : undefined}
              >
                <span className="app-nav-step">{String(index + 1).padStart(2, '0')}</span>
                <span className="app-nav-label-wrap">
                  <span className="app-nav-label">{tab.label}</span>
                  {route.labTab === tab.id ? <span className="app-nav-help">{tab.hint}</span> : null}
                </span>
              </button>
            ))}
          </div>
        )}

        <div className="app-sidebar-foot">
          <span className={`app-chrome-pill ${loading ? 'is-live' : ''}`}>{loading ? '동기화 중' : '준비 완료'}</span>
          <span className="app-chrome-pill">{FEATURE_FLAGS.refactorBundleDNavigation ? '개편 네비게이션' : '기존 네비게이션'}</span>
        </div>
      </aside>

      <main className="app-main">
        <header className="app-main-header">
          <div>
            <div className="app-main-kicker">{activePage.label}</div>
            <h1 className="app-main-title">{activeLabel}</h1>
            <div className="app-main-copy">{activeHint}</div>
          </div>
        </header>

        <div className="app-main-content">
          {route.page === 'operations-dashboard' && route.dashboardTab === 'overview' && (
            <WealthPulseHomePage
              {...sharedProps}
              onGoLab={() => navigateTo('/lab/validation')}
              onGoAnalysis={() => navigateTo('/research-ai')}
            />
          )}
          {route.page === 'operations-dashboard' && route.dashboardTab === 'scanner' && <ScannerPage {...sharedProps} />}
          {route.page === 'operations-dashboard' && route.dashboardTab === 'performance' && <PerformancePage {...sharedProps} />}
          {route.page === 'operations-dashboard' && route.dashboardTab === 'watch-decision' && (
            <ReportsPage
              {...sharedProps}
            />
          )}

          {route.page === 'orders-execution' && <PaperPortfolioPage {...sharedProps} />}
          {route.page === 'agent-dashboard' && <AgentDashboardPage {...sharedProps} />}
          {route.page === 'watchlist' && <WatchlistPage {...sharedProps} />}

          {route.page === 'lab' && route.labTab === 'validation' && <BacktestValidationPage {...sharedProps} />}
          {route.page === 'lab' && route.labTab === 'strategies' && <StrategiesPage {...sharedProps} />}
          {route.page === 'lab' && route.labTab === 'universe' && <UniversePage {...sharedProps} />}

          {route.page === 'research-ai' && route.researchTab === 'research' && <CandidateResearchPage {...sharedProps} />}
        </div>
      </main>
    </div>
  );
}
