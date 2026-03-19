import { useState } from 'react';
import { DEFAULT_BACKTEST_QUERY, useBacktest } from '../hooks/useBacktest';
import type { BacktestData, BacktestQuery, BacktestTrade } from '../types';

function formatMoney(value?: number | null) {
  if (value === undefined || value === null) return '—';
  return new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 0 }).format(value) + '원';
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

function Sparkline({ data }: { data: BacktestData }) {
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
          <span>{formatMoney(min)} ~ {formatMoney(max)}</span>
          <span>{data.equity_curve?.[data.equity_curve.length - 1]?.date || '종료일 없음'}</span>
        </div>
      </div>
    </div>
  );
}

function TradeBlock({ title, trades, tone }: { title: string; trades: BacktestTrade[]; tone: 'up' | 'down' }) {
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
              <span>진입 {formatMoney(trade.entry_price)}</span>
              <span>청산 {formatMoney(trade.exit_price)}</span>
              <span>{trade.holding_days}일 보유</span>
              <span>손익 {formatMoney(trade.pnl)}</span>
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
  return (
    <label style={{ display: 'grid', gap: 8 }}>
      <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)' }}>{label}</span>
      <div className="backtest-input-wrap">
        <input
          className="backtest-input"
          type="number"
          value={value ?? ''}
          min={min}
          step={step}
          onChange={(event) => {
            const raw = event.target.value.trim();
            onChange(raw ? Number(raw) : null);
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

export function BacktestPage({ onBack }: { onBack: () => void }) {
  const { data, status, run } = useBacktest();
  const [draft, setDraft] = useState<BacktestQuery>(DEFAULT_BACKTEST_QUERY);
  const metrics = data.metrics;
  const equity = data.equity_curve || [];
  const trades = data.trades || [];
  const bestTrades = [...trades].sort((a, b) => b.pnl_pct - a.pnl_pct).slice(0, 3);
  const worstTrades = [...trades].sort((a, b) => a.pnl_pct - b.pnl_pct).slice(0, 3);

  function patchDraft<K extends keyof BacktestQuery>(key: K, value: BacktestQuery[K]) {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  function handleRun() {
    run(draft);
  }

  function handleReset() {
    setDraft(DEFAULT_BACKTEST_QUERY);
    run(DEFAULT_BACKTEST_QUERY);
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
                <span className="hero-chip">기본 우주: KOSPI50 + S&amp;P50</span>
                <span className="hero-chip">환산 기준: KRW</span>
                <span className="hero-chip">기술 규칙 + 손절/익절</span>
              </div>
            </div>
            <div className="hero-sidecard">
              <div className="hero-sidecard-label">현재 설정</div>
              <div className="hero-sidecard-value">{buildPresetLabel(draft.lookback_days)} · {draft.market_scope === 'all' ? '양시장' : draft.market_scope === 'kospi' ? 'KOSPI50' : 'S&P50'}</div>
              <div className="hero-sidecard-copy">
                초기자금 {formatMoney(draft.initial_cash)} · 최대 {draft.max_positions}종목 · 손절 {draft.stop_loss_pct ?? '없음'}% · 익절 {draft.take_profit_pct ?? '없음'}%
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
                  { value: 'all', label: 'KOSPI50 + S&P50' },
                  { value: 'kospi', label: 'KOSPI50' },
                  { value: 'nasdaq', label: 'S&P50' },
                ].map((option) => (
                  <button
                    key={option.value}
                    className={`backtest-pill ${draft.market_scope === option.value ? 'active' : ''}`}
                    onClick={() => patchDraft('market_scope', option.value as BacktestQuery['market_scope'])}
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
            <NumericField label="초기 자금" value={draft.initial_cash} suffix="원" min={1000000} step={1000000} onChange={(value) => patchDraft('initial_cash', value ?? DEFAULT_BACKTEST_QUERY.initial_cash)} />
            <NumericField label="최대 보유 종목 수" value={draft.max_positions} suffix="종목" min={1} onChange={(value) => patchDraft('max_positions', value ?? DEFAULT_BACKTEST_QUERY.max_positions)} />
            <NumericField label="최대 보유 일수" value={draft.max_holding_days} suffix="일" min={5} onChange={(value) => patchDraft('max_holding_days', value ?? DEFAULT_BACKTEST_QUERY.max_holding_days)} />
          </div>
        </div>

        <div className="page-section" style={{ display: 'grid', gap: 18 }}>
          <div>
            <div style={{ fontSize: 12, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: '0.12em' }}>Advanced Rules</div>
            <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--text-1)', marginTop: 6 }}>고급 전략 파라미터</div>
            <div style={{ fontSize: 13, color: 'var(--text-4)', marginTop: 8 }}>RSI 진입 범위, 거래량 기준, 손절·익절 값을 바꿔 전략 민감도를 조절합니다.</div>
          </div>
          <div className="backtest-grid">
            <NumericField label="RSI 최소값" value={draft.rsi_min} min={10} onChange={(value) => patchDraft('rsi_min', value ?? DEFAULT_BACKTEST_QUERY.rsi_min)} />
            <NumericField label="RSI 최대값" value={draft.rsi_max} min={10} onChange={(value) => patchDraft('rsi_max', value ?? DEFAULT_BACKTEST_QUERY.rsi_max)} />
            <NumericField label="최소 거래량 배수" value={draft.volume_ratio_min} min={0.5} step={0.1} onChange={(value) => patchDraft('volume_ratio_min', value ?? DEFAULT_BACKTEST_QUERY.volume_ratio_min)} />
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
                      {data.universe || 'KOSPI50 + S&P50'} · {equity[0]?.date || '—'} ~ {equity[equity.length - 1]?.date || '—'} · 생성 시각 {data.generated_at || '없음'}
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
                <MetricCard title="최종 자산" value={formatMoney(metrics?.final_equity)} detail={`초기자금 ${formatMoney(data.config?.initial_cash)}`} tone="up" />
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

            <Sparkline data={data} />

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
              <TradeBlock title="상위 수익 거래" trades={bestTrades} tone="up" />
              <TradeBlock title="손실이 컸던 거래" trades={worstTrades} tone="down" />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
