import { useEffect, useState } from 'react';
import { defaultBacktestQuery, loadBacktestQuery, saveBacktestQuery, useBacktest } from '../hooks/useBacktest';
import type { BacktestData, BacktestQuery, BacktestTrade } from '../types';

function formatMoney(value?: number | null, currency: 'KRW' | 'USD' = 'KRW') {
  if (value === undefined || value === null) return '—';
  const formatted = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 0 }).format(value);
  return currency === 'USD' ? `$${formatted}` : `${formatted}원`;
}

function formatPct(value?: number | null) {
  if (value === undefined || value === null) return '—';
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
}

function MetricCard({ title, value, detail, tone = 'neutral' }: { title: string; value: string; detail: string; tone?: 'up' | 'down' | 'neutral' }) {
  const borderColor = tone === 'up' ? 'rgba(24,121,78,.2)' : tone === 'down' ? 'rgba(196,68,45,.2)' : 'var(--border)';
  return (
    <div style={{ background: 'var(--bg-soft)', border: `1px solid ${borderColor}`, borderRadius: 18, padding: 16 }}>
      <div style={{ fontSize: 12, color: 'var(--text-3)' }}>{title}</div>
      <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--text-1)', marginTop: 8 }}>{value}</div>
      <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 6, lineHeight: 1.6 }}>{detail}</div>
    </div>
  );
}

function Sparkline({ data, currency = 'KRW' }: { data: BacktestData; currency?: 'KRW' | 'USD' }) {
  const values = (data.equity_curve || []).map((item) => item.equity);
  if (values.length < 2) return null;

  const width = 720;
  const height = 180;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const points = values
    .map((value, index) => {
      const x = (index / Math.max(values.length - 1, 1)) * width;
      const y = height - ((value - min) / range) * height;
      return `${x},${y}`;
    })
    .join(' ');

  return (
    <div className="page-section" style={{ padding: 20 }}>
      <div style={{ fontSize: 12, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: '0.12em' }}>Equity Curve</div>
      <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-1)', marginTop: 6 }}>가상 자산 추이</div>
      <div style={{ marginTop: 16, padding: 16, borderRadius: 20, background: 'var(--bg-soft)', border: '1px solid var(--border)' }}>
        <svg viewBox={`0 0 ${width} ${height}`} width="100%" height="180" role="img" aria-label="backtest equity curve">
          <defs>
            <linearGradient id="equity-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="rgba(15,76,92,0.28)" />
              <stop offset="100%" stopColor="rgba(15,76,92,0.02)" />
            </linearGradient>
          </defs>
          <polyline
            fill="none"
            stroke="var(--accent)"
            strokeWidth="4"
            strokeLinejoin="round"
            strokeLinecap="round"
            points={points}
          />
          <polygon fill="url(#equity-fill)" points={`0,${height} ${points} ${width},${height}`} />
        </svg>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginTop: 10, fontSize: 12, color: 'var(--text-4)' }}>
          <span>{data.equity_curve?.[0]?.date || '시작일 없음'}</span>
          <span>{formatMoney(min, currency)} ~ {formatMoney(max, currency)}</span>
          <span>{data.equity_curve?.[data.equity_curve.length - 1]?.date || '종료일 없음'}</span>
        </div>
      </div>
    </div>
  );
}

