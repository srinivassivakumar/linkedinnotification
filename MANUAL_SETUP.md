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

## 5. Run it

**Preferred: cloud, no device online.** See **`CLOUD_SETUP.md`** — push to a
private GitHub repo, add 5 secrets, and `.github/workflows/agent.yml` runs
`run_agent.py cloud` every 3 h (scan + Gmail pass + drain Telegram approvals +
commit state back). Your phone is just the Telegram approval screen.

**Local alternative (laptop stays on):**

- `python run_agent.py workers` — Gmail watcher + Telegram callback worker,
  supervised (real-time approvals).
- Or `python run_agent.py once` from Windows Task Scheduler every 2–4 h.

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
  parses HTML **and** plain-text links, scores them, sends a Telegram card with
  an OPEN / APPLY ON NAUKRI link for **manual** action), or run:
  ```powershell
  python run_agent.py naukri --url "<naukri job url>" --title "..." --company "..." --location "Pune" --description "<paste JD>" [--dry-run]
  ```
- Never: login/browser automation, auto-apply, CAPTCHA handling, bot evasion,
  automated Naukri messaging, or scraping Naukri pages. None of that is in the
  code and it must not be added.

---

## 8a. Interview invites and calendar

- When the Gmail watcher classifies a mail as `interview_invite` it:
  extracts a date/time if the email states one, generates
  `artifacts/generated/<company>/<role>/interview_prep.md` (company brief marked
  `NEEDS_CONFIRMATION`, JD→evidence matrix, STAR stories from the evidence bank
  only, 30-min revision plan, questions to ask, thank-you draft), records an
  `interview_prep_ready` event, and sends a Telegram card.
- **Calendar events are never created automatically.** The card tells you a
  proposal exists; approve it and a Google Calendar event is added via the
  connector as an explicit step.

---

## 8b. Apify

- `artifacts/apify_actor_review.md` is a **discovery-only** review of candidate
  actors for Indeed India, Naukri, Foundit, Hirist, Cutshort, Instahyre,
  Wellfound (sourced from public web search — the Apify plugin was not connected
  to the session).
- Before enabling anything: open the actor in the Apify console, verify
  id/schema/pricing/ToS, run once with `maxItems` 5–10, then pin it. Nothing is
  scheduled. Naukri and any login-walled portal stay off without explicit approval.

---

## 9. LinkedIn — what stays manual

Sending connection requests and messages is always manual. The agent only:
parses the acceptance email, infers the company, checks your jobs table for a
match, drafts a message, and shows it in Telegram with an OPEN LINKEDIN button.
Pressing APPROVE marks it approved — it does **not** send anything.

---

## What is still stubbed (needs a later build, not a manual step)

- `sources/career_ops.py` — disabled boundary (see 7.3).
- Apify actors — reviewed but not wired in or scheduled (see 8b).
- Asana / Airtable sync — design only, in `docs/asana_airtable_design.md`; approve
  one to have it built behind an env flag.
- Follow-up timing engine (day 0/4/9 cadence) — not built.
- Human-path research beyond LinkedIn-connection cross-linking — not built.
- Calendar event creation is deliberately manual/approval-only, not stubbed.
