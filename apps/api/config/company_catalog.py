"""추천 및 뉴스 매핑에 사용하는 공통 종목 카탈로그."""
from dataclasses import dataclass

from config.backtest_universe import get_kospi100_universe, get_sp100_nasdaq_universe
from config.portfolio import HOLDINGS


@dataclass(frozen=True)
class CompanyCatalogEntry:
    name: str
    code: str
    market: str
    sector: str
    aliases: tuple[str, ...]


_BASE_ENTRIES = [
    CompanyCatalogEntry("삼성전자", "005930", "KOSPI", "반도체", ("삼성전자", "삼성 전자", "20만전자")),
    CompanyCatalogEntry("SK하이닉스", "000660", "KOSPI", "반도체", ("sk하이닉스", "sk 하이닉스", "하이닉스")),
    CompanyCatalogEntry("현대차", "005380", "KOSPI", "자동차", ("현대차", "현대 자동차", "현대차그룹")),
    CompanyCatalogEntry("기아", "000270", "KOSPI", "자동차", ("기아", "기아차")),
    CompanyCatalogEntry("현대모비스", "012330", "KOSPI", "자동차부품", ("현대모비스", "현대 모비스")),
    CompanyCatalogEntry("LG에너지솔루션", "373220", "KOSPI", "2차전지", ("lg에너지솔루션", "lg 에너지솔루션")),
    CompanyCatalogEntry("LG화학", "051910", "KOSPI", "화학", ("lg화학", "lg 화학")),
    CompanyCatalogEntry("NAVER", "035420", "KOSPI", "플랫폼", ("naver", "네이버")),
    CompanyCatalogEntry("카카오", "035720", "KOSPI", "플랫폼", ("카카오",)),
    CompanyCatalogEntry("한미반도체", "042700", "KOSPI", "반도체", ("한미반도체", "한미 반도체")),
    CompanyCatalogEntry("한화에어로스페이스", "012450", "KOSPI", "방산", ("한화에어로스페이스", "한화 에어로스페이스")),
    CompanyCatalogEntry("대한항공", "003490", "KOSPI", "항공", ("대한항공", "대한 항공")),
    CompanyCatalogEntry("아시아나항공", "020560", "KOSPI", "항공", ("아시아나항공", "아시아나 항공")),
    CompanyCatalogEntry("IBK기업은행", "024110", "KOSPI", "금융", ("ibk기업은행", "ibk 기업은행", "기업은행", "ibk")),
    CompanyCatalogEntry("KB금융", "105560", "KOSPI", "금융", ("kb금융", "kb 금융", "국민은행")),
    CompanyCatalogEntry("신한지주", "055550", "KOSPI", "금융", ("신한지주", "신한금융", "신한 금융")),
    CompanyCatalogEntry("셀트리온", "068270", "KOSPI", "바이오", ("셀트리온",)),
    CompanyCatalogEntry("LS", "006260", "KOSPI", "산업재", ("ls", "ls corp", "ls그룹", "엘에스")),
    CompanyCatalogEntry("LS ELECTRIC", "010120", "KOSPI", "산업재", ("ls electric", "ls일렉트릭", "엘에스일렉트릭")),
    CompanyCatalogEntry("에코프로", "086520", "KOSDAQ", "2차전지", ("에코프로",)),
    CompanyCatalogEntry("에코프로비엠", "247540", "KOSDAQ", "2차전지", ("에코프로비엠", "에코프로 비엠")),
    CompanyCatalogEntry("알테오젠", "196170", "KOSDAQ", "바이오", ("알테오젠",)),
    CompanyCatalogEntry("미래에셋증권", "006800", "KOSPI", "금융", ("미래에셋증권", "미래에셋 증권")),
    CompanyCatalogEntry("한국전력", "015760", "KOSPI", "유틸리티", ("한전", "한국전력")),
    CompanyCatalogEntry("삼성바이오로직스", "207940", "KOSPI", "바이오", ("삼성바이오로직스", "삼성 바이오로직스")),
    CompanyCatalogEntry("LG전자", "066570", "KOSPI", "가전", ("lg전자", "lg 전자")),
    CompanyCatalogEntry("두산로보틱스", "454910", "KOSPI", "로봇", ("두산로보틱스", "두산 로보틱스", "협동로봇")),
    CompanyCatalogEntry("Apple", "AAPL", "NASDAQ", "플랫폼", ("apple", "aapl", "애플")),
    CompanyCatalogEntry("Microsoft", "MSFT", "NASDAQ", "플랫폼", ("microsoft", "msft", "마이크로소프트")),
    CompanyCatalogEntry("Amazon", "AMZN", "NASDAQ", "플랫폼", ("amazon", "amzn", "아마존")),
    CompanyCatalogEntry("Alphabet", "GOOGL", "NASDAQ", "플랫폼", ("alphabet", "google", "googl", "구글")),
    CompanyCatalogEntry("Meta", "META", "NASDAQ", "플랫폼", ("meta", "메타")),
    CompanyCatalogEntry("NVIDIA", "NVDA", "NASDAQ", "반도체", ("nvidia", "nvda", "엔비디아")),
    CompanyCatalogEntry("AMD", "AMD", "NASDAQ", "반도체", ("amd",)),
    CompanyCatalogEntry("Broadcom", "AVGO", "NASDAQ", "반도체", ("broadcom", "avgo", "브로드컴")),
    CompanyCatalogEntry("Micron", "MU", "NASDAQ", "반도체", ("micron", "mu", "마이크론")),
    CompanyCatalogEntry("Qualcomm", "QCOM", "NASDAQ", "반도체", ("qualcomm", "qcom", "퀄컴")),
    CompanyCatalogEntry("Tesla", "TSLA", "NASDAQ", "자동차", ("tesla", "tsla", "테슬라")),
    CompanyCatalogEntry("Symbotic", "SYM", "NASDAQ", "로봇", ("symbotic", "sym", "심보틱", "물류로봇")),
    CompanyCatalogEntry("Intuitive Surgical", "ISRG", "NASDAQ", "로봇", ("intuitive surgical", "isrg", "인튜이티브 서지컬", "수술로봇")),
    CompanyCatalogEntry("Teradyne", "TER", "NASDAQ", "로봇", ("teradyne", "ter", "테라다인", "산업용 로봇")),
    CompanyCatalogEntry("Serve Robotics", "SERV", "NASDAQ", "로봇", ("serve robotics", "serv", "서브 로보틱스", "배달로봇")),
]

