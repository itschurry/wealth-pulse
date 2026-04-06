"""한국투자증권 Open API 연결 테스트."""

from __future__ import annotations

import argparse
import sys

from broker.kis_client import KISAPIError, KISClient, KISConfigError


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--symbol",
        default="005930",
        help="현재가 조회를 시도할 국내 종목 코드 (기본값: 005930)",
    )
    parser.add_argument(
        "--token-only",
        action="store_true",
        help="토큰 발급까지만 확인하고 시세 조회는 생략합니다.",
    )
    args = parser.parse_args()

    try:
        client = KISClient.from_env()
        status = client.check_connection()
        print(
            "[KIS] token ok",
            f"mode={status['mode']}",
            f"base_url={status['base_url']}",
            f"token_prefix={status['token_prefix']}...",
        )

        if args.token_only:
            return 0

        quote = client.get_domestic_price(args.symbol)
        print(
            "[KIS] quote ok",
            f"symbol={quote['code']}",
            f"name={quote['name'] or '-'}",
            f"price={quote['price']}",
            f"change_pct={quote['change_pct']}",
            f"volume={quote['volume']}",
        )
        return 0
    except KISConfigError as exc:
        print(f"[KIS] config error: {exc}", file=sys.stderr)
        return 2
    except KISAPIError as exc:
        print(f"[KIS] api error: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:  # pragma: no cover
        print(f"[KIS] unexpected error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
