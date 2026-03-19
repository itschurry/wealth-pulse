"""뉴스 RSS 피드 및 유튜브 채널 설정"""

NEWS_FEEDS = [
    {
        "name": "Samsung Global Newsroom",
        "url": "https://news.samsung.com/global/feed/rss",
        "lang": "en",
        "priority": 1,
    },
    {
        "name": "SK hynix Newsroom",
        "url": "https://news.skhynix.com/feed/",
        "lang": "en",
        "priority": 1,
    },
    {
        "name": "NVIDIA Newsroom",
        "url": "https://nvidianews.nvidia.com/rss",
        "lang": "en",
        "priority": 1,
    },
    {
        "name": "한국경제 증권",
        "url": "https://www.hankyung.com/feed/stock",
        "lang": "ko",
        "priority": 1,
    },
    {
        "name": "연합뉴스 경제",
        "url": "https://www.yna.co.kr/rss/economy.xml",
        "lang": "ko",
        "priority": 1,
    },
    {
        "name": "매일경제",
        "url": "https://www.mk.co.kr/rss/30100041/",
        "lang": "ko",
        "priority": 2,
    },
    {
        "name": "CNBC Markets",
        "url": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
        "lang": "en",
        "priority": 1,
    },
    {
        "name": "Reuters Business",
        "url": "https://www.reutersagency.com/feed/?taxonomy=best-sectors&post_type=best",
        "lang": "en",
        "priority": 2,
    },
]


NEWS_CONFIG = {
    "max_articles_per_feed": 10,
    "max_age_hours": 24,
    "max_body_chars": 2000,
    "keywords_boost": [
        "CPI", "PPI", "인플레이션", "물가",
        "고용지표", "실업률", "비농업고용",
        "금리인상", "금리인하", "긴축", "완화",
        "양적완화", "QT", "테이퍼링",
        "반도체", "SK하이닉스", "삼성전자", "HBM",
        "AI", "엔비디아", "NVIDIA", "GTC",
        "FOMC", "금리", "연준", "Fed",
        "유가", "자율주행",
        "코스피", "나스닥", "S&P",
        "ETF", "자금유입", "자금유출",
        "외국인", "기관", "연기금",
        "공매도", "숏커버링",
        "매수세", "매도세",
        "원유", "천연가스", "원자재",
        "OPEC", "감산", "증산",
        "환율", "달러", "환율상승",
    ],
}
