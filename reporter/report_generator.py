"""Jinja2 템플릿으로 HTML/Markdown 리포트 생성"""
from dataclasses import asdict, is_dataclass
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List

import markdown2
import pytz
from jinja2 import Environment, FileSystemLoader
from loguru import logger

from config.settings import REPORT_OUTPUT_DIR, BASE_DIR
from collectors.models import DailyData


_TEMPLATE_DIR = BASE_DIR / "templates"
_KST = pytz.timezone("Asia/Seoul")


def _get_jinja_env() -> Environment:
    return Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=False)


def _fix_markdown(text: str) -> str:
    """AI 출력 마크다운 전처리: 불릿 리스트 앞에 빈 줄 추가하여 <ul> 변환 보장"""
    text = re.sub(r'([^\n])\n([ \t]*[\*\-]\s)', r'\1\n\n\2', text)
    text = re.sub(r'(⚠️[^\n]+)', r'\n\1\n', text)
    return text.strip()


def _extract_summary(analysis_md: str) -> List[str]:
    """분석 마크다운에서 '## 3줄 요약' 섹션을 추출해 최대 3개 항목 반환"""
    m = re.search(r'##\s*3줄\s*요약\s*\n(.*?)(?:\n---|\n##)',
                  analysis_md, re.DOTALL)
    if not m:
        return []
    block = m.group(1).strip()
    lines = [re.sub(r'^\d+\.\s*', '', l).strip()
             for l in block.splitlines() if l.strip()]
    return lines[:3]


def generate_html(analysis: str, data: DailyData) -> str:
    """분석 결과를 HTML 리포트로 변환"""
    env = _get_jinja_env()
    template = env.get_template("daily_report.html")

    summary_lines = _extract_summary(analysis)

    analysis_html = markdown2.markdown(
        _fix_markdown(analysis),
        extras=["fenced-code-blocks", "tables"],
    )

    # 면책 문구 paragraph에 class 추가
    analysis_html = re.sub(
        r'<p>(⚠️[^<]*)</p>',
        r'<p class="disclaimer-inline">\1</p>',
        analysis_html,
        count=1,
    )

    now_kst = datetime.now(_KST)

    context = {
        "report_date":    now_kst.strftime("%Y년 %m월 %d일"),
        "generated_at":   now_kst.strftime("%Y-%m-%d %H:%M KST"),
        "market":         data.market,
        "holdings":       data.holdings,
        "macro":          data.macro,
        "market_context": data.market_context,
        "analysis_html":  analysis_html,
        "summary_lines":  summary_lines,
        "news_count":     len(data.news),
    }
    return template.render(**context)


def generate_markdown(analysis: str, data: DailyData) -> str:
    """분석 결과를 Markdown 리포트로 변환"""
    env = _get_jinja_env()
    template = env.get_template("daily_report.md")
    now_kst = datetime.now(_KST)

    context = {
        "report_date":  now_kst.strftime("%Y년 %m월 %d일"),
        "generated_at": now_kst.strftime("%Y-%m-%d %H:%M KST"),
        "market":       data.market,
        "holdings":     data.holdings,
        "macro":        data.macro,
        "market_context": data.market_context,
        "analysis":     analysis,
        "news_count":   len(data.news),
    }
    return template.render(**context)


def save_report(content: str, date: str, fmt: str = "html") -> str:
    """리포트를 파일로 저장하고 경로 반환"""
    filename = f"{date}_daily_report.{fmt}"
    path = REPORT_OUTPUT_DIR / filename
    path.write_text(content, encoding="utf-8")
    logger.info(f"리포트 저장: {path}")
    return str(path)


