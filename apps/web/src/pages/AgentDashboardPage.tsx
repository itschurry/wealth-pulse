import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  fetchAgentBrokerStatus,
  fetchAgentDecisions,
  fetchAgentOrders,
  fetchAgentRiskConfig,
  fetchAgentRuns,
  runAgent,
} from '../api/domain';
import { ConsoleActionBar } from '../components/ConsoleActionBar';
import type {
  AgentBrokerStatusResponse,
  AgentDecisionItem,
  AgentOrderItem,
  AgentRiskConfigResponse,
  AgentRunItem,
  AgentRunResponse,
} from '../types/domain';
import { formatDateTime, formatNumber } from '../utils/format';

interface AgentDashboardPageProps {
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
}

interface AgentDashboardState {
  runs: AgentRunItem[];
  decisions: AgentDecisionItem[];
  orders: AgentOrderItem[];
  riskConfig: AgentRiskConfigResponse['config'];
  broker: AgentBrokerStatusResponse | null;
  lastRun: AgentRunResponse | null;
  loading: boolean;
  error: string;
  updatedAt: string;
}

function emptyState(): AgentDashboardState {
  return {
    runs: [],
    decisions: [],
    orders: [],
    riskConfig: undefined,
    broker: null,
    lastRun: null,
    loading: true,
    error: '',
    updatedAt: new Date().toISOString(),
  };
}

function statusBadge(value: string | undefined): { label: string; tone: string } {
  const normalized = String(value || '').toLowerCase();
  if (['completed', 'submitted', 'approved', 'buy'].includes(normalized)) return { label: value || '-', tone: 'inline-badge is-success' };
  if (['failed', 'rejected', 'blocked', 'sell'].includes(normalized)) return { label: value || '-', tone: 'inline-badge is-danger' };
  if (['running', 'paper', 'hold', 'skipped'].includes(normalized)) return { label: value || '-', tone: 'inline-badge' };
  return { label: value || '-', tone: 'inline-badge' };
}

function StatCard({ label, value, copy }: { label: string; value: string | number; copy?: string }) {
  return (
    <div className="page-section" style={{ padding: 16 }}>
      <div className="section-copy">{label}</div>
      <div style={{ fontSize: 28, fontWeight: 800, fontVariantNumeric: 'tabular-nums', marginTop: 4 }}>{value}</div>
      {copy && <div className="section-copy" style={{ marginTop: 6 }}>{copy}</div>}
    </div>
  );
}

