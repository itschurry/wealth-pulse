"""Shared technical snapshot helpers for KIS-backed equities."""
from __future__ import annotations

import datetime
import logging
import time
from typing import Any

from broker.kis_client import KISAPIError, KISClient, KISConfigError
from market_utils import lookup_company_listing, resolve_quote_market

logger = logging.getLogger(__name__)

_KST = datetime.timezone(datetime.timedelta(hours=9))
_TECHNICAL_CACHE_TTL = 900
_technical_cache: dict[str, dict[str, Any]] = {}
_kis_client: KISClient | None = None
_kis_client_disabled = False
_kis_client_retry_after: float = 0.0
_KIS_CLIENT_RETRY_INTERVAL = 60.0


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    multiplier = 2 / (period + 1)
    ema_values = [values[0]]
    for value in values[1:]:
        ema_values.append(
            (value - ema_values[-1]) * multiplier + ema_values[-1])
    return ema_values


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for prev, current in zip(values[:-1], values[1:]):
        delta = current - prev
        gains.append(max(delta, 0.0))
        losses.append(abs(min(delta, 0.0)))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for idx in range(period, len(gains)):
        avg_gain = ((avg_gain * (period - 1)) + gains[idx]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[idx]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _atr(rows: list[dict[str, Any]], period: int = 14) -> float | None:
    if len(rows) <= period:
        return None
    true_ranges: list[float] = []
    previous_close: float | None = None
    for row in rows:
        close = row.get("close")
        high = row.get("high", close)
        low = row.get("low", close)
        if close is None or high is None or low is None:
            continue
        if previous_close is None:
            tr = float(high) - float(low)
        else:
            tr = max(
                float(high) - float(low),
                abs(float(high) - float(previous_close)),
                abs(float(low) - float(previous_close)),
            )
        true_ranges.append(max(tr, 0.0))
        previous_close = float(close)
    if len(true_ranges) < period:
        return None

    atr_value = sum(true_ranges[:period]) / period
    for idx in range(period, len(true_ranges)):
        atr_value = ((atr_value * (period - 1)) + true_ranges[idx]) / period
    return atr_value


def _adx(rows: list[dict[str, Any]], period: int = 14) -> float | None:
    """ADX (Average Directional Index) 계산 - 추세 강도"""
    if len(rows) <= period:
        return None

    plus_dm = []
    minus_dm = []
    true_ranges = []

    for i in range(1, len(rows)):
        high = float(rows[i].get("high") or rows[i].get("close"))
        low = float(rows[i].get("low") or rows[i].get("close"))
        prev_high = float(rows[i-1].get("high") or rows[i-1].get("close"))
        prev_low = float(rows[i-1].get("low") or rows[i-1].get("close"))
        close = float(rows[i].get("close"))
        prev_close = float(rows[i-1].get("close"))

        up_move = high - prev_high
        down_move = prev_low - low

        pdm = max(up_move, 0) if up_move > down_move else 0
        mdm = max(down_move, 0) if down_move > up_move else 0

        plus_dm.append(pdm)
        minus_dm.append(mdm)

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close),
        )
        true_ranges.append(max(tr, 0.0))

    if len(true_ranges) < period or len(plus_dm) < period:
        return None

    # 평활 이동분
    plus_di = sum(plus_dm[:period]) / period
    minus_di = sum(minus_dm[:period]) / period
    atr = sum(true_ranges[:period]) / period

    for idx in range(period, len(true_ranges)):
        plus_di = ((plus_di * (period - 1)) + plus_dm[idx]) / period
        minus_di = ((minus_di * (period - 1)) + minus_dm[idx]) / period
        atr = ((atr * (period - 1)) + true_ranges[idx]) / period

    # DX 계산
    di_sum = plus_di + minus_di
    if di_sum < 0.001:
        return 0.0
    dx = 100 * abs(plus_di - minus_di) / di_sum

    # ADX 계산 (첫 ADX는 DX의 기간 평균)
    dxs = [dx]
    plus_dis = [plus_di]
    minus_dis = [minus_di]
    atrs = [atr]

    for idx in range(period, len(true_ranges)):
        # 다음 DX 계산
        plus_di = ((plus_dis[-1] * (period - 1)) + plus_dm[idx]) / \
            period if idx < len(plus_dm) else plus_dis[-1]
        minus_di = ((minus_dis[-1] * (period - 1)) + minus_dm[idx]) / \
            period if idx < len(minus_dm) else minus_dis[-1]
        atr = ((atrs[-1] * (period - 1)) + true_ranges[idx]) / period

        di_sum = plus_di + minus_di
        if di_sum < 0.001:
            dx = 0.0
        else:
            dx = 100 * abs(plus_di - minus_di) / di_sum

        dxs.append(dx)
        plus_dis.append(plus_di)
        minus_dis.append(minus_di)
        atrs.append(atr)

    if len(dxs) < period:
        return 0.0

    adx_val = sum(dxs[:period]) / period
    for idx in range(period, len(dxs)):
        adx_val = ((adx_val * (period - 1)) + dxs[idx]) / period

    return max(0.0, min(100.0, adx_val))


