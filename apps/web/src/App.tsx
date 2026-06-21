import { useEffect, useState } from 'react';
import { UI_TEXT } from './constants/uiText';
import { useConsoleData } from './hooks/useConsoleData';
import { RuntimePortfolioPage } from './pages/RuntimePortfolioPage';
import { CandidateResearchPage } from './pages/CandidateResearchPage';
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
  { id: 'agent-dashboard', label: '운용', path: '/agent-dashboard', hint: '자산과 손익' },
  { id: 'research-ai', label: '리서치', path: '/research-ai', hint: '성공과 실패' },
  { id: 'orders-execution', label: '주문', path: '/orders-execution', hint: '주문과 보유' },
  { id: 'watchlist', label: '관심', path: '/watchlist', hint: '관심 종목' },
  { id: 'lab', label: '관리', path: '/lab/strategies', hint: '전략과 종목군' },
];

const LAB_TABS: Array<{ id: LabTab; label: string; path: string; hint: string }> = [
  { id: 'strategies', label: UI_TEXT.labTabs.strategies, path: '/lab/strategies', hint: '프리셋' },
  { id: 'universe', label: UI_TEXT.labTabs.universe, path: '/lab/universe', hint: '종목군' },
];

const PAGE_COPY: Record<WorkspacePage, string> = {
  'agent-dashboard': '',
  'research-ai': '',
  'orders-execution': '',
  watchlist: '',
  lab: '',
};

function normalizeSearch(search = ''): string {
  if (!search) return '';
  return search.startsWith('?') ? search : `?${search}`;
}

function buildUrl(path: string, search = ''): string {
  return `${path}${normalizeSearch(search)}`;
}

function withDefaults(partial: Partial<RouteState> & Pick<RouteState, 'page' | 'canonicalPath'>, search = ''): RouteState {
  return {
    dashboardTab: 'overview',
    labTab: 'strategies',
    researchTab: 'research',
    search: normalizeSearch(search),
    ...partial,
  };
}

function defaultRouteState(search = ''): RouteState {
  return withDefaults({ page: 'agent-dashboard', canonicalPath: '/agent-dashboard' }, search);
}

function toRouteState(pathname: string, search = ''): RouteState {
  const path = pathname.toLowerCase().replace(/\/$/, '') || '/';
  const normalizedSearch = normalizeSearch(search);

  if (path === '/' || path === '/agent-dashboard') {
    return withDefaults({ page: 'agent-dashboard', canonicalPath: '/agent-dashboard' }, normalizedSearch);
  }
  if (path === '/research-ai') {
    return withDefaults({ page: 'research-ai', researchTab: 'research', canonicalPath: '/research-ai' }, normalizedSearch);
  }
  if (path === '/signal-review') {
    return withDefaults({ page: 'orders-execution', canonicalPath: '/orders-execution' }, normalizedSearch);
  }
  if (path === '/orders-execution') {
    return withDefaults({ page: 'orders-execution', canonicalPath: '/orders-execution' }, normalizedSearch);
  }
  if (path === '/performance') {
    return withDefaults({ page: 'agent-dashboard', canonicalPath: '/agent-dashboard' }, normalizedSearch);
  }
  if (path === '/watchlist') {
    return withDefaults({ page: 'watchlist', canonicalPath: '/watchlist' }, normalizedSearch);
  }
  if (path === '/operations-dashboard') {
    return withDefaults({ page: 'agent-dashboard', canonicalPath: '/agent-dashboard' }, normalizedSearch);
  }
  if (path.startsWith('/lab/')) {
    const segment = path.replace('/lab/', '');
    const found = LAB_TABS.find((tab) => tab.id === segment);
    if (found) {
      return withDefaults({ page: 'lab', labTab: found.id, canonicalPath: found.path }, normalizedSearch);
    }
    return withDefaults({ page: 'lab', labTab: 'strategies', canonicalPath: '/lab/strategies' }, normalizedSearch);
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
  const activeLabTab = LAB_TABS.find((tab) => tab.id === route.labTab);
  const activeLabel = route.page === 'lab' ? activeLabTab?.label || activePage.label : activePage.label;
  const activeHint = route.page === 'lab' ? activeLabTab?.hint || activePage.hint : activePage.hint;

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
              <div className="app-sidebar-title">WealthPulse</div>
            </div>
            <div className="app-sidebar-meta">
              <span className="app-live-pill">감시 중</span>
              <span className="app-sidebar-clock">{clockText}</span>
            </div>
          </div>
          <div className="app-sidebar-copy">{PAGE_COPY[route.page]}</div>
        </div>

        <div className="app-sidebar-group">
          <div className="app-sidebar-group-label">메뉴</div>
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

        {route.page === 'lab' && (
          <div className="app-sidebar-group">
            <div className="app-sidebar-group-label">실험</div>
            {LAB_TABS.map((tab, index) => (
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
          <span className="app-chrome-pill">자동투자</span>
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
          {route.page === 'agent-dashboard' && (
            <WealthPulseHomePage
              {...sharedProps}
              onGoLab={() => navigateTo('/lab/strategies')}
            />
          )}
          {route.page === 'research-ai' && <CandidateResearchPage {...sharedProps} />}
          {route.page === 'orders-execution' && <RuntimePortfolioPage {...sharedProps} />}
          {route.page === 'watchlist' && <WatchlistPage {...sharedProps} />}

          {route.page === 'lab' && route.labTab === 'strategies' && <StrategiesPage {...sharedProps} />}
          {route.page === 'lab' && route.labTab === 'universe' && <UniversePage {...sharedProps} />}
        </div>
      </main>
    </div>
  );
}
