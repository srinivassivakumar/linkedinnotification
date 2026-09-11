# Career Agent

One integrated job-hunt automation project, built from
`Claude_Job_Hunt_Automation_Build_Guide_Revised_Connector_First.pdf` and merged
with the `linkedinnotification` codebase.

- **Deterministic orchestrator** — Greenhouse / Lever / Ashby / Workday /
  SmartRecruiters ATS adapters, free job APIs (RemoteOK / Remotive / Arbeitnow /
  Hacker News "Who is hiring"), Gmail job-alert-email parsers (LinkedIn / Indeed /
  Naukri / Instahyre / Cutshort / Google Alerts), a common `Job` model,
  cross-source dedupe, conservative freshness / location / seniority /
  role-family filtering, an explainable pre-score, idempotent runs. All of this
  runs at **₹0/month** — Apify (paid) is optional and off by default.
- **Claude reasoning layer** (`IntelligenceProvider`) — `evaluate_jobs` (serious
  candidates only, strict structured output, evidence-grounded),
  `classify_reply`, `tailor_application` (P0-gated), `research_connection`.
  `MockProvider` runs until `CLAUDE_MODE=claude` after a manual audit. Auth is the
  `ant auth login` subscription — no API key.
- **Telegram** — candidate + ops-console cards, and a callback worker that turns
  inline buttons into idempotent state changes (PREPARE / SKIP / WHY / JD /
  HUMAN PATH / APPROVE). Nothing is ever sent on your behalf.
- **Gmail watcher** — background loop (read-only scope) that routes LinkedIn
  "accepted" mails to connection cross-linking, and recruiter / ATS / Naukri mail
  to the Claude classifier, with `processed_emails` idempotency.
- **LinkedIn** — parse the acceptance email, infer the company, match against your
  jobs table, draft a message, card it for manual sending.
- **SQLite** (`state/career_agent.db`) — single source of truth: jobs,
  applications, events, contacts, connections, processed emails.

## Setup

```powershell
cd E:\sri\X-Pent-Dev\ClaudeJob
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
ant auth login            # Claude via your Anthropic subscription
```

See **`MANUAL_SETUP.md`** for the full checklist (job sources, evidence bank
audit, turning Claude on, running the workers, optional connectors).

## Commands

```powershell
python run_agent.py scan --dry-run --limit 5          # smoke test, no sends
python run_agent.py scan                              # real scan -> Telegram
python run_agent.py once                              # one scan + one Gmail pass (for Task Scheduler)
python run_agent.py workers                           # Gmail + Telegram workers, supervised
python -m orchestrator.main --mode dashboard-test --fixture tests/fixtures/golden_jobs.json
pytest -q
```

## Job discovery — sources

Job discovery is entirely free by default. Every source below produces the same
`orchestrator.models.Job` record (`orchestrator/pipeline.py::build_sources`
wires them all in), which then flows through one pipeline:

```
email / feed -> platform parser or ATS/API client -> list[Job]
             -> dedupe (orchestrator/dedupe.py)
             -> freshness + location/seniority/role-family filters
             -> scoring (orchestrator/scorer.py)
             -> SQLite (state/career_agent.db)
             -> Telegram card (human approves everything from here)
```

Parsers and API clients never score or filter — that stays centralized in
`orchestrator/scorer.py` / `orchestrator/policies.py` so every source is judged
the same way.

### 1. Direct ATS feeds (`config/sources.yaml` → `sources.ats`)

Official, public, keyless JSON APIs per company — no scraping:

| ATS | Adapter | Needs |
|---|---|---|
| Greenhouse | `sources/greenhouse.py` | board tokens (`boards.greenhouse.io/<token>`) |
| Lever | `sources/lever.py` | company slugs (`jobs.lever.co/<slug>`) |
| Ashby | `sources/ashby.py` | org slugs (`jobs.ashbyhq.com/<slug>`) |
| Workday | `sources/workday.py` | `{host, tenant, site}` from the careers URL |
| SmartRecruiters | `sources/smartrecruiters.py` | company identifiers (`careers.smartrecruiters.com/<id>`) |

Add companies you care about under `sources.ats.<name>.boards` /
`.companies` in `config/sources.yaml`.

### 2. Free job APIs (`config/sources.yaml` → `sources.free_apis` / `sources.hackernews` / `sources.adzuna`)