def _bollinger_bands(closes: list[float], period: int = 20, std_dev: float = 2.0) -> tuple[float | None, float | None, float | None]:
    """Bollinger Bands 계산 - (upper, lower, %b)"""
    if len(closes) < period:
        return None, None, None

    recent = closes[-period:]
    sma = sum(recent) / period
    variance = sum((x - sma) ** 2 for x in recent) / period
    std = variance ** 0.5

    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)

    current = closes[-1]
    if upper == lower:
        bb_pct = 0.5
    else:
        bb_pct = (current - lower) / (upper - lower)
    bb_pct = max(0.0, min(1.0, bb_pct))

    return round(upper, 2), round(lower, 2), round(bb_pct, 2)


def _obv(rows: list[dict[str, Any]]) -> str:
    """OBV (On-Balance Volume) - 거래량 추세 ("up", "flat", "down")"""
    if len(rows) < 2:
        return "flat"

    obv_val = 0.0
    obv_values = []

    for row in rows:
        close = float(row.get("close", 0))
        prev_close = rows[rows.index(
            row) - 1].get("close") if rows.index(row) > 0 else close
        prev_close = float(prev_close) if prev_close else close
        volume = float(row.get("volume", 0))

        if close > prev_close:
            obv_val += volume
        elif close < prev_close:
            obv_val -= volume

        obv_values.append(obv_val)

    if len(obv_values) < 20:
        return "flat"

    obv_recent = obv_values[-1]
    obv_avg_20 = sum(obv_values[-20:]) / 20

    if obv_recent > obv_avg_20 * 1.05:
        return "up"
    elif obv_recent < obv_avg_20 * 0.95:
        return "down"
    else:
        return "flat"


def _mfi(rows: list[dict[str, Any]], period: int = 14) -> float | None:
    """MFI (Money Flow Index) 계산"""
    if len(rows) < period + 1:
        return None

    typical_prices = []
    money_flows = []

    for row in rows:
        high = float(row.get("high", row.get("close")))
        low = float(row.get("low", row.get("close")))
        close = float(row.get("close"))
        volume = float(row.get("volume", 0))

        tp = (high + low + close) / 3.0
        mf = tp * volume

        typical_prices.append(tp)
        money_flows.append(mf)

    positive_mf = 0.0
    negative_mf = 0.0

    for i in range(1, len(typical_prices)):
        if typical_prices[i] > typical_prices[i-1]:
            positive_mf += money_flows[i]
        elif typical_prices[i] < typical_prices[i-1]:
            negative_mf += money_flows[i]

    if negative_mf == 0:
        return 100.0

    mr = positive_mf / negative_mf
    mfi = 100 - (100 / (1 + mr))

    return max(0.0, min(100.0, mfi))


