# Career Agent

One integrated job-hunt automation project, built from
`Claude_Job_Hunt_Automation_Build_Guide_Revised_Connector_First.pdf` and merged
with the `linkedinnotification` codebase.

- **Deterministic orchestrator** — Greenhouse / Lever / Ashby ATS adapters, a
  common `Job` model, conservative dedupe / freshness / location / seniority /
  role-family filtering, an explainable pre-score, idempotent runs.
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

## Boundary

Career Ops and Apify are not wired in (connector/review tasks — see
`MANUAL_SETUP.md` §7). LinkedIn sending/scraping/browser automation and Naukri
automation are out of scope by policy. Interview prep and the follow-up cadence
engine are stubs.
