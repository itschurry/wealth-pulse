export interface CompanyCatalogEntry {
  name: string;
  code?: string;
  market?: string;
  aliases: string[];
}

export const COMPANY_CATALOG: CompanyCatalogEntry[] = [
  {
    "name": "신일전자",
    "code": "002700",
    "market": "KOSPI",
    "aliases": [
      "신일전자",
      "002700",
      "SHINIL ELECTRONICS"
    ]
  },
  {
    "name": "보령",
    "code": "003850",
    "market": "KOSPI",
    "aliases": [
      "보령",
      "003850",
      "Boryung"
    ]
  },
  {
    "name": "엔케이",
    "code": "085310",
    "market": "KOSPI",
    "aliases": [
      "엔케이",
      "085310",
      "NK"
    ]
  },
  {
    "name": "두산밥캣",
    "code": "241560",
    "market": "KOSPI",
    "aliases": [
      "두산밥캣",
      "241560",
      "Doosan Bobcat"
    ]
  },
  {
    "name": "IPARK현대산업개발",
    "code": "294870",
    "market": "KOSPI",
    "aliases": [
      "IPARK현대산업개발",
      "294870",
      "아이파크현대산업개발",
      "HDC현대산업개발",
      "IPARK HYUNDAI DEVELOPMENT COMPANY"
    ]
  }
];

export const CANDIDATE_EXCLUDES = new Set([
  'kospi', 'kosdaq', 'cnbc', 'fomc', 'wti', 'btc', 'usd', 'krw', 'fed', 'sec',
  '연준', '환율', '금리', '시장', '지수', '유가', '달러', '원달러', '항공', '금융', '반도체',
  '대형주', '성장주', '기술주', '가상자산', '스테이블코인', '에너지', '소프트웨어', '플랫폼',
]);