| Source | Adapter | Auth |
|---|---|---|
| RemoteOK | `sources/free_apis.py::RemoteOKSource` | none |
| Remotive | `sources/free_apis.py::RemotiveSource` | none |
| Arbeitnow | `sources/free_apis.py::ArbeitnowSource` | none |
| HN "Who is hiring?" | `sources/hackernews.py` | none (free Algolia API) |
| Adzuna | `sources/adzuna.py` | free API key (`ADZUNA_APP_ID`/`ADZUNA_APP_KEY`); source is skipped (not an error) if unset |

RemoteOK / Remotive / Arbeitnow / HN are broad global feeds, so each applies a
keyword gate (`min_keyword_hits` against `keywords`/target-role terms) before a
posting becomes a `Job` — scoring itself still happens centrally afterward.

### 3. Gmail job-alert emails (`config/sources.yaml` → `sources.email_alerts`)

You subscribe to job alerts on each platform; the platform emails you matches;
`gmail/watcher.py` (already polling your inbox read-only for other purposes)
routes recognized alert mail to a per-platform parser in
`sources/job_alert_emails.py` (and `sources/naukri.py` for Naukri). This is
not scraping — it's reading mail you asked to receive.

| Platform | Detection | Extraction |
|---|---|---|
| **LinkedIn** | sender/subject contains `linkedin.com` + `job`/`alert`/`hiring` | `<a href>` matching `linkedin.com/jobs/view/<id>`; title from link text; company/location are **not** reliably in the alert markup, so the job is carded with a `(from LinkedIn alert - confirm)` placeholder company for the operator to confirm before acting |
| **Naukri** | sender/subject contains `naukri` | `<a href>` and raw-text URLs matching `naukri.com/job(-listings)?`; title from link text (falls back to titleizing the URL slug) |
| **Indeed** | sender/subject contains `indeed.com` | `<a href>` query param `jk=`/`vjk=`; skips "Apply now"/"View job" button text |
| **Instahyre** | sender/subject contains `instahyre` | `<a href>` matching `instahyre.com/job(or opportunity)/<id>` |
| **Cutshort** | sender/subject contains `cutshort` | `<a href>` matching `cutshort.io/job/<slug>` |
| **Google Alerts** | sender is `googlealerts-noreply@google.com` (or subject says "Google Alert") | Google wraps every link as `google.com/url?q=<target>`; the parser unwraps it, then keeps **only** links that resolve to a recognized ATS posting URL (Greenhouse/Lever/Ashby/Workday/SmartRecruiters) — those are tagged with the *same* `source` name as the direct ATS adapter so dedupe merges them; everything else (news/blog links) is discarded as noise |

Every platform can be turned off independently in `config/sources.yaml` under
`sources.email_alerts.<platform>.enabled` without touching code.

**Edge cases / assumptions**: alert-email HTML changes without notice, so every
parser is best-effort — it extracts whatever is reliably present (a job URL +
title) and lets the deterministic scorer/filters do the rest downstream. When
a platform doesn't expose company/location in its alert markup, the job is
carded with an explicit `(from <platform> alert - confirm)` placeholder rather
than guessing — and the dedupe fallback tier (see below) is written to never
merge on that placeholder, so it can't falsely collapse two different roles
that merely share a title.

### 4. Apify (`config/sources.yaml` → `sources.career_ops`) — optional, paid, OFF by default

`sources/career_ops.py` remains fully implemented and wired into the pipeline,
but `career_ops.enabled: false` by default and the source returns nothing
without `APIFY_TOKEN` set — so the whole system works with **zero** paid
dependencies and no Apify account at all. Turn it on only if you deliberately
want the extra Apify-scraped coverage; `min_interval_hours` and
`monthly_cost_cap_usd` bound the spend when you do.

### Why not scrape LinkedIn directly

Direct LinkedIn scraping (login automation, browser automation, CAPTCHA
handling) is intentionally out of scope — it violates LinkedIn's Terms of
Service and risks the account behind the whole job search. LinkedIn coverage
here comes only from job-alert **emails** you already subscribed to (no
scraping) and, when the owner later wires one in, an explicitly reviewed,
opt-in Apify actor under `career_ops` (still off by default). The existing
LinkedIn **connection-acceptance** workflow (`linkedin/`) is separate from job
discovery entirely and untouched by this refactor — it parses acceptance
*emails*, the same "read mail you already receive" pattern.