def _stochastic(rows: list[dict[str, Any]], period: int = 14, smooth_k: int = 3, smooth_d: int = 3) -> tuple[float | None, float | None]:
    """Stochastic Oscillator 계산 - (%K, %D)"""
    if len(rows) < period:
        return None, None

    lows = []
    highs = []
    closes = []

    for row in rows[-period:]:
        high = float(row.get("high", row.get("close")))
        low = float(row.get("low", row.get("close")))
        close = float(row.get("close"))

        highs.append(high)
        lows.append(low)
        closes.append(close)

    highest = max(highs)
    lowest = min(lows)

    if highest == lowest:
        k_pct = 50.0
    else:
        k_pct = 100.0 * (closes[-1] - lowest) / (highest - lowest)

    k_pct = max(0.0, min(100.0, k_pct))
    d_pct = k_pct  # 단순화: K를 그대로 사용 (smooth_k/smooth_d 평활화는 생략)

    return round(k_pct, 1), round(d_pct, 1)


def compute_technical_snapshot_from_history(history: list[dict[str, Any]]) -> dict[str, Any] | None:
    normalized_rows: list[dict[str, float | None]] = []
    for item in history:
        close = item.get("close")
        if close is None:
            continue
        close_f = float(close)
        high = item.get("high")
        low = item.get("low")
        volume = item.get("volume")
        normalized_rows.append(
            {
                "close": close_f,
                "high": float(high) if high is not None else close_f,
                "low": float(low) if low is not None else close_f,
                "volume": float(volume) if volume is not None else None,
            }
        )

    closes = [float(item["close"])
              for item in normalized_rows if item.get("close") is not None]
    volumes = [float(item["volume"])
               for item in normalized_rows if item.get("volume") is not None]
    if len(closes) < 35:
        return None

    current_price = closes[-1]
    prev_close = closes[-2] if len(closes) >= 2 else closes[-1]
    change_pct = ((current_price - prev_close) /
                  prev_close * 100) if prev_close else None
    sma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
    sma60 = sum(closes[-60:]) / 60 if len(closes) >= 60 else None
    volume = volumes[-1] if volumes else None
    volume_avg20 = (sum(volumes[-20:]) / 20) if len(volumes) >= 20 else None
    volume_ratio = (volume / volume_avg20) if volume and volume_avg20 else None

    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_series = [fast - slow for fast,
                   slow in zip(ema12[-len(ema26):], ema26)]
    signal_series = _ema(macd_series, 9)
    macd = macd_series[-1] if macd_series else None
    macd_signal = signal_series[-1] if signal_series else None
    macd_hist = (
        macd - macd_signal) if macd is not None and macd_signal is not None else None
    rsi14 = _rsi(closes, 14)
    atr14 = _atr(normalized_rows, 14)
    atr14_pct = ((atr14 / current_price) *
                 100) if atr14 not in (None, 0) and current_price else None

    # Phase 2: 새로운 지표 계산
    adx14 = _adx(normalized_rows, 14)
    bb_upper, bb_lower, bb_pct = _bollinger_bands(closes, 20, 2.0)
    obv_trend = _obv(normalized_rows)
    mfi14 = _mfi(normalized_rows, 14)
    stoch_k, stoch_d = _stochastic(normalized_rows, 14)

    breakout_20d_high = None
    breakout_20d = None
    if len(normalized_rows) >= 21:
        prior_highs = [float(item.get("high") or item.get("close"))
                       for item in normalized_rows[-21:-1]]
        if prior_highs:
            breakout_20d_high = max(prior_highs)
            breakout_20d = current_price > breakout_20d_high

    trend = "neutral"
    if sma20 is not None and sma60 is not None:
        if current_price > sma20 and sma20 > sma60:
            trend = "bullish"
        elif current_price < sma20 and sma20 < sma60:
            trend = "bearish"

    return {
        "current_price": round(current_price, 2),
        "change_pct": round(change_pct, 2) if change_pct is not None else None,
        "sma20": round(sma20, 2) if sma20 is not None else None,
        "sma60": round(sma60, 2) if sma60 is not None else None,
        "volume": int(volume) if volume is not None else None,
        "volume_avg20": int(volume_avg20) if volume_avg20 is not None else None,
        "volume_ratio": round(volume_ratio, 2) if volume_ratio is not None else None,
        "rsi14": round(rsi14, 1) if rsi14 is not None else None,
        "macd": round(macd, 3) if macd is not None else None,
        "macd_signal": round(macd_signal, 3) if macd_signal is not None else None,
        "macd_hist": round(macd_hist, 3) if macd_hist is not None else None,
        "atr14": round(atr14, 2) if atr14 is not None else None,
        "atr14_pct": round(atr14_pct, 2) if atr14_pct is not None else None,
        "breakout_20d": breakout_20d,
        "breakout_20d_high": round(breakout_20d_high, 2) if breakout_20d_high is not None else None,
        "trend": trend,
        # Phase 2: 새로운 지표
        "adx14": round(adx14, 1) if adx14 is not None else None,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "bb_pct": bb_pct,
        "obv_trend": obv_trend,
        "mfi14": round(mfi14, 1) if mfi14 is not None else None,
        "stoch_k": stoch_k,
        "stoch_d": stoch_d,
    }


