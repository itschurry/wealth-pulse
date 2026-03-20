"""Shared technical snapshot helpers for KIS-backed equities."""
from __future__ import annotations

import datetime
import time
from typing import Any

from broker.kis_client import KISAPIError, KISClient, KISConfigError
from market_utils import lookup_company_listing, resolve_quote_market

_KST = datetime.timezone(datetime.timedelta(hours=9))
_TECHNICAL_CACHE_TTL = 900
_technical_cache: dict[str, dict[str, Any]] = {}
_kis_client: KISClient | None = None
_kis_client_disabled = False


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    multiplier = 2 / (period + 1)
    ema_values = [values[0]]
    for value in values[1:]:
        ema_values.append((value - ema_values[-1]) * multiplier + ema_values[-1])
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

    closes = [float(item["close"]) for item in normalized_rows if item.get("close") is not None]
    volumes = [float(item["volume"]) for item in normalized_rows if item.get("volume") is not None]
    if len(closes) < 35:
        return None

    current_price = closes[-1]
    prev_close = closes[-2] if len(closes) >= 2 else closes[-1]
    change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close else None
    sma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
    sma60 = sum(closes[-60:]) / 60 if len(closes) >= 60 else None
    volume = volumes[-1] if volumes else None
    volume_avg20 = (sum(volumes[-20:]) / 20) if len(volumes) >= 20 else None
    volume_ratio = (volume / volume_avg20) if volume and volume_avg20 else None

    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_series = [fast - slow for fast, slow in zip(ema12[-len(ema26):], ema26)]
    signal_series = _ema(macd_series, 9)
    macd = macd_series[-1] if macd_series else None
    macd_signal = signal_series[-1] if signal_series else None
    macd_hist = (macd - macd_signal) if macd is not None and macd_signal is not None else None
    rsi14 = _rsi(closes, 14)
    atr14 = _atr(normalized_rows, 14)
    atr14_pct = ((atr14 / current_price) * 100) if atr14 not in (None, 0) and current_price else None

    breakout_20d_high = None
    breakout_20d = None
    if len(normalized_rows) >= 21:
        prior_highs = [float(item.get("high") or item.get("close")) for item in normalized_rows[-21:-1]]
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
        gate_reasons.extend([reason for reason in negatives if reason in {"추세 역배열", "MACD 모멘텀이 약세", "RSI 과열 구간", "이벤트 리스크와 변동성 확대가 겹침"}][:2])
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
    global _kis_client, _kis_client_disabled
    if _kis_client_disabled:
        return None
    if _kis_client is not None:
        return _kis_client
    if not KISClient.is_configured():
        _kis_client_disabled = True
        return None
    try:
        _kis_client = KISClient.from_env(timeout=timeout)
        return _kis_client
    except (KISConfigError, KISAPIError):
        _kis_client_disabled = True
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
    listing = lookup_company_listing(code=normalized_code, name=normalized_code, scope="core")
    resolved_code = str((listing or {}).get("code") or normalized_code).strip().upper()
    resolved_market = str((listing or {}).get("market") or market or "").strip()
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
        return None

    history_market = resolved_market.strip().upper()
    if history_market not in {"KOSPI", "NASDAQ", "NYSE", "AMEX"}:
        history_market = normalized_market

    end_date = datetime.datetime.now(_KST).strftime("%Y%m%d")
    start_date = (datetime.datetime.now(_KST) - datetime.timedelta(days=_lookback_days(range_))).strftime("%Y%m%d")
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
                except Exception:
                    rows = []
                    continue
                if rows:
                    break
    except Exception:
        rows = []

    snapshot = compute_technical_snapshot_from_history(rows)
    if snapshot:
        _technical_cache[cache_key] = {"ts": now, "data": snapshot}
    return snapshot