function TradeBlock({ title, trades, tone, currency = 'KRW' }: { title: string; trades: BacktestTrade[]; tone: 'up' | 'down'; currency?: 'KRW' | 'USD' }) {
  return (
    <div className="page-section">
      <div style={{ fontSize: 12, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: '0.12em' }}>{tone === 'up' ? 'Best Trades' : 'Worst Trades'}</div>
      <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-1)', marginTop: 6 }}>{title}</div>
      <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
        {trades.length === 0 && (
          <div style={{ padding: '14px 16px', borderRadius: 18, border: '1px solid var(--border)', background: 'var(--bg-soft)', color: 'var(--text-4)', fontSize: 13 }}>
            표시할 거래가 없습니다.
          </div>
        )}
        {trades.map((trade) => (
          <div key={`${trade.code}-${trade.entry_date}-${trade.exit_date}`} style={{ display: 'grid', gap: 8, padding: '14px 16px', borderRadius: 18, border: '1px solid var(--border)', background: 'var(--bg-soft)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: 14, fontWeight: 800, color: 'var(--text-1)' }}>{trade.name}</div>
                <div style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 4 }}>{trade.code} · {trade.entry_date} → {trade.exit_date}</div>
              </div>
              <div style={{ fontSize: 15, fontWeight: 800, color: tone === 'up' ? 'var(--up)' : 'var(--down)' }}>
                {formatPct(trade.pnl_pct)}
              </div>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, fontSize: 12, color: 'var(--text-3)' }}>
              <span>진입 {formatMoney(trade.entry_price, currency)}</span>
              <span>청산 {formatMoney(trade.exit_price, currency)}</span>
              <span>{trade.holding_days}일 보유</span>
              <span>손익 {formatMoney(trade.pnl, currency)}</span>
              <span>{trade.reason}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function CountByMarket({ data }: { data: BacktestData }) {
  const counts = (data.symbols || []).reduce<Record<string, number>>((acc, item) => {
    const market = item.market || '기타';
    acc[market] = (acc[market] || 0) + 1;
    return acc;
  }, {});

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
      {Object.entries(counts).map(([market, count]) => (
        <span key={market} style={{ padding: '7px 10px', borderRadius: 999, border: '1px solid var(--border)', background: 'var(--bg-soft)', fontSize: 12, color: 'var(--text-3)' }}>
          {market} {count}종목
        </span>
      ))}
    </div>
  );
}

function NumericField({
  label,
  value,
  suffix,
  step = 1,
  min,
  onChange,
}: {
  label: string;
  value: number | null | undefined;
  suffix?: string;
  step?: number;
  min?: number;
  onChange: (value: number | null) => void;
}) {
  const [display, setDisplay] = useState('');

  useEffect(() => {
    if (value === undefined || value === null) {
      setDisplay('');
      return;
    }
    setDisplay(String(value));
  }, [value]);

  return (
    <label style={{ display: 'grid', gap: 8 }}>
      <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)' }}>{label}</span>
      <div className="backtest-input-wrap">
        <input
          className="backtest-input"
          type="number"
          value={display}
          min={min}
          step={step}
          onChange={(event) => {
            const raw = event.target.value.trim();
            if (!raw) {
              setDisplay('');
              onChange(null);
              return;
            }
            const parsed = Number(raw);
            if (!Number.isFinite(parsed)) return;
            setDisplay(raw);
            onChange(parsed);
          }}
          onBlur={() => {
            if (!display) return;
            const parsed = Number(display);
            if (!Number.isFinite(parsed)) return;
            const next = min !== undefined ? Math.max(parsed, min) : parsed;
            if (next !== parsed) {
              setDisplay(String(next));
              onChange(next);
            }
          }}
        />
        {suffix && <span className="backtest-input-suffix">{suffix}</span>}
      </div>
    </label>
  );
}

function CurrencyField({
  label,
  value,
  suffix,
  min,
  onChange,
}: {
  label: string;
  value: number | null | undefined;
  suffix?: string;
  min?: number;
  onChange: (value: number | null) => void;
}) {
  const [display, setDisplay] = useState('');

  useEffect(() => {
    if (value === undefined || value === null) {
      setDisplay('');
      return;
    }
    setDisplay(new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 0 }).format(value));
  }, [value]);

  return (
    <label style={{ display: 'grid', gap: 8 }}>
      <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)' }}>{label}</span>
      <div className="backtest-input-wrap">
        <input
          className="backtest-input"
          type="text"
          inputMode="numeric"
          value={display}
          onChange={(event) => {
            const digits = event.target.value.replace(/\D/g, '');
            if (!digits) {
              setDisplay('');
              onChange(null);
              return;
            }
            const parsed = Number(digits);
            if (!Number.isFinite(parsed)) return;
            setDisplay(new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 0 }).format(parsed));
            onChange(parsed);
          }}
          onBlur={() => {
            const digits = display.replace(/\D/g, '');
            if (!digits) return;
            const parsed = Number(digits);
            if (!Number.isFinite(parsed)) return;
            const next = min !== undefined ? Math.max(parsed, min) : parsed;
            if (next !== parsed) {
              onChange(next);
            }
            setDisplay(new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 0 }).format(next));
          }}
        />
        {suffix && <span className="backtest-input-suffix">{suffix}</span>}
      </div>
    </label>
  );
}

