from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from intelligence.provider import get_intelligence_provider
from orchestrator.pipeline import (
    build_candidates,
    fetch_all_sources,
    load_evidence,
    load_fixture,
    load_preferences,
    load_sources_config,
    run_pipeline,
)
from telegram.bot import TelegramBot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pre-Claude Career Agent")
    parser.add_argument(
        "--mode",
        choices=["fetch-only", "scan", "notify-test", "dashboard-test", "prepare"],
        default="scan",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--fixture", type=Path, default=None)
    parser.add_argument("--job-key", default=None)
    return parser


def run_dashboard_test(args: argparse.Namespace, bot: TelegramBot) -> None:
    preferences = load_preferences()
    evidence = load_evidence()
    sources_config = load_sources_config()
    if args.fixture:
        raw = load_fixture(args.fixture)
        if args.limit is not None:
            raw = raw[: args.limit]
        source_results = [{"source": "fixture", "fetched": len(raw), "errors": []}]
    else:
        raw, source_result_models = fetch_all_sources(sources_config, args.limit)
        source_results = [item.model_dump() for item in source_result_models]

    candidates, counts = build_candidates(raw, preferences, evidence, sources_config)
    candidates = get_intelligence_provider("mock").evaluate_jobs(candidates, evidence)
    sent = bot.send_dashboard_preview(candidates)
    print(
        json.dumps(
            {
                "mode": "dashboard-test",
                "telegram_configured": bot.configured,
                "dashboard_messages_sent": sent,
                "counts": counts,
                "source_results": source_results,
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
    )


def main() -> None:
    load_dotenv()
    args = build_parser().parse_args()
    bot = TelegramBot()

    if args.mode == "notify-test":
        result = bot.notify_test()
        print(json.dumps(result, indent=2, sort_keys=True))
        return

    if args.mode == "dashboard-test":
        run_dashboard_test(args, bot)
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
