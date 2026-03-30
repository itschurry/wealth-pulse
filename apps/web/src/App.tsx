import { useEffect, useState } from 'react';
import { UI_TEXT } from './constants/uiText';
import { useConsoleData } from './hooks/useConsoleData';
import { useValidationSettingsStore } from './hooks/useValidationSettingsStore';
import { BacktestValidationPage } from './pages/BacktestValidationPage';
import { OverviewPage } from './pages/OverviewPage';
import { PaperPortfolioPage } from './pages/PaperPortfolioPage';
import { ReportsPage } from './pages/ReportsPage';
import { SignalsPage } from './pages/SignalsPage';
import type { ConsoleTab, ReportTab, TopSection } from './types/navigation';

interface RouteState {
  section: TopSection;
  consoleTab: ConsoleTab;
  reportTab: ReportTab;
  canonicalPath: string;
}

const CONSOLE_TABS: Array<{ id: ConsoleTab; label: string; path: string }> = [
  { id: 'overview', label: UI_TEXT.consoleTabs.overview, path: '/console/overview' },
  { id: 'signals', label: UI_TEXT.consoleTabs.signals, path: '/console/signals' },
  { id: 'paper', label: UI_TEXT.consoleTabs.paper, path: '/console/paper' },
  { id: 'validation', label: UI_TEXT.consoleTabs.validation, path: '/console/validation' },
];

const REPORT_TABS: Array<{ id: ReportTab; label: string; path: string }> = [
  { id: 'today-report', label: UI_TEXT.reportTabs.todayReport, path: '/reports/today-report' },
  { id: 'action-board', label: UI_TEXT.reportTabs.actionBoard, path: '/reports/action-board' },
  { id: 'watch-decision', label: UI_TEXT.reportTabs.watchDecision, path: '/reports/watch-decision' },
];

const SECTION_COPY: Record<TopSection, string> = {
  console: '실행 상태 확인, 제어, 검증 실행 같은 운영 작업용 화면입니다.',
  reports: '오늘 판단, 우선순위, 체크리스트를 읽는 브리핑 화면입니다.',
};

const SECTION_BADGE: Record<TopSection, string> = {
  console: 'Operator Console',
  reports: 'Decision Reports',
};

function toRouteState(pathname: string): RouteState {
  const path = pathname.toLowerCase();
  const normalize = (nextPath: string): RouteState => toRouteState(nextPath);

  const legacyRedirects: Record<string, string> = {
    '/overview': '/console/overview',
    '/signals': '/console/signals',
    '/paper': '/console/paper',
    '/backtest': '/console/validation',
    '/reports': '/reports/today-report',
    '/console/backtest': '/console/validation',
    '/reports/today': '/reports/today-report',
    '/reports/recommendations': '/reports/today-report',
    '/reports/today-recommendations': '/reports/today-report',
    '/': '/console/overview',
  };
  if (legacyRedirects[path]) return normalize(legacyRedirects[path]);

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

  return normalize('/console/overview');
}

function pushPath(path: string) {
  history.pushState(null, '', path);
}

function replacePath(path: string) {
  history.replaceState(null, '', path);
}

