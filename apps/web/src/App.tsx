import { useEffect, useState } from 'react';
import { UI_TEXT } from './constants/uiText';
import { useConsoleData } from './hooks/useConsoleData';
import { AgentDashboardPage } from './pages/AgentDashboardPage';
import { BacktestValidationPage } from './pages/BacktestValidationPage';
import { PaperPortfolioPage } from './pages/PaperPortfolioPage';
import { PerformancePage } from './pages/PerformancePage';
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
  { id: 'agent-dashboard', label: 'Agent 관제', path: '/agent-dashboard', hint: 'Hermes 판단 · Risk Gate · Runtime 주문 감사' },
  { id: 'research-ai', label: '종목 선정/리서치', path: '/research-ai', hint: '5대 후보 입력원과 Research Snapshot' },
  { id: 'signal-review', label: '신호/리스크', path: '/signal-review', hint: 'Layer A~E 신호와 차단 사유 검토' },
  { id: 'orders-execution', label: '주문/포트폴리오', path: '/orders-execution', hint: 'Runtime 주문 · 포지션 · 체결 이력' },
  { id: 'performance', label: '성과/회고', path: '/performance', hint: '체결 성과와 에이전트 의사결정 회고' },
  { id: 'watchlist', label: UI_TEXT.analysisTabs.watchlist, path: '/watchlist', hint: '사용자 관심 종목 입력원 관리' },
  { id: 'lab', label: '실험실', path: '/lab/validation', hint: '백테스트 · 전략 프리셋 · 유니버스 검증' },
  { id: 'operations-dashboard', label: '운영 개요', path: '/operations-dashboard', hint: '전체 상태 요약과 시장/포트폴리오 개요' },
];

const LAB_TABS: Array<{ id: LabTab; label: string; path: string; hint: string }> = [
  { id: 'validation', label: UI_TEXT.labTabs.validation, path: '/lab/validation', hint: '백테스트 · 검증 · 재검증' },
  { id: 'strategies', label: UI_TEXT.labTabs.strategies, path: '/lab/strategies', hint: '실험용 프리셋 생성 · 복제 · 삭제' },
  { id: 'universe', label: UI_TEXT.labTabs.universe, path: '/lab/universe', hint: '실험용 유니버스 비교' },
];

const PAGE_COPY: Record<WorkspacePage, string> = {
  'agent-dashboard': '자동거래의 현재 중심입니다. Hermes 판단, Risk Gate, Runtime 주문 감사를 이 화면에서 먼저 봅니다.',
  'research-ai': '거래대금 상위, 등락률 상위, 뉴스 급증, 보유 종목, 관심 종목을 후보 입력원으로 모읍니다.',
  'signal-review': '후보가 어떤 레이어에서 허용·차단됐는지 점검합니다. 주문 버튼보다 근거 확인이 우선입니다.',
  'orders-execution': 'Risk Gate를 통과한 Runtime 주문과 포트폴리오 상태를 확인합니다.',
  performance: '주문 접수와 실제 체결 성과를 분리해 에이전트 결정을 회고합니다.',
  watchlist: '사용자 의도를 반영하는 관심 종목 입력원을 관리합니다.',
  lab: '백테스트, 전략, 유니버스 실험은 운영 흐름과 분리된 실험실에서만 다룹니다.',
  'operations-dashboard': '운영자가 전체 시스템 상태를 빠르게 훑어보는 보조 요약 화면입니다.',
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
    labTab: 'validation',
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
    return withDefaults({ page: 'signal-review', canonicalPath: '/signal-review' }, normalizedSearch);
  }
  if (path === '/orders-execution') {
    return withDefaults({ page: 'orders-execution', canonicalPath: '/orders-execution' }, normalizedSearch);
  }
  if (path === '/performance') {
    return withDefaults({ page: 'performance', canonicalPath: '/performance' }, normalizedSearch);
  }
  if (path === '/watchlist') {
    return withDefaults({ page: 'watchlist', canonicalPath: '/watchlist' }, normalizedSearch);
  }
  if (path === '/operations-dashboard') {
    return withDefaults({ page: 'operations-dashboard', dashboardTab: 'overview', canonicalPath: '/operations-dashboard' }, normalizedSearch);
  }
  if (path.startsWith('/lab/')) {
    const segment = path.replace('/lab/', '');
    const found = LAB_TABS.find((tab) => tab.id === segment);
    if (found) {
      return withDefaults({ page: 'lab', labTab: found.id, canonicalPath: found.path }, normalizedSearch);
    }
    return withDefaults({ page: 'lab', labTab: 'validation', canonicalPath: '/lab/validation' }, normalizedSearch);
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
              <div className="app-sidebar-title">Agent 운영 작업 공간</div>
            </div>
            <div className="app-sidebar-meta">
              <span className="app-live-pill">WATCH</span>
              <span className="app-sidebar-clock">{clockText}</span>
            </div>
          </div>
          <div className="app-sidebar-copy">{PAGE_COPY[route.page]}</div>
        </div>

        <div className="app-sidebar-group">
          <div className="app-sidebar-group-label">Agent-primary 흐름</div>
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
            <div className="app-sidebar-group-label">실험 화면</div>
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
          <span className="app-chrome-pill">Agent-primary</span>
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
          {route.page === 'agent-dashboard' && <AgentDashboardPage {...sharedProps} />}
          {route.page === 'research-ai' && <CandidateResearchPage {...sharedProps} />}
          {route.page === 'signal-review' && <ScannerPage {...sharedProps} />}
          {route.page === 'orders-execution' && <PaperPortfolioPage {...sharedProps} />}
          {route.page === 'performance' && <PerformancePage {...sharedProps} />}
          {route.page === 'watchlist' && <WatchlistPage {...sharedProps} />}
          {route.page === 'operations-dashboard' && (
            <WealthPulseHomePage
              {...sharedProps}
              onGoLab={() => navigateTo('/lab/validation')}
              onGoAnalysis={() => navigateTo('/research-ai')}
            />
          )}

          {route.page === 'lab' && route.labTab === 'validation' && <BacktestValidationPage {...sharedProps} />}
          {route.page === 'lab' && route.labTab === 'strategies' && <StrategiesPage {...sharedProps} />}
          {route.page === 'lab' && route.labTab === 'universe' && <UniversePage {...sharedProps} />}
        </div>
      </main>
    </div>
  );
}
