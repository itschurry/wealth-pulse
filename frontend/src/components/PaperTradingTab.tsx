import { useEffect, useMemo, useState } from 'react';
import { usePaperTrading } from '../hooks/usePaperTrading';
import type { PaperEngineConfig, PaperSkippedItem } from '../types';

const SKIP_REASON_LABELS: Record<string, string> = {
  entry_signal_not_matched: '매수신호 미충족',
  rsi_above_max: 'RSI 과열',
  rsi_below_min: 'RSI 과매도',
  stop_loss: '손절 매도',
  take_profit: '익절 매도',
  max_holding_days: '보유기간 초과',
  insufficient_cash: '잔액 부족',
  already_holding: '이미 보유 중',
  max_positions: '최대 포지션 도달',
  invalid_quote: '시세 오류',
  technicals_error: '지표 오류',
  technicals_unavailable: '지표 없음',
  buy_failed: '매수 실패',
  order_failed: '매수 실패',
  sell_failed: '매도 실패',
};

function labelSkipReason(reason?: string): string {
  if (!reason) return '알 수 없음';
  if (reason.startsWith('quote_error')) return '시세 조회 오류';
  return SKIP_REASON_LABELS[reason] ?? reason;
}

function formatKrw(value?: number | null) {
  if (value === undefined || value === null) return '—';
  return `${new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 0 }).format(value)}원`;
}

function formatUsd(value?: number | null) {
  if (value === undefined || value === null) return '—';
  return `$${new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value)}`;
}

function withCommaDigits(raw: string) {
  const digits = raw.replace(/\D/g, '');
  if (!digits) return '';
  return new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 0 }).format(Number(digits));
}

function parseCommaNumber(value: string) {
  const normalized = value.replace(/,/g, '').trim();
  if (!normalized) return 0;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatIntegerInput(value?: number | null) {
  if (value === undefined || value === null || !Number.isFinite(value)) return '';
  return new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 0 }).format(Math.trunc(value));
}

function formatSignedPct(value?: number | null) {
  if (value === undefined || value === null) return '—';
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
}

function formatDateTime(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('ko-KR');
}

function normalizeMarkets(markets?: Array<'KOSPI' | 'NASDAQ'>) {
  return [...(markets || [])].sort().join(',');
}

const DEFAULT_THEME_FOCUS: Array<'automotive' | 'robotics' | 'physical_ai'> = ['automotive', 'robotics', 'physical_ai'];