def evaluate_technical_snapshot(
    snapshot: dict[str, Any] | None,
    *,
    horizon: str = "short_term",
    has_event_risk: bool = False,
) -> dict[str, Any]:
    if not snapshot:
        return {
            "setup_quality": "unknown",
            "technical_view": "기술 스냅샷이 없어 가격·추세·변동성 검증이 비어 있습니다.",
            "gate_status": "caution",
            "gate_reasons": ["기술지표 확인 전"],
            "positives": [],
            "negatives": [],
            "score_adjustment": -2.0,
            "alignment_adjustment": -8.0,
        }

    positives: list[str] = []
    negatives: list[str] = []
    score_adjustment = 0.0
    alignment_adjustment = 0.0

    trend = str(snapshot.get("trend") or "neutral")
    volume_ratio = snapshot.get("volume_ratio")
    rsi14 = snapshot.get("rsi14")
    macd = snapshot.get("macd")
    macd_signal = snapshot.get("macd_signal")
    macd_hist = snapshot.get("macd_hist")
    atr14_pct = snapshot.get("atr14_pct")
    breakout_20d = snapshot.get("breakout_20d")
    # Phase 3: 새 지표 변수
    adx14 = snapshot.get("adx14")
    bb_pct = snapshot.get("bb_pct")
    obv_trend = snapshot.get("obv_trend")
    mfi14 = snapshot.get("mfi14")
    stoch_k = snapshot.get("stoch_k")
    stoch_d = snapshot.get("stoch_d")

    if trend == "bullish":
        positives.append("20일선과 60일선 위의 정배열")
        score_adjustment += 2.0
        alignment_adjustment += 6.0
    elif trend == "bearish":
        negatives.append("추세 역배열")
        score_adjustment -= 3.0
        alignment_adjustment -= 10.0

    if breakout_20d:
        positives.append("최근 20일 고점 돌파")
        score_adjustment += 2.5
        alignment_adjustment += 7.0

    if volume_ratio is not None and volume_ratio >= 1.5:
        positives.append("거래량이 20일 평균을 상회")
        score_adjustment += 1.5
        alignment_adjustment += 4.0
    elif volume_ratio is not None and volume_ratio < 0.8:
        negatives.append("거래량 확산이 약함")
        score_adjustment -= 1.0
        alignment_adjustment -= 3.0

    if macd is not None and macd_signal is not None and macd_hist is not None:
        if macd_hist > 0 and macd > macd_signal:
            positives.append("MACD 모멘텀이 우상향")
            score_adjustment += 1.5
            alignment_adjustment += 4.0
        elif macd_hist < 0 and macd < macd_signal:
            negatives.append("MACD 모멘텀이 약세")
            score_adjustment -= 2.0
            alignment_adjustment -= 5.0

    if rsi14 is not None and rsi14 >= 74:
        negatives.append("RSI 과열 구간")
        score_adjustment -= 2.5
        alignment_adjustment -= 6.0
    elif rsi14 is not None and rsi14 <= 35:
        negatives.append("RSI가 낮아 추세 확인이 더 필요")
        score_adjustment -= 0.5
        alignment_adjustment -= 1.0

    if atr14_pct is not None and atr14_pct >= 5.5:
        negatives.append("ATR 기준 변동성 확대 구간")
        score_adjustment -= 2.0 if horizon == "short_term" else 1.0
        alignment_adjustment -= 5.0 if horizon == "short_term" else 2.0

    if has_event_risk and atr14_pct is not None and atr14_pct >= 4.5:
        negatives.append("이벤트 리스크와 변동성 확대가 겹침")
        score_adjustment -= 2.5
        alignment_adjustment -= 6.0

    # Phase 3: 새 지표 평가
    if adx14 is not None:
        if adx14 >= 25:
            positives.append("ADX가 강추세 신호")
            score_adjustment += 1.5
            alignment_adjustment += 4.0
        elif adx14 < 15:
            negatives.append("ADX가 낮아 횡보장 신호")
            score_adjustment -= 2.0
            alignment_adjustment -= 5.0

    if bb_pct is not None:
        if bb_pct < 0.2:
            positives.append("볼린저 밴드 하단 근처")
            score_adjustment += 1.5
            alignment_adjustment += 3.0
        elif bb_pct > 0.85:
            negatives.append("볼린저 밴드 상단 근처")
            score_adjustment -= 1.5
            alignment_adjustment -= 3.0

    if obv_trend == "up":
        positives.append("OBV가 상승 추세")
        score_adjustment += 1.0
        alignment_adjustment += 2.0
    elif obv_trend == "down":
        negatives.append("OBV가 하강 추세")
        score_adjustment -= 1.5
        alignment_adjustment -= 3.0

    if mfi14 is not None and mfi14 < 25:
        positives.append("MFI 과매도 구간")
        score_adjustment += 1.0
        alignment_adjustment += 2.0
    elif mfi14 is not None and mfi14 > 75:
        negatives.append("MFI 과매수 구간")
        score_adjustment -= 1.0
        alignment_adjustment -= 2.0

    if stoch_k is not None and stoch_d is not None:
        if stoch_k < 25 and stoch_d < 25:
            positives.append("Stochastic 과매도 구간")
            score_adjustment += 1.0
            alignment_adjustment += 2.0
        elif stoch_k > 80 and stoch_d > 80:
            negatives.append("Stochastic 과매수 구간")
            score_adjustment -= 1.0
            alignment_adjustment -= 2.0

    negative_count = len(negatives)
    positive_count = len(positives)
    if negative_count == 0 and positive_count >= 3:
        setup_quality = "high"
    elif negative_count >= 3 and positive_count == 0:
        setup_quality = "low"
    else:
        setup_quality = "mixed"

    gate_status = "passed"
    gate_reasons: list[str] = []
    if negative_count >= 3 and (trend == "bearish" or ((macd_hist or 0) < 0 and (rsi14 or 0) >= 70)):
        gate_status = "blocked"
        gate_reasons.extend([reason for reason in negatives if reason in {
                            "추세 역배열", "MACD 모멘텀이 약세", "RSI 과열 구간", "이벤트 리스크와 변동성 확대가 겹침"}][:2])
    elif negatives:
        gate_status = "caution"
        gate_reasons.extend(negatives[:2])

    if setup_quality == "high":
        technical_view = "정배열, 거래량 확산, 모멘텀이 겹쳐 단기 셋업 품질이 양호합니다."
    elif setup_quality == "low":
        technical_view = "추세·모멘텀·변동성 조합이 불리해 지금은 기대값이 낮습니다."
    else:
        technical_view = "기술 신호가 혼재해 돌파 지속성 또는 눌림 확인이 더 필요합니다."

    return {
        "setup_quality": setup_quality,
        "technical_view": technical_view,
        "gate_status": gate_status,
        "gate_reasons": gate_reasons[:2],
        "positives": positives[:3],
        "negatives": negatives[:3],
        "score_adjustment": score_adjustment,
        "alignment_adjustment": alignment_adjustment,
    }


