export interface CompanyCatalogEntry {
  name: string;
  code?: string;
  market?: string;
  aliases: string[];
}

// Source of truth lives on the backend universe snapshot / lookup layer.
// The frontend should not import runtime-generated files from storage/ directly.
export const COMPANY_CATALOG: CompanyCatalogEntry[] = [];

export const CANDIDATE_EXCLUDES = new Set([
  'kospi', 'kosdaq', 'cnbc', 'fomc', 'wti', 'btc', 'usd', 'krw', 'fed', 'sec',
  '연준', '환율', '금리', '시장', '지수', '유가', '달러', '원달러', '항공', '금융', '반도체',
  '대형주', '성장주', '기술주', '가상자산', '스테이블코인', '에너지', '소프트웨어', '플랫폼',
]);
