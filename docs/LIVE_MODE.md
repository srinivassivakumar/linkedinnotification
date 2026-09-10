# `python run_agent.py live` — single long-running local runtime

One process. No GitHub Actions. It is the **only** Telegram listener while it runs.

```
python run_agent.py live
```

## What it does

Job sources: Greenhouse / Lever / Ashby / **Workday** / **SmartRecruiters**
company boards, the **Adzuna** free API, the **Hacker News "Who is hiring"**
thread, and **job-alert emails** (LinkedIn / Indeed / Instahyre / Naukri, via the
Gmail watcher) — all free, see `docs/FREE_SOURCES.md`. Optionally pinned Apify
actors when `sources.career_ops.enabled` is true — see `docs/CAREER_OPS_APIFY.md`.

1. **Startup scan, immediately.** The first time this machine's state database
   ever completes a scan it looks back **7 days**; every scan after that looks
   back **12 hours** (`--first-window-days`, `--scan-window-hours`).
2. **Surfaces each job once, ever.** Every job key that has been shown, skipped,
   saved, prepared or applied is recorded in `state/career_agent.db`
   (`known_job_keys`). It is never sent as a new card again, across restarts, for
   the life of that database.
3. **Stays alive and listens.** Long-polls Telegram `getUpdates` and runs every
   button callback locally (`telegram.callback_worker.handle_callback`).
4. **AI actions use the local Claude Code CLI.** `PREPARE APPLICATION`,
   `UPDATED RESUME`, `EMAIL DRAFT`, `LINKEDIN DRAFT` shell out to `claude -p`
   (your signed-in Claude Pro subscription — no API key) and generate the full
   artifact-factory output (`fit_report.md`, `evidence_matrix.md`, `resume.md`,
   `cover_letter.md`, `recruiter_email.txt`, `referral_message.txt`,
   `linkedin_message.txt`, `application_answers.md`, `application_notes.md`)
   under `artifacts/generated/<company>/<role>/`.
5. **SCAN NOW.** Every scan summary and the startup message carry a `🔄 SCAN NOW`
   button. `/scan` and `/status` also work as chat commands.
6. **Auto rescan.** Every 2 hours while running (`--scan-interval 0` disables).
7. **Gmail.** The read-only Gmail pass runs on the same loop every ~10 min if
   `secrets/credentials.json` + `secrets/token.json` exist (`--no-gmail` skips).

## Options

| flag | default | meaning |
|---|---|---|
| `--ai local\|mock` | `local` | `local` = Claude Code CLI for the four AI actions; `mock` = deterministic placeholders |
| `--scan-interval H` | `2.0` | hours between automatic rescans; `0` = manual only |
| `--first-window-days N` | `7` | look-back for the very first scan |
| `--scan-window-hours N` | `12` | look-back for every scan after the first |
| `--no-gmail` | off | don't run the Gmail pass |
| `--limit N` | — | cap jobs fetched per source (debugging) |

Optional env: `CLAUDE_CLI_MODEL=claude-opus-5` pins the model the CLI uses for
tailoring; `CLAUDE_CLI_TIMEOUT` (seconds, default 300) bounds each call.

## Requirements

- `.env` with `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` (live mode exits without them).
- `claude` on `PATH`, signed in (`claude` once, interactively). If it is missing,
  live mode still runs — only the four AI actions fail, with a clear message.

## One listener only

A Telegram bot allows a single `getUpdates` poller. Before starting live mode,
stop anything else that polls the same bot:

- the GitHub Actions **Career Agent - Callbacks** workflow (disable it in the
  repo's Actions tab, or delete `.github/workflows/callbacks.yml`);
- any local `run_agent.py telegram` / `workers` / old `linkedin-ai-assistant` worker.

The cloud **Cloud Tick** workflow can stay (it only scans + drains on a
schedule), but if you run live full-time it is redundant — the local process
covers scanning, callbacks and Gmail.

## Stopping

`Ctrl+C`. State is on disk (`state/career_agent.db`), so the next start resumes
the same "seen" set and the 12-hour window.