def _normalize_quote_market(code: str, market: str) -> str:
    return resolve_quote_market(code=code, market=market, scope="core")


def _overseas_exchange_candidates(market: str) -> list[str]:
    normalized = (market or "").strip().upper()
    if normalized in {"NYSE", "AMEX", "NASDAQ"}:
        ordered = [normalized, "NASDAQ", "NYSE", "AMEX"]
    else:
        ordered = ["NASDAQ", "NYSE", "AMEX"]
    deduped: list[str] = []
    for item in ordered:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _lookback_days(range_: str) -> int:
    normalized = (range_ or "").strip().lower()
    if normalized == "1d":
        return 5
    if normalized == "5d":
        return 10
    if normalized == "1mo":
        return 45
    if normalized == "3mo":
        return 120
    if normalized == "1y":
        return 420
    return 180


def _get_kis_client(timeout: float = 8.0) -> KISClient | None:
    global _kis_client, _kis_client_disabled, _kis_client_retry_after
    if _kis_client_disabled:
        return None
    if _kis_client_retry_after and time.time() < _kis_client_retry_after:
        return None
    if _kis_client is not None:
        return _kis_client
    if not KISClient.is_configured():
        _kis_client_disabled = True
        logger.warning("KIS 클라이언트 설정 없음 — 지표 조회 비활성화")
        return None
    try:
        _kis_client = KISClient.from_env(timeout=timeout)
        _kis_client_retry_after = 0.0
        return _kis_client
    except KISConfigError as exc:
        _kis_client_disabled = True
        logger.warning("KIS 설정 오류로 지표 조회 비활성화: %s", exc)
        return None
    except KISAPIError as exc:
        _kis_client = None
        _kis_client_retry_after = time.time() + _KIS_CLIENT_RETRY_INTERVAL
        logger.warning("KIS 클라이언트 초기화 실패 (%s초 후 재시도): %s",
                       _KIS_CLIENT_RETRY_INTERVAL, exc)
        return None


