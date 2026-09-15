# Session context (2026-09-15) — read this first in a new chat

This file exists so a fresh Claude Code session in this repo can pick up
exactly where the last one left off, without re-deriving everything from
scratch. It's a snapshot, not a permanent doc — update or delete it once
its content is stale.

## What this project is

A deterministic job-hunt orchestrator (`run_agent.py`) with Claude as the
reasoning layer, Telegram as the human-approval layer, a Gmail watcher, and
LinkedIn connection cross-linking. Full architecture rules live in
`CLAUDE.md` — read that first, it's the constitution (no LinkedIn
scraping/automation, no paid API keys, Claude only reasons over verified
evidence, etc.). This file is just "what happened last session" on top of
that.

## Current live status (as of last session)

- **Telegram bot**: `@SriCarrierAgent_bot`, token in `.env` (gitignored).
  Chat id `1107164988`. **Do not confuse this with a chat called "Sri
  Networking Assistant"** — that's a dead, unrelated leftover bot from an
  earlier setup; nothing listens to it.
- **Gmail OAuth**: `secrets/credentials.json` + `secrets/token.json`
  (both gitignored), read-only scope, against the GCP project
  `linkedin-ai-assistan`. Re-run `python -m gmail.auth` if the token ever
  expires/revokes.
- **`CLAUDE_MODE=mock`** in `.env` (deterministic scoring — per
  `CLAUDE.md` this stays `mock` until a manual audit). The Telegram
  button actions (PREPARE/RESUME/EMAIL/LINKEDIN) use a *different* path:
  `ClaudeCliProvider`, which shells out to the signed-in local `claude`
  CLI (no API key) — that's what actually writes tailored resumes/emails.
- **Launch command** (what was running at end of last session):
  ```
  python run_agent.py live --scan-interval 12 --first-window-days 7 --scan-window-hours 12
  ```
  or just `.\start.ps1`. This is a long-running foreground process — if
  the terminal that launched it closed, it's not running anymore and
  needs restarting. Check with `Get-Process python` and by whether
  `@SriCarrierAgent_bot` responds to `/status`.
- The important-to-know secrets (Telegram token, Gmail OAuth files) live
  ONLY on this machine now, at `D:\portfolio\autoupload`. An earlier copy
  at `E:\sri\X-Pent-Dev\ClaudeJob` was lost (deleted, not in Recycle Bin)
  before this session — that's what triggered redoing this setup from
  scratch. If asked to "find the old credentials," they no longer exist;
  regenerate, don't search.

## What got fixed/built last session (10 commits, all on `claudeautomation`)

Real bugs found and fixed (not hypothetical — each was reproduced and
re-verified against real data before committing):

1. **Dedupe bug** (`orchestrator/dedupe.py`): `gh_jid` was wrongly treated
   as a strippable tracking param, collapsing every distinct posting on a
   Greenhouse board shaped like `.../jobs/search?gh_jid=X` (e.g. Stripe)
   into one "duplicate." Fixed.
2. **Flaky test fixture** (`tests/test_claude_provider.py`): hardcoded
   `posted_at` dates went stale as wall-clock time passed the 7-day
   freshness window. Now shifted relative to a fixture anchor.
3. **Gmail only scanned page 1** (`gmail/watcher.py`): `list_messages`
   never paginated past 25/100 messages. Now pages via `nextPageToken`
   up to `GMAIL_MAX_RESULTS` (default 500).
4. **Telegram buttons silently doing nothing** (`telegram/bot.py`): a
   stale `answerCallbackQuery` ack (Telegram rejects it once a callback
   query goes stale) raised and aborted the *real* action that was
   supposed to follow it. Now best-effort/non-fatal.
5. **Scans blocked the whole bot** (`orchestrator/live.py`): `SCAN NOW`
   and the Gmail pass ran synchronously inside the single poll loop, so
   any other button press queued behind a multi-minute scan and often
   went stale before it could be answered. Both now run on background
   threads with a single-flight lock.
6. **No real people/emails on FIND PEOPLE** (`linkedin/people_search.py`,
   new file): added a DuckDuckGo (`ddgs`) public-search-based finder —
   never scrapes/logs into LinkedIn itself, matching the
   `linkedin-ai-assistant` predecessor's technique. Also guesses likely
   emails via common name+domain patterns, always labelled unverified.
   Took three follow-up fixes to get reliable:
   - dropped the exact-phrase job title from the query (was
     over-constraining it to zero results),
   - removed the literal term `"HR"` from the role OR-group (it broke
     DuckDuckGo's query parsing outright),
   - added a duckduckgo/bing/brave backend fallback since the free
     scraper occasionally rate-limits and returns garbage for a
     perfectly valid query.
7. **Claude drafts came out in the JD's language** (`intelligence/claude.py`):
   a French job posting produced a French LinkedIn/email draft because no
   system prompt specified an output language. Added an explicit English
   instruction to every prompt.
8. **`sendDocument` + buttons = 400 error** (`telegram/bot.py`): multipart
   form fields aren't auto-JSON-serialized like `json=...` is — passing
   `reply_markup` as a raw dict there made Telegram reject the request.
   This silently broke EMAIL DRAFT and LINKEDIN DRAFT specifically (the
   two draft types that attach buttons). Fixed by `json.dumps`-ing it
   first.
9. **UX change** (`telegram/callback_worker.py`, `telegram/cards.py`): JD,
   why-score, resume, recruiter-email, and LinkedIn/referral drafts are
   now delivered as tap-to-open Telegram documents instead of long chat
   messages — closer to the "open a page, press back to return to chat"
   feel the user wanted, with zero new hosting (Telegram's own document
   viewer does this natively).

All 123 tests pass (`pytest -q`) after every change above. Each fix was
verified against the *real* Telegram API and/or real job data, not just
unit tests — several of these bugs (query flakiness, sendDocument 400,
gh_jid collapsing real jobs) only showed up against real data.

## Known limitations (by design, not bugs — don't "fix" these without asking)

- LinkedIn people search is public-web-search-based, not scraped from
  LinkedIn itself, and results are genuinely unverified — always
  presented that way in the card. This is intentional per `CLAUDE.md`'s
  "LinkedIn automation stays manual" rule (LinkedIn bans accounts for
  scraping/automation, even read-only).
- Guessed emails are pattern guesses (`first.last@domain` etc.), not
  looked-up/confirmed addresses. There is no paid email-finder API in
  this project and `CLAUDE.md` forbids adding one.
- `career_ops` (Apify-based Naukri/LinkedIn discovery) stays disabled
  until a specific actor is manually reviewed and pinned — see
  `docs/CAREER_OPS_APIFY.md` / `artifacts/apify_actor_review.md`.
- `adzuna` source is unconfigured (no `ADZUNA_APP_ID`/`ADZUNA_APP_KEY`) —
  shows up as a harmless `source_errors` entry on every scan; ignore
  unless the user wants that free-tier source turned on.

## Not yet pushed as of writing this file

10 commits ahead of `origin/claudeautomation`, about to be pushed. If
they're already on GitHub by the time you read this, this file is stale
on that point — check `git log --oneline origin/claudeautomation..HEAD`.

`state/career_agent.db` had local uncommitted changes (from running scans/
Gmail passes during the session) — check `git status` before assuming the
working tree is clean.
