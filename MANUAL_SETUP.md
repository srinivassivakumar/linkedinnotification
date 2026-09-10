# Manual setup — everything you must do by hand

The code is one integrated project now (deterministic orchestrator + Claude
reasoning + Telegram approval layer + Gmail watcher + LinkedIn connection
cross-linking, all on one SQLite database). Everything below is a step the code
**cannot** do for you, in order. Nothing here needs a paid API key — Claude runs
on your Anthropic subscription.

---

## 1. One-time environment

| # | Do this | How |
|---|---------|-----|
| 1.1 | Install deps | `cd E:\sri\X-Pent-Dev\ClaudeJob`; `.\.venv\Scripts\Activate.ps1`; `pip install -r requirements.txt` |
| 1.2 | Authenticate Claude to your subscription | `ant auth login` — opens a browser, stores an OAuth profile the SDK reads automatically. Verify: `ant auth status`. Do **not** set `ANTHROPIC_API_KEY`. |
| 1.3 | Confirm `.env` | Already created from `linkedin-ai-assistant` (Telegram token + chat id, `APPROVAL_SECRET`, Gmail label). It is gitignored. Nothing to add. |
| 1.4 | Confirm Gmail creds | `secrets/credentials.json` + `secrets/token.json` are already copied (gitignored). Token scope is `gmail.readonly`. If Gmail calls fail with an auth error, run `python -m gmail.auth` once to re-consent. |
| 1.5 | Smoke-test | `python -m pytest -q` (expect all green), then `python run_agent.py scan --dry-run --limit 5` (no network sends). |

---

## 2. Give the scanner real job sources

The ATS scanner returns nothing until you fill in board IDs.

- **2.1** Edit `config/sources.yaml` → `sources.greenhouse.boards`, `sources.lever.companies`,
  `sources.ashby.companies` with the real slugs of companies you want watched
  (e.g. Greenhouse board token from `boards.greenhouse.io/<token>`).
- **2.2** Run `python run_agent.py scan` and confirm jobs appear
  (`python -c "from state.store import SqliteStore; print(len(SqliteStore('state').load_latest_jobs()))"`).

---

## 3. Turn Claude on (after an audit)

Claude stays in `mock` mode until you verify it on real data.

- **3.1** Temporarily set `CLAUDE_MODE=claude` in your shell (not `.env` yet):
  `$env:CLAUDE_MODE = "claude"`.
- **3.2** Run `python run_agent.py scan` on ~20 real jobs.
- **3.3** Manually audit: score ordering sane? every `evidence_fit` line cites a
  real id from `profile/evidence_bank.yaml`? no invented skills? `gaps`/`risks`
  believable?
- **3.4** Only if it passes: set `CLAUDE_MODE=claude` in `.env`.
- **3.5** Watch cost with `CLAUDE_MAX_EVALUATIONS` (default 25 serious jobs/run).

---

## 4. Verify the evidence bank is true

`profile/evidence_bank.yaml` is the only thing standing between you and a
hallucinated resume. Read every entry. Each claim must be defensible in an
interview. Fix anything wrong; set `verified: false` on anything you can't stand behind.

---

## 5. Run the workers

Two background loops. Run them on your always-on machine (not GitHub Actions —
the SQLite state can't survive an ephemeral runner).

- **5.1** `python run_agent.py workers` — starts the Gmail watcher + Telegram
  callback worker together, restarts either if it dies.
- **5.2** Or individually: `python run_agent.py gmail` and
  `python run_agent.py telegram`.
- **5.3** For scheduled scans: **Windows Task Scheduler** → action
  `E:\sri\X-Pent-Dev\ClaudeJob\.venv\Scripts\python.exe run_agent.py once`
  every 2–4 hours. (`once` = one scan + one Gmail pass.)

---

## 6. Gmail labels / filters (recommended)

The watcher query defaults to `newer_than:3d` on interview/recruiter/LinkedIn
subjects. To make it precise and cheap:

- **6.1** In Gmail, create a filter that labels LinkedIn "accepted your
  invitation" mails and recruiter mail as `LinkedInAccepted` (or your own label).
- **6.2** Set `GMAIL_QUERY` in `.env` to something like
  `label:LinkedInAccepted newer_than:7d` if you prefer label-based selection.

---

## 7. Connectors you may add later (all optional, all gated)

These are **not** wired in. When you want them:

- **7.1 Apify** — in Claude Code run `/plugin` → install Apify → authenticate.
  Then ask Claude only to **discover** actors for Naukri/Indeed/LinkedIn-adjacent
  boards and report ToS, pricing, `maxItems`, input/output schema. **Do not run
  or schedule any actor** until you have reviewed that. Then pin one reviewed
  actor in a Career Ops `portals.yml` entry.
- **7.2 Google Workspace connector** — `/mcp` → connect Gmail/Calendar/Drive for
  interactive (in-session) email and calendar work. The background watcher keeps
  using the file-based OAuth in `secrets/`.
- **7.3 Career Ops** — clone `github.com/career-ops-hq/career-ops` locally and
  tell Claude; `sources/career_ops.py` is a disabled boundary until you decide
  between `node scan.mjs` + exported artifacts or a pinned `portals.yml`.

---

## 8. Naukri — what is allowed

- Allowed: forward Naukri job-alert emails to the watched inbox (the watcher
  parses them, scores them, sends a Telegram card with OPEN/APPLY for **manual**
  action), or hand a Naukri URL to `sources.naukri.job_from_manual(...)`.
- Never: login/browser automation, auto-apply, CAPTCHA handling, bot evasion,
  automated Naukri messaging. None of that is in the code and it must not be added.

---

## 9. LinkedIn — what stays manual

Sending connection requests and messages is always manual. The agent only:
parses the acceptance email, infers the company, checks your jobs table for a
match, drafts a message, and shows it in Telegram with an OPEN LINKEDIN button.
Pressing APPROVE marks it approved — it does **not** send anything.

---

## What is still stubbed (needs a later build, not a manual step)

- `sources/career_ops.py` — disabled boundary (see 7.3).
- `interview/prep.py` and `ClaudeProvider.prepare_interview` — R4, raise/placeholder.
- Follow-up timing engine (day 0/4/9 cadence) — not built.
- Human-path research beyond LinkedIn-connection cross-linking — not built.
