"""한국투자증권 잔고/주문 테스트 도구."""

from __future__ import annotations

import argparse
import json
import sys

from broker.kis_client import KISAPIError, KISClient, KISConfigError


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("balance", help="국내주식 잔고를 조회합니다.")

    orderable = subparsers.add_parser(
        "orderable", help="주문 가능 금액/수량을 조회합니다."
    )
    orderable.add_argument("--symbol", required=True, help="국내 종목 코드")
    orderable.add_argument("--price", required=True, type=int, help="주문 단가")
    orderable.add_argument(
        "--order-division",
        default="00",
        help="주문 구분 코드 (기본: 00, 지정가)",
    )

    for side in ("buy", "sell"):
        order_parser = subparsers.add_parser(
            side,
            help=f"실전 {side} 주문을 전송합니다.",
        )
        order_parser.add_argument("--symbol", required=True, help="국내 종목 코드")
        order_parser.add_argument("--qty", required=True, type=int, help="주문 수량")
        order_parser.add_argument("--price", required=True, type=int, help="주문 단가")
        order_parser.add_argument(
            "--order-division",
            default="00",
            help="주문 구분 코드 (기본: 00, 지정가)",
        )
        order_parser.add_argument(
            "--confirm",
            action="store_true",
            help="실제 실전 주문 전송을 허용합니다.",
        )

    args = parser.parse_args()

    try:
        client = KISClient.from_env()

        if args.command == "balance":
            payload = client.get_balance()
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        if args.command == "orderable":
            payload = client.get_orderable_amount(
                args.symbol,
                args.price,
                order_division=args.order_division,
            )
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        if not args.confirm:
            print(
                "[KIS] safety error: 주문 전송에는 --confirm 이 필요합니다.",
                file=sys.stderr,
            )
            return 4

        payload = client.place_cash_order(
            side=args.command,
            code=args.symbol,
            quantity=args.qty,
            price=args.price,
            order_division=args.order_division,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
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
