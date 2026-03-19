"""뉴스 기반 오늘의 추천 및 관심종목 액션 계산."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from zoneinfo import ZoneInfo

from collectors.models import DailyData, NewsArticle
from config.company_catalog import CompanyCatalogEntry, get_company_catalog

_KST = ZoneInfo("Asia/Seoul")

_POSITIVE_KEYWORDS = (
    "상승", "강세", "확대", "수혜", "개선", "성장", "급등", "돌파", "신제품",
    "실적 개선", "상향", "기대", "주목", "계약", "수주", "출시", "진출",
)
_NEGATIVE_KEYWORDS = (
    "하락", "약세", "불확실", "우려", "악화", "급락", "리스크", "경고", "압박",
    "둔화", "매파", "전쟁", "충돌", "지연", "축소", "실적 부진",
)
_THEME_BOOSTS = {
    "방산": ("전쟁", "국방", "무기", "방산"),
    "에너지": ("유가", "원유", "에너지"),
    "항공": ("여행", "노선", "관광"),
    "반도체": ("반도체", "hbm", "ai", "칩", "엔비디아"),
    "가전": ("가전", "냉장고", "가정용 ai", "비스포크"),
}


def _normalize(value: str) -> str:
    return value.lower().strip()


def _article_text(article: NewsArticle) -> str:
    return " ".join([article.title, article.summary, article.body]).lower()


def _score_keywords(text: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for keyword in keywords if keyword.lower() in text)


def _market_adjustment(data: DailyData, sector: str) -> float:
    adjustment = 0.0
    context = data.market_context
    market = data.market

    if context and context.dollar_signal == "강세" and sector in {"반도체", "자동차", "자동차부품"}:
        adjustment -= 2.0
    if context and context.risk_level == "높음":
        adjustment -= 3.0
    elif context and context.risk_level == "중간":
        adjustment -= 1.0

    if market.kospi_change_pct is not None:
        adjustment += max(min(market.kospi_change_pct, 2.0), -2.0)
    if market.nasdaq_change_pct is not None and sector in {"반도체", "플랫폼", "가전"}:
        adjustment += max(min(market.nasdaq_change_pct, 2.0), -2.0)

    return adjustment


def _signal_from_score(score: float) -> str:
    if score >= 72:
        return "추천"
    if score >= 56:
        return "중립"
    return "회피"


def _serialize_article(article: NewsArticle) -> dict:
    return {
        "title": article.title,
        "url": article.url,
        "source": article.source,
        "published": article.published.astimezone(_KST).strftime("%Y-%m-%d %H:%M KST"),
        "summary": article.summary[:240],
    }


def _build_pick(entry: CompanyCatalogEntry, articles: list[NewsArticle], data: DailyData) -> dict:
    texts = [_article_text(article) for article in articles]
    joined = " ".join(texts)
    positive = sum(_score_keywords(text, _POSITIVE_KEYWORDS) for text in texts)
    negative = sum(_score_keywords(text, _NEGATIVE_KEYWORDS) for text in texts)
    theme_boost = sum(1 for keyword in _THEME_BOOSTS.get(entry.sector, ()) if keyword.lower() in joined)
    recent_bonus = sum(1 for article in articles if (datetime.now(_KST) - article.published.astimezone(_KST)).total_seconds() <= 12 * 3600)

    score = 48 + len(articles) * 8 + positive * 3 - negative * 4 + theme_boost * 2 + recent_bonus * 2
    score += _market_adjustment(data, entry.sector)
    score = max(25, min(95, round(score, 1)))

    reasons = [
        f"관련 뉴스 {len(articles)}건",
        f"긍정 신호 {positive}건 / 부정 신호 {negative}건",
    ]
    if theme_boost:
        reasons.append(f"{entry.sector} 테마 키워드 반영")
    if data.market_context:
        reasons.append(f"거시 컨텍스트: {data.market_context.summary}")

    risks = []
    if negative > 0:
        risks.append("부정 기사 비중이 높아 변동성 확대 가능성")
    if data.market_context and data.market_context.dollar_signal == "강세":
        risks.append("달러 강세 국면으로 위험자산 변동성 확대 가능성")
    if not risks:
        risks.append("단기 재료 소멸 여부를 점검할 필요")

    catalysts = [article.title for article in articles[:2]]

    return {
        "name": entry.name,
        "code": entry.code,
        "market": entry.market,
        "sector": entry.sector,
        "signal": _signal_from_score(score),
        "score": score,
        "confidence": max(45, min(92, 42 + len(articles) * 9 + abs(positive - negative) * 5)),
        "reasons": reasons,
        "risks": risks[:3],
        "catalysts": catalysts,
        "related_news": [_serialize_article(article) for article in articles[:3]],
    }


def generate_today_picks(data: DailyData, limit: int = 8) -> dict:
    """뉴스에서 기업을 매칭해 오늘의 추천 종목을 생성한다."""
    now = datetime.now(_KST)
    matched: list[dict] = []

    for entry in get_company_catalog():
        aliases = tuple(_normalize(alias) for alias in entry.aliases)
        related = []
        for article in data.news:
            text = _article_text(article)
            if any(alias in text for alias in aliases):
                related.append(article)

        if not related:
            continue

        matched.append(_build_pick(entry, related, data))

    matched.sort(key=lambda item: (item["score"], item["confidence"]), reverse=True)

    market_tone = "중립"
    if data.market.kospi_change_pct is not None and data.market.kospi_change_pct >= 1:
        market_tone = "국내 위험선호"
    elif data.market.nasdaq_change_pct is not None and data.market.nasdaq_change_pct <= -1:
        market_tone = "글로벌 위험회피"

    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M KST"),
        "date": now.strftime("%Y-%m-%d"),
        "market_tone": market_tone,
        "strategy": "news-driven-picks-v1",
        "picks": matched[:limit],
    }


def build_watchlist_actions(
    watchlist_items: list[dict],
    today_picks: dict | None,
    recommendations: dict | None,
    previous_recommendations: dict | None = None,
    previous_today_picks: dict | None = None,
) -> dict:
    """관심종목에 대해 buy/hold/sell/watch 액션을 계산한다."""
    now = datetime.now(_KST)
    pick_map = {}
    previous_pick_map = {}
    recommendation_map = {}
    previous_recommendation_map = {}

    for item in (today_picks or {}).get("picks", []):
        pick_map[item.get("code") or item.get("name")] = item
        pick_map[item.get("name")] = item

    for item in (previous_today_picks or {}).get("picks", []):
        previous_pick_map[item.get("code") or item.get("name")] = item
        previous_pick_map[item.get("name")] = item

    for item in (recommendations or {}).get("recommendations", []):
        key = (item.get("ticker") or "").split(".")[0] or item.get("name")
        recommendation_map[key] = item
        recommendation_map[item.get("name")] = item

    for item in (previous_recommendations or {}).get("recommendations", []):
        key = (item.get("ticker") or "").split(".")[0] or item.get("name")
        previous_recommendation_map[key] = item
        previous_recommendation_map[item.get("name")] = item

    actions = []
    for watch in watchlist_items:
        key = watch.get("code") or watch.get("name")
        current_pick = pick_map.get(key) or pick_map.get(watch.get("name"))
        current_rec = recommendation_map.get(key) or recommendation_map.get(watch.get("name"))
        previous_pick = previous_pick_map.get(key) or previous_pick_map.get(watch.get("name"))
        previous_rec = previous_recommendation_map.get(key) or previous_recommendation_map.get(watch.get("name"))

        score = 50.0
        reasons = []
        risks = []
        technical_reasons = []
        technical_risks = []
        flow_reasons = []
        flow_risks = []
        related_news = []
        signal = "중립"
        technicals = watch.get("technicals") or {}
        investor_flow = watch.get("investor_flow") or {}

        if current_pick:
            score = max(score, float(current_pick.get("score", score)))
            signal = current_pick.get("signal", signal)
            reasons.extend(current_pick.get("reasons", []))
            risks.extend(current_pick.get("risks", []))
            related_news = current_pick.get("related_news", [])
        if current_rec:
            score = (score + float(current_rec.get("score", score))) / 2
            signal = current_rec.get("signal", signal)
            reasons.extend(current_rec.get("reasons", []))
            risks.extend(current_rec.get("risks", []))

        if watch.get("change_pct") is not None:
            change_pct = float(watch["change_pct"])
            if change_pct <= -2:
                score -= 2
                risks.append("단기 낙폭이 커 변동성 관리 필요")
            elif change_pct >= 2:
                reasons.append("단기 모멘텀이 확인되는 흐름")

        if technicals:
            current_price = technicals.get("current_price")
            sma20 = technicals.get("sma20")
            sma60 = technicals.get("sma60")
            volume_ratio = technicals.get("volume_ratio")
            rsi14 = technicals.get("rsi14")
            macd_hist = technicals.get("macd_hist")
            macd = technicals.get("macd")
            macd_signal = technicals.get("macd_signal")

            if current_price is not None and sma20 is not None:
                if current_price > sma20:
                    score += 2.0
                    technical_reasons.append("주가가 20일 이동평균선 위에서 유지")
                else:
                    score -= 2.0
                    technical_risks.append("주가가 20일 이동평균선 아래에 위치")

            if sma20 is not None and sma60 is not None:
                if sma20 > sma60:
                    score += 1.5
                    technical_reasons.append("20일선이 60일선 위로 올라선 추세")
                else:
                    score -= 1.5
                    technical_risks.append("20일선이 60일선 아래로 약화된 추세")

            if volume_ratio is not None:
                if volume_ratio >= 1.5:
                    score += 1.5
                    technical_reasons.append(f"거래량이 20일 평균 대비 {volume_ratio:.2f}배")
                elif volume_ratio <= 0.7:
                    score -= 0.5
                    technical_risks.append("거래량이 줄어 추세 신뢰도가 낮음")

            if rsi14 is not None:
                if rsi14 <= 30:
                    score += 1.5
                    technical_reasons.append(f"RSI {rsi14:.1f}로 과매도 구간")
                elif rsi14 >= 70:
                    score -= 2.0
                    technical_risks.append(f"RSI {rsi14:.1f}로 과열 구간")

            if macd_hist is not None and macd is not None and macd_signal is not None:
                if macd_hist > 0 and macd > macd_signal:
                    score += 2.0
                    technical_reasons.append("MACD가 시그널선 위에서 모멘텀 개선")
                elif macd_hist < 0 and macd < macd_signal:
                    score -= 2.0
                    technical_risks.append("MACD가 시그널선 아래로 약세 전환")

        if investor_flow:
            foreign_1d = investor_flow.get("foreign_net_1d")
            foreign_5d = investor_flow.get("foreign_net_5d")
            institution_1d = investor_flow.get("institution_net_1d")
            institution_5d = investor_flow.get("institution_net_5d")

            if foreign_1d is not None and institution_1d is not None:
                if foreign_1d > 0 and institution_1d > 0:
                    score += 1.5
                    flow_reasons.append("외국인·기관이 최근 1일 동반 순매수")
                elif foreign_1d < 0 and institution_1d < 0:
                    score -= 1.5
                    flow_risks.append("외국인·기관이 최근 1일 동반 순매도")

            if foreign_5d is not None and institution_5d is not None:
                if foreign_5d > 0 and institution_5d > 0:
                    score += 2.5
                    flow_reasons.append("외국인·기관이 최근 5일 누적 순매수")
                elif foreign_5d < 0 and institution_5d < 0:
                    score -= 2.5
                    flow_risks.append("외국인·기관이 최근 5일 누적 순매도")
                elif foreign_5d * institution_5d < 0:
                    score -= 0.5
                    flow_risks.append("외국인과 기관 수급 방향이 엇갈림")

        score = round(max(20, min(95, score)), 1)
        if signal == "회피" and score <= 54:
            action = "sell"
        elif signal == "추천" and score >= 68:
            action = "buy"
        elif score >= 58:
            action = "hold"
        elif score >= 48:
            action = "watch"
        else:
            action = "sell"

        previous_signal = None
        if previous_pick:
            previous_signal = previous_pick.get("signal")
        elif previous_rec:
            previous_signal = previous_rec.get("signal")

        changed_from_yesterday = None
        previous_score = None
        if previous_pick:
            previous_score = float(previous_pick.get("score", 0))
        elif previous_rec:
            previous_score = float(previous_rec.get("score", 0))
        if previous_signal is not None or previous_score is not None:
            changed_from_yesterday = {
                "previous_signal": previous_signal,
                "score_diff": round(score - (previous_score or 0), 1),
            }

        confidence = 55
        if current_pick:
            confidence = current_pick.get("confidence", confidence)
        elif current_rec:
            confidence = current_rec.get("confidence", confidence)

        actions.append({
            "code": watch.get("code", ""),
            "name": watch.get("name", ""),
            "market": watch.get("market", ""),
            "price": watch.get("price"),
            "change_pct": watch.get("change_pct"),
            "action": action,
            "signal": signal,
            "score": score,
            "confidence": confidence,
            "reasons": (technical_reasons + flow_reasons + reasons)[:4] or ["오늘 기준 뚜렷한 추가 재료는 제한적입니다."],
            "risks": (technical_risks + flow_risks + risks)[:3] or ["단기 변동성 관리가 필요합니다."],
            "related_news": related_news[:2],
            "technicals": technicals or None,
            "investor_flow": investor_flow or None,
            "changed_from_yesterday": changed_from_yesterday,
        })

    actions.sort(key=lambda item: item["score"], reverse=True)
    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M KST"),
        "date": now.strftime("%Y-%m-%d"),
        "actions": actions,
    }