function buildPresetLabel(lookbackDays: number) {
  if (lookbackDays === 365) return '1년';
  if (lookbackDays === 730) return '2년';
  return '3년';
}

function marketCashPreset(market: BacktestQuery['market_scope']) {
  return market === 'nasdaq'
    ? { currency: 'USD' as const, initialCash: 10_000, min: 1_000, suffix: '달러', label: '초기 자금(USD)' }
    : { currency: 'KRW' as const, initialCash: 10_000_000, min: 1_000_000, suffix: '원', label: '초기 자금(KRW)' };
}

export function BacktestPage({ onBack }: { onBack: () => void }) {
  const [initialQuery] = useState<BacktestQuery>(loadBacktestQuery);
  const { data, status, run } = useBacktest(initialQuery);
  const [draft, setDraft] = useState<BacktestQuery>(initialQuery);
  const marketPreset = marketCashPreset(draft.market_scope);
  const baseCurrency = (data.config?.base_currency || marketPreset.currency) as 'KRW' | 'USD';
  const metrics = data.metrics;
  const equity = data.equity_curve || [];
  const trades = data.trades || [];
  const bestTrades = [...trades].sort((a, b) => b.pnl_pct - a.pnl_pct).slice(0, 3);
  const worstTrades = [...trades].sort((a, b) => a.pnl_pct - b.pnl_pct).slice(0, 3);

  // 몬테카를로 최적화 상태
  const [optimizedParams, setOptimizedParams] = useState<Record<string, unknown> | null>(null);
  const [optStatus, setOptStatus] = useState<'idle' | 'loading' | 'running' | 'error'>('idle');
  const [optMessage, setOptMessage] = useState('');

  useEffect(() => {
    saveBacktestQuery(draft);
  }, [draft]);

  useEffect(() => {
    fetch('/api/optimized-params')
      .then((r) => r.json())
      .then((d) => { if (d?.status === 'ok') setOptimizedParams(d); })
      .catch(() => {});
  }, []);

  function patchDraft<K extends keyof BacktestQuery>(key: K, value: BacktestQuery[K]) {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  function handleRun() {
    run(draft);
  }

  function handleReset() {
    const resetQuery = defaultBacktestQuery(draft.market_scope);
    setDraft(resetQuery);
    run(resetQuery);
  }

  async function handleRunOptimization() {
    setOptStatus('loading');
    setOptMessage('');
    try {
      const r = await fetch('/api/run-optimization', { method: 'POST' });
      const d = await r.json();
      if (d?.status === 'started') {
        setOptStatus('running');
        setOptMessage('백그라운드에서 실행 중입니다. 완료까지 수 분~수십 분 소요됩니다.');
      } else if (d?.status === 'already_running') {
        setOptStatus('running');
        setOptMessage('이미 실행 중입니다.');
      } else {
        setOptStatus('error');
        setOptMessage(d?.error || '알 수 없는 오류');
      }
    } catch {
      setOptStatus('error');
      setOptMessage('서버 연결 실패');
    }
  }

  async function handleRefreshOptParams() {
    setOptStatus('loading');
    try {
      const r = await fetch('/api/optimized-params');
      const d = await r.json();
      if (d?.status === 'ok') {
        setOptimizedParams(d);
        setOptStatus('idle');
        setOptMessage('');
      } else {
        setOptimizedParams(null);
        setOptStatus('idle');
        setOptMessage('최적화 결과가 없습니다.');
      }
    } catch {
      setOptStatus('error');
      setOptMessage('조회 실패');
    }
  }

  return (
    <div className="app-shell">
      <div className="page-frame" style={{ display: 'grid', gap: 20 }}>
        <div className="hero-banner">
          <div className="hero-grid">
            <div>
              <div className="hero-eyebrow">Strategy Lab</div>
              <div className="hero-title">백테스트 실험실</div>
              <div className="hero-subtitle">
                시장, 기간, 포지션 수를 빠르게 바꾸고, RSI·거래량·손절·익절 같은 전략 파라미터까지 함께 조절해 결과를 바로 비교합니다.
              </div>
              <div className="hero-chip-row">
                <button className="ghost-button" style={{ background: 'rgba(255,255,255,.1)', color: '#fffaf2', borderColor: 'rgba(255,255,255,.18)' }} onClick={onBack}>
                  메인 대시보드로
                </button>
                <span className="hero-chip">종목 유니버스: {draft.market_scope === 'kospi' ? 'KOSPI100' : 'S&P100'}</span>
                <span className="hero-chip">기준 통화: {marketPreset.currency}</span>
                <span className="hero-chip">기술 규칙 + 손절/익절</span>
              </div>
            </div>
            <div className="hero-sidecard">
              <div className="hero-sidecard-label">현재 설정</div>
              <div className="hero-sidecard-value">{buildPresetLabel(draft.lookback_days)} · {draft.market_scope === 'kospi' ? 'KOSPI100' : 'S&P100'}</div>
              <div className="hero-sidecard-copy">
                초기자금 {formatMoney(draft.initial_cash, marketPreset.currency)} · 최대 {draft.max_positions}종목 · 손절 {draft.stop_loss_pct ?? '없음'}% · 익절 {draft.take_profit_pct ?? '없음'}%
              </div>
            </div>
          </div>
        </div>

        <div className="page-section" style={{ display: 'grid', gap: 18 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
            <div>
              <div style={{ fontSize: 12, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: '0.12em' }}>Scenario Builder</div>
              <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--text-1)', marginTop: 6 }}>백테스트 설정</div>
              <div style={{ fontSize: 13, color: 'var(--text-4)', marginTop: 8 }}>기본 범위와 고급 전략 조건을 함께 조절한 뒤 실행합니다.</div>
            </div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <button className="ghost-button" onClick={handleReset}>기본값 복원</button>
              <button className="ghost-button" style={{ background: 'var(--accent)', color: '#fffaf2', borderColor: 'var(--accent)' }} onClick={handleRun}>
                백테스트 실행
              </button>
            </div>
          </div>

          <div style={{ display: 'grid', gap: 14 }}>
            <div>
              <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)', marginBottom: 8 }}>시장 범위</div>
              <div className="backtest-pill-row">
                {[
                  { value: 'kospi', label: 'KOSPI100' },
                  { value: 'nasdaq', label: 'S&P100' },
                ].map((option) => (
                  <button
                    key={option.value}
                    className={`backtest-pill ${draft.market_scope === option.value ? 'active' : ''}`}
                    onClick={() => {
                      const nextMarket = option.value as BacktestQuery['market_scope'];
                      setDraft((prev) => ({ ...defaultBacktestQuery(nextMarket), lookback_days: prev.lookback_days }));
                    }}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)', marginBottom: 8 }}>테스트 기간</div>
              <div className="backtest-pill-row">
                {[365, 730, 1095].map((days) => (
                  <button
                    key={days}
                    className={`backtest-pill ${draft.lookback_days === days ? 'active' : ''}`}
                    onClick={() => patchDraft('lookback_days', days)}
                  >
                    {buildPresetLabel(days)}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="backtest-grid">
            <CurrencyField label={marketPreset.label} value={draft.initial_cash} suffix={marketPreset.suffix} min={marketPreset.min} onChange={(value) => {
              if (value === null) return;
              patchDraft('initial_cash', value);
            }} />
            <NumericField label="최대 보유 종목 수" value={draft.max_positions} suffix="종목" min={1} onChange={(value) => {
              if (value === null) return;
              patchDraft('max_positions', value);
            }} />
            <NumericField label="최대 보유 일수" value={draft.max_holding_days} suffix="일" min={5} onChange={(value) => {
              if (value === null) return;
              patchDraft('max_holding_days', value);
            }} />
          </div>
        </div>

        <div className="page-section" style={{ display: 'grid', gap: 18 }}>
          <div>
            <div style={{ fontSize: 12, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: '0.12em' }}>Advanced Rules</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--text-1)', marginTop: 6 }}>고급 전략 파라미터</div>
            <div style={{ fontSize: 13, color: 'var(--text-4)', marginTop: 8 }}>RSI 진입 범위, 거래량 기준, 손절·익절 값을 바꿔 전략 민감도를 조절합니다.</div>
          </div>
          <div className="backtest-grid">
            <NumericField label="RSI 최소값" value={draft.rsi_min} min={10} onChange={(value) => {
              if (value === null) return;
              patchDraft('rsi_min', value);
            }} />
            <NumericField label="RSI 최대값" value={draft.rsi_max} min={10} onChange={(value) => {
              if (value === null) return;
              patchDraft('rsi_max', value);
            }} />
            <NumericField label="최소 거래량 배수" value={draft.volume_ratio_min} min={0.5} step={0.1} onChange={(value) => {
              if (value === null) return;
              patchDraft('volume_ratio_min', value);
            }} />
            <NumericField label="손절 기준" value={draft.stop_loss_pct} suffix="%" min={1} step={0.5} onChange={(value) => patchDraft('stop_loss_pct', value)} />
            <NumericField label="익절 기준" value={draft.take_profit_pct} suffix="%" min={1} step={0.5} onChange={(value) => patchDraft('take_profit_pct', value)} />
          </div>
        </div>

        {status === 'loading' && (
          <div className="page-section" style={{ display: 'grid', gap: 10 }}>
            {[88, 74, 81, 62].map((w, i) => (
              <div key={i} className="shimmer-line" style={{ height: 16, borderRadius: 999, background: 'var(--surface-alt)', width: `${w}%` }} />
            ))}
          </div>
        )}

        {status === 'error' && (
          <div className="page-section" style={{ textAlign: 'center', padding: '48px 24px' }}>
            <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--down)' }}>백테스트를 실행할 수 없습니다</div>
            <div style={{ fontSize: 13, color: 'var(--text-4)', marginTop: 8 }}>{data.error || '서버 응답을 확인해 주세요.'}</div>
          </div>
        )}

        {status === 'ok' && (
          <>
            <div className="page-section" style={{ padding: 0, overflow: 'hidden' }}>
              <div style={{ padding: 24, background: 'linear-gradient(135deg, rgba(20,51,78,0.98) 0%, rgba(15,76,92,0.96) 100%)', color: '#fffaf2' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                  <div>
                    <div style={{ fontSize: 12, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'rgba(255,250,242,.64)' }}>Backtest Result</div>
                    <div style={{ fontSize: 30, fontWeight: 800, marginTop: 8 }}>실행 결과</div>
                    <div style={{ fontSize: 15, color: 'rgba(255,250,242,.82)', marginTop: 10, lineHeight: 1.7, maxWidth: 760 }}>
                      {data.universe || (draft.market_scope === 'kospi' ? 'KOSPI100' : 'S&P100')} · {equity[0]?.date || '—'} ~ {equity[equity.length - 1]?.date || '—'} · 생성 시각 {data.generated_at || '없음'}
                    </div>
                    <CountByMarket data={data} />
                  </div>
                  <div style={{ minWidth: 240, padding: 18, borderRadius: 20, background: 'rgba(255,255,255,.08)', border: '1px solid rgba(255,255,255,.14)' }}>
                    <div style={{ fontSize: 11, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'rgba(255,250,242,.58)' }}>Applied Rules</div>
                    <div style={{ marginTop: 10, fontSize: 13, lineHeight: 1.7, color: 'rgba(255,250,242,.82)' }}>
                      RSI {data.config?.rsi_min}~{data.config?.rsi_max} · 거래량 {data.config?.volume_ratio_min}배 이상
                      <br />
                      손절 {data.config?.stop_loss_pct ?? '없음'}% · 익절 {data.config?.take_profit_pct ?? '없음'}%
                    </div>
                  </div>
                </div>
              </div>
              <div style={{ padding: 18, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, background: 'rgba(255,253,248,0.78)' }}>
                <MetricCard title="최종 자산" value={formatMoney(metrics?.final_equity, baseCurrency)} detail={`초기자금 ${formatMoney(data.config?.initial_cash, baseCurrency)}`} tone="up" />
                <MetricCard title="총수익률" value={formatPct(metrics?.total_return_pct)} detail={`CAGR ${formatPct(metrics?.cagr_pct)}`} tone={(metrics?.total_return_pct || 0) >= 0 ? 'up' : 'down'} />
                <MetricCard title="최대 낙폭" value={formatPct(metrics?.max_drawdown_pct)} detail="낙폭이 작을수록 방어력이 높습니다." tone="down" />
                <MetricCard title="거래 수 / 승률" value={`${metrics?.trade_count ?? 0}건`} detail={`승률 ${formatPct(metrics?.win_rate_pct)}`} />
              </div>
            </div>

            <div className="backtest-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
              <div className="page-section">
                <div style={{ fontSize: 12, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: '0.12em' }}>Setup</div>
                <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-1)', marginTop: 6 }}>적용 설정 요약</div>
                <div style={{ display: 'grid', gap: 10, marginTop: 14, fontSize: 13, color: 'var(--text-3)' }}>
                  <div>시장: {(data.config?.markets || []).join(' + ') || data.universe || '—'}</div>
                  <div>룩백: {data.config?.lookback_days || 0}일</div>
                  <div>최대 포지션: {data.config?.max_positions || 0}종목</div>
                  <div>최대 보유기간: {data.config?.max_holding_days || 0}일</div>
                </div>
              </div>
              <div className="page-section">
                <div style={{ fontSize: 12, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: '0.12em' }}>Filters</div>
                <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-1)', marginTop: 6 }}>진입 조건</div>
                <div style={{ display: 'grid', gap: 10, marginTop: 14, fontSize: 13, color: 'var(--text-3)' }}>
                  <div>RSI: {data.config?.rsi_min} ~ {data.config?.rsi_max}</div>
                  <div>거래량: {data.config?.volume_ratio_min}배 이상</div>
                  <div>추세: 종가 &gt; 20일선 &gt; 60일선</div>
                  <div>모멘텀: MACD 히스토그램 양수</div>
                </div>
              </div>
              <div className="page-section">
                <div style={{ fontSize: 12, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: '0.12em' }}>Exits</div>
                <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-1)', marginTop: 6 }}>청산 조건</div>
                <div style={{ display: 'grid', gap: 10, marginTop: 14, fontSize: 13, color: 'var(--text-3)' }}>
                  <div>손절: {data.config?.stop_loss_pct ?? '사용 안 함'}%</div>
                  <div>익절: {data.config?.take_profit_pct ?? '사용 안 함'}%</div>
                  <div>추세 이탈: 20일선 하회</div>
                  <div>기본 종료: MACD 약세 / RSI 과열 / 보유기간 만료</div>
                </div>
              </div>
            </div>

            <Sparkline data={data} currency={baseCurrency} />

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
              <TradeBlock title="상위 수익 거래" trades={bestTrades} tone="up" currency={baseCurrency} />
              <TradeBlock title="손실이 컸던 거래" trades={worstTrades} tone="down" currency={baseCurrency} />
            </div>
          </>
        )}

        {/* 몬테카를로 파라미터 최적화 */}
        <div className="page-section" style={{ display: 'grid', gap: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
            <div>
              <div style={{ fontSize: 12, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: '0.12em' }}>Monte Carlo</div>
              <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--text-1)', marginTop: 6 }}>파라미터 최적화</div>
              <div style={{ fontSize: 13, color: 'var(--text-4)', marginTop: 8 }}>
                몬테카를로 시뮬레이션으로 손절/익절/보유기간 최적값을 탐색합니다. 결과를 모의투자에 적용해 전략을 개선하세요.
              </div>
            </div>
            <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
              <button
                onClick={handleRefreshOptParams}
                disabled={optStatus === 'loading'}
                style={{ padding: '6px 12px', borderRadius: 8, fontSize: 12, background: 'var(--bg-2)', color: 'var(--text-2)', border: '1px solid var(--border)', cursor: optStatus === 'loading' ? 'not-allowed' : 'pointer' }}
              >
                새로고침
              </button>
              <button
                onClick={handleRunOptimization}
                disabled={optStatus === 'loading' || optStatus === 'running'}
                style={{ padding: '6px 14px', borderRadius: 8, fontSize: 12, background: optStatus === 'running' ? 'var(--bg-2)' : 'var(--up)', color: optStatus === 'running' ? 'var(--text-3)' : '#fff', border: 'none', cursor: (optStatus === 'loading' || optStatus === 'running') ? 'not-allowed' : 'pointer', fontWeight: 700 }}
              >
                {optStatus === 'loading' ? '요청 중...' : optStatus === 'running' ? '실행 중...' : '최적화 실행'}
              </button>
            </div>
          </div>

          {optMessage && (
            <div style={{ fontSize: 12, color: optStatus === 'error' ? 'var(--down)' : 'var(--text-3)', background: 'var(--bg-soft)', padding: '8px 12px', borderRadius: 8, border: '1px solid var(--border)' }}>
              {optMessage}
            </div>
          )}

          {optimizedParams ? (
            <div style={{ display: 'grid', gap: 10 }}>
              <div style={{ fontSize: 12, color: 'var(--text-4)' }}>
                최적화 일시: {optimizedParams.optimized_at ? new Date(optimizedParams.optimized_at as string).toLocaleString('ko-KR') : '—'}
                {' · '}방법: {String(optimizedParams.method ?? '—')}
                {' · '}시뮬레이션: {String(optimizedParams.n_simulations ?? '—')}회
              </div>
              {(optimizedParams.global_params as Record<string, unknown>) && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 8 }}>
                  {Object.entries(optimizedParams.global_params as Record<string, unknown>).map(([key, val]) => (
                    <div key={key} style={{ padding: '10px 12px', background: 'var(--bg-soft)', borderRadius: 10, border: '1px solid var(--border)' }}>
                      <div style={{ fontSize: 11, color: 'var(--text-4)', marginBottom: 4 }}>{key}</div>
                      <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-1)' }}>{val === null ? '—' : String(val)}</div>
                    </div>
                  ))}
                </div>
              )}
              {(optimizedParams.per_symbol as Record<string, unknown>) && Object.keys(optimizedParams.per_symbol as Record<string, unknown>).length > 0 && (
                <div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-2)', marginBottom: 8 }}>종목별 최적 파라미터</div>
                  <div style={{ display: 'grid', gap: 6 }}>
                    {Object.entries(optimizedParams.per_symbol as Record<string, Record<string, unknown>>)
                      .filter(([, sym]) => sym.is_reliable)
                      .map(([code, sym]) => (
                        <div key={code} style={{ display: 'grid', gridTemplateColumns: '80px 1fr', gap: 8, alignItems: 'center', padding: '8px 12px', background: 'var(--bg-soft)', borderRadius: 8, border: '1px solid var(--border)' }}>
                          <div style={{ fontWeight: 700, fontSize: 13, color: 'var(--text-1)' }}>{code}</div>
                          <div style={{ fontSize: 12, color: 'var(--text-3)', display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                            {(['stop_loss_pct', 'take_profit_pct', 'max_holding_days', 'rsi_min', 'rsi_max'] as const).map((k) =>
                              sym[k] !== undefined && sym[k] !== null
                                ? <span key={k}><span style={{ color: 'var(--text-4)' }}>{k.replace(/_pct$/, '(%)')}: </span>{String(sym[k])}</span>
                                : null
                            )}
                            <span style={{ color: 'var(--text-4)', fontSize: 11 }}>샤프={typeof sym.sharpe_ratio === 'number' ? sym.sharpe_ratio.toFixed(2) : '—'}</span>
                          </div>
                        </div>
                      ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div style={{ fontSize: 13, color: 'var(--text-4)' }}>
              최적화 결과가 없습니다. "최적화 실행" 버튼을 눌러 시작하거나, 스케줄러가 매주 일요일 02:00 KST에 자동으로 실행합니다.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
