import { useEffect, useState } from 'react';
import { UI_TEXT } from './constants/uiText';
import { useConsoleData } from './hooks/useConsoleData';
import { FEATURE_FLAGS } from './lib/featureFlags';
import { BacktestValidationPage } from './pages/BacktestValidationPage';
import { PaperPortfolioPage } from './pages/PaperPortfolioPage';
import { PerformancePage } from './pages/PerformancePage';
import { ReportsPage } from './pages/ReportsPage';
import { ResearchSnapshotsPage } from './pages/ResearchSnapshotsPage';
import { ScannerPage } from './pages/ScannerPage';
import { SettingsPage } from './pages/SettingsPage';
import { StrategiesPage } from './pages/StrategiesPage';
import { UniversePage } from './pages/UniversePage';
import { WatchlistPage } from './pages/WatchlistPage';
import { WealthPulseHomePage } from './pages/WealthPulseHomePage';
import type { DashboardTab, LabTab, ResearchTab, WorkspacePage } from './types/navigation';

interface RouteState {
  page: WorkspacePage;
  dashboardTab: DashboardTab;
  labTab: LabTab;
  researchTab: ResearchTab;
  canonicalPath: string;
  search: string;
}

const WORKSPACE_PAGES: Array<{ id: WorkspacePage; label: string; path: string; hint: string }> = [
  { id: 'operations-dashboard', label: '운영 대시보드', path: '/operations-dashboard', hint: 'applied 전략 · 신호 · 이상 징후' },
  { id: 'orders-execution', label: '주문/체결', path: '/orders-execution', hint: '주문 상태 · 차단 사유 · 포지션' },
  { id: 'strategy-operations', label: '전략 운영 상태', path: '/strategy-operations', hint: 'approved/applied 상태 추적' },
  { id: 'lab', label: '실험실(Lab)', path: '/lab/validation', hint: '백테스트 · 탐색 · 재검증' },
  { id: 'research-ai', label: '리서치/AI', path: '/research-ai/brief', hint: '시장 브리프 · AI 인사이트' },
  { id: 'settings', label: '설정', path: '/settings', hint: 'draft/saved/displayed 상태 관리' },
];

const DASHBOARD_TABS: Array<{ id: DashboardTab; label: string; path: string; hint: string }> = [
  { id: 'overview', label: UI_TEXT.operationsTabs.overview, path: '/operations-dashboard', hint: '현재 applied 전략과 오늘 파이프라인 상태' },
  { id: 'scanner', label: UI_TEXT.operationsTabs.scanner, path: '/operations-dashboard/scanner', hint: '장중 후보와 blocked reason 관찰' },
  { id: 'performance', label: UI_TEXT.operationsTabs.performance, path: '/operations-dashboard/performance', hint: '체결/운용 성과 추적' },
];

const LAB_TABS: Array<{ id: LabTab; label: string; path: string; hint: string }> = [
  { id: 'validation', label: UI_TEXT.labTabs.validation, path: '/lab/validation', hint: '백테스트 · 검증 · 재검증' },
  { id: 'strategies', label: UI_TEXT.labTabs.strategies, path: '/lab/strategies', hint: '실험용 프리셋 생성 · 복제 · 삭제' },
  { id: 'universe', label: UI_TEXT.labTabs.universe, path: '/lab/universe', hint: '실험용 유니버스 비교' },
];

const RESEARCH_TABS: Array<{ id: ResearchTab; label: string; path: string; hint: string }> = [
  { id: 'today-report', label: UI_TEXT.analysisTabs.todayReport, path: '/research-ai/brief', hint: '오늘 시장 브리프와 실행 포인트' },
  { id: 'alerts', label: UI_TEXT.analysisTabs.alerts, path: '/research-ai/alerts', hint: '리스크 알림과 대응 포인트' },
  { id: 'watch-decision', label: UI_TEXT.analysisTabs.watchDecision, path: '/research-ai/watch-decisions', hint: '관심 시나리오 검토' },
  { id: 'watchlist', label: UI_TEXT.analysisTabs.watchlist, path: '/research-ai/watchlist', hint: '관심 종목 저장과 분석' },
  { id: 'research', label: UI_TEXT.analysisTabs.research, path: '/research-ai/research', hint: '리서치 스냅샷 조회' },
];

