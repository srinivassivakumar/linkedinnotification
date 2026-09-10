# R2 / R3 Plan (post-R1)

R1 delivered `intelligence/claude.py` (`ClaudeProvider.evaluate_jobs`) with strict
structured output, an evidence-grounding gate, a serious/uncertain candidate gate,
a per-run evaluation cap, and tests. `CLAUDE_MODE` stays `mock` and
`orchestrator/pipeline.py` still hard-codes the mock provider until the sections
below are built and validated.

## Cross-cutting first step: connector inventory

No MCP servers or Claude Code plugins are currently enabled for this workspace
(`~/.claude.json` has empty `mcpServers`, no `enabledPlugins`; no `.mcp.json`).
Before R2 coding:

1. Apify plugin/MCP — **actor discovery only**. Enable via `/plugin`, authenticate
   once, then use the MCP `search-actors` / `get-actor` tools to inspect Naukri /
   Indeed / LinkedIn-adjacent actors: legality/ToS, pricing, `maxItems`, input
   schema, output fields. Do **not** run or schedule any actor. Record findings in
   `INTEGRATION_HANDOFF.md` and only then pin one actor in a Career Ops
   `portals.yml` entry.
2. Google Workspace connectors (Gmail, Calendar, Drive) — enable for interactive
   R3 email/calendar/artifact work. Background Gmail polling stays on the existing
   OAuth worker path, behind approval.
3. GitHub connector — enable only if a specific repo reference is needed
   (`career-ops-hq/career-ops`, `srinivassivakumar/linkedinnotification`).
4. Keep filesystem/shell local. Secrets, `.env` writes, email sends, paid actor
   runs and external-account actions remain approval-gated.

## R2 — Connector-fed intelligence + application factory

### R2.1 Career Ops / Apify job feed
- Implement `sources/career_ops.py` to consume Career Ops output. Decide between
  (a) `node scan.mjs` + read exported artifacts, or (b) a pinned `portals.yml`
  `provider: apify` entry. No invented actor IDs.
- Normalise Career Ops / Apify rows into the existing `Job` model. Reuse
  `dedupe_jobs`, `freshness_status`, `live_status`. Add URL/JD-hash dedupe fields.
- Config: extend `config/sources.yaml` `career_ops` block with `mode`, pinned
  `actor`, `field_map`, `max_items`, `cost_cap`.
- Tests: fixture-driven normalisation + dedupe against ATS copies.

### R2.2 Naukri (constrained)
- Allowed: parse Naukri job-alert emails and manually supplied Naukri URLs →
  `Job` model → score → artifacts → Telegram card with OPEN/APPLY link for manual
  action.
- Forbidden: browser automation, login automation, auto-apply, CAPTCHA bypass,
  bot evasion, automated Naukri messaging.
- If Apify is used for Naukri discovery: actor discovery only, no runs/schedules
  until legality/ToS, pricing, fields, `maxItems`, output schema are reviewed.

### R2.3 Wire Claude provider into the pipeline
- Replace the hard-coded `get_intelligence_provider("mock")` in
  `orchestrator/pipeline.py` with `get_intelligence_provider(os.getenv("CLAUDE_MODE", "mock"))`.
- Flip `CLAUDE_MODE=claude` only after a live run is manually audited (20 JDs,
  score ordering, evidence citations all verified).
- Add `evaluate_jobs` batching + structured-output (`output_config.format`) once
  the plain-JSON path is proven.

### R2.4 P0-only application artifact factory
- Implement `ClaudeProvider.tailor_application`: select closest base resume track
  (AI/GenAI, ML, Data, MLOps, DevOps/Cloud), build a requirement→evidence matrix,
  tailor only claims supported by `evidence_bank.yaml`, emit resume + cover +
  recruiter/referral/LinkedIn drafts.
- Gate: only run for `priority == "P0"` (or Claude `recommended_next_action ==
  act_now`). Never spend tokens on P2/archive.
- Career Ops generates the ATS PDF where available; deterministic PDF fallback
  only for gaps. Save every artifact under the company/role folder.
- Tests: every tailored claim traces to a verified evidence id; placeholder text
  never ships.

## R3 — Human path, Telegram approvals, Gmail classifier

### R3.1 Telegram approval buttons
- Extend the existing card (`telegram/cards.py` already has the keyboard scaffold)
  with a callback worker: PREPARE / SKIP / WHY / FULL JD / HUMAN PATH / APPROVE.
- Double-click / idempotency guard so one approval cannot send twice.
- Reuse callback patterns from `linkedinnotification` (`telegram_callback_worker.py`).

### R3.2 Gmail reply classifier (Claude)
- Implement `ClaudeProvider.classify_reply` returning
  `{class, company, role, confidence, recommended_action, needs_human}`.
- Classes: application_receipt, recruiter_reply, assessment, interview_invite,
  rejection, offer, unknown. Never auto-reply to offers, compensation or ambiguous
  messages — escalate to Telegram.
- Background: existing Gmail OAuth worker records the event, calls the classifier,
  updates pipeline stage, notifies Telegram. Interactive triage uses the Google
  Workspace Gmail connector with approval.
- Tests: extend `tests/test_gmail_classifier.py` with a fake Claude client.

### R3.3 Human-path research
- For every P0/P1 job, find the best legitimate route to a real person: Career Ops
  contacto first, then approved structured public research.
- Store `{company, name, role_type, title, public_profile_url, email_confidence,
  source}` plus prepared message drafts. LinkedIn connect/message stays manual.
- Cross-link accepted LinkedIn connections (from the Gmail parser) to open jobs at
  the same company to raise the human-path score.

### R3.4 Cost / permission caps
- Central config: `max_evaluations` per run (already in `ClaudeProvider`),
  `tailor` only on P0, Apify `max_items` + `cost_cap`, recruiter-email send behind
  approval, daily outreach cap, LinkedIn automation denied.
- Log token spend per run; add `P0 cost per interview` metric.

## Definition of done
- R2: a scheduled scan discovers a real fresh Pune/Remote-India role via a pinned
  connector, produces a Claude fit score with cited evidence, and a P0 role gets a
  truthful tailored package.
- R3: that role ships a Telegram card with approval buttons and a credible
  human-path contact; a simulated recruiter reply moves the pipeline stage.
