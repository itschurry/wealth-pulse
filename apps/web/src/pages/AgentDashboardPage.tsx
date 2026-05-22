import { useCallback, useEffect, useState } from 'react';
import {
  fetchAgentBrokerStatus,
  fetchAgentRiskConfig,
} from '../api/domain';
import { SymbolIdentity } from '../components/SymbolIdentity';
import type { ConsoleSnapshot } from '../types/consoleView';
import type {
  AgentBrokerStatusResponse,
  AgentRiskConfigResponse,
} from '../types/domain';
import {
  formatDateTime,
  formatDateTimeWithAge,
  formatKRW,
  formatNumber,
  formatPercent,
  formatUSD,
} from '../utils/format';

interface AgentDashboardPageProps {
  snapshot: ConsoleSnapshot;
  loading: boolean;
  errorMessage: string;
  onRefresh: () => void;
}

interface DashboardState {
  riskConfig: AgentRiskConfigResponse['config'];
  broker: AgentBrokerStatusResponse | null;
  loading: boolean;
  error: string;
  updatedAt: string;
}

interface PositionView {
  key: string;
  code: string;
  name: string;
  market: string;
  quantity: number;
  valueKrw: number;
  pnlKrw: number;
  pnlPct: number | null;
}

function emptyState(): DashboardState {
  return {
    riskConfig: undefined,
    broker: null,
    loading: true,
    error: '',
    updatedAt: new Date().toISOString(),
  };
}

function toNumber(value: unknown): number {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : 0;
}

function toOptionalNumber(value: unknown): number | null {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function signedKRW(value: number): string {
  const prefix = value > 0 ? '+' : '';
  return `${prefix}${formatKRW(value, true)}`;
}

function signedPercent(value: number | null): string {
  if (value == null) return '-';
  const prefix = value > 0 ? '+' : '';
  return `${prefix}${formatPercent(value, 2)}`;
}

function toneFor(value: number | null | undefined): string {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric === 0) return 'is-neutral';
  return numeric > 0 ? 'is-up' : 'is-down';
}

function clampRatio(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, value));
}

function sharePct(value: number, total: number): number {
  if (!Number.isFinite(value) || !Number.isFinite(total) || total <= 0) return 0;
  return clampRatio((value / total) * 100);
}

function normalizePositions(raw: unknown): PositionView[] {
  const items = Array.isArray(raw)
    ? raw as Array<Record<string, unknown>>
    : raw && typeof raw === 'object'
      ? Object.values(raw as Record<string, unknown>).filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'))
      : [];

  return items
    .map((item, index) => {
      const quantity = toNumber(item.quantity);
      const valueKrw = toNumber(item.market_value_krw) || toNumber(item.last_price_krw) * quantity;
      return {
        key: `${String(item.market || '-')}:${String(item.code || index)}`,
        code: String(item.code || ''),
        name: String(item.name || ''),
        market: String(item.market || '-').toUpperCase(),
        quantity,
        valueKrw,
        pnlKrw: toNumber(item.unrealized_pnl_krw),
        pnlPct: toOptionalNumber(item.unrealized_pnl_pct),
      };
    })
    .sort((left, right) => right.valueKrw - left.valueKrw);
}

function researchStatusLabel(status: string | undefined, partialFailure?: boolean): { label: string; tone: 'good' | 'neutral' | 'bad' } {
  if (partialFailure) return { label: '일부 실패', tone: 'bad' };
  const normalized = String(status || '').toLowerCase();
  if (normalized === 'healthy') return { label: '정상', tone: 'good' };
  if (normalized === 'missing') return { label: '없음', tone: 'neutral' };
  if (normalized === 'stale') return { label: '지연', tone: 'bad' };
  if (normalized === 'invalid') return { label: '무효', tone: 'bad' };
  return { label: normalized || '대기', tone: 'neutral' };
}

