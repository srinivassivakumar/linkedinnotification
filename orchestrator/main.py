from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from orchestrator.pipeline import run_pipeline
from telegram.bot import TelegramBot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pre-Claude Career Agent")
    parser.add_argument("--mode", choices=["fetch-only", "scan", "notify-test", "prepare"], default="scan")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--fixture", type=Path, default=None)
    parser.add_argument("--job-key", default=None)
    return parser


def main() -> None:
    load_dotenv()
    args = build_parser().parse_args()
    bot = TelegramBot()
    if args.mode == "notify-test":
        result = bot.notify_test()
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    summary = run_pipeline(
        mode="scan" if args.mode == "prepare" else args.mode,
        dry_run=args.dry_run,
        limit=args.limit,
        fixture=args.fixture,
        notifier=None if args.dry_run else bot,
        prepare_key=args.job_key if args.mode == "prepare" else None,
    )
    print(json.dumps(summary.model_dump(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

