"""수동 1회 실행"""
import asyncio
from main import run_daily_report


def main() -> None:
    asyncio.run(run_daily_report())


if __name__ == "__main__":
    main()