const PAGE_COPY: Record<WorkspacePage, string> = {
  'operations-dashboard': '운영자가 자동거래 파이프라인 상태를 첫 화면에서 이해하도록 구성한 관제 홈입니다.',
  'orders-execution': '주문 lifecycle, blocked reason, 체결 상태를 운영 관점에서 추적합니다.',
  'strategy-operations': '운영 반영 대상 전략의 approved/applied 상태와 런타임 반영 여부를 봅니다.',
  lab: '백테스트, 탐색, 검증, 프리셋 실험은 이 영역에서만 수행합니다.',
  'research-ai': '리서치, 시장 데이터, AI 인사이트를 실행 판단과 분리해 조회합니다.',
  settings: 'draft, saved, displayed 설정 상태와 공유 저장 기준을 한곳에서 관리합니다.',
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
    researchTab: 'today-report',
    canonicalPath: '/operations-dashboard',
    search: normalizeSearch(search),
  };
}

function withDefaults(partial: Partial<RouteState> & Pick<RouteState, 'page' | 'canonicalPath'>, search = ''): RouteState {
  return {
    dashboardTab: 'overview',
    labTab: 'validation',
    researchTab: 'today-report',
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
    '/operations/performance': '/operations-dashboard/performance',
    '/operations/orders': '/orders-execution',
    '/operations/strategies': '/strategy-operations',
    '/console/strategies': '/strategy-operations',
    '/console/scanner': '/operations-dashboard/scanner',
    '/console/orders': '/orders-execution',
    '/console/performance': '/operations-dashboard/performance',
    '/console/watchlist': '/research-ai/watchlist',
    '/console/research': '/research-ai/research',
    '/console/validation': '/lab/validation',
    '/console/validation-lab': '/lab/validation',
    '/console/universe': '/lab/universe',
    '/reports': '/research-ai/brief',
    '/reports/today-report': '/research-ai/brief',
    '/reports/today': '/research-ai/brief',
    '/reports/recommendations': '/research-ai/brief',
    '/reports/today-recommendations': '/research-ai/brief',
    '/reports/alerts': '/research-ai/alerts',
    '/reports/watch-decision': '/research-ai/watch-decisions',
    '/reports/action-board': '/research-ai/alerts',
    '/analysis/brief': '/research-ai/brief',
    '/analysis/alerts': '/research-ai/alerts',
    '/analysis/watch-decisions': '/research-ai/watch-decisions',
    '/analysis/watchlist': '/research-ai/watchlist',
    '/analysis/research': '/research-ai/research',
    '/signals': '/operations-dashboard/scanner',
    '/paper': '/orders-execution',
    '/backtest': '/lab/validation',
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
  if (path === '/orders-execution') {
    return withDefaults({ page: 'orders-execution', canonicalPath: '/orders-execution' }, normalizedSearch);
  }
  if (path === '/strategy-operations') {
    return withDefaults({ page: 'strategy-operations', canonicalPath: '/strategy-operations' }, normalizedSearch);
  }
  if (path.startsWith('/lab/')) {
    const segment = path.replace('/lab/', '');
    const found = LAB_TABS.find((tab) => tab.id === segment);
    if (found) {
      return withDefaults({ page: 'lab', labTab: found.id, canonicalPath: found.path }, normalizedSearch);
    }
    return normalize('/lab/validation');
  }
  if (path.startsWith('/research-ai/')) {
    const segment = path.replace('/research-ai/', '');
    const normalizedSegment = segment === 'brief'
      ? 'today-report'
      : segment === 'watch-decisions'
        ? 'watch-decision'
        : segment;
    const found = RESEARCH_TABS.find((tab) => tab.id === normalizedSegment);
    if (found) {
      return withDefaults({ page: 'research-ai', researchTab: found.id, canonicalPath: found.path }, normalizedSearch);
    }
    return normalize('/research-ai/brief');
  }
  if (path === '/settings') {
    return withDefaults({ page: 'settings', canonicalPath: '/settings' }, normalizedSearch);
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

      <aside className="app-sidebar" aria-label="Workspace navigation">
        <div className="app-sidebar-brand">
          <div className="app-sidebar-kicker">WealthPulse</div>
          <div className="app-sidebar-title">Operator Workspace</div>
          <div className="app-sidebar-copy">{PAGE_COPY[route.page]}</div>
        </div>

        <div className="app-sidebar-group">
          <div className="app-sidebar-group-label">Workspace</div>
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
                <span className="app-nav-help">{page.hint}</span>
              </span>
            </button>
          ))}
        </div>

        {(route.page === 'operations-dashboard' || route.page === 'lab' || route.page === 'research-ai') && (
          <div className="app-sidebar-group">
            <div className="app-sidebar-group-label">
              {route.page === 'operations-dashboard' ? '운영 보조 화면' : route.page === 'lab' ? '실험 화면' : '리서치/AI 화면'}
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
                  <span className="app-nav-help">{tab.hint}</span>
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
                  <span className="app-nav-help">{tab.hint}</span>
                </span>
              </button>
            ))}
            {route.page === 'research-ai' && RESEARCH_TABS.map((tab, index) => (
              <button
                key={tab.id}
                onClick={() => navigateTo(tab.path)}
                className={`app-nav-button is-sub ${route.researchTab === tab.id ? 'active' : ''}`}
                aria-current={route.researchTab === tab.id ? 'page' : undefined}
              >
                <span className="app-nav-step">{String(index + 1).padStart(2, '0')}</span>
                <span className="app-nav-label-wrap">
                  <span className="app-nav-label">{tab.label}</span>
                  <span className="app-nav-help">{tab.hint}</span>
                </span>
              </button>
            ))}
          </div>
        )}

        <div className="app-sidebar-foot">
          <span className={`app-chrome-pill ${loading ? 'is-live' : ''}`}>{loading ? 'Syncing' : 'Ready'}</span>
          <span className="app-chrome-pill">{FEATURE_FLAGS.refactorBundleDNavigation ? 'Bundle D IA' : 'Legacy IA'}</span>
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
              onGoAnalysis={() => navigateTo('/research-ai/brief')}
            />
          )}
          {route.page === 'operations-dashboard' && route.dashboardTab === 'scanner' && <ScannerPage {...sharedProps} />}
          {route.page === 'operations-dashboard' && route.dashboardTab === 'performance' && <PerformancePage {...sharedProps} />}

          {route.page === 'orders-execution' && <PaperPortfolioPage {...sharedProps} />}
          {route.page === 'strategy-operations' && <StrategiesPage {...sharedProps} mode="operations" />}

          {route.page === 'lab' && route.labTab === 'validation' && <BacktestValidationPage {...sharedProps} />}
          {route.page === 'lab' && route.labTab === 'strategies' && <StrategiesPage {...sharedProps} mode="lab" />}
          {route.page === 'lab' && route.labTab === 'universe' && <UniversePage {...sharedProps} />}

          {route.page === 'research-ai' && ['today-report', 'alerts', 'watch-decision'].includes(route.researchTab) && (
            <ReportsPage
              {...sharedProps}
              reportTab={route.researchTab as 'today-report' | 'alerts' | 'watch-decision'}
            />
          )}
          {route.page === 'research-ai' && route.researchTab === 'watchlist' && <WatchlistPage {...sharedProps} />}
          {route.page === 'research-ai' && route.researchTab === 'research' && <ResearchSnapshotsPage {...sharedProps} />}

          {route.page === 'settings' && (
            <SettingsPage
              {...sharedProps}
              onOpenLab={() => navigateTo('/lab/validation')}
              onOpenStrategyStatus={() => navigateTo('/strategy-operations')}
            />
          )}
        </div>
      </main>
    </div>
  );
}
