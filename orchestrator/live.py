"""``python run_agent.py live`` - a single long-running local process.

Responsibilities:

* Run one discovery scan immediately on startup (7-day window the first time the
  local state DB has ever completed a scan, 12-hour window every time after).
* Stay alive as the *only* Telegram bot listener: long-poll ``getUpdates`` and
  execute every callback locally (``telegram.callback_worker.handle_callback``).
* Offer a ``SCAN NOW`` button / ``/scan`` command.
* Optionally repeat the discovery scan every N hours while running.
* Optionally run the Gmail pass on the same loop.

A job is surfaced as *new* exactly once for the life of the state database:
:meth:`SqliteStore.known_job_keys` covers everything ever shown, skipped, saved,
prepared or applied. AI-backed actions use :class:`ClaudeCliProvider` (the
signed-in local Claude Code CLI) - no Anthropic API key.

GitHub Actions is not involved in this runtime.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from intelligence.provider import get_intelligence_provider
from orchestrator.pipeline import (
    build_candidates,
    fetch_all_sources,
    load_sources_config,
)
from orchestrator.policies import load_evidence, load_preferences
from state.store import SqliteStore
from telegram.bot import TelegramBot
from telegram.callback_worker import handle_callback
from telegram.cards import live_status_card, scan_now_button

_FIRST_SCAN_DONE = "live_first_scan_done"
_LAST_SCAN_AT = "live_last_scan_at"
_OFFSET_KEY = "telegram_callback_offset"

_GMAIL_INTERVAL_SECONDS = 600
_POLL_TIMEOUT_SECONDS = 25


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def live_scan(
    store: SqliteStore,
    bot: TelegramBot,
    scan_provider: Any,
    *,
    window_hours: int,
    limit: int | None = None,
) -> dict[str, Any]:
    """One discovery pass. Only job keys never seen before are scored, persisted
    and pushed to Telegram."""
    preferences = load_preferences()
    evidence = load_evidence()
    sources_config = load_sources_config()

    raw, source_results = fetch_all_sources(sources_config, limit)
    candidates, counts = build_candidates(
        raw, preferences, evidence, sources_config, max_age_hours=window_hours
    )

    known = store.known_job_keys()
    unseen = [c for c in candidates if c.job_key not in known]

    evaluated = scan_provider.evaluate_jobs(unseen, evidence)
    store.persist(evaluated)
    notified = bot.send_candidates(evaluated)

    store.set_runtime(_LAST_SCAN_AT, _now_iso())
    store.append_event(
        "live_scan",
        None,
        {
            "window_hours": window_hours,
            "fetched": len(raw),
            "eligible": len(candidates),
            "new": len(unseen),
            "notified": len(notified),
        },
    )
    return {
        "window_hours": window_hours,
        "fetched": len(raw),
        "eligible_after_filters": len(candidates),
        "new_jobs": len(unseen),
        "notified": notified,
        "source_errors": [r.model_dump() for r in source_results if r.errors],
        "counts": counts,
    }


class LiveAgent:
    def __init__(
        self,
        store: SqliteStore,
        bot: TelegramBot,
        *,
        scan_provider: Any,
        action_provider: Any,
        scan_interval_hours: float = 2.0,
        first_window_days: int = 7,
        scan_window_hours: int = 12,
        gmail: bool = True,
        limit: int | None = None,
    ) -> None:
        self.store = store
        self.bot = bot
        self.scan_provider = scan_provider
        self.action_provider = action_provider
        self.scan_interval = max(0.0, scan_interval_hours) * 3600
        self.first_window_days = first_window_days
        self.scan_window_hours = scan_window_hours
        self.gmail = gmail
        self.limit = limit

        self._stop = False
        self._scans = 0
        self._new_jobs_total = 0
        self._last_scan_monotonic = 0.0
        self._last_gmail_monotonic = 0.0

    # -- lifecycle ---------------------------------------------------------
    def run(self) -> None:
        if not self.bot.configured:
            raise SystemExit("Telegram is not configured (.env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID). Live mode needs it.")

        ai_mode = "local Claude Code CLI" if getattr(self.action_provider, "is_live", False) else "mock (deterministic)"
        if getattr(self.action_provider, "is_live", False) and not getattr(self.action_provider, "available", True):
            self.bot._try_send(
                "⚠️ 'claude' CLI not found on PATH - PREPARE/RESUME/EMAIL/LINKEDIN will fail until it is "
                "installed and signed in. Everything else works.",
                None,
            )
            ai_mode = "unavailable (claude CLI missing)"

        self.bot._try_send(
            "🟢 CAREER AGENT — LIVE\n\n"
            f"AI actions: {ai_mode}\n"
            f"Auto scan: {'every %g h' % (self.scan_interval / 3600) if self.scan_interval else 'off'}\n"
            f"Gmail watch: {'on' if self.gmail else 'off'}\n\n"
            "I'm the only Telegram listener now. Running the first scan…",
            scan_now_button(),
        )

        self._run_scan("startup")

        print("live: entering poll loop (Ctrl+C to stop)", flush=True)
        while not self._stop:
            try:
                self._poll_once()
            except KeyboardInterrupt:
                break
            except Exception as exc:  # noqa: BLE001 - keep the process alive
                print(f"live loop error: {type(exc).__name__}: {exc}", flush=True)
                time.sleep(5)
            self._maybe_scheduled_scan()
            self._maybe_gmail()

        self.bot._try_send("🔴 Career Agent live process stopped.", None)
        print("live: stopped", flush=True)

    # -- scanning --------------------------------------------------------
    def _window_hours(self) -> int:
        first = self.store.get_runtime(_FIRST_SCAN_DONE) != "1"
        return self.first_window_days * 24 if first else self.scan_window_hours

    def _run_scan(self, trigger: str) -> None:
        window = self._window_hours()
        label = f"{self.first_window_days}d" if window == self.first_window_days * 24 else f"{window}h"
        print(f"live: scan ({trigger}, window {label})", flush=True)
        try:
            result = live_scan(
                self.store, self.bot, self.scan_provider, window_hours=window, limit=self.limit
            )
        except Exception as exc:  # noqa: BLE001
            self.bot._try_send(f"⚠️ Scan failed ({trigger}): {type(exc).__name__}: {exc}", scan_now_button())
            print(f"live: scan failed: {exc}", flush=True)
            return

        self.store.set_runtime(_FIRST_SCAN_DONE, "1")
        self._scans += 1
        self._new_jobs_total += result["new_jobs"]
        self._last_scan_monotonic = time.monotonic()

        lines = [
            f"🔍 Scan done · {trigger}",
            f"window: last {label}",
            f"fetched {result['fetched']} · {result['eligible_after_filters']} eligible · {result['new_jobs']} new",
            f"cards sent: {len(result['notified'])}",
        ]
        if result["source_errors"]:
            srcs = ", ".join(e["source"] for e in result["source_errors"])
            lines.append(f"⚠️ source errors: {srcs}")
        if not result["new_jobs"]:
            lines.append("(nothing new — you're caught up)")
        self.bot._try_send("\n".join(lines), scan_now_button())

    def _maybe_scheduled_scan(self) -> None:
        if not self.scan_interval:
            return
        if time.monotonic() - self._last_scan_monotonic >= self.scan_interval:
            self._run_scan("scheduled")

    # -- gmail ----------------------------------------------------------
    def _maybe_gmail(self) -> None:
        if not self.gmail:
            return
        if time.monotonic() - self._last_gmail_monotonic < _GMAIL_INTERVAL_SECONDS:
            return
        self._last_gmail_monotonic = time.monotonic()
        try:
            from gmail.watcher import run_once as gmail_run_once

            status = gmail_run_once(provider=self.action_provider)
            if status.get("status") == "ok" and status.get("processed"):
                print(f"live: gmail processed {status['processed']}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"live: gmail pass failed: {type(exc).__name__}: {exc}", flush=True)

    # -- telegram -----------------------------------------------------
    def _poll_once(self) -> None:
        stored = self.store.get_runtime(_OFFSET_KEY)
        offset = int(stored) if stored and stored.lstrip("-").isdigit() else None
        try:
            response = self.bot.get_updates(offset, timeout=_POLL_TIMEOUT_SECONDS)
        except Exception as exc:  # noqa: BLE001 - transient network / 409 conflict
            print(f"live: getUpdates failed: {type(exc).__name__}: {exc}", flush=True)
            time.sleep(10)
            return

        for update in response.get("result", []):
            self.store.set_runtime(_OFFSET_KEY, str(update["update_id"] + 1))
            callback = update.get("callback_query")
            message = update.get("message")
            if callback:
                self._handle_callback(callback)
            elif message:
                self._handle_message(message)

    def _handle_callback(self, callback: dict[str, Any]) -> None:
        data = callback.get("data", "")
        if data == "scan:now":
            self.bot.answer_callback_query(callback["id"], "Scanning now…")
            self._run_scan("SCAN NOW button")
            return
        try:
            result = handle_callback(data, callback["id"], self.bot, self.store, self.action_provider)
            print(f"live: callback {data} -> {result}", flush=True)
        except Exception as exc:  # noqa: BLE001 - one bad press must not kill the loop
            print(f"live: callback {data} failed: {type(exc).__name__}: {exc}", flush=True)
            self.bot._try_send(f"⚠️ That action failed: {type(exc).__name__}: {exc}", None)

    def _handle_message(self, message: dict[str, Any]) -> None:
        text = (message.get("text") or "").strip().lower()
        if text in {"/scan", "scan", "/scannow", "scan now"}:
            self._run_scan("/scan command")
        elif text in {"/status", "status"}:
            self._send_status()
        elif text in {"/start", "/help", "help"}:
            self.bot._try_send(
                "Career Agent live commands:\n"
                "/scan — run a discovery scan now\n"
                "/status — show live status\n\n"
                "Everything else is the buttons on the job cards.",
                scan_now_button(),
            )

    def _send_status(self) -> None:
        last = self.store.get_runtime(_LAST_SCAN_AT) or "never"
        if self.scan_interval and self._last_scan_monotonic:
            secs = max(0, int(self.scan_interval - (time.monotonic() - self._last_scan_monotonic)))
            nxt = f"in ~{secs // 60} min"
        else:
            nxt = "manual only"
        ai_mode = "local Claude CLI" if getattr(self.action_provider, "is_live", False) else "mock"
        self.bot._try_send(
            live_status_card(
                scans=self._scans,
                new_jobs=self._new_jobs_total,
                last_scan=last,
                next_scan=nxt,
                ai_mode=ai_mode,
                gmail="on" if self.gmail else "off",
            ),
            scan_now_button(),
        )


def run_live(args: Any) -> None:
    from orchestrator.pipeline import ROOT

    store = SqliteStore(ROOT / "state")
    bot = TelegramBot()

    scan_provider = get_intelligence_provider("mock")
    action_provider: Any = get_intelligence_provider("mock" if args.ai == "mock" else "claude_cli")

    agent = LiveAgent(
        store,
        bot,
        scan_provider=scan_provider,
        action_provider=action_provider,
        scan_interval_hours=args.scan_interval,
        first_window_days=args.first_window_days,
        scan_window_hours=args.scan_window_hours,
        gmail=not args.no_gmail,
        limit=args.limit,
    )
    agent.run()