def save_analysis_cache(analysis: str, date: str) -> None:
    """AI 분석 결과를 JSON으로 캐시 저장 (api_server.py가 읽어 /api/analysis 제공)"""
    summary_lines = _extract_summary(analysis)

    analysis_html = markdown2.markdown(
        _fix_markdown(analysis),
        extras=["fenced-code-blocks", "tables"],
    )
    analysis_html = re.sub(
        r'<p>(⚠️[^<]*)</p>',
        r'<p class="disclaimer-inline">\1</p>',
        analysis_html,
        count=1,
    )

    now_kst = datetime.now(_KST)
    payload = {
        "generated_at":  now_kst.strftime("%Y-%m-%d %H:%M KST"),
        "summary_lines": summary_lines,
        "analysis_html": analysis_html,
        "date":          date,
    }
    cache_path = REPORT_OUTPUT_DIR / f"{date}_analysis.json"
    cache_path.write_text(json.dumps(
        payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"분석 캐시 저장: {cache_path}")


def save_recommendations_cache(payload: dict, date: str) -> None:
    """투자 추천 결과를 JSON으로 캐시 저장 (api_server.py가 읽어 /api/recommendations 제공)"""
    out = dict(payload)
    out["date"] = date
    cache_path = REPORT_OUTPUT_DIR / f"{date}_recommendations.json"
    cache_path.write_text(json.dumps(
        out, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"추천 캐시 저장: {cache_path}")


def save_macro_cache(items: list, date: str) -> None:
    """거시 지표를 JSON으로 저장한다."""
    payload = {
        "date": date,
        "items": [asdict(item) for item in items],
        "summary": [item.summary for item in items if getattr(item, "summary", "")],
    }
    cache_path = REPORT_OUTPUT_DIR / f"{date}_macro.json"
    cache_path.write_text(json.dumps(
        payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"거시 캐시 저장: {cache_path}")


def save_calendar_cache(items: list, date: str) -> None:
    """경제 일정을 JSON으로 저장한다."""
    payload = {
        "date": date,
        "items": [asdict(item) for item in items],
    }
    cache_path = REPORT_OUTPUT_DIR / f"{date}_calendar.json"
    cache_path.write_text(json.dumps(
        payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    logger.info(f"일정 캐시 저장: {cache_path}")


def save_disclosures_cache(items: list, date: str) -> None:
    """공시 데이터를 JSON으로 저장한다."""
    payload = {
        "date": date,
        "items": [asdict(item) for item in items],
    }
    cache_path = REPORT_OUTPUT_DIR / f"{date}_disclosures.json"
    cache_path.write_text(json.dumps(
        payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    logger.info(f"공시 캐시 저장: {cache_path}")


def save_investor_flows_cache(items: list, date: str) -> None:
    """수급 데이터를 JSON으로 저장한다."""
    payload = {
        "date": date,
        "items": [asdict(item) for item in items],
    }
    cache_path = REPORT_OUTPUT_DIR / f"{date}_investor_flows.json"
    cache_path.write_text(json.dumps(
        payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    logger.info(f"수급 캐시 저장: {cache_path}")


def save_market_context_cache(context, date: str) -> None:
    """시장 컨텍스트를 JSON으로 저장한다."""
    payload = {"date": date, "context": asdict(context) if context else {}}
    cache_path = REPORT_OUTPUT_DIR / f"{date}_market_context.json"
    cache_path.write_text(json.dumps(
        payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"시장 컨텍스트 캐시 저장: {cache_path}")


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"JSON serializable unsupported type: {type(value)!r}")


def save_news_cache(items: list, date: str) -> None:
    """수집한 뉴스 원문 메타데이터를 JSON으로 저장한다."""
    payload = {
        "date": date,
        "items": items,
    }
    cache_path = REPORT_OUTPUT_DIR / f"{date}_news.json"
    cache_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    logger.info(f"뉴스 캐시 저장: {cache_path}")


def save_today_picks_cache(payload: dict, date: str) -> None:
    """오늘의 추천 종목 결과를 JSON으로 저장한다."""
    out = dict(payload)
    out["date"] = date
    cache_path = REPORT_OUTPUT_DIR / f"{date}_today_picks.json"
    cache_path.write_text(json.dumps(
        out, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"오늘의 추천 캐시 저장: {cache_path}")