export function PaperTradingTab() {
  const { account, engineState, status, lastError, refresh, reset, autoInvest, refreshEngineStatus, startEngine, stopEngine } = usePaperTrading();
  const [seedKrw, setSeedKrw] = useState('10,000,000');
  const [seedUsd, setSeedUsd] = useState('10,000');
  const [paperDays, setPaperDays] = useState('7');
  const [autoMarket] = useState<'KOSPI' | 'NASDAQ'>('NASDAQ');
  const [autoMaxPositions, setAutoMaxPositions] = useState('12');
  const [autoMinScore, setAutoMinScore] = useState('50');
  const [autoIncludeNeutral, setAutoIncludeNeutral] = useState(true);
  const [engineIntervalSeconds, setEngineIntervalSeconds] = useState('300');
  const [engineSignalInterval, setEngineSignalInterval] = useState<'1m' | '2m' | '5m' | '15m' | '30m' | '60m' | '90m' | '1d'>('15m');
  const [engineSignalRange, setEngineSignalRange] = useState<'1d' | '5d' | '1mo' | '3mo' | '6mo' | '1y'>('5d');
  const [engineRunKOSPI, setEngineRunKOSPI] = useState(true);
  const [engineRunNASDAQ, setEngineRunNASDAQ] = useState(true);
  const [engineDailyBuyLimit, setEngineDailyBuyLimit] = useState('100');
  const [engineDailySellLimit, setEngineDailySellLimit] = useState('100');
  const [engineMaxOrdersPerSymbol, setEngineMaxOrdersPerSymbol] = useState('3');
  const [engineRsiMin, setEngineRsiMin] = useState('35');
  const [engineRsiMax, setEngineRsiMax] = useState('78');
  const [engineVolumeRatioMin, setEngineVolumeRatioMin] = useState('0.8');
  const [engineStopLossPct, setEngineStopLossPct] = useState('5');
  const [engineTakeProfitPct, setEngineTakeProfitPct] = useState('10');
  const [engineMaxHoldingDays, setEngineMaxHoldingDays] = useState('10');
  const [themeGateEnabled, setThemeGateEnabled] = useState(true);
  const [themeMinScore, setThemeMinScore] = useState('2.5');
  const [themeMinNews, setThemeMinNews] = useState('1');
  const [themePriorityBonus, setThemePriorityBonus] = useState('2.0');
  const [statusMessage, setStatusMessage] = useState('');
  const [lastAutoInvestSkipped, setLastAutoInvestSkipped] = useState<PaperSkippedItem[]>([]);
  const [showAutoInvestSkipDetail, setShowAutoInvestSkipDetail] = useState(false);
  const [showEngineSkipDetail, setShowEngineSkipDetail] = useState(false);

  const initialTotalKrw = useMemo(() => {
    return (account.initial_cash_krw || 0) + ((account.initial_cash_usd || 0) * (account.fx_rate || 0));
  }, [account.initial_cash_krw, account.initial_cash_usd, account.fx_rate]);

  const runningReturnPct = useMemo(() => {
    if (!initialTotalKrw) return 0;
    return ((account.equity_krw / initialTotalKrw) - 1) * 100;
  }, [account.equity_krw, initialTotalKrw]);

  const buildEngineConfig = (): PaperEngineConfig | null => {
    const markets: Array<'KOSPI' | 'NASDAQ'> = [];
    if (engineRunKOSPI) markets.push('KOSPI');
    if (engineRunNASDAQ) markets.push('NASDAQ');
    if (markets.length === 0) {
      return null;
    }
    const parsedThemeScore = Number(themeMinScore);
    const parsedThemeNews = Number(themeMinNews);
    const parsedThemeBonus = Number(themePriorityBonus);
    return {
      interval_seconds: Math.max(30, Math.min(3600, Math.floor(Number(engineIntervalSeconds) || 300))),
      signal_interval: engineSignalInterval,
      signal_range: engineSignalRange,
      markets,
      max_positions_per_market: Math.max(1, Math.min(20, Math.floor(Number(autoMaxPositions) || 5))),
      min_score: Math.max(0, Math.min(100, Number(autoMinScore) || 50)),
      include_neutral: autoIncludeNeutral,
      theme_gate_enabled: themeGateEnabled,
      theme_min_score: Number.isFinite(parsedThemeScore) ? Math.max(0, Math.min(30, parsedThemeScore)) : 2.5,
      theme_min_news: Number.isFinite(parsedThemeNews) ? Math.max(0, Math.min(10, Math.floor(parsedThemeNews))) : 1,
      theme_priority_bonus: Number.isFinite(parsedThemeBonus) ? Math.max(0, Math.min(10, parsedThemeBonus)) : 2,
      theme_focus: DEFAULT_THEME_FOCUS,
      daily_buy_limit: Math.max(1, Math.min(200, Math.floor(Number(engineDailyBuyLimit) || 20))),
      daily_sell_limit: Math.max(1, Math.min(200, Math.floor(Number(engineDailySellLimit) || 20))),
      max_orders_per_symbol_per_day: Math.max(1, Math.min(10, Math.floor(Number(engineMaxOrdersPerSymbol) || 1))),
      rsi_min: Math.max(10, Math.min(90, Number(engineRsiMin) || 45)),
      rsi_max: Math.max(10, Math.min(90, Number(engineRsiMax) || 68)),
      volume_ratio_min: Math.max(0.5, Math.min(5, Number(engineVolumeRatioMin) || 1.2)),
      stop_loss_pct: Math.max(1, Math.min(50, Number(engineStopLossPct) || 7)),
      take_profit_pct: Math.max(1, Math.min(100, Number(engineTakeProfitPct) || 18)),
      max_holding_days: Math.max(1, Math.min(180, Math.floor(Number(engineMaxHoldingDays) || 30))),
    };
  };

  const desiredEngineConfig = useMemo(() => buildEngineConfig(), [
    autoIncludeNeutral,
    autoMaxPositions,
    autoMinScore,
    engineDailyBuyLimit,
    engineDailySellLimit,
    engineIntervalSeconds,
    engineMaxHoldingDays,
    engineMaxOrdersPerSymbol,
    engineRsiMax,
    engineRsiMin,
    engineRunKOSPI,
    engineRunNASDAQ,
    engineSignalInterval,
    engineSignalRange,
    engineStopLossPct,
    engineTakeProfitPct,
    engineVolumeRatioMin,
    themeGateEnabled,
    themeMinNews,
    themePriorityBonus,
    themeMinScore,
  ]);

  const appliedMarkets = engineState.config?.markets || [];
  const isKospiRunning = engineState.running && appliedMarkets.includes('KOSPI');
  const isNasdaqRunning = engineState.running && appliedMarkets.includes('NASDAQ');
  const candidateCountsByMarket = engineState.last_summary?.candidate_counts_by_market || {};
  const skipReasonEntries = Object.entries(engineState.last_summary?.skip_reason_counts || {})
    .sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0));
  const isEngineConfigDirty = useMemo(() => {
    const cfg = desiredEngineConfig;
    const applied = engineState.config;
    if (!engineState.running || !cfg || !applied) return false;
    return (
      cfg.interval_seconds !== applied.interval_seconds ||
      cfg.signal_interval !== applied.signal_interval ||
      cfg.signal_range !== applied.signal_range ||
      normalizeMarkets(cfg.markets) !== normalizeMarkets(applied.markets) ||
      cfg.max_positions_per_market !== applied.max_positions_per_market ||
      cfg.min_score !== applied.min_score ||
      cfg.include_neutral !== applied.include_neutral ||
      cfg.theme_gate_enabled !== applied.theme_gate_enabled ||
      cfg.theme_min_score !== applied.theme_min_score ||
      cfg.theme_min_news !== applied.theme_min_news ||
      cfg.theme_priority_bonus !== applied.theme_priority_bonus ||
      cfg.daily_buy_limit !== applied.daily_buy_limit ||
      cfg.daily_sell_limit !== applied.daily_sell_limit ||
      cfg.max_orders_per_symbol_per_day !== applied.max_orders_per_symbol_per_day ||
      cfg.rsi_min !== applied.rsi_min ||
      cfg.rsi_max !== applied.rsi_max ||
      cfg.volume_ratio_min !== applied.volume_ratio_min ||
      cfg.stop_loss_pct !== applied.stop_loss_pct ||
      cfg.take_profit_pct !== applied.take_profit_pct ||
      cfg.max_holding_days !== applied.max_holding_days
    );
  }, [desiredEngineConfig, engineState.config, engineState.running]);

  useEffect(() => {
    setSeedKrw(formatIntegerInput(account.initial_cash_krw));
    setSeedUsd(formatIntegerInput(account.initial_cash_usd));
    setPaperDays(formatIntegerInput(account.paper_days));
  }, [account.initial_cash_krw, account.initial_cash_usd, account.paper_days]);

  useEffect(() => {
    const cfg = engineState.config;
    if (!cfg) return;

    if (cfg.interval_seconds !== undefined) setEngineIntervalSeconds(String(cfg.interval_seconds));
    if (cfg.signal_interval) setEngineSignalInterval(cfg.signal_interval);
    if (cfg.signal_range) setEngineSignalRange(cfg.signal_range);
    if (cfg.max_positions_per_market !== undefined) setAutoMaxPositions(String(cfg.max_positions_per_market));
    if (cfg.min_score !== undefined) setAutoMinScore(String(cfg.min_score));
    if (cfg.include_neutral !== undefined) setAutoIncludeNeutral(cfg.include_neutral);
    if (cfg.theme_gate_enabled !== undefined) setThemeGateEnabled(Boolean(cfg.theme_gate_enabled));
    if (cfg.theme_min_score !== undefined) setThemeMinScore(String(cfg.theme_min_score));
    if (cfg.theme_min_news !== undefined) setThemeMinNews(String(cfg.theme_min_news));
    if (cfg.theme_priority_bonus !== undefined) setThemePriorityBonus(String(cfg.theme_priority_bonus));
    if (cfg.daily_buy_limit !== undefined) setEngineDailyBuyLimit(String(cfg.daily_buy_limit));
    if (cfg.daily_sell_limit !== undefined) setEngineDailySellLimit(String(cfg.daily_sell_limit));
    if (cfg.max_orders_per_symbol_per_day !== undefined) setEngineMaxOrdersPerSymbol(String(cfg.max_orders_per_symbol_per_day));
    if (cfg.rsi_min !== undefined) setEngineRsiMin(String(cfg.rsi_min));
    if (cfg.rsi_max !== undefined) setEngineRsiMax(String(cfg.rsi_max));
    if (cfg.volume_ratio_min !== undefined) setEngineVolumeRatioMin(String(cfg.volume_ratio_min));
    if (cfg.stop_loss_pct !== undefined) setEngineStopLossPct(String(cfg.stop_loss_pct));
    if (cfg.take_profit_pct !== undefined) setEngineTakeProfitPct(String(cfg.take_profit_pct));
    if (cfg.max_holding_days !== undefined) setEngineMaxHoldingDays(String(cfg.max_holding_days));
    if (cfg.markets) {
      setEngineRunKOSPI(cfg.markets.includes('KOSPI'));
      setEngineRunNASDAQ(cfg.markets.includes('NASDAQ'));
    }
  }, [
    engineState.config?.daily_buy_limit,
    engineState.config?.daily_sell_limit,
    engineState.config?.include_neutral,
    engineState.config?.interval_seconds,
    engineState.config?.markets?.join(','),
    engineState.config?.max_holding_days,
    engineState.config?.max_orders_per_symbol_per_day,
    engineState.config?.max_positions_per_market,
    engineState.config?.min_score,
    engineState.config?.rsi_max,
    engineState.config?.rsi_min,
    engineState.config?.signal_interval,
    engineState.config?.signal_range,
    engineState.config?.stop_loss_pct,
    engineState.config?.take_profit_pct,
    engineState.config?.theme_gate_enabled,
    engineState.config?.theme_min_news,
    engineState.config?.theme_priority_bonus,
    engineState.config?.theme_min_score,
    engineState.config?.volume_ratio_min,
  ]);

  async function handleReset() {
    const result = await reset({
      initial_cash_krw: parseCommaNumber(seedKrw),
      initial_cash_usd: parseCommaNumber(seedUsd),
      paper_days: Math.max(1, Math.min(365, Math.floor(parseCommaNumber(paperDays)))),
    });
    if (!result.ok) {
      setStatusMessage(result.error || '초기화 실패');
      return;
    }
    setStatusMessage('모의계좌를 초기화했습니다.');
  }

  async function handleAutoInvest() {
    const parsedMax = Number(autoMaxPositions);
    const parsedScore = Number(autoMinScore);
    const parsedThemeScore = Number(themeMinScore);
    const parsedThemeNews = Number(themeMinNews);
    const parsedThemeBonus = Number(themePriorityBonus);
    const result = await autoInvest({
      market: autoMarket,
      max_positions: Number.isFinite(parsedMax) ? Math.max(1, Math.floor(parsedMax)) : 5,
      min_score: Number.isFinite(parsedScore) ? parsedScore : 50,
      include_neutral: autoIncludeNeutral,
      theme_gate_enabled: themeGateEnabled,
      theme_min_score: Number.isFinite(parsedThemeScore) ? Math.max(0, Math.min(30, parsedThemeScore)) : 2.5,
      theme_min_news: Number.isFinite(parsedThemeNews) ? Math.max(0, Math.min(10, Math.floor(parsedThemeNews))) : 1,
      theme_priority_bonus: Number.isFinite(parsedThemeBonus) ? Math.max(0, Math.min(10, parsedThemeBonus)) : 2,
      theme_focus: DEFAULT_THEME_FOCUS,
    });
    if (!result.ok) {
      setStatusMessage(result.error || '자동매수 실패');
      return;
    }
    const payload = result.payload || {};
    const executed = Array.isArray(payload.executed) ? payload.executed.length : 0;
    const skippedList: PaperSkippedItem[] = Array.isArray(payload.skipped) ? payload.skipped : [];
    setLastAutoInvestSkipped(skippedList);
    setShowAutoInvestSkipDetail(false);
    if (executed === 0 && payload.message) {
      setStatusMessage(String(payload.message));
      return;
    }
    setStatusMessage(`추천 기반 자동매수 완료: 체결 ${executed}건, 스킵 ${skippedList.length}건`);
  }

  async function handleStartEngine() {
    if (engineState.running) {
      setStatusMessage('이미 실행 중입니다. 설정 변경 사항은 재시작으로 반영해 주세요.');
      return;
    }
    const config = desiredEngineConfig;
    if (!config) {
      setStatusMessage('최소 1개 시장을 선택해 주세요.');
      return;
    }
    const result = await startEngine(config);
    if (!result.ok) {
      setStatusMessage(result.error || '자동매매 실행 실패');
      return;
    }
    const message = result.payload?.message ? String(result.payload.message) : '추천 기반 자동매매 엔진을 시작했습니다. (매수/매도, 지표 기반, 백그라운드 반복 실행)';
    setStatusMessage(message);
    await refreshEngineStatus();
  }

  async function handleRestartEngine() {
    const config = desiredEngineConfig;
    if (!config) {
      setStatusMessage('최소 1개 시장을 선택해 주세요.');
      return;
    }
    if (!engineState.running) {
      await handleStartEngine();
      return;
    }
    const stopped = await stopEngine();
    if (!stopped.ok) {
      setStatusMessage(stopped.error || '자동매매 중지 실패');
      return;
    }
    const restarted = await startEngine(config);
    if (!restarted.ok) {
      setStatusMessage(restarted.error || '자동매매 재시작 실패');
      return;
    }
    setStatusMessage('설정 변경 사항을 반영해 자동매매 엔진을 재시작했습니다.');
    await refreshEngineStatus();
  }

  async function handleStopEngine() {
    const result = await stopEngine();
    if (!result.ok) {
      setStatusMessage(result.error || '자동매매 중지 실패');
      return;
    }
    setStatusMessage('자동매매 엔진을 중지했습니다.');
    await refreshEngineStatus();
  }

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div className="page-section" style={{ display: 'grid', gap: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 12, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: '0.12em' }}>Paper Trading</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--text-1)', marginTop: 6 }}>자동 모의투자</div>
            <div style={{ fontSize: 13, color: 'var(--text-4)', marginTop: 8 }}>KOSPI/NASDAQ를 병렬 운용하며 원화/달러 자금을 분리해 관리합니다.</div>
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <button className="ghost-button" onClick={() => refresh(true)}>평가 갱신</button>
            <span style={{ fontSize: 12, color: 'var(--text-4)' }}>{status === 'loading' ? '불러오는 중' : status === 'error' ? '오류' : '정상'}</span>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10 }}>
          <div style={{ padding: '12px 14px', borderRadius: 14, border: '1px solid var(--border)', background: 'var(--bg-soft)' }}>
            <div style={{ fontSize: 12, color: 'var(--text-4)' }}>총자산 (KRW 환산)</div>
            <div style={{ fontSize: 22, fontWeight: 800, marginTop: 6 }}>{formatKrw(account.equity_krw)}</div>
          </div>
          <div style={{ padding: '12px 14px', borderRadius: 14, border: '1px solid var(--border)', background: 'var(--bg-soft)' }}>
            <div style={{ fontSize: 12, color: 'var(--text-4)' }}>현금 (KRW / USD)</div>
            <div style={{ fontSize: 16, fontWeight: 800, marginTop: 6 }}>{formatKrw(account.cash_krw)}</div>
            <div style={{ fontSize: 14, color: 'var(--text-3)', marginTop: 4 }}>{formatUsd(account.cash_usd)}</div>
          </div>
          <div style={{ padding: '12px 14px', borderRadius: 14, border: '1px solid var(--border)', background: 'var(--bg-soft)' }}>
            <div style={{ fontSize: 12, color: 'var(--text-4)' }}>평가손익률</div>
            <div style={{ fontSize: 22, fontWeight: 800, marginTop: 6, color: runningReturnPct >= 0 ? 'var(--up)' : 'var(--down)' }}>{formatSignedPct(runningReturnPct)}</div>
          </div>
          <div style={{ padding: '12px 14px', borderRadius: 14, border: '1px solid var(--border)', background: 'var(--bg-soft)' }}>
            <div style={{ fontSize: 12, color: 'var(--text-4)' }}>모의투자 기간</div>
            <div style={{ fontSize: 16, fontWeight: 800, marginTop: 6 }}>{account.paper_days || 0}일</div>
            <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 4 }}>경과 {account.days_elapsed || 0}일 · 남음 {account.days_left || 0}일</div>
          </div>
        </div>
      </div>

      <div className="page-section" style={{ display: 'grid', gap: 12 }}>
        <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-1)' }}>초기 자금 / 기간 설정</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10 }}>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>초기 원화 자금 (KRW)</span>
            <input className="backtest-input" inputMode="numeric" value={seedKrw} onChange={(event) => setSeedKrw(withCommaDigits(event.target.value))} />
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>초기 달러 자금 (USD)</span>
            <input className="backtest-input" inputMode="numeric" value={seedUsd} onChange={(event) => setSeedUsd(withCommaDigits(event.target.value))} />
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>모의투자 기간 (일)</span>
            <input className="backtest-input" inputMode="numeric" value={paperDays} onChange={(event) => setPaperDays(withCommaDigits(event.target.value))} />
          </label>
        </div>
        <div>
          <button className="ghost-button" onClick={handleReset}>초기 자금/기간 적용</button>
        </div>
      </div>

      <div className="page-section" style={{ display: 'grid', gap: 12 }}>
        <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-1)' }}>추천 기반 자동투자 엔진</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10 }}>
          <div style={{ padding: '10px 12px', border: '1px solid var(--border)', borderRadius: 12, background: 'var(--bg-soft)', fontSize: 12, color: 'var(--text-3)' }}>
            <div>상태: <b style={{ color: engineState.running ? 'var(--up)' : 'var(--text-2)' }}>{engineState.running ? '실행 중' : '중지'}</b></div>
            <div style={{ marginTop: 4 }}>시작: {formatDateTime(engineState.started_at)}</div>
            <div style={{ marginTop: 4 }}>최근 실행: {formatDateTime(engineState.last_run_at)}</div>
            <div style={{ marginTop: 4 }}>
              최근 체결: 매수 {engineState.last_summary?.executed_buy_count ?? 0}건 / 매도 {engineState.last_summary?.executed_sell_count ?? 0}건
            </div>
            <div style={{ marginTop: 4 }}>
              최근 후보: KOSPI {candidateCountsByMarket.KOSPI ?? 0}건 / NASDAQ {candidateCountsByMarket.NASDAQ ?? 0}건
            </div>
            {skipReasonEntries.length > 0 && (
              <div style={{ marginTop: 6, borderTop: '1px solid var(--border)', paddingTop: 6 }}>
                <div style={{ fontWeight: 700, color: 'var(--text-2)', marginBottom: 4 }}>스킵 이유 ({skipReasonEntries.reduce((s, [, c]) => s + Number(c), 0)}건)</div>
                {skipReasonEntries.map(([reason, count]) => (
                  <div key={reason} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginTop: 2 }}>
                    <span style={{ color: 'var(--text-3)' }}>{labelSkipReason(reason)}</span>
                    <span style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--text-2)' }}>{count}건</span>
                  </div>
                ))}
                {(engineState.last_summary?.skipped?.length ?? 0) > 0 && (
                  <button
                    className="ghost-button"
                    style={{ marginTop: 6, fontSize: 11, padding: '2px 8px' }}
                    onClick={() => setShowEngineSkipDetail((v) => !v)}
                  >
                    종목별 상세 {showEngineSkipDetail ? '▲ 접기' : '▼ 펼치기'}
                  </button>
                )}
                {showEngineSkipDetail && (
                  <div style={{ marginTop: 6, display: 'grid', gap: 2, maxHeight: 200, overflowY: 'auto' }}>
                    {(engineState.last_summary?.skipped ?? []).map((item, idx) => (
                      <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 11, color: 'var(--text-4)' }}>
                        <span style={{ fontWeight: 600, color: 'var(--text-2)' }}>{item.code ?? '—'}{item.market ? ` (${item.market})` : ''}</span>
                        <span>{labelSkipReason(item.reason)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
            {skipReasonEntries.length === 0 && (
              <div style={{ marginTop: 4 }}>스킵: 없음</div>
            )}
            <div style={{ marginTop: 4, color: engineState.last_error ? 'var(--down)' : 'var(--text-4)' }}>
              오류: {engineState.last_error || '없음'}
            </div>
          </div>
          <div style={{ padding: '10px 12px', border: '1px solid var(--border)', borderRadius: 12, background: 'var(--bg-soft)', fontSize: 12, color: 'var(--text-3)' }}>
            <div>KOSPI: <b style={{ color: isKospiRunning ? 'var(--up)' : 'var(--text-2)' }}>{isKospiRunning ? '실행 중' : '중지'}</b></div>
            <div style={{ marginTop: 4 }}>적용 시장: {appliedMarkets.includes('KOSPI') ? '포함' : '미포함'}</div>
          </div>
          <div style={{ padding: '10px 12px', border: '1px solid var(--border)', borderRadius: 12, background: 'var(--bg-soft)', fontSize: 12, color: 'var(--text-3)' }}>
            <div>NASDAQ: <b style={{ color: isNasdaqRunning ? 'var(--up)' : 'var(--text-2)' }}>{isNasdaqRunning ? '실행 중' : '중지'}</b></div>
            <div style={{ marginTop: 4 }}>적용 시장: {appliedMarkets.includes('NASDAQ') ? '포함' : '미포함'}</div>
          </div>
          <div style={{ padding: '10px 12px', border: '1px solid var(--border)', borderRadius: 12, background: 'var(--bg-soft)', fontSize: 12, color: isEngineConfigDirty ? 'var(--accent)' : 'var(--text-3)' }}>
            <div>설정 상태: <b>{isEngineConfigDirty ? '재시작 필요' : '동기화됨'}</b></div>
            <div style={{ marginTop: 4 }}>{isEngineConfigDirty ? '현재 입력값이 실행 중인 엔진 설정과 다릅니다.' : '화면 입력값과 엔진 설정이 같습니다.'}</div>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 10 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 24 }}>
            <input type="checkbox" checked={engineRunKOSPI} onChange={(event) => setEngineRunKOSPI(event.target.checked)} />
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>KOSPI 실행</span>
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 24 }}>
            <input type="checkbox" checked={engineRunNASDAQ} onChange={(event) => setEngineRunNASDAQ(event.target.checked)} />
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>NASDAQ 실행</span>
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>최대 포지션 수</span>
            <input className="backtest-input" type="number" min={1} max={20} value={autoMaxPositions} onChange={(event) => setAutoMaxPositions(event.target.value)} />
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>최소 점수</span>
            <input className="backtest-input" type="number" min={0} max={100} value={autoMinScore} onChange={(event) => setAutoMinScore(event.target.value)} />
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>실행 주기(초)</span>
            <input className="backtest-input" type="number" min={30} max={3600} value={engineIntervalSeconds} onChange={(event) => setEngineIntervalSeconds(event.target.value)} />
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>지표 봉 간격</span>
            <select className="backtest-input" value={engineSignalInterval} onChange={(event) => setEngineSignalInterval(event.target.value as '1m' | '2m' | '5m' | '15m' | '30m' | '60m' | '90m' | '1d')}>
              <option value="1m">1m</option>
              <option value="2m">2m</option>
              <option value="5m">5m</option>
              <option value="15m">15m</option>
              <option value="30m">30m</option>
              <option value="60m">60m</option>
              <option value="90m">90m</option>
              <option value="1d">1d</option>
            </select>
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>지표 조회 범위</span>
            <select className="backtest-input" value={engineSignalRange} onChange={(event) => setEngineSignalRange(event.target.value as '1d' | '5d' | '1mo' | '3mo' | '6mo' | '1y')}>
              <option value="1d">1d</option>
              <option value="5d">5d</option>
              <option value="1mo">1mo</option>
              <option value="3mo">3mo</option>
              <option value="6mo">6mo</option>
              <option value="1y">1y</option>
            </select>
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>RSI 최소/최대</span>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <input className="backtest-input" type="number" min={10} max={90} value={engineRsiMin} onChange={(event) => setEngineRsiMin(event.target.value)} />
              <input className="backtest-input" type="number" min={10} max={90} value={engineRsiMax} onChange={(event) => setEngineRsiMax(event.target.value)} />
            </div>
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>최소 거래량 배수</span>
            <input className="backtest-input" type="number" min={0.5} max={5} step={0.1} value={engineVolumeRatioMin} onChange={(event) => setEngineVolumeRatioMin(event.target.value)} />
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>손절/익절(%)</span>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <input className="backtest-input" type="number" min={1} max={50} value={engineStopLossPct} onChange={(event) => setEngineStopLossPct(event.target.value)} />
              <input className="backtest-input" type="number" min={1} max={100} value={engineTakeProfitPct} onChange={(event) => setEngineTakeProfitPct(event.target.value)} />
            </div>
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>최대 보유일</span>
            <input className="backtest-input" type="number" min={1} max={180} value={engineMaxHoldingDays} onChange={(event) => setEngineMaxHoldingDays(event.target.value)} />
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>일일 매수/매도 제한</span>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <input className="backtest-input" type="number" min={1} max={200} value={engineDailyBuyLimit} onChange={(event) => setEngineDailyBuyLimit(event.target.value)} />
              <input className="backtest-input" type="number" min={1} max={200} value={engineDailySellLimit} onChange={(event) => setEngineDailySellLimit(event.target.value)} />
            </div>
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>종목별 일 최대 주문</span>
            <input className="backtest-input" type="number" min={1} max={10} value={engineMaxOrdersPerSymbol} onChange={(event) => setEngineMaxOrdersPerSymbol(event.target.value)} />
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 24 }}>
            <input type="checkbox" checked={autoIncludeNeutral} onChange={(event) => setAutoIncludeNeutral(event.target.checked)} />
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>추천 없으면 중립도 포함</span>
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, paddingTop: 24 }}>
            <input type="checkbox" checked={themeGateEnabled} onChange={(event) => setThemeGateEnabled(event.target.checked)} />
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>테마 우선 적용 (없으면 일반 허용)</span>
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>테마 최소 점수</span>
            <input className="backtest-input" type="number" min={0} max={30} step={0.1} value={themeMinScore} onChange={(event) => setThemeMinScore(event.target.value)} />
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>테마 최소 뉴스 수</span>
            <input className="backtest-input" type="number" min={0} max={10} value={themeMinNews} onChange={(event) => setThemeMinNews(event.target.value)} />
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>테마 우선 보너스</span>
            <input className="backtest-input" type="number" min={0} max={10} step={0.1} value={themePriorityBonus} onChange={(event) => setThemePriorityBonus(event.target.value)} />
          </label>
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <button
            className="ghost-button"
            style={{
              background: engineState.running ? 'var(--bg-soft)' : 'var(--accent)',
              color: engineState.running ? 'var(--text-4)' : '#fffaf2',
              borderColor: engineState.running ? 'var(--border)' : 'var(--accent)',
              cursor: engineState.running ? 'not-allowed' : 'pointer',
              opacity: engineState.running ? 0.7 : 1,
            }}
            onClick={handleStartEngine}
            disabled={engineState.running}
          >
            자동매매 엔진 시작
          </button>
          <button className="ghost-button" onClick={handleRestartEngine} disabled={engineState.running ? !isEngineConfigDirty : false}>
            설정으로 재시작
          </button>
          <button className="ghost-button" onClick={handleStopEngine}>자동매매 엔진 중지</button>
          <button className="ghost-button" onClick={() => refreshEngineStatus()}>엔진 상태 새로고침</button>
          <button className="ghost-button" onClick={handleAutoInvest}>1회 자동매수 실행</button>
        </div>
        {lastAutoInvestSkipped.length > 0 && (() => {
          const autoInvestSkipCounts: Record<string, number> = {};
          for (const item of lastAutoInvestSkipped) {
            const key = item.reason ?? 'unknown';
            autoInvestSkipCounts[key] = (autoInvestSkipCounts[key] ?? 0) + 1;
          }
          const sortedEntries = Object.entries(autoInvestSkipCounts).sort((a, b) => b[1] - a[1]);
          return (
            <div style={{ marginTop: 8, padding: '10px 12px', border: '1px solid var(--border)', borderRadius: 12, background: 'var(--bg-soft)', fontSize: 12, color: 'var(--text-3)' }}>
              <div style={{ fontWeight: 700, color: 'var(--text-2)', marginBottom: 6 }}>1회 자동매수 스킵 내역 ({lastAutoInvestSkipped.length}건)</div>
              {sortedEntries.map(([reason, count]) => (
                <div key={reason} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginTop: 2 }}>
                  <span>{labelSkipReason(reason)}</span>
                  <span style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--text-2)' }}>{count}건</span>
                </div>
              ))}
              <button
                className="ghost-button"
                style={{ marginTop: 6, fontSize: 11, padding: '2px 8px' }}
                onClick={() => setShowAutoInvestSkipDetail((v) => !v)}
              >
                종목별 상세 {showAutoInvestSkipDetail ? '▲ 접기' : '▼ 펼치기'}
              </button>
              {showAutoInvestSkipDetail && (
                <div style={{ marginTop: 6, display: 'grid', gap: 2, maxHeight: 200, overflowY: 'auto' }}>
                  {lastAutoInvestSkipped.map((item, idx) => (
                    <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 11, color: 'var(--text-4)' }}>
                      <span style={{ fontWeight: 600, color: 'var(--text-2)' }}>{item.code ?? '—'}</span>
                      <span>{labelSkipReason(item.reason)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })()}
      </div>

      {(statusMessage || lastError) && (
        <div className="page-section" style={{ fontSize: 13, color: lastError ? 'var(--down)' : 'var(--text-2)' }}>
          {lastError || statusMessage}
        </div>
      )}

      <div className="page-section" style={{ display: 'grid', gap: 12 }}>
        <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-1)' }}>포지션</div>
        {account.positions.length === 0 && <div style={{ color: 'var(--text-4)', fontSize: 13 }}>보유 포지션이 없습니다.</div>}
        {account.positions.length > 0 && (
          <div style={{ display: 'grid', gap: 8 }}>
            {account.positions.map((position) => (
              <div key={`${position.market}-${position.code}`} style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr', gap: 10, padding: '12px 14px', border: '1px solid var(--border)', borderRadius: 14, background: 'var(--bg-soft)' }}>
                <div>
                  <div style={{ fontWeight: 700, color: 'var(--text-1)' }}>{position.name}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 4 }}>{position.code} · {position.market} · {position.quantity}주</div>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-3)' }}>
                  <div>평균가 {position.currency === 'USD' ? formatUsd(position.avg_price_local) : formatKrw(position.avg_price_local)}</div>
                  <div style={{ marginTop: 4 }}>현재가 {position.currency === 'USD' ? formatUsd(position.last_price_local) : formatKrw(position.last_price_local)}</div>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-3)' }}>
                  <div>평가액 {formatKrw(position.market_value_krw)}</div>
                  <div style={{ marginTop: 4 }}>환율 {position.fx_rate.toFixed(2)}</div>
                </div>
                <div style={{ fontSize: 12, color: position.unrealized_pnl_krw >= 0 ? 'var(--up)' : 'var(--down)' }}>
                  <div>{formatKrw(position.unrealized_pnl_krw)}</div>
                  <div style={{ marginTop: 4 }}>{formatSignedPct(position.unrealized_pnl_pct)}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
