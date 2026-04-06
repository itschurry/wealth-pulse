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
    {
        "name": "Google News - EV & Autonomous",
        "url": "https://news.google.com/rss/search?q=electric+vehicle+autonomous+driving+when:3d&hl=en-US&gl=US&ceid=US:en",
        "lang": "en",
        "priority": 1,
    },
    {
        "name": "Google News - Robotics",
        "url": "https://news.google.com/rss/search?q=robotics+industry+humanoid+when:3d&hl=en-US&gl=US&ceid=US:en",
        "lang": "en",
        "priority": 1,
    },
    {
        "name": "Google News - Physical AI",
        "url": "https://news.google.com/rss/search?q=physical+ai+embodied+ai+humanoid+robot+when:3d&hl=en-US&gl=US&ceid=US:en",
        "lang": "en",
        "priority": 1,
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
        "자동차", "전기차", "SDV", "로봇", "휴머노이드",
        "피지컬 AI", "physical AI", "robotics", "humanoid",
        "코스피", "나스닥", "S&P",
        "ETF", "자금유입", "자금유출",
        "외국인", "기관", "연기금",
        "공매도", "숏커버링",
        "매수세", "매도세",
        "원유", "천연가스", "원자재",
        "OPEC", "감산", "증산",
        "환율", "달러", "환율상승",
    ],
    "theme_keywords": {
        "automotive": [
            "자동차", "완성차", "전기차", "ev", "자율주행", "로보택시", "robotaxi",
            "sdv", "차량용 반도체", "테슬라", "현대차", "기아", "모빌리티",
        ],
        "robotics": [
            "로봇", "로보틱스", "robot", "robotics", "협동로봇", "산업용 로봇",
            "로봇팔", "자동화", "factory automation", "물류로봇", "servicerobot",
            "휴머노이드", "humanoid",
        ],
        "physical_ai": [
            "피지컬 ai", "physical ai", "embodied ai", "humanoid",
            "world model", "멀티모달 제어", "에이전트 로봇", "robot foundation model",
            "real-world ai", "온디바이스 ai", "vision-language-action", "vla",
            "자율주행 ai", "로봇 ai",
        ],
        "energy_lng": [
            "lng", "액화천연가스", "천연가스", "natural gas", "cheniere", "eni",
            "lng 운반선", "가스전", "가스 수출", "lpg", "pipeline",
        ],
        "defense": [
            "방산", "국방", "탄약", "미사일", "군수", "방위산업", "defense",
            "aerospace", "military", "drone", "드론",
        ],
        "semiconductor_ai": [
            "ai 반도체", "hbm", "gpu", "npu", "asic", "파운드리",
            "advanced packaging", "co-packaged optics", "chiplet",
        ],
        "biotech": [
            "바이오", "신약", "임상", "임상3상", "fda", "허가", "pharma",
            "biotech", "항암", "비만치료제",
        ],
        "finance_macro": [
            "금리", "인하", "인상", "yield", "credit spread", "유동성",
            "순이자마진", "npl", "자사주", "배당", "insurance",
        ],
    },
    "theme_weights": {
        "automotive": 1.2,
        "robotics": 1.4,
        "physical_ai": 1.6,
        "energy_lng": 1.3,
        "defense": 1.2,
        "semiconductor_ai": 1.4,
        "biotech": 1.15,
        "finance_macro": 1.1,
    },
}
