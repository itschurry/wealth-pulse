import { useEffect, useState } from 'react';
import { UI_TEXT } from './constants/uiText';
import { useConsoleData } from './hooks/useConsoleData';
import { useValidationSettingsStore } from './hooks/useValidationSettingsStore';
import { BacktestValidationPage } from './pages/BacktestValidationPage';
import { OverviewPage } from './pages/OverviewPage';
import { PaperPortfolioPage } from './pages/PaperPortfolioPage';
import { ReportsPage } from './pages/ReportsPage';
import { SignalsPage } from './pages/SignalsPage';
import { WealthPulseHomePage } from './pages/WealthPulseHomePage';
import type { ConsoleTab, ReportTab, TopSection } from './types/navigation';

interface RouteState {
  section: TopSection;
  consoleTab: ConsoleTab;
  reportTab: ReportTab;
  canonicalPath: string;
}

const CONSOLE_TABS: Array<{ id: ConsoleTab; label: string; path: string; hint: string }> = [
  { id: 'overview', label: UI_TEXT.consoleTabs.overview, path: '/console/overview', hint: '운용 현황과 핵심 지표' },
  { id: 'signals', label: UI_TEXT.consoleTabs.signals, path: '/console/signals', hint: '후보군 필터와 실행 판단' },
  { id: 'paper', label: UI_TEXT.consoleTabs.paper, path: '/console/paper', hint: 'Paper 계좌와 주문 상태' },
  { id: 'validation', label: UI_TEXT.consoleTabs.validation, path: '/console/validation', hint: '설정 저장, 백테스트, 재검증' },
];

const REPORT_TABS: Array<{ id: ReportTab; label: string; path: string; hint: string }> = [
  { id: 'today-report', label: UI_TEXT.reportTabs.todayReport, path: '/reports/today-report', hint: '오늘 시장 브리프와 해석' },
  { id: 'alerts', label: UI_TEXT.reportTabs.alerts, path: '/reports/alerts', hint: '리스크 알림과 대응 포인트' },
  { id: 'watch-decision', label: UI_TEXT.reportTabs.watchDecision, path: '/reports/watch-decision', hint: '관심 종목 시나리오 검토' },
];

const SECTION_COPY: Record<TopSection, string> = {
  home: '포트폴리오 상태와 오늘의 실행 포인트를 빠르게 확인합니다.',
  console: '전략 설정 저장부터 백테스트와 실행 준비까지 한 화면에서 운영합니다.',
  reports: '시장 해석과 시나리오를 읽고 실행 아이디어로 연결합니다.',
};

const SECTION_BADGE: Record<TopSection, string> = {
  home: 'Portfolio + Signals + Risk',
  console: 'Validation + Execution + Observability',
  reports: 'Research + Scenarios + Decisions',
};

