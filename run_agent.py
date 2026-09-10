"""Single entry point for the integrated career agent.

Subcommands:
  scan       one deterministic scan pass (ATS sources -> score -> Telegram cards)
  gmail      run the background Gmail watcher loop (local always-on machine)
  telegram   run the Telegram callback (approval) worker loop (local always-on)
  workers    run gmail + telegram workers together, supervised (local always-on)
  once       one scan pass + one gmail pass
  cloud      one full tick for a scheduled/cloud runner: scan + gmail pass +
             drain pending Telegram approvals, then (optionally) persist state to
             git. Nothing device-bound; safe to run headless on a schedule.

State lives in SQLite (state/career_agent.db). Claude runs in CLAUDE_MODE
(mock until a live audit); auth is the Claude Pro subscription.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent


def _bootstrap_gmail_secrets() -> None:
    """In a cloud runner the OAuth files come from env, not the local disk."""
    secrets = ROOT / "secrets"
    mapping = {
        "GMAIL_CREDENTIALS_JSON": secrets / "credentials.json",
        "GMAIL_TOKEN_JSON": secrets / "token.json",
    }
    for env_key, target in mapping.items():
        value = os.getenv(env_key)
        if value and not target.exists():
            secrets.mkdir(parents=True, exist_ok=True)
            target.write_text(value, encoding="utf-8")


def _git_persist(paths: list[str], message: str) -> str:
    """Commit + push the given paths. Used only when AGENT_PERSIST_GIT=1."""
    try:
        subprocess.run(["git", "add", "-f", *paths], cwd=ROOT, check=True, capture_output=True)
        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT)
        if diff.returncode == 0:
            return "no changes"
        subprocess.run(["git", "-c", "user.name=career-agent-bot",
                        "-c", "user.email=career-agent-bot@users.noreply.github.com",
                        "commit", "-m", message], cwd=ROOT, check=True, capture_output=True)
        push = subprocess.run(["git", "push"], cwd=ROOT, capture_output=True, text=True)
        return "committed + pushed" if push.returncode == 0 else f"committed, push failed: {push.stderr.strip()}"
    except subprocess.CalledProcessError as exc:
        return f"git error: {exc.stderr.decode() if exc.stderr else exc}"


def _run_cloud(args: argparse.Namespace) -> None:
    from gmail.watcher import run_once as gmail_run_once
    from intelligence.provider import get_intelligence_provider
    from orchestrator.pipeline import run_pipeline
    from state.store import SqliteStore
    from telegram.bot import TelegramBot
    from telegram.callback_worker import drain_callbacks

    _bootstrap_gmail_secrets()
    bot = TelegramBot()
    store = SqliteStore(ROOT / "state")
    provider = get_intelligence_provider(os.getenv("CLAUDE_MODE", "mock"))

    scan = run_pipeline(mode="scan", dry_run=False, limit=args.limit, notifier=bot, store=store)
    gmail = gmail_run_once()
    approvals = drain_callbacks(bot, store, provider)

    summary = {
        "claude_mode": os.getenv("CLAUDE_MODE", "mock"),
        "scan_counts": scan.counts,
        "scan_source_errors": [r.model_dump() for r in scan.source_results if r.errors],
        "notified": scan.notified,
        "gmail": gmail,
        "telegram_approvals": approvals,
    }
    needs_human = [e for e in store.recent_events(30)
                   if e["type"] in {"email_classified", "interview_prep_ready", "connection_discovered"}]
    summary["recent_needs_review"] = [
        {"type": e["type"], "at": e["created_at"]} for e in needs_human[:10]
    ]

    if os.getenv("AGENT_PERSIST_GIT") == "1":
        summary["persist"] = _git_persist(
            ["state/career_agent.db"],
            f"state: cloud tick ({summary['scan_counts'].get('new_or_changed', 0)} new)",
        )

    print(json.dumps(summary, indent=2, sort_keys=True, default=str))


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


def _run_naukri(args: argparse.Namespace) -> None:
    from intelligence.provider import get_intelligence_provider
    from orchestrator.models import Candidate
    from orchestrator.pipeline import ROOT
    from orchestrator.policies import load_evidence, load_preferences
    from orchestrator.scorer import score_job
    from sources.naukri import job_from_manual
    from state.store import SqliteStore
    from telegram.bot import TelegramBot

    evidence = load_evidence()
    job = job_from_manual(
        args.url,
        title=args.title,
        company=args.company,
        description=args.description or "",
        location=args.location,
    )
    candidate = Candidate(job=job, score=score_job(job, load_preferences(), evidence))
    store = SqliteStore(ROOT / "state")
    provider = get_intelligence_provider(os.getenv("CLAUDE_MODE", "mock"))
    evaluated = provider.evaluate_jobs(store.diff_new_or_changed([candidate]), evidence)

    sent: list[str] = []
    if not args.dry_run:
        store.persist(evaluated)
        sent = TelegramBot().send_naukri_candidates(evaluated)

    print(
        json.dumps(
            {
                "dry_run": args.dry_run,
                "job_key": candidate.job_key,
                "new_or_changed": [item.job_key for item in evaluated],
                "score": candidate.score.model_dump(),
                "telegram_sent": sent,
                "manual_action": "Open/apply on Naukri manually; this command does not submit applications.",
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
    )


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

    p_naukri = sub.add_parser("naukri")
    p_naukri.add_argument("--url", required=True)
    p_naukri.add_argument("--title", required=True)
    p_naukri.add_argument("--company", required=True)
    p_naukri.add_argument("--location", default=None)
    p_naukri.add_argument("--description", default="")
    p_naukri.add_argument("--dry-run", action="store_true")

    sub.add_parser("gmail")
    sub.add_parser("telegram")
    sub.add_parser("workers")
    sub.add_parser("once").add_argument("--limit", type=int, default=None)
    p_cloud = sub.add_parser("cloud")
    p_cloud.add_argument("--limit", type=int, default=None)

    args = parser.parse_args()

    if args.command == "scan":
        _run_scan(args)
    elif args.command == "cloud":
        _run_cloud(args)
    elif args.command == "naukri":
        _run_naukri(args)
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