def fetch_technical_snapshot(
    code: str,
    market: str,
    *,
    range_: str = "6mo",
    interval: str = "1d",
    timeout: float = 8.0,
) -> dict[str, Any] | None:
    normalized_code = str(code or "").split(".")[0].strip().upper()
    listing = lookup_company_listing(
        code=normalized_code, name=normalized_code, scope="core")
    resolved_code = str((listing or {}).get(
        "code") or normalized_code).strip().upper()
    resolved_market = str((listing or {}).get(
        "market") or market or "").strip()
    normalized_market = _normalize_quote_market(resolved_code, resolved_market)
    if normalized_market not in {"KOSPI", "NASDAQ"} or interval != "1d":
        return None

    cache_key = f"{resolved_market}:{resolved_code}:{range_}:{interval}"
    now = time.time()
    cached = _technical_cache.get(cache_key)
    if cached and now - float(cached.get("ts") or 0.0) < _TECHNICAL_CACHE_TTL:
        return cached.get("data")

    client = _get_kis_client(timeout=timeout)
    if client is None:
        logger.debug("KIS 클라이언트 없음 — %s (%s) 지표 조회 불가",
                     resolved_code, normalized_market)
        return None

    history_market = resolved_market.strip().upper()
    if history_market not in {"KOSPI", "NASDAQ", "NYSE", "AMEX"}:
        history_market = normalized_market

    end_date = datetime.datetime.now(_KST).strftime("%Y%m%d")
    start_date = (datetime.datetime.now(
        _KST) - datetime.timedelta(days=_lookback_days(range_))).strftime("%Y%m%d")
    rows: list[dict[str, Any]] = []

    try:
        if history_market == "KOSPI":
            rows = client.get_domestic_daily_history(
                resolved_code,
                start_date=start_date,
                end_date=end_date,
            )
        else:
            for exchange in _overseas_exchange_candidates(history_market):
                try:
                    rows = client.get_overseas_daily_history(
                        resolved_code,
                        exchange=exchange,
                        start_date=start_date,
                        end_date=end_date,
                    )
                except Exception as exc:
                    logger.debug("KIS 해외 히스토리 조회 실패 %s/%s: %s",
                                 resolved_code, exchange, exc)
                    rows = []
                    continue
                if rows:
                    break
    except Exception as exc:
        logger.warning("KIS 히스토리 조회 실패 %s (%s): %s",
                       resolved_code, history_market, exc)
        rows = []

    snapshot = compute_technical_snapshot_from_history(rows)
    if not snapshot:
        logger.debug(
            "지표 계산 불가 %s (%s): 데이터 %d건 (최소 35건 필요)",
            resolved_code, history_market, len(rows),
        )
    elif snapshot:
        _technical_cache[cache_key] = {"ts": now, "data": snapshot}
    return snapshot
