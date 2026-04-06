"""KIS 국내 종목 조회/일봉 테스트 스크립트."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
CURRENT_FILE = Path(__file__).resolve()
API_DIR = CURRENT_FILE.parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))
from broker.kis_client import KISAPIError, KISClient, KISConfigError

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="apps/api/.env 의 KIS 키를 사용해 국내 종목 현재가/일봉을 테스트합니다.")
    parser.add_argument('--symbol', default='005930')
    parser.add_argument('--start-date', default='20240101')
    parser.add_argument('--end-date', default='')
    parser.add_argument('--history-limit', type=int, default=5)
    parser.add_argument('--price-only', action='store_true')
    parser.add_argument('--json', action='store_true')
    return parser

def main() -> int:
    args = build_parser().parse_args()
    try:
        client = KISClient.from_env()
        status = client.check_connection()
        quote = client.get_domestic_price(args.symbol)
        result = {'connection': {'ok': True, 'mode': status['mode'], 'base_url': status['base_url'], 'token_prefix': f"{status['token_prefix']}..."}, 'quote': quote}
        if not args.price_only:
            rows = client.get_domestic_daily_history(args.symbol, start_date=args.start_date, end_date=args.end_date)
            result['history'] = {'count': len(rows), 'recent': rows[-args.history_limit:]}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print('[KIS] connection ok', f"mode={status['mode']}", f"base_url={status['base_url']}", f"token_prefix={status['token_prefix']}...")
            print('[KIS] quote ok', f"symbol={quote['code']}", f"name={quote['name'] or '-'}", f"price={quote['price']}", f"change_pct={quote['change_pct']}", f"volume={quote['volume']}")
            if not args.price_only:
                h = result['history']
                print('[KIS] history ok', f"rows={h['count']}", f"recent={json.dumps(h['recent'], ensure_ascii=False)}")
        return 0
    except KISConfigError as exc:
        print(f'[KIS] config error: {exc}', file=sys.stderr)
        return 2
    except KISAPIError as exc:
        print(f'[KIS] api error: {exc}', file=sys.stderr)
        return 3
    except Exception as exc:
        print(f'[KIS] unexpected error: {exc}', file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