## Dedupe — how cross-source merging works

`orchestrator/dedupe.py::dedupe_jobs` merges on three keys, in this order:

1. **`canonical_key`** (`source:source_job_id`) — exact match, same source
   re-fetched.
2. **Normalized URL** — tracking/redirect params stripped (`utm_*`, `trk`,
   `ref`, `gh_src`, LinkedIn/Lever affiliate params, etc.), host lower-cased,
   trailing slash trimmed. Catches the same posting reached through a
   different source or a wrapped/redirected link.
3. **Normalized company + title + location fallback** — for roles discovered
   through channels that share neither an id nor a URL (e.g. a LinkedIn alert
   email vs. the same role via a direct Greenhouse fetch). This tier
   deliberately **ignores the job description** (alert-email snippets and full
   ATS descriptions for the same posting never read identically, so matching
   on description would just fail to merge) and **never fires when the company
   is a known placeholder** (`(from <platform> alert - confirm)` /
   `(company from ... - confirm)`) — a placeholder can't safely be treated as
   equal to anything.

What it does **not** merge: two different titles at the same company, two
different companies, or anything involving a placeholder company on the
fallback tier. First-seen source wins when two Jobs merge (order = the order
sources are fetched in `build_sources`).

## Environment variables

| Variable | Required? | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Required for review cards | Telegram bot used for every human-approval card |
| `GMAIL_CREDENTIALS_JSON`/`credentials.json`, token | Required for Gmail sources | OAuth for the read-only Gmail watcher (alert emails, connection acceptances, replies) |
| `CLAUDE_MODE` | Optional (default `mock`) | `mock` = deterministic placeholders; `claude` = signed-in Claude CLI/Pro subscription |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Optional | Free Adzuna API key; Adzuna source is silently skipped (not an error) if unset |
| `APIFY_TOKEN` | **Optional — off by default** | Only used if you explicitly set `sources.career_ops.enabled: true`; the whole system runs with zero paid services if this is never set |
| `GMAIL_QUERY`, `GMAIL_MAX_RESULTS`, `GMAIL_POLL_SECONDS` | Optional | Tune the Gmail watcher's search query / batch size / poll interval |
| `AGENT_PERSIST_GIT` | Optional | `1` to have `cloud`/`drafts --deliver` commit+push state after a run |

`APIFY_TOKEN` is explicitly **optional**: RemoteOK/Remotive/Arbeitnow/HN need no
key at all, the ATS adapters need no key, and Gmail alert-email parsing needs
only the Gmail OAuth you'd set up anyway for the connection-acceptance
workflow. Confirmed working with `APIFY_TOKEN` unset and
`sources.career_ops.enabled: false` (`python run_agent.py scan --dry-run`).

## Manual setup for the new sources

- **Gmail filters/labels**: subscribe to job alerts on LinkedIn, Indeed,
  Instahyre, Cutshort, and Naukri from their own sites (Settings → Job
  alerts), and/or create a Google Alert for something like
  `site:boards.greenhouse.io "AI Engineer" India` (repeat per ATS domain you
  care about: `jobs.lever.co`, `jobs.ashbyhq.com`, `myworkdayjobs.com`,
  `jobs.smartrecruiters.com`). No Gmail filter/label is required — the watcher
  already searches recent mail by subject/sender pattern
  (`gmail/watcher.py::DEFAULT_QUERY`); a label just keeps your inbox tidy.
- **ATS company slugs**: edit `config/sources.yaml` → `sources.ats.<name>` and
  add the board tokens/company slugs/Workday host-tenant-site you want tracked
  (see the table above for where each slug comes from).
- Each email/API source can be toggled independently in
  `config/sources.yaml` without touching code (`sources.email_alerts.*`,
  `sources.free_apis.*`, `sources.hackernews`, `sources.adzuna`,
  `sources.career_ops`).

## Boundary

LinkedIn sending/scraping/browser automation and Naukri automation are out of
scope by policy — nothing in this codebase submits an application, sends a
recruiter message, or sends a LinkedIn message automatically; Telegram is
always the human review/approval step. Interview prep and the follow-up
cadence engine are stubs.
