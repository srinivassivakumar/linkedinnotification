# Claude / contributor guide

One integrated project: a deterministic job-hunt orchestrator with Claude as the
reasoning layer, Telegram as the approval layer, a background Gmail watcher, and
LinkedIn connection → job cross-linking. State is one SQLite database
(`state/career_agent.db`). Built per
`Claude_Job_Hunt_Automation_Build_Guide_Revised_Connector_First.pdf`.

## Architecture rules (non-negotiable)
- `IntelligenceProvider` is the only AI boundary. `MockProvider` is active until
  `CLAUDE_MODE=claude` after a manual audit.
- Claude reasons only over verified evidence (`profile/evidence_bank.yaml`) and
  job/connection snapshots. It may rephrase evidence, never invent it. Any
  evidence id it cites that is not in the bank is dropped and flagged.
- Claude evaluates only serious/uncertain candidates (bucket `strong_candidate` /
  `review`), never every raw job. Per-run cap: `CLAUDE_MAX_EVALUATIONS`.
- No paid API keys. Claude auth is the `ant auth login` subscription profile.
- SQLite is the single source of truth. Every pipeline run is idempotent
  (signature-based change detection; `processed_emails` for the inbox).
- LinkedIn sending/scraping/browser automation stays manual. Naukri: parse
  emails / manual URLs only — no login, browser automation, auto-apply, CAPTCHA
  handling, bot evasion or automated messaging.
- Apify: actor discovery only until an actor is reviewed and pinned.
- Secrets, `.env` writes, email sends, paid actor runs and external-account
  actions stay behind approval.

## Layout
- `orchestrator/` — deterministic spine (fetch, dedupe, filter, score, pipeline).
- `intelligence/` — `ClaudeProvider` (evaluate_jobs, classify_reply,
  tailor_application, research_connection) + `MockProvider`.
- `state/store.py` — `SqliteStore`, the unified state layer.
- `sources/` — ATS adapters + `career_ops` (disabled boundary) + `naukri`
  (parse-only).
- `gmail/` — `auth` (file OAuth) + `watcher` (background loop).
- `telegram/` — `bot` (API) + `cards` + `callback_worker` (approval loop).
- `linkedin/` — `email_parser` + `connections` (cross-link to jobs).
- `application/` — artifact factory (P0-gated).
- `run_agent.py` — single entry point (`scan` / `gmail` / `telegram` /
  `workers` / `once`).

## Still stubbed
- `sources/career_ops.py`, `interview/prep.py`,
  `ClaudeProvider.prepare_interview`, follow-up timing engine, deeper human-path
  research.

## Manual setup
See `MANUAL_SETUP.md`. Run `pytest -q` before every commit.