export function AgentDashboardPage({ snapshot, loading, errorMessage, onRefresh }: AgentDashboardPageProps) {
  const [state, setState] = useState<DashboardState>(() => emptyState());

  const refresh = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: '' }));
    try {
      const [riskConfig, broker] = await Promise.all([
        fetchAgentRiskConfig(),
        fetchAgentBrokerStatus(),
      ]);
      setState((prev) => ({
        ...prev,
        riskConfig: riskConfig.config,
        broker,
        loading: false,
        error: riskConfig.error || broker.error || '',
        updatedAt: new Date().toISOString(),
      }));
    } catch (error) {
      setState((prev) => ({ ...prev, loading: false, error: error instanceof Error ? error.message : String(error) }));
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const engineState = snapshot.engine.execution?.state || {};
  const engineAccount = snapshot.engine.execution?.account || {};
  const portfolioAccount = snapshot.portfolio.account || {};
  const performance = snapshot.performance.live || {};
  const account = Object.keys(portfolioAccount).length > 0 ? portfolioAccount : engineAccount;
  const positions = normalizePositions(account.positions || engineAccount.positions);

  const equityKrw = toNumber(account.equity_krw) || toNumber(performance.equity_krw) || toNumber(engineState.current_equity);
  const cashKrw = toNumber(account.cash_krw) || toNumber(performance.cash_krw);
  const cashUsd = toNumber(account.cash_usd) || toNumber(performance.cash_usd);
  const marketValueKrw = positions.reduce((sum, item) => sum + item.valueKrw, 0) || toNumber(performance.market_value_krw);
  const unrealizedPnlKrw = positions.reduce((sum, item) => sum + item.pnlKrw, 0) || toNumber(performance.unrealized_pnl_krw);
  const realizedPnlKrw = toNumber(performance.realized_pnl_krw) || toNumber(engineState.today_realized_pnl);
  const totalReturnPct = toOptionalNumber(performance.total_return_pct);
  const positionReturnPct = toOptionalNumber(performance.position_return_pct);
  const research = snapshot.research || {};
  const researchStatus = researchStatusLabel(research.status, research.partial_failure);
  const brokerReady = Boolean(state.broker?.configured && state.broker?.account_configured);
  const allocationMode = String(state.riskConfig?.allocation_mode || 'diversified') === 'concentrated' ? '집중투자' : '분산투자';
  const visibleError = state.error || errorMessage;
  const investedPct = sharePct(marketValueKrw, equityKrw || marketValueKrw + cashKrw);
  const cashPct = sharePct(cashKrw, equityKrw || marketValueKrw + cashKrw);
  const researchSuccess = toNumber(research.success_count);
  const researchFailure = toNumber(research.failure_count);
  const researchTotal = Math.max(researchSuccess + researchFailure, 1);
  const researchSuccessPct = sharePct(researchSuccess, researchTotal);
  const researchFailurePct = sharePct(researchFailure, researchTotal);

  return (
    <div className="content-shell portfolio-dashboard">
      <div className="portfolio-topbar">
        <div className="portfolio-status-row">
          <span className={engineState.running ? 'portfolio-dot is-good' : 'portfolio-dot'} />
          <span>{engineState.running ? '실행' : '중지'}</span>
          <span className={researchStatus.tone === 'good' ? 'portfolio-dot is-good' : researchStatus.tone === 'bad' ? 'portfolio-dot is-bad' : 'portfolio-dot'} />
          <span>리서치 {researchStatus.label}</span>
          <span className={brokerReady ? 'portfolio-dot is-good' : 'portfolio-dot'} />
          <span>{brokerReady ? '계좌' : '계좌 미설정'}</span>
        </div>
        <button
          type="button"
          className="ghost-button"
          disabled={loading || state.loading}
          onClick={() => {
            onRefresh();
            void refresh();
          }}
        >
          갱신
        </button>
      </div>
      {visibleError ? <div className="console-error-line">{visibleError}</div> : null}

      <section className="portfolio-hero-simple">
        <div>
          <div className="portfolio-label">자산</div>
          <div className="portfolio-equity">{formatKRW(equityKrw, true)}</div>
          <div className="portfolio-allocation">
            <div className="portfolio-allocation-track">
              <div className="portfolio-allocation-invested" style={{ width: `${investedPct}%` }} />
              <div className="portfolio-allocation-cash" style={{ width: `${cashPct}%` }} />
            </div>
            <div className="portfolio-subline">
              <span>투자 {formatKRW(marketValueKrw, true)}</span>
              <span>현금 {formatKRW(cashKrw, true)}</span>
              <span>USD {formatUSD(cashUsd, true)}</span>
              <span>{formatNumber(positions.length, 0)}종목</span>
            </div>
          </div>
        </div>
        <div className="portfolio-pnl-grid">
          <div>
            <span>평가</span>
            <strong className={toneFor(unrealizedPnlKrw)}>{signedKRW(unrealizedPnlKrw)}</strong>
          </div>
          <div>
            <span>실현</span>
            <strong className={toneFor(realizedPnlKrw)}>{signedKRW(realizedPnlKrw)}</strong>
          </div>
          <div>
            <span>총률</span>
            <strong className={toneFor(totalReturnPct)}>{signedPercent(totalReturnPct)}</strong>
          </div>
          <div>
            <span>보유률</span>
            <strong className={toneFor(positionReturnPct)}>{signedPercent(positionReturnPct)}</strong>
          </div>
        </div>
      </section>

      <section className="portfolio-main-grid">
        <div className="page-section portfolio-panel">
          <div className="portfolio-panel-head">
            <div className="section-title">보유</div>
            <div className="inline-badge">{formatKRW(marketValueKrw, true)}</div>
          </div>
          <div className="holding-list">
            {positions.slice(0, 8).map((position) => (
              <div key={position.key} className="holding-row">
                <div>
                  <SymbolIdentity code={position.code} name={position.name} market={position.market} compact />
                  <div className="holding-weight-track">
                    <div style={{ width: `${sharePct(position.valueKrw, marketValueKrw)}%` }} />
                  </div>
                </div>
                <div className="holding-row-number">
                  <strong>{formatKRW(position.valueKrw, true)}</strong>
                  <span>{formatNumber(position.quantity, 0)}주</span>
                </div>
                <div className={`holding-row-pnl ${toneFor(position.pnlKrw)}`}>
                  <strong>{signedKRW(position.pnlKrw)}</strong>
                  <span>{signedPercent(position.pnlPct)}</span>
                </div>
              </div>
            ))}
            {positions.length === 0 && <div className="workspace-empty-state">현재 보유종목이 없어.</div>}
          </div>
        </div>

        <div className="page-section portfolio-panel">
          <div className="portfolio-panel-head">
            <div className="section-title">리서치</div>
            <span className={researchStatus.tone === 'good' ? 'inline-badge is-success' : researchStatus.tone === 'bad' ? 'inline-badge is-danger' : 'inline-badge'}>
              {researchStatus.label}
            </span>
          </div>
          <div className="research-health-bar">
            <div className="is-good" style={{ width: `${researchSuccessPct}%` }} />
            <div className="is-bad" style={{ width: `${researchFailurePct}%` }} />
          </div>
          <div className="research-simple-grid">
            <div><span>상태</span><strong>{research.last_run_status || '대기'}</strong></div>
            <div><span>대상</span><strong>{formatNumber(research.selected_count, 0)}</strong></div>
            <div><span>성공</span><strong>{formatNumber(research.success_count, 0)}</strong></div>
            <div><span>실패</span><strong>{formatNumber(research.failure_count, 0)}</strong></div>
            <div><span>최신</span><strong>{formatNumber(research.fresh_symbol_count, 0)}</strong></div>
            <div><span>지연</span><strong>{formatNumber(research.stale_symbol_count, 0)}</strong></div>
          </div>
          {research.partial_failure && Array.isArray(research.recent_errors) && research.recent_errors.length > 0 && (
            <div className="research-error-line">
              {research.recent_errors.slice(0, 3).map((item) => `${item.market || '-'}:${item.symbol || '-'} ${item.error || ''}`).join(' / ')}
            </div>
          )}
          <div className="portfolio-meta-list">
            <div>{formatDateTimeWithAge(research.last_generated_at || research.latest_bucket_ts)}</div>
            <div>{allocationMode} · {brokerReady ? '계좌 준비' : '계좌 미설정'}</div>
            <div>{formatDateTime(engineState.next_run_at)}</div>
          </div>
        </div>
      </section>
    </div>
  );
}
