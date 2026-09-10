"""Single entry point for the integrated career agent.

Subcommands:
  scan       one deterministic scan pass (ATS sources -> score -> Telegram cards)
  gmail      run the background Gmail watcher loop
  telegram   run the Telegram callback (approval) worker loop
  workers    run gmail + telegram workers together, supervised
  once       one scan pass + one gmail pass (useful for cron / CI)

State lives in SQLite (state/career_agent.db). Claude runs in CLAUDE_MODE
(mock until a live audit); auth is the `ant auth login` subscription profile.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time

from dotenv import load_dotenv


def _run_scan(args: argparse.Namespace) -> None:
    from orchestrator.pipeline import run_pipeline
    from telegram.bot import TelegramBot

    bot = TelegramBot()
    summary = run_pipeline(
        mode="scan",
        dry_run=args.dry_run,
        limit=args.limit,
        notifier=None if args.dry_run else bot,
    )
    print(json.dumps(summary.model_dump(), indent=2, sort_keys=True, default=str))


def _run_gmail_once() -> None:
    from gmail.watcher import run_once

    print(json.dumps(run_once(), indent=2, default=str))


def _supervise() -> None:
    procs = {
        "gmail": [sys.executable, "-u", "-m", "gmail.watcher"],
        "telegram": [sys.executable, "-u", "-m", "telegram.callback_worker"],
    }
    running = {name: subprocess.Popen(cmd) for name, cmd in procs.items()}
    print("workers started:", ", ".join(running), flush=True)
    try:
        while True:
            for name, proc in list(running.items()):
                if proc.poll() is not None:
                    print(f"{name} exited ({proc.returncode}); restarting in 5s", flush=True)
                    time.sleep(5)
                    running[name] = subprocess.Popen(procs[name])
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nstopping workers...", flush=True)
        for proc in running.values():
            proc.terminate()
        for proc in running.values():
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Integrated career agent")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan")
    p_scan.add_argument("--dry-run", action="store_true")
    p_scan.add_argument("--limit", type=int, default=None)

    sub.add_parser("gmail")
    sub.add_parser("telegram")
    sub.add_parser("workers")
    sub.add_parser("once").add_argument("--limit", type=int, default=None)

    args = parser.parse_args()

    if args.command == "scan":
        _run_scan(args)
    elif args.command == "gmail":
        from gmail.watcher import main as gmail_main

        gmail_main()
    elif args.command == "telegram":
        from telegram.callback_worker import main as telegram_main

        telegram_main()
    elif args.command == "workers":
        _supervise()
    elif args.command == "once":
        args.dry_run = False
        _run_scan(args)
        _run_gmail_once()


if __name__ == "__main__":
    main()