function toRouteState(pathname: string): RouteState {
  const path = pathname.toLowerCase();
  const normalize = (nextPath: string): RouteState => toRouteState(nextPath);

  const legacyRedirects: Record<string, string> = {
    '/home': '/',
    '/dashboard': '/',
    '/overview': '/console/overview',
    '/signals': '/console/signals',
    '/paper': '/console/paper',
    '/backtest': '/console/validation',
    '/reports': '/reports/today-report',
    '/console/backtest': '/console/validation',
    '/reports/today': '/reports/today-report',
    '/reports/recommendations': '/reports/today-report',
    '/reports/today-recommendations': '/reports/today-report',
    '/reports/action-board': '/reports/alerts',
  };
  if (legacyRedirects[path]) return normalize(legacyRedirects[path]);

  if (path === '/') {
    return {
      section: 'home',
      consoleTab: 'overview',
      reportTab: 'today-report',
      canonicalPath: '/',
    };
  }

  if (path.startsWith('/console/')) {
    const segment = path.replace('/console/', '');
    const found = CONSOLE_TABS.find((tab) => tab.id === segment);
    if (found) {
      return {
        section: 'console',
        consoleTab: found.id,
        reportTab: 'today-report',
        canonicalPath: found.path,
      };
    }
    return normalize('/console/overview');
  }

  if (path.startsWith('/reports/')) {
    const segment = path.replace('/reports/', '');
    const found = REPORT_TABS.find((tab) => tab.id === segment);
    if (found) {
      return {
        section: 'reports',
        consoleTab: 'overview',
        reportTab: found.id,
        canonicalPath: found.path,
      };
    }
    return normalize('/reports/today-report');
  }

  return normalize('/');
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
  const { snapshot, loading, hasError, errorMessage, refresh } = useConsoleData();
  const validationSettings = useValidationSettingsStore();
  const activeConsoleTab = CONSOLE_TABS.find((tab) => tab.id === route.consoleTab);
  const activeReportTab = REPORT_TABS.find((tab) => tab.id === route.reportTab);
  const notifications = snapshot.notifications || {};
  const alertingDisabled = !notifications.enabled;
  const alertingUnconfigured = Boolean(notifications.enabled) && !(notifications.configured && notifications.chat_id_configured);
  const activeLabel = route.section === 'home'
    ? UI_TEXT.topTabs.home
    : route.section === 'console'
      ? activeConsoleTab?.label || UI_TEXT.consoleTabs.overview
      : activeReportTab?.label || UI_TEXT.reportTabs.todayReport;

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
    const targetPath = section === 'home'
      ? '/'
      : section === 'console'
        ? '/console/overview'
        : '/reports/today-report';
    const next = toRouteState(targetPath);
    pushPath(next.canonicalPath);
    setRoute(next);
    setMobileNavOpen(false);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function moveToConsoleTab(tab: ConsoleTab) {
    const target = CONSOLE_TABS.find((item) => item.id === tab);
    if (!target) return;
    const next = toRouteState(target.path);
    pushPath(next.canonicalPath);
    setRoute(next);
    setMobileNavOpen(false);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function moveToReportTab(tab: ReportTab) {
    const target = REPORT_TABS.find((item) => item.id === tab);
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
          <div className="app-sidebar-title">Investor Workspace</div>
          <div className="app-sidebar-copy">{SECTION_COPY[route.section]}</div>
        </div>

        <div className="app-sidebar-group">
          <div className="app-sidebar-group-label">Workspace</div>
          <button
            onClick={() => moveToSection('home')}
            className={`app-nav-button ${route.section === 'home' ? 'active' : ''}`}
            aria-current={route.section === 'home' ? 'page' : undefined}
          >
            <span className="app-nav-step">01</span>
            <span className="app-nav-label-wrap">
              <span className="app-nav-label">{UI_TEXT.topTabs.home}</span>
              <span className="app-nav-help">포트폴리오 · 신호 · 리스크 요약</span>
            </span>
          </button>
          <button
            onClick={() => moveToSection('console')}
            className={`app-nav-button ${route.section === 'console' ? 'active' : ''}`}
            aria-current={route.section === 'console' ? 'page' : undefined}
          >
            <span className="app-nav-step">02</span>
            <span className="app-nav-label-wrap">
              <span className="app-nav-label">{UI_TEXT.topTabs.console}</span>
              <span className="app-nav-help">설정 · 실행 · 상태 운영</span>
            </span>
          </button>
          <button
            onClick={() => moveToSection('reports')}
            className={`app-nav-button ${route.section === 'reports' ? 'active' : ''}`}
            aria-current={route.section === 'reports' ? 'page' : undefined}
          >
            <span className="app-nav-step">03</span>
            <span className="app-nav-label-wrap">
              <span className="app-nav-label">{UI_TEXT.topTabs.reports}</span>
              <span className="app-nav-help">시장 브리프 · 시나리오 의사결정</span>
            </span>
          </button>
        </div>

        {route.section !== 'home' && (
          <div className="app-sidebar-group">
            <div className="app-sidebar-group-label">{route.section === 'console' ? 'Console Views' : 'Report Views'}</div>
            {route.section === 'console' && CONSOLE_TABS.map((tab, index) => (
              <button
                key={tab.id}
                onClick={() => moveToConsoleTab(tab.id)}
                className={`app-nav-button is-sub ${route.consoleTab === tab.id ? 'active' : ''}`}
                aria-current={route.consoleTab === tab.id ? 'page' : undefined}
              >
                <span className="app-nav-step">{String(index + 1).padStart(2, '0')}</span>
                <span className="app-nav-label-wrap">
                  <span className="app-nav-label">
                    {tab.label}
                    {tab.id === 'validation' && validationSettings.unsaved && (
                      <span className="tab-dirty-badge" aria-label="저장 필요">저장 필요</span>
                    )}
                  </span>
                  <span className="app-nav-help">{tab.hint}</span>
                </span>
              </button>
            ))}
            {route.section === 'reports' && REPORT_TABS.map((tab, index) => (
              <button
                key={tab.id}
                onClick={() => moveToReportTab(tab.id)}
                className={`app-nav-button is-sub ${route.reportTab === tab.id ? 'active' : ''}`}
                aria-current={route.reportTab === tab.id ? 'page' : undefined}
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
          <span className="app-chrome-pill">{SECTION_BADGE[route.section]}</span>
          {route.section === 'console' && validationSettings.unsaved && (
            <span className="app-chrome-pill is-warning">Validation draft</span>
          )}
          {(alertingDisabled || alertingUnconfigured) && (
            <span className="app-chrome-pill is-warning">Alerting check</span>
          )}
        </div>
      </aside>

      <main className="app-main">
        <header className="app-main-header">
          <div>
            <div className="app-main-kicker">Current Workspace</div>
            <h1 className="app-main-title">{activeLabel}</h1>
            <div className="app-main-copy">{SECTION_COPY[route.section]}</div>
          </div>
        </header>

        {(alertingDisabled || alertingUnconfigured) && (
          <div className="app-alert-banner" role="alert">
            <strong>{alertingDisabled ? '알림 발송이 꺼져 있음' : '알림 채널 설정 미완료'}</strong>
            <span>
              {alertingDisabled
                ? '텔레그램/운영 알림이 비활성이라 실패 주문·엔진 이상을 놓칠 수 있습니다. Reports → 리스크 알림에서 바로 확인하세요.'
                : '채널은 켜져 있지만 chat_id 또는 연결 설정이 끝나지 않았습니다. Reports → 리스크 알림에서 연결 상태를 마무리하세요.'}
            </span>
          </div>
        )}

        <div className="app-main-content">
          {route.section === 'home' && (
            <WealthPulseHomePage
              {...sharedProps}
              onGoConsole={() => moveToSection('console')}
              onGoReports={() => moveToSection('reports')}
            />
          )}
          {route.section === 'console' && route.consoleTab === 'overview' && <OverviewPage {...sharedProps} />}
          {route.section === 'console' && route.consoleTab === 'signals' && <SignalsPage {...sharedProps} />}
          {route.section === 'console' && route.consoleTab === 'paper' && <PaperPortfolioPage {...sharedProps} />}
          {route.section === 'console' && route.consoleTab === 'validation' && <BacktestValidationPage {...sharedProps} />}
          {route.section === 'reports' && (
            <ReportsPage
              {...sharedProps}
              reportTab={route.reportTab}
            />
          )}
        </div>
      </main>
    </div>
  );
}
