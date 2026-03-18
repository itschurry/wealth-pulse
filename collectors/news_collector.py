"""RSS 뉴스 수집"""
from datetime import datetime, timezone, timedelta
from typing import List

import feedparser
from bs4 import BeautifulSoup
from loguru import logger

from config.sources import NEWS_FEEDS, NEWS_CONFIG
from collectors.models import NewsArticle


def _parse_date(entry) -> datetime:
    """feedparser entry의 날짜를 datetime으로 변환"""
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            import time as _time
            return datetime.fromtimestamp(_time.mktime(t), tz=timezone.utc)
    return datetime.now(tz=timezone.utc)


def _clean_html(text: str) -> str:
    """HTML 태그 제거"""
    return BeautifulSoup(text, "html.parser").get_text(separator=" ").strip()


def _score_article(article: NewsArticle) -> float:
    """키워드 매칭으로 relevance_score 계산"""
    keywords = NEWS_CONFIG["keywords_boost"]
    text = (article.title + " " + article.summary).lower()
    return sum(1.0 for kw in keywords if kw.lower() in text)


def collect_news() -> List[NewsArticle]:
    """RSS 피드에서 뉴스 기사 수집 후 relevance_score 기준 정렬 반환"""
    max_age = timedelta(hours=NEWS_CONFIG["max_age_hours"])
    cutoff = datetime.now(tz=timezone.utc) - max_age
    max_per_feed = NEWS_CONFIG["max_articles_per_feed"]
    max_body = NEWS_CONFIG["max_body_chars"]

    articles: List[NewsArticle] = []

    for feed_cfg in NEWS_FEEDS:
        name = feed_cfg["name"]
        url = feed_cfg["url"]
        try:
            feed = feedparser.parse(url, request_headers={"User-Agent": "Mozilla/5.0"})
            count = 0
            for entry in feed.entries:
                if count >= max_per_feed:
                    break
                pub = _parse_date(entry)
                if pub < cutoff:
                    continue
                title = _clean_html(getattr(entry, "title", ""))
                summary = _clean_html(getattr(entry, "summary", ""))[:max_body]
                link = getattr(entry, "link", "")
                article = NewsArticle(
                    title=title,
                    url=link,
                    source=name,
                    published=pub,
                    summary=summary,
                    lang=feed_cfg["lang"],
                )
                article.relevance_score = _score_article(article)
                articles.append(article)
                count += 1
            logger.info(f"뉴스 수집: {name} → {count}건")
        except Exception as e:
            logger.warning(f"뉴스 수집 실패 [{name}]: {e}")

    articles.sort(key=lambda a: (a.relevance_score, a.published), reverse=True)
    logger.info(f"뉴스 총 {len(articles)}건 수집 완료")
    return articles