export default function App() {
  const [route, setRoute] = useState<RouteState>(() => toRouteState(location.pathname));
  const { snapshot, loading, hasError, errorMessage, refresh } = useConsoleData();
  const validationSettings = useValidationSettingsStore();
  const activeConsoleTab = CONSOLE_TABS.find((tab) => tab.id === route.consoleTab);
  const activeReportTab = REPORT_TABS.find((tab) => tab.id === route.reportTab);
  const activeLabel = route.section === 'console'
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
      if (location.pathname !== next.canonicalPath) {
        replacePath(next.canonicalPath);
      }
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  function moveToSection(section: TopSection) {
    const targetPath = section === 'console' ? '/console/overview' : '/reports/today-report';
    const next = toRouteState(targetPath);
    pushPath(next.canonicalPath);
    setRoute(next);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function moveToConsoleTab(tab: ConsoleTab) {
    const target = CONSOLE_TABS.find((item) => item.id === tab);
    if (!target) return;
    const next = toRouteState(target.path);
    pushPath(next.canonicalPath);
    setRoute(next);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function moveToReportTab(tab: ReportTab) {
    const target = REPORT_TABS.find((item) => item.id === tab);
    if (!target) return;
    const next = toRouteState(target.path);
    pushPath(next.canonicalPath);
    setRoute(next);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  const sharedProps = {
    snapshot,
    loading,
    errorMessage: hasError ? errorMessage : '',
    onRefresh: refresh,
  };

  return (
    <>
      <div className="app-chrome-shell">
        <div className="app-chrome-header">
          <div>
            <div className="app-chrome-kicker">Daily Market Brief</div>
            <div className="app-chrome-title">{activeLabel}</div>
            <div className="app-chrome-copy">{SECTION_COPY[route.section]}</div>
          </div>
          <div className="app-chrome-meta">
            <span className={`app-chrome-pill ${loading ? 'is-live' : ''}`}>{loading ? 'Syncing' : 'Ready'}</span>
            <span className="app-chrome-pill">{SECTION_BADGE[route.section]}</span>
            {route.section === 'console' && validationSettings.unsaved && (
              <span className="app-chrome-pill is-warning">Validation draft</span>
            )}
          </div>
        </div>

        <div className="tab-shell">
          <div className="tab-shell-row">
            <div className="tab-strip">
              <button
                onClick={() => moveToSection('console')}
                className={`tab-button ${route.section === 'console' ? 'active' : ''}`}
                aria-current={route.section === 'console' ? 'page' : undefined}
              >
                <span className="tab-step">01</span>
                <span className="tab-label">{UI_TEXT.topTabs.console}</span>
              </button>
              <button
                onClick={() => moveToSection('reports')}
                className={`tab-button ${route.section === 'reports' ? 'active' : ''}`}
                aria-current={route.section === 'reports' ? 'page' : undefined}
              >
                <span className="tab-step">02</span>
                <span className="tab-label">{UI_TEXT.topTabs.reports}</span>
              </button>
            </div>
          </div>
        </div>

        <div className="tab-shell tab-shell-secondary">
          <div className="tab-shell-row">
            <div className="tab-strip">
              {route.section === 'console' && CONSOLE_TABS.map((tab, index) => (
                <button
                  key={tab.id}
                  onClick={() => moveToConsoleTab(tab.id)}
                  className={`tab-button ${route.consoleTab === tab.id ? 'active' : ''}`}
                  aria-current={route.consoleTab === tab.id ? 'page' : undefined}
                >
                  <span className="tab-step">{String(index + 1).padStart(2, '0')}</span>
                  <span className="tab-label">
                    {tab.label}
                    {tab.id === 'validation' && validationSettings.unsaved && (
                      <span className="tab-dirty-badge" aria-label="저장 필요">저장 필요</span>
                    )}
                  </span>
                </button>
              ))}
              {route.section === 'reports' && REPORT_TABS.map((tab, index) => (
                <button
                  key={tab.id}
                  onClick={() => moveToReportTab(tab.id)}
                  className={`tab-button ${route.reportTab === tab.id ? 'active' : ''}`}
                  aria-current={route.reportTab === tab.id ? 'page' : undefined}
                >
                  <span className="tab-step">{String(index + 1).padStart(2, '0')}</span>
                  <span className="tab-label">{tab.label}</span>
                </button>
              ))}
            </div>
          </div>
          <div className="tab-shell-caption">
            <span className="tab-shell-caption-title">{SECTION_BADGE[route.section]}</span>
            <span className="tab-shell-caption-copy">{SECTION_COPY[route.section]}</span>
          </div>
        </div>
      </div>

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
    </>
  );
}