function safeSummaryValue(item: AgentRunItem | null | undefined, key: keyof NonNullable<AgentRunItem['summary']>): number {
  const value = item?.summary?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

export function AgentDashboardPage({ loading, errorMessage, onRefresh }: AgentDashboardPageProps) {
  const [state, setState] = useState<AgentDashboardState>(() => emptyState());
  const [running, setRunning] = useState(false);
  const latestRun = state.runs[0] || null;
  const latestDecision = state.decisions[0] || null;
  const latestOrder = state.orders[0] || null;

  const refresh = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: '' }));
    try {
      const [runs, decisions, orders, riskConfig, broker] = await Promise.all([
        fetchAgentRuns(20),
        fetchAgentDecisions(50),
        fetchAgentOrders(50),
        fetchAgentRiskConfig(),
        fetchAgentBrokerStatus(),
      ]);
      setState((prev) => ({
        ...prev,
        runs: runs.items || [],
        decisions: decisions.items || [],
        orders: orders.items || [],
        riskConfig: riskConfig.config,
        broker,
        loading: false,
        error: runs.error || decisions.error || orders.error || riskConfig.error || broker.error || '',
        updatedAt: new Date().toISOString(),
      }));
    } catch (error) {
      setState((prev) => ({ ...prev, loading: false, error: error instanceof Error ? error.message : String(error) }));
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const summaryCards = useMemo(() => {
    return [
      { label: '최근 후보', value: safeSummaryValue(latestRun, 'candidate_count'), copy: 'Agent Run 입력 후보 수' },
      { label: '판단', value: safeSummaryValue(latestRun, 'decisions'), copy: 'Hermes/스냅샷 BUY·SELL·HOLD 판단' },
      { label: 'Risk 승인', value: safeSummaryValue(latestRun, 'risk_approved'), copy: '결정적 Risk Gate 통과' },
      { label: '주문 기록', value: safeSummaryValue(latestRun, 'orders_submitted'), copy: 'Executor가 남긴 주문/실행 기록' },
    ];
  }, [latestRun]);

  async function handleRunAgent() {
    setRunning(true);
    setState((prev) => ({ ...prev, error: '' }));
    try {
      const result = await runAgent({ limit: 5 });
      setState((prev) => ({ ...prev, lastRun: result }));
      await refresh();
      onRefresh();
    } catch (error) {
      setState((prev) => ({ ...prev, error: error instanceof Error ? error.message : String(error) }));
    } finally {
      setRunning(false);
    }
  }

  const riskConfig = state.riskConfig || {};
  const broker = state.broker;
  const combinedLoading = loading || state.loading || running;
  const visibleError = state.error || errorMessage;
  const latestOrderStatus = statusBadge(latestOrder?.status);
  const latestDecisionStatus = statusBadge(latestDecision?.action);

  return (
    <div className="content-shell workspace-grid">
      <ConsoleActionBar
        title="Agent 자동거래 관제"
        subtitle="Hermes 판단, Risk Gate, Executor 기록을 런타임 모드와 분리해서 관제합니다."
        lastUpdated={state.updatedAt}
        loading={combinedLoading}
        errorMessage={visibleError}
        statusItems={[
          { label: '관제 상태', value: running ? '실행 중' : '대기', tone: running ? 'good' : 'neutral' },
          { label: 'Risk Gate', value: `${formatNumber(Number(riskConfig.min_confidence ?? 0), 2)}+`, tone: 'neutral' },
          { label: 'KIS 설정', value: broker?.configured ? '준비' : '미설정', tone: broker?.configured ? 'good' : 'neutral' },
          { label: '계좌', value: broker?.account_configured ? '준비' : '미설정', tone: broker?.account_configured ? 'good' : 'neutral' },
        ]}
        onRefresh={refresh}
        actions={[
          { label: running ? 'Agent 실행 중' : 'Agent 1회 실행', onClick: handleRunAgent, tone: 'primary', disabled: running },
        ]}
        logs={[]}
        onClearLogs={() => undefined}
      />

      <section className="page-section" style={{ padding: 16 }}>
        <div className="section-title">종목 선정 1차 기준</div>
        <div className="section-copy" style={{ marginTop: 6 }}>
          거래대금 상위 · 등락률 상위 · 뉴스 급증 종목 · 보유 종목 · 관심 종목을 표준 입력원으로 모아 중복 제거 후 Hermes/Risk Gate로 넘깁니다. 뉴스 급증은 가장 높은 우선순위 보너스를 받습니다.
        </div>
      </section>

      {visibleError && <div className="page-section workspace-empty-state">Agent Dashboard 오류: {visibleError}</div>}
      {state.lastRun && (
        <section className="page-section" style={{ padding: 16 }}>
          <div className="section-title">방금 실행 결과</div>
          <div className="section-copy" style={{ marginTop: 6 }}>
            Run #{state.lastRun.run_id || '-'} · 후보 {formatNumber(state.lastRun.summary?.candidate_count || 0)}개 · 주문 {formatNumber(state.lastRun.summary?.orders_submitted || 0)}건 · {state.lastRun.ok ? '정상 완료' : state.lastRun.error || '확인 필요'}
          </div>
        </section>
      )}

      <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
        {summaryCards.map((card) => <StatCard key={card.label} {...card} />)}
      </section>

      <section className="page-section" style={{ padding: 16 }}>
        <div className="workspace-card-head" style={{ marginBottom: 12 }}>
          <div>
            <div className="section-title">안전 설정 / 브로커 상태</div>
            <div className="section-copy">민감 정보는 서버에서 [REDACTED]로만 노출하고, 이 화면은 실계좌 연결 테스트를 수행하지 않습니다.</div>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
          <div className="workspace-summary-card">
            <div className="workspace-summary-title">Risk Gate</div>
            <div className="workspace-summary-copy">최소 신뢰도 {formatNumber(Number(riskConfig.min_confidence ?? 0), 2)}</div>
            <div className="workspace-summary-copy">손익비 {formatNumber(Number(riskConfig.min_reward_risk_ratio ?? 0), 2)} 이상</div>
            <div className="workspace-summary-copy">종목당 한도 {formatNumber(Number(riskConfig.max_symbol_position_ratio ?? 0) * 100, 1)}%</div>
          </div>
          <div className="workspace-summary-card">
            <div className="workspace-summary-title">KIS Broker</div>
            <div className="workspace-summary-copy">API 키 {broker?.configured ? '설정됨' : '미설정'} · 계좌 {broker?.account_configured ? '설정됨' : '미설정'}</div>
            <div className="workspace-summary-copy">Base URL {broker?.base_url || '-'}</div>
            <div className="workspace-summary-copy">주문 실행은 Runtime 엔진에서 결정</div>
          </div>
        </div>
      </section>

      <section className="page-section workspace-table-section">
        <div className="workspace-section-head" style={{ padding: '16px 16px 0' }}>
          <div>
            <div className="section-title">최근 Agent Runs</div>
            <div className="section-copy">후보 수, 판단 수, Risk 승인/거절, 주문 기록 수를 한 줄로 확인합니다.</div>
          </div>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table className="workspace-table">
            <thead>
              <tr><th>Run</th><th>상태</th><th>채널</th><th>후보</th><th>판단</th><th>승인/거절</th><th>주문</th><th>시각</th></tr>
            </thead>
            <tbody>
              {state.runs.length === 0 && <tr><td colSpan={8}>아직 Agent Run 기록이 없습니다.</td></tr>}
              {state.runs.map((item) => {
                const badge = statusBadge(item.status);
                const runId = item.id ?? item.run_id ?? '-';
                return (
                  <tr key={String(runId)}>
                    <td>#{String(runId)}</td>
                    <td><span className={badge.tone}>{badge.label}</span></td>
                    <td>{item.execution_channel || 'runtime'}</td>
                    <td>{formatNumber(item.summary?.candidate_count || 0)}</td>
                    <td>{formatNumber(item.summary?.decisions || 0)}</td>
                    <td>{formatNumber(item.summary?.risk_approved || 0)} / {formatNumber(item.summary?.risk_rejected || 0)}</td>
                    <td>{formatNumber(item.summary?.orders_submitted || 0)} 제출 · {formatNumber(item.summary?.orders_skipped || 0)} 스킵</td>
                    <td>{formatDateTime(item.finished_at || item.started_at || item.created_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
        <div className="page-section" style={{ padding: 16 }}>
          <div className="section-title">최근 판단</div>
          <div className="workspace-chip-row" style={{ marginTop: 10 }}>
            <span className={latestDecisionStatus.tone}>{latestDecisionStatus.label}</span>
            <span className="inline-badge">{latestDecision?.symbol || '-'}</span>
            <span className="inline-badge">신뢰도 {formatNumber(Number(latestDecision?.confidence || 0), 2)}</span>
          </div>
          <div className="section-copy" style={{ marginTop: 10 }}>{formatDateTime(latestDecision?.created_at)}</div>
        </div>
        <div className="page-section" style={{ padding: 16 }}>
          <div className="section-title">최근 주문 기록</div>
          <div className="workspace-chip-row" style={{ marginTop: 10 }}>
            <span className={latestOrderStatus.tone}>{latestOrderStatus.label}</span>
            <span className="inline-badge">{latestOrder?.execution_channel || 'runtime'}</span>
            <span className="inline-badge">{latestOrder?.symbol || '-'}</span>
          </div>
          <div className="section-copy" style={{ marginTop: 10 }}>Executor가 남긴 최신 주문/실행 기록입니다.</div>
        </div>
      </section>
    </div>
  );
}
