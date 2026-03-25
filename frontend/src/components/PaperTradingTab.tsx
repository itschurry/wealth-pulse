import { useEffect, useMemo, useState } from 'react';
import { usePaperTrading } from '../hooks/usePaperTrading';
import type { PaperEngineConfig, PaperSeedPositionInput, PaperSkippedItem, PaperStrategyProfile } from '../types';

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
  if (reason.startsWith('technicals_error:')) {
    const detail = reason.slice('technicals_error:'.length).trim();
    return `지표 오류 (${detail})`;
  }
  return SKIP_REASON_LABELS[reason] ?? reason;
}

function SkipCodeBadge({ item }: { item: PaperSkippedItem }) {
  const [hovered, setHovered] = useState(false);
  const label = labelSkipReason(item.reason);
  const display = item.name || item.code || '—';
  return (
    <span
      style={{ position: 'relative', display: 'inline-block' }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <span style={{
        display: 'inline-block',
        padding: '1px 6px',
        borderRadius: 4,
        background: 'var(--bg-2)',
        border: '1px solid var(--border)',
        cursor: 'default',
        fontSize: 11,
        fontWeight: 600,
        color: 'var(--text-2)',
        userSelect: 'none',
      }}>
        {display}
      </span>
      {hovered && (
        <span style={{
          position: 'absolute',
          bottom: 'calc(100% + 6px)',
          left: '50%',
          transform: 'translateX(-50%)',
          background: '#2a2a2a',
          color: '#f0f0f0',
          padding: '4px 9px',
          borderRadius: 6,
          fontSize: 11,
          whiteSpace: 'nowrap',
          zIndex: 200,
          pointerEvents: 'none',
          boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
          border: '1px solid #444',
        }}>
          {label}
          <span style={{
            position: 'absolute',
            top: '100%',
            left: '50%',
            transform: 'translateX(-50%)',
            width: 0,
            height: 0,
            borderLeft: '5px solid transparent',
            borderRight: '5px solid transparent',
            borderTop: '5px solid #444',
          }} />
          <span style={{
            position: 'absolute',
            top: 'calc(100% - 1px)',
            left: '50%',
            transform: 'translateX(-50%)',
            width: 0,
            height: 0,
            borderLeft: '5px solid transparent',
            borderRight: '5px solid transparent',
            borderTop: '5px solid #2a2a2a',
          }} />
        </span>
      )}
    </span>
  );
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

function withCommaDecimal(raw: string, maxFractionDigits = 4) {
  const cleaned = raw.replace(/,/g, '').replace(/[^\d.]/g, '');
  if (!cleaned) return '';
  const hasDot = cleaned.includes('.');
  const [intRaw, fractionRaw = ''] = cleaned.split('.', 2);
  const normalizedInt = intRaw ? new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 0 }).format(Number(intRaw)) : '0';
  if (!hasDot) return normalizedInt;
  return `${normalizedInt}.${fractionRaw.slice(0, maxFractionDigits)}`;
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
const DEFAULT_PAPER_STRATEGY_PROFILES: Record<'KOSPI' | 'NASDAQ', PaperStrategyProfile> = {
  KOSPI: {
    market: 'KOSPI',
    max_positions: 5,
    max_holding_days: 15,
    rsi_min: 45,
    rsi_max: 62,
    volume_ratio_min: 1.0,
    adx_min: 10,
    mfi_min: 20,
    mfi_max: 80,
    bb_pct_min: 0.05,
    bb_pct_max: 0.95,
    stoch_k_min: 10,
    stoch_k_max: 90,
    stop_loss_pct: 5,
    take_profit_pct: null,
    signal_interval: '1d',
    signal_range: '6mo',
  },
  NASDAQ: {
    market: 'NASDAQ',
    max_positions: 5,
    max_holding_days: 30,
    rsi_min: 45,
    rsi_max: 68,
    volume_ratio_min: 1.2,
    adx_min: 10,
    mfi_min: 20,
    mfi_max: 80,
    bb_pct_min: 0.05,
    bb_pct_max: 0.95,
    stoch_k_min: 10,
    stoch_k_max: 90,
    stop_loss_pct: null,
    take_profit_pct: null,
    signal_interval: '1d',
    signal_range: '6mo',
  },
};

function cloneDefaultProfiles(): Record<'KOSPI' | 'NASDAQ', PaperStrategyProfile> {
  return {
    KOSPI: { ...DEFAULT_PAPER_STRATEGY_PROFILES.KOSPI },
    NASDAQ: { ...DEFAULT_PAPER_STRATEGY_PROFILES.NASDAQ },
  };
}

type SeedHoldingFormRow = {
  id: string;
  market: 'KOSPI' | 'NASDAQ';
  code: string;
  name: string;
  quantity: string;
  avgPriceLocal: string;
};

function createSeedHoldingRow(seed?: Partial<PaperSeedPositionInput> & { name?: string }): SeedHoldingFormRow {
  return {
    id: `seed-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    market: seed?.market || 'KOSPI',
    code: seed?.code || '',
    name: seed?.name || '',
    quantity: seed?.quantity ? formatIntegerInput(seed.quantity) : '',
    avgPriceLocal: seed?.avg_price_local ? withCommaDecimal(String(seed.avg_price_local)) : '',
  };
}

function normalizeProfileMap(
  profiles?: Partial<Record<'KOSPI' | 'NASDAQ', Partial<PaperStrategyProfile>>>,
): Record<'KOSPI' | 'NASDAQ', PaperStrategyProfile> {
  const base = cloneDefaultProfiles();
  (['KOSPI', 'NASDAQ'] as const).forEach((market) => {
    const raw = profiles?.[market];
    if (!raw) return;
    const baseProfile = base[market];
    base[market] = {
      ...baseProfile,
      ...raw,
      market,
      adx_min: raw.adx_min ?? baseProfile.adx_min,
      mfi_min: raw.mfi_min ?? baseProfile.mfi_min,
      mfi_max: raw.mfi_max ?? baseProfile.mfi_max,
      bb_pct_min: raw.bb_pct_min ?? baseProfile.bb_pct_min,
      bb_pct_max: raw.bb_pct_max ?? baseProfile.bb_pct_max,
      stoch_k_min: raw.stoch_k_min ?? baseProfile.stoch_k_min,
      stoch_k_max: raw.stoch_k_max ?? baseProfile.stoch_k_max,
      signal_interval: (raw.signal_interval || baseProfile.signal_interval) as PaperStrategyProfile['signal_interval'],
      signal_range: (raw.signal_range || baseProfile.signal_range) as PaperStrategyProfile['signal_range'],
    };
  });
  return base;
}

function profileSignature(profiles?: Partial<Record<'KOSPI' | 'NASDAQ', Partial<PaperStrategyProfile>>>) {
  const normalized = normalizeProfileMap(profiles);
  return JSON.stringify({
    KOSPI: normalized.KOSPI,
    NASDAQ: normalized.NASDAQ,
  });
}

export function PaperTradingTab() {
  const { account, engineState, status, lastError, refresh, reset, autoInvest, refreshEngineStatus, startEngine, stopEngine } = usePaperTrading();
  const [seedKrw, setSeedKrw] = useState('10,000,000');
  const [seedUsd, setSeedUsd] = useState('10,000');
  const [paperDays, setPaperDays] = useState('7');
  const [seedHoldings, setSeedHoldings] = useState<SeedHoldingFormRow[]>([]);
  const [seedHoldingsDirty, setSeedHoldingsDirty] = useState(false);
  const [autoMarket] = useState<'KOSPI' | 'NASDAQ'>('NASDAQ');
  const [autoMaxPositions, setAutoMaxPositions] = useState('5');
  const [autoMinScore, setAutoMinScore] = useState('50');
  const [autoIncludeNeutral, setAutoIncludeNeutral] = useState(true);
  const [engineIntervalSeconds, setEngineIntervalSeconds] = useState('300');
  const [engineRunKOSPI, setEngineRunKOSPI] = useState(true);
  const [engineRunNASDAQ, setEngineRunNASDAQ] = useState(true);
  const [engineDailyBuyLimit, setEngineDailyBuyLimit] = useState('100');
  const [engineDailySellLimit, setEngineDailySellLimit] = useState('100');
  const [engineMaxOrdersPerSymbol, setEngineMaxOrdersPerSymbol] = useState('3');
  const [strategyEditMarket, setStrategyEditMarket] = useState<'KOSPI' | 'NASDAQ'>('KOSPI');
  const [engineMarketProfiles, setEngineMarketProfiles] = useState<Record<'KOSPI' | 'NASDAQ', PaperStrategyProfile>>(cloneDefaultProfiles);
  const [themeGateEnabled, setThemeGateEnabled] = useState(true);
  const [themeMinScore, setThemeMinScore] = useState('2.5');
  const [themeMinNews, setThemeMinNews] = useState('1');
  const [themePriorityBonus, setThemePriorityBonus] = useState('2.0');
  const [statusMessage, setStatusMessage] = useState('');
  const [lastAutoInvestSkipped, setLastAutoInvestSkipped] = useState<PaperSkippedItem[]>([]);
  const [optApplyStatus, setOptApplyStatus] = useState<'idle' | 'loading' | 'applied' | 'error'>('idle');

  const initialTotalKrw = useMemo(() => {
    return account.starting_equity_krw || 0;
  }, [account.starting_equity_krw]);

  const runningReturnPct = useMemo(() => {
    if (!initialTotalKrw) return 0;
    return ((account.equity_krw / initialTotalKrw) - 1) * 100;
  }, [account.equity_krw, initialTotalKrw]);

  const activeProfile = engineMarketProfiles[strategyEditMarket];

  function patchActiveProfile(patch: Partial<PaperStrategyProfile>) {
    setEngineMarketProfiles((prev) => ({
      ...prev,
      [strategyEditMarket]: {
        ...prev[strategyEditMarket],
        ...patch,
        market: strategyEditMarket,
      },
    }));
  }

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
    const maxPositionsPerMarket = Math.max(1, Math.min(20, Math.floor(Number(autoMaxPositions) || 5)));
    const normalizedProfiles: Record<'KOSPI' | 'NASDAQ', PaperStrategyProfile> = {
      KOSPI: {
        ...engineMarketProfiles.KOSPI,
        market: 'KOSPI',
        max_positions: maxPositionsPerMarket,
        max_holding_days: Math.max(1, Math.min(180, Math.floor(Number(engineMarketProfiles.KOSPI.max_holding_days) || 15))),
        rsi_min: Math.max(10, Math.min(90, Number(engineMarketProfiles.KOSPI.rsi_min) || 45)),
        rsi_max: Math.max(10, Math.min(90, Number(engineMarketProfiles.KOSPI.rsi_max) || 62)),
        volume_ratio_min: Math.max(0.5, Math.min(5, Number(engineMarketProfiles.KOSPI.volume_ratio_min) || 1)),
        adx_min: engineMarketProfiles.KOSPI.adx_min == null ? null : Math.max(5, Math.min(40, Number(engineMarketProfiles.KOSPI.adx_min) || 10)),
        mfi_min: engineMarketProfiles.KOSPI.mfi_min == null ? null : Math.max(0, Math.min(100, Number(engineMarketProfiles.KOSPI.mfi_min) || 20)),
        mfi_max: engineMarketProfiles.KOSPI.mfi_max == null ? null : Math.max(0, Math.min(100, Number(engineMarketProfiles.KOSPI.mfi_max) || 80)),
        bb_pct_min: engineMarketProfiles.KOSPI.bb_pct_min == null ? null : Math.max(0, Math.min(1, Number(engineMarketProfiles.KOSPI.bb_pct_min) || 0.05)),
        bb_pct_max: engineMarketProfiles.KOSPI.bb_pct_max == null ? null : Math.max(0, Math.min(1, Number(engineMarketProfiles.KOSPI.bb_pct_max) || 0.95)),
        stoch_k_min: engineMarketProfiles.KOSPI.stoch_k_min == null ? null : Math.max(0, Math.min(100, Number(engineMarketProfiles.KOSPI.stoch_k_min) || 10)),
        stoch_k_max: engineMarketProfiles.KOSPI.stoch_k_max == null ? null : Math.max(0, Math.min(100, Number(engineMarketProfiles.KOSPI.stoch_k_max) || 90)),
        stop_loss_pct: engineMarketProfiles.KOSPI.stop_loss_pct === null ? null : Math.max(1, Math.min(50, Number(engineMarketProfiles.KOSPI.stop_loss_pct) || 5)),
        take_profit_pct: engineMarketProfiles.KOSPI.take_profit_pct === null ? null : Math.max(1, Math.min(100, Number(engineMarketProfiles.KOSPI.take_profit_pct) || 18)),
      },
      NASDAQ: {
        ...engineMarketProfiles.NASDAQ,
        market: 'NASDAQ',
        max_positions: maxPositionsPerMarket,
        max_holding_days: Math.max(1, Math.min(180, Math.floor(Number(engineMarketProfiles.NASDAQ.max_holding_days) || 30))),
        rsi_min: Math.max(10, Math.min(90, Number(engineMarketProfiles.NASDAQ.rsi_min) || 45)),
        rsi_max: Math.max(10, Math.min(90, Number(engineMarketProfiles.NASDAQ.rsi_max) || 68)),
        volume_ratio_min: Math.max(0.5, Math.min(5, Number(engineMarketProfiles.NASDAQ.volume_ratio_min) || 1.2)),
        adx_min: engineMarketProfiles.NASDAQ.adx_min == null ? null : Math.max(5, Math.min(40, Number(engineMarketProfiles.NASDAQ.adx_min) || 10)),
        mfi_min: engineMarketProfiles.NASDAQ.mfi_min == null ? null : Math.max(0, Math.min(100, Number(engineMarketProfiles.NASDAQ.mfi_min) || 20)),
        mfi_max: engineMarketProfiles.NASDAQ.mfi_max == null ? null : Math.max(0, Math.min(100, Number(engineMarketProfiles.NASDAQ.mfi_max) || 80)),
        bb_pct_min: engineMarketProfiles.NASDAQ.bb_pct_min == null ? null : Math.max(0, Math.min(1, Number(engineMarketProfiles.NASDAQ.bb_pct_min) || 0.05)),
        bb_pct_max: engineMarketProfiles.NASDAQ.bb_pct_max == null ? null : Math.max(0, Math.min(1, Number(engineMarketProfiles.NASDAQ.bb_pct_max) || 0.95)),
        stoch_k_min: engineMarketProfiles.NASDAQ.stoch_k_min == null ? null : Math.max(0, Math.min(100, Number(engineMarketProfiles.NASDAQ.stoch_k_min) || 10)),
        stoch_k_max: engineMarketProfiles.NASDAQ.stoch_k_max == null ? null : Math.max(0, Math.min(100, Number(engineMarketProfiles.NASDAQ.stoch_k_max) || 90)),
        stop_loss_pct: engineMarketProfiles.NASDAQ.stop_loss_pct === null ? null : Math.max(1, Math.min(50, Number(engineMarketProfiles.NASDAQ.stop_loss_pct) || 5)),
        take_profit_pct: engineMarketProfiles.NASDAQ.take_profit_pct === null ? null : Math.max(1, Math.min(100, Number(engineMarketProfiles.NASDAQ.take_profit_pct) || 18)),
      },
    };
    const primaryProfile = normalizedProfiles[strategyEditMarket];
    return {
      interval_seconds: Math.max(30, Math.min(3600, Math.floor(Number(engineIntervalSeconds) || 300))),
      signal_interval: primaryProfile.signal_interval,
      signal_range: primaryProfile.signal_range,
      markets,
      max_positions_per_market: maxPositionsPerMarket,
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
      rsi_min: primaryProfile.rsi_min,
      rsi_max: primaryProfile.rsi_max,
      volume_ratio_min: primaryProfile.volume_ratio_min,
      adx_min: primaryProfile.adx_min,
      mfi_min: primaryProfile.mfi_min,
      mfi_max: primaryProfile.mfi_max,
      bb_pct_min: primaryProfile.bb_pct_min,
      bb_pct_max: primaryProfile.bb_pct_max,
      stoch_k_min: primaryProfile.stoch_k_min,
      stoch_k_max: primaryProfile.stoch_k_max,
      stop_loss_pct: primaryProfile.stop_loss_pct ?? 0,
      take_profit_pct: primaryProfile.take_profit_pct ?? 0,
      max_holding_days: primaryProfile.max_holding_days,
      market_profiles: normalizedProfiles,
    };
  };

  const desiredEngineConfig = useMemo(() => buildEngineConfig(), [
    autoIncludeNeutral,
    autoMaxPositions,
    autoMinScore,
    engineDailyBuyLimit,
    engineDailySellLimit,
    engineIntervalSeconds,
    engineMaxOrdersPerSymbol,
    engineRunKOSPI,
    engineRunNASDAQ,
    JSON.stringify(engineMarketProfiles),
    themeGateEnabled,
    themeMinNews,
    themePriorityBonus,
    themeMinScore,
  ]);

  const appliedMarkets = engineState.config?.markets || [];
  const isKospiRunning = engineState.running && appliedMarkets.includes('KOSPI');
  const isNasdaqRunning = engineState.running && appliedMarkets.includes('NASDAQ');
  const candidateCountsByMarket = engineState.last_summary?.candidate_counts_by_market || {};
  const isEngineConfigDirty = useMemo(() => {
    const cfg = desiredEngineConfig;
    const applied = engineState.config;
    if (!engineState.running || !cfg || !applied) return false;
    return (
      cfg.interval_seconds !== applied.interval_seconds ||
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
      profileSignature(cfg.market_profiles) !== profileSignature(applied.market_profiles)
    );
  }, [desiredEngineConfig, engineState.config, engineState.running]);

  useEffect(() => {
    setSeedKrw(formatIntegerInput(account.initial_cash_krw));
    setSeedUsd(formatIntegerInput(account.initial_cash_usd));
    setPaperDays(formatIntegerInput(account.paper_days));
  }, [account.initial_cash_krw, account.initial_cash_usd, account.paper_days]);

  useEffect(() => {
    if (seedHoldingsDirty) return;
    setSeedHoldings(account.positions.map((position) => createSeedHoldingRow({
      market: position.market,
      code: position.code,
      name: position.name,
      quantity: position.quantity,
      avg_price_local: position.avg_price_local,
    })));
  }, [account.positions, seedHoldingsDirty]);

  useEffect(() => {
    const cfg = engineState.config;
    if (!cfg) return;

    if (cfg.interval_seconds !== undefined) setEngineIntervalSeconds(String(cfg.interval_seconds));
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
    if (cfg.market_profiles) {
      setEngineMarketProfiles(normalizeProfileMap(cfg.market_profiles));
    } else {
      setEngineMarketProfiles((prev) => ({
        KOSPI: {
          ...prev.KOSPI,
          signal_interval: (cfg.signal_interval || prev.KOSPI.signal_interval) as PaperStrategyProfile['signal_interval'],
          signal_range: (cfg.signal_range || prev.KOSPI.signal_range) as PaperStrategyProfile['signal_range'],
          rsi_min: cfg.rsi_min ?? prev.KOSPI.rsi_min,
          rsi_max: cfg.rsi_max ?? prev.KOSPI.rsi_max,
          volume_ratio_min: cfg.volume_ratio_min ?? prev.KOSPI.volume_ratio_min,
          adx_min: cfg.adx_min ?? prev.KOSPI.adx_min,
          mfi_min: cfg.mfi_min ?? prev.KOSPI.mfi_min,
          mfi_max: cfg.mfi_max ?? prev.KOSPI.mfi_max,
          bb_pct_min: cfg.bb_pct_min ?? prev.KOSPI.bb_pct_min,
          bb_pct_max: cfg.bb_pct_max ?? prev.KOSPI.bb_pct_max,
          stoch_k_min: cfg.stoch_k_min ?? prev.KOSPI.stoch_k_min,
          stoch_k_max: cfg.stoch_k_max ?? prev.KOSPI.stoch_k_max,
          stop_loss_pct: cfg.stop_loss_pct ?? prev.KOSPI.stop_loss_pct,
          take_profit_pct: cfg.take_profit_pct ?? prev.KOSPI.take_profit_pct,
          max_holding_days: cfg.max_holding_days ?? prev.KOSPI.max_holding_days,
        },
        NASDAQ: {
          ...prev.NASDAQ,
          signal_interval: (cfg.signal_interval || prev.NASDAQ.signal_interval) as PaperStrategyProfile['signal_interval'],
          signal_range: (cfg.signal_range || prev.NASDAQ.signal_range) as PaperStrategyProfile['signal_range'],
          rsi_min: cfg.rsi_min ?? prev.NASDAQ.rsi_min,
          rsi_max: cfg.rsi_max ?? prev.NASDAQ.rsi_max,
          volume_ratio_min: cfg.volume_ratio_min ?? prev.NASDAQ.volume_ratio_min,
          adx_min: cfg.adx_min ?? prev.NASDAQ.adx_min,
          mfi_min: cfg.mfi_min ?? prev.NASDAQ.mfi_min,
          mfi_max: cfg.mfi_max ?? prev.NASDAQ.mfi_max,
          bb_pct_min: cfg.bb_pct_min ?? prev.NASDAQ.bb_pct_min,
          bb_pct_max: cfg.bb_pct_max ?? prev.NASDAQ.bb_pct_max,
          stoch_k_min: cfg.stoch_k_min ?? prev.NASDAQ.stoch_k_min,
          stoch_k_max: cfg.stoch_k_max ?? prev.NASDAQ.stoch_k_max,
          stop_loss_pct: cfg.stop_loss_pct ?? prev.NASDAQ.stop_loss_pct,
          take_profit_pct: cfg.take_profit_pct ?? prev.NASDAQ.take_profit_pct,
          max_holding_days: cfg.max_holding_days ?? prev.NASDAQ.max_holding_days,
        },
      }));
    }
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
    engineState.config?.max_orders_per_symbol_per_day,
    engineState.config?.max_positions_per_market,
    engineState.config?.min_score,
    engineState.config?.theme_gate_enabled,
    engineState.config?.theme_min_news,
    engineState.config?.theme_priority_bonus,
    engineState.config?.theme_min_score,
    JSON.stringify(engineState.config?.market_profiles || {}),
  ]);

  async function handleApplyOptimizedParams() {
    setOptApplyStatus('loading');
    try {
      const res = await fetch('/api/optimized-params');
      const data = await res.json();
      if (data.status !== 'ok' || !data.global_params) {
        setOptApplyStatus('error');
        setStatusMessage('최적화 결과가 없습니다. 먼저 백테스터 탭에서 최적화를 실행하세요.');
        return;
      }
      const gp = data.global_params as Record<string, number | null>;
      setEngineMarketProfiles((prev) => {
        const patch: Partial<PaperStrategyProfile> = {
          ...(gp.stop_loss_pct != null && { stop_loss_pct: gp.stop_loss_pct }),
          ...(gp.take_profit_pct != null && { take_profit_pct: gp.take_profit_pct }),
          ...(gp.max_holding_days != null && { max_holding_days: gp.max_holding_days }),
          ...(gp.rsi_min != null && { rsi_min: gp.rsi_min }),
          ...(gp.rsi_max != null && { rsi_max: gp.rsi_max }),
          ...(gp.volume_ratio_min != null && { volume_ratio_min: gp.volume_ratio_min }),
          ...(gp.adx_min != null && { adx_min: gp.adx_min }),
          ...(gp.mfi_min != null && { mfi_min: gp.mfi_min }),
          ...(gp.mfi_max != null && { mfi_max: gp.mfi_max }),
          ...(gp.bb_pct_min != null && { bb_pct_min: gp.bb_pct_min }),
          ...(gp.bb_pct_max != null && { bb_pct_max: gp.bb_pct_max }),
          ...(gp.stoch_k_min != null && { stoch_k_min: gp.stoch_k_min }),
          ...(gp.stoch_k_max != null && { stoch_k_max: gp.stoch_k_max }),
        };
        return {
          KOSPI: { ...prev.KOSPI, ...patch, market: 'KOSPI' },
          NASDAQ: { ...prev.NASDAQ, ...patch, market: 'NASDAQ' },
        };
      });
      setOptApplyStatus('applied');
      setStatusMessage(`최적화 파라미터 적용 완료 (손절 ${gp.stop_loss_pct ?? '—'}% · 익절 ${gp.take_profit_pct ?? '—'}% · ADX ${gp.adx_min ?? '—'} · MFI ${gp.mfi_min ?? '—'}~${gp.mfi_max ?? '—'})`);
    } catch {
      setOptApplyStatus('error');
      setStatusMessage('최적화 파라미터 조회 중 오류가 발생했습니다.');
    }
  }

  function handleAddSeedHolding() {
    setSeedHoldingsDirty(true);
    setSeedHoldings((prev) => [...prev, createSeedHoldingRow()]);
  }

  function handleSeedHoldingChange(id: string, patch: Partial<SeedHoldingFormRow>) {
    setSeedHoldingsDirty(true);
    setSeedHoldings((prev) => prev.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  }

  function handleRemoveSeedHolding(id: string) {
    setSeedHoldingsDirty(true);
    setSeedHoldings((prev) => prev.filter((item) => item.id !== id));
  }

  function buildSeedHoldingsPayload():
    | { ok: true; items: PaperSeedPositionInput[] }
    | { ok: false; error: string } {
    const items: PaperSeedPositionInput[] = [];
    for (let index = 0; index < seedHoldings.length; index += 1) {
      const row = seedHoldings[index];
      const code = row.code.trim().toUpperCase();
      const name = row.name.trim();
      const quantity = Math.floor(parseCommaNumber(row.quantity));
      const avgPriceLocal = parseCommaNumber(row.avgPriceLocal);
      const isBlank = !code && !name && quantity <= 0 && avgPriceLocal <= 0;
      if (isBlank) continue;
      if (!code) {
        return { ok: false, error: `보유 종목 ${index + 1}행: 종목코드를 입력해 주세요.` };
      }
      if (quantity <= 0) {
        return { ok: false, error: `보유 종목 ${index + 1}행: 수량은 1 이상이어야 합니다.` };
      }
      if (avgPriceLocal <= 0) {
        return { ok: false, error: `보유 종목 ${index + 1}행: 평균단가는 0보다 커야 합니다.` };
      }
      items.push({
        market: row.market,
        code,
        name,
        quantity,
        avg_price_local: avgPriceLocal,
      });
    }
    return { ok: true, items };
  }

  async function handleReset() {
    const seedPayload = buildSeedHoldingsPayload();
    if (!seedPayload.ok) {
      setStatusMessage(seedPayload.error);
      return;
    }
    const result = await reset({
      initial_cash_krw: parseCommaNumber(seedKrw),
      initial_cash_usd: parseCommaNumber(seedUsd),
      paper_days: Math.max(1, Math.min(365, Math.floor(parseCommaNumber(paperDays)))),
      seed_positions: seedPayload.items,
    });
    if (!result.ok) {
      setStatusMessage(result.error || '초기화 실패');
      return;
    }
    setSeedHoldings(seedPayload.items.map((item) => createSeedHoldingRow(item)));
    setSeedHoldingsDirty(false);
    setStatusMessage(`모의계좌를 초기화했습니다. 시작 보유 종목 ${seedPayload.items.length}건 반영.`);
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
        <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-1)' }}>보유 종목 현황</div>
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
        <div style={{ display: 'grid', gap: 10, padding: '12px 14px', borderRadius: 14, border: '1px solid var(--border)', background: 'var(--bg-soft)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <div>
              <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-1)' }}>시작 보유 종목</div>
              <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 4 }}>초기화 적용 시 아래 종목이 시작 포지션으로 들어갑니다. 현금은 위 자금과 별도로 유지됩니다.</div>
            </div>
            <button className="ghost-button" onClick={handleAddSeedHolding}>종목 추가</button>
          </div>
          {seedHoldings.length === 0 && (
            <div style={{ fontSize: 13, color: 'var(--text-4)' }}>추가된 시작 보유 종목이 없습니다.</div>
          )}
          {seedHoldings.length > 0 && (
            <div style={{ display: 'grid', gap: 10 }}>
              {seedHoldings.map((row, index) => (
                <div key={row.id} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10, alignItems: 'end', padding: '12px', borderRadius: 12, border: '1px solid var(--border)', background: 'rgba(255,255,255,0.02)' }}>
                  <label style={{ display: 'grid', gap: 6 }}>
                    <span style={{ fontSize: 12, color: 'var(--text-3)' }}>시장</span>
                    <select className="backtest-input" value={row.market} onChange={(event) => handleSeedHoldingChange(row.id, { market: event.target.value as 'KOSPI' | 'NASDAQ' })}>
                      <option value="KOSPI">KOSPI</option>
                      <option value="NASDAQ">NASDAQ</option>
                    </select>
                  </label>
                  <label style={{ display: 'grid', gap: 6 }}>
                    <span style={{ fontSize: 12, color: 'var(--text-3)' }}>종목코드</span>
                    <input className="backtest-input" value={row.code} onChange={(event) => handleSeedHoldingChange(row.id, { code: event.target.value.toUpperCase() })} placeholder={row.market === 'KOSPI' ? '005930' : 'AAPL'} />
                  </label>
                  <label style={{ display: 'grid', gap: 6 }}>
                    <span style={{ fontSize: 12, color: 'var(--text-3)' }}>종목명</span>
                    <input className="backtest-input" value={row.name} onChange={(event) => handleSeedHoldingChange(row.id, { name: event.target.value })} placeholder="삼성전자" />
                  </label>
                  <label style={{ display: 'grid', gap: 6 }}>
                    <span style={{ fontSize: 12, color: 'var(--text-3)' }}>수량</span>
                    <input className="backtest-input" inputMode="numeric" value={row.quantity} onChange={(event) => handleSeedHoldingChange(row.id, { quantity: withCommaDigits(event.target.value) })} placeholder="160" />
                  </label>
                  <label style={{ display: 'grid', gap: 6 }}>
                    <span style={{ fontSize: 12, color: 'var(--text-3)' }}>평균 매수가</span>
                    <input className="backtest-input" inputMode="decimal" value={row.avgPriceLocal} onChange={(event) => handleSeedHoldingChange(row.id, { avgPriceLocal: withCommaDecimal(event.target.value, row.market === 'NASDAQ' ? 4 : 0) })} placeholder={row.market === 'NASDAQ' ? '182.35' : '187,193'} />
                  </label>
                  <button className="ghost-button" onClick={() => handleRemoveSeedHolding(row.id)} style={{ alignSelf: 'end' }}>
                    {index + 1}행 삭제
                  </button>
                </div>
              ))}
            </div>
          )}
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
            {(engineState.last_summary?.skipped?.length ?? 0) > 0 && (
              <div style={{ marginTop: 6, borderTop: '1px solid var(--border)', paddingTop: 6 }}>
                <div style={{ fontWeight: 700, color: 'var(--text-2)', marginBottom: 4 }}>
                  스킵 이유 ({engineState.last_summary!.skipped!.length}건)
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {(engineState.last_summary?.skipped ?? []).map((item, idx) => (
                    <SkipCodeBadge key={idx} item={item} />
                  ))}
                </div>
              </div>
            )}
            {(engineState.last_summary?.skipped?.length ?? 0) === 0 && (
              <div style={{ marginTop: 4 }}>스킵: 없음</div>
            )}
            <div style={{ marginTop: 4, color: engineState.last_error ? 'var(--down)' : 'var(--text-4)' }}>
              오류: {engineState.last_error || '없음'}
            </div>
          </div>
          <div style={{ padding: '10px 12px', border: '1px solid var(--border)', borderRadius: 12, background: 'var(--bg-soft)', fontSize: 12, color: 'var(--text-3)' }}>
            <div>KOSPI: <b style={{ color: isKospiRunning ? 'var(--up)' : 'var(--text-2)' }}>{isKospiRunning ? '실행 중' : '중지'}</b></div>
            <div style={{ marginTop: 4 }}>적용 시장: {appliedMarkets.includes('KOSPI') ? '포함' : '미포함'}</div>
            {engineState.last_summary?.market_stats?.['KOSPI']?.market_closed && (
              <div style={{ marginTop: 4, color: 'var(--text-4)' }}>장외 시간 (거래 스킵)</div>
            )}
          </div>
          <div style={{ padding: '10px 12px', border: '1px solid var(--border)', borderRadius: 12, background: 'var(--bg-soft)', fontSize: 12, color: 'var(--text-3)' }}>
            <div>NASDAQ: <b style={{ color: isNasdaqRunning ? 'var(--up)' : 'var(--text-2)' }}>{isNasdaqRunning ? '실행 중' : '중지'}</b></div>
            <div style={{ marginTop: 4 }}>적용 시장: {appliedMarkets.includes('NASDAQ') ? '포함' : '미포함'}</div>
            {engineState.last_summary?.market_stats?.['NASDAQ']?.market_closed && (
              <div style={{ marginTop: 4, color: 'var(--text-4)' }}>장외 시간 (거래 스킵)</div>
            )}
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
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>전략 편집 시장</span>
            <select className="backtest-input" value={strategyEditMarket} onChange={(event) => setStrategyEditMarket(event.target.value as 'KOSPI' | 'NASDAQ')}>
              <option value="KOSPI">KOSPI</option>
              <option value="NASDAQ">NASDAQ</option>
            </select>
          </label>
          <div style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>몬테카를로 최적화 결과 적용</span>
            <button
              onClick={handleApplyOptimizedParams}
              disabled={optApplyStatus === 'loading'}
              style={{ padding: '7px 12px', borderRadius: 8, fontSize: 12, background: optApplyStatus === 'applied' ? 'var(--up)' : 'var(--bg-2)', color: optApplyStatus === 'applied' ? '#fff' : 'var(--text-2)', border: '1px solid var(--border)', cursor: optApplyStatus === 'loading' ? 'not-allowed' : 'pointer', fontWeight: 600 }}
            >
              {optApplyStatus === 'loading' ? '불러오는 중...' : optApplyStatus === 'applied' ? '✓ 적용됨' : '최적화 파라미터 적용'}
            </button>
          </div>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>지표 봉 간격</span>
            <select className="backtest-input" value={activeProfile.signal_interval} onChange={(event) => patchActiveProfile({ signal_interval: event.target.value as PaperStrategyProfile['signal_interval'] })}>
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
            <select className="backtest-input" value={activeProfile.signal_range} onChange={(event) => patchActiveProfile({ signal_range: event.target.value as PaperStrategyProfile['signal_range'] })}>
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
              <input className="backtest-input" type="number" min={10} max={90} value={activeProfile.rsi_min} onChange={(event) => patchActiveProfile({ rsi_min: Number(event.target.value) })} />
              <input className="backtest-input" type="number" min={10} max={90} value={activeProfile.rsi_max} onChange={(event) => patchActiveProfile({ rsi_max: Number(event.target.value) })} />
            </div>
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>최소 거래량 배수</span>
            <input className="backtest-input" type="number" min={0.5} max={5} step={0.1} value={activeProfile.volume_ratio_min} onChange={(event) => patchActiveProfile({ volume_ratio_min: Number(event.target.value) })} />
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>ADX 최소값</span>
            <input className="backtest-input" type="number" min={5} max={40} step={1} value={activeProfile.adx_min ?? ''} onChange={(event) => patchActiveProfile({ adx_min: event.target.value === '' ? null : Number(event.target.value) })} />
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>MFI 최소/최대</span>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <input className="backtest-input" type="number" min={0} max={100} value={activeProfile.mfi_min ?? ''} onChange={(event) => patchActiveProfile({ mfi_min: event.target.value === '' ? null : Number(event.target.value) })} />
              <input className="backtest-input" type="number" min={0} max={100} value={activeProfile.mfi_max ?? ''} onChange={(event) => patchActiveProfile({ mfi_max: event.target.value === '' ? null : Number(event.target.value) })} />
            </div>
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>BB %b 최소/최대</span>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <input className="backtest-input" type="number" min={0} max={1} step={0.01} value={activeProfile.bb_pct_min ?? ''} onChange={(event) => patchActiveProfile({ bb_pct_min: event.target.value === '' ? null : Number(event.target.value) })} />
              <input className="backtest-input" type="number" min={0} max={1} step={0.01} value={activeProfile.bb_pct_max ?? ''} onChange={(event) => patchActiveProfile({ bb_pct_max: event.target.value === '' ? null : Number(event.target.value) })} />
            </div>
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>Stochastic K 최소/최대</span>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <input className="backtest-input" type="number" min={0} max={100} value={activeProfile.stoch_k_min ?? ''} onChange={(event) => patchActiveProfile({ stoch_k_min: event.target.value === '' ? null : Number(event.target.value) })} />
              <input className="backtest-input" type="number" min={0} max={100} value={activeProfile.stoch_k_max ?? ''} onChange={(event) => patchActiveProfile({ stoch_k_max: event.target.value === '' ? null : Number(event.target.value) })} />
            </div>
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>손절 기준(%)</span>
            <input className="backtest-input" type="number" min={1} max={50} value={activeProfile.stop_loss_pct ?? ''} onChange={(event) => patchActiveProfile({ stop_loss_pct: event.target.value === '' ? null : Number(event.target.value) })} />
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>익절 기준(%)</span>
            <input className="backtest-input" type="number" min={1} max={100} value={activeProfile.take_profit_pct ?? ''} onChange={(event) => patchActiveProfile({ take_profit_pct: event.target.value === '' ? null : Number(event.target.value) })} />
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>최대 보유일</span>
            <input className="backtest-input" type="number" min={1} max={180} value={activeProfile.max_holding_days} onChange={(event) => patchActiveProfile({ max_holding_days: Number(event.target.value) })} />
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
        {lastAutoInvestSkipped.length > 0 && (
          <div style={{ marginTop: 8, padding: '10px 12px', border: '1px solid var(--border)', borderRadius: 12, background: 'var(--bg-soft)', fontSize: 12, color: 'var(--text-3)' }}>
            <div style={{ fontWeight: 700, color: 'var(--text-2)', marginBottom: 6 }}>1회 자동매수 스킵 내역 ({lastAutoInvestSkipped.length}건)</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {lastAutoInvestSkipped.map((item, idx) => (
                <SkipCodeBadge key={idx} item={item} />
              ))}
            </div>
          </div>
        )}
      </div>

      {(statusMessage || lastError) && (
        <div className="page-section" style={{ fontSize: 13, color: lastError ? 'var(--down)' : 'var(--text-2)' }}>
          {lastError || statusMessage}
        </div>
      )}

    </div>
  );
}