_ALLOWED_MARKETS = {"KOSPI", "KOSDAQ", "NASDAQ"}
_CATALOG_CACHE: dict[str, list[CompanyCatalogEntry]] = {}


def _catalog_aliases(name: str, code: str) -> tuple[str, ...]:
    lowered = name.lower()
    aliases = [name, lowered, code, code.lower()]
    deduped: list[str] = []
    for alias in aliases:
        value = str(alias).strip()
        if value and value not in deduped:
            deduped.append(value)
    return tuple(deduped)


def _guess_sector(name: str, market: str) -> str:
    lowered = name.lower()
    if any(keyword in lowered for keyword in ("semiconductor", "chip", "반도체")):
        return "반도체"
    if any(keyword in lowered for keyword in ("robot", "로봇", "automation")):
        return "로봇"
    if any(keyword in lowered for keyword in ("auto", "vehicle", "자동차", "mobility")):
        return "자동차"
    if any(keyword in lowered for keyword in ("bank", "financial", "insurance", "금융")):
        return "금융"
    if any(keyword in lowered for keyword in ("bio", "pharma", "health", "바이오")):
        return "바이오"
    if any(keyword in lowered for keyword in ("energy", "oil", "gas", "전력", "에너지")):
        return "에너지"
    return "국내주식" if market == "KOSPI" else "미국주식"


def _build_core_catalog() -> list[CompanyCatalogEntry]:
    seen_codes = {entry.code for entry in _BASE_ENTRIES if entry.code}
    merged = list(_BASE_ENTRIES)

    for holding in HOLDINGS:
        code = (holding.ticker_kr or holding.ticker_us or "").split(".")[0]
        if not code or code in seen_codes:
            continue
        merged.append(
            CompanyCatalogEntry(
                name=holding.name,
                code=code,
                market="KOSPI" if holding.ticker_kr else "NASDAQ",
                sector=holding.sector,
                aliases=(holding.name.lower(), holding.name),
            )
        )
        seen_codes.add(code)

    return [entry for entry in merged if entry.market in _ALLOWED_MARKETS]


def _build_live_catalog(core_catalog: list[CompanyCatalogEntry]) -> list[CompanyCatalogEntry]:
    merged = list(core_catalog)
    seen_codes = {entry.code for entry in merged if entry.code}
    sector_by_code = {entry.code: entry.sector for entry in merged}

    for item in get_kospi100_universe():
        code = str(item.get("code") or "").strip().upper()
        market = str(item.get("market") or "").strip().upper()
        name = str(item.get("name") or "").strip()
        if not code or code in seen_codes or market != "KOSPI":
            continue
        merged.append(
            CompanyCatalogEntry(
                name=name or code,
                code=code,
                market="KOSPI",
                sector=sector_by_code.get(code) or _guess_sector(name or code, "KOSPI"),
                aliases=_catalog_aliases(name or code, code),
            )
        )
        seen_codes.add(code)

    for item in get_sp100_nasdaq_universe():
        code = str(item.get("code") or "").strip().upper()
        market = str(item.get("market") or "").strip().upper()
        name = str(item.get("name") or "").strip()
        if not code or code in seen_codes or market != "NASDAQ":
            continue
        merged.append(
            CompanyCatalogEntry(
                name=name or code,
                code=code,
                market="NASDAQ",
                sector=sector_by_code.get(code) or _guess_sector(name or code, "NASDAQ"),
                aliases=_catalog_aliases(name or code, code),
            )
        )
        seen_codes.add(code)

    return [entry for entry in merged if entry.market in _ALLOWED_MARKETS]


def get_company_catalog(scope: str = "core") -> list[CompanyCatalogEntry]:
    """공통 카탈로그를 반환한다.

    scope:
    - core: 공시/수급 수집에 쓰는 핵심 종목군
    - live: 오늘의픽/자동매매 후보 확장 종목군
    """
    normalized_scope = str(scope or "core").strip().lower()
    if normalized_scope not in {"core", "live"}:
        normalized_scope = "core"

    cached = _CATALOG_CACHE.get(normalized_scope)
    if cached is not None:
        return list(cached)

    core_catalog = _build_core_catalog()
    if normalized_scope == "core":
        _CATALOG_CACHE["core"] = core_catalog
        return list(core_catalog)

    live_catalog = _build_live_catalog(core_catalog)
    _CATALOG_CACHE["core"] = core_catalog
    _CATALOG_CACHE["live"] = live_catalog
    return list(live_catalog)
