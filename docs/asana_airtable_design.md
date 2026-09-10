# Asana + Airtable — proposed design (NOT implemented)

Both connectors are optional. SQLite (`state/career_agent.db`) stays the single
source of truth. Nothing below is built; no connector writes happen until you
approve a specific one. These are mirrors/views on top of the existing pipeline.

## Guardrails

- One-way by default: SQLite → Asana/Airtable. The agent does not read task state
  back as pipeline input.
- Writes are batched at the end of a scan/watch cycle, idempotent by external key
  (job_key / application id / event id), and gated behind an env flag
  (`ASANA_SYNC=1`, `AIRTABLE_SYNC=1`) that defaults off.
- No PII beyond what is already in SQLite. Recruiter names/emails only if you
  opt in per-field.
- A sync failure is logged and never breaks the scan.

## Asana — task tracker for the things a human must do

**Why:** the agent produces work items (review P0 job, follow up on day 4, prep
for interview). Asana is a better surface than Telegram for tracking those over days.

**Project:** `Career Agent` with sections: `P0 Review`, `Applications`,
`Follow-ups`, `Interviews`, `Done`.

| Trigger (SQLite event) | Asana task | Fields |
|---|---|---|
| `job_discovered` with priority P0 | "Review P0: {company} — {title}" in `P0 Review` | notes = fit reason + job URL; due = +2 days |
| `application_prepared` | "Submit: {company} — {title}" in `Applications` | notes = artifact dir path; due = +1 day |
| `email_classified` type `recruiter_reply` | "Reply to recruiter: {company}" in `Follow-ups` | due = +1 day |
| `interview_prep_ready` | "Interview: {company} — {role}" in `Interviews` | notes = prep pack path; due = interview datetime if known |
| follow-up cadence (day 0/4/9) | "Follow up: {contact/company}" in `Follow-ups` | due = computed date |

**Write surface:** `create_task`, `update_task` (status → Done when SQLite marks
the application submitted / thread closed). Store the returned `asana_gid` in a
new `state` table column so updates are idempotent.

**Read surface (optional, later):** poll task completion to mark an application
`submitted` in SQLite — only if you want Asana to be the control surface.

## Airtable — reporting mirror + conversion analytics

**Why:** Airtable is a good read/reporting layer (filtered views, charts) over the
jobs/applications/events that SQLite holds transactionally.

**Base:** `Career Agent` with tables mirroring SQLite:

| Airtable table | Source | Key | Columns |
|---|---|---|---|
| `Jobs` | `jobs` | `job_key` | company, title, location, url, pre_score, bucket, priority, claude_verdict, status, first_seen_at |
| `Applications` | `applications` | `id` | job_key (link), status, artifact_dir, created_at, updated_at |
| `Events` | `events` | `event_id` | type, job_key (link), created_at, payload summary |
| `Connections` | `connections` | `id` | name, company, person_type, matched_job_key (link), status |

**Views:** `P0 pipeline`, `Applied — awaiting reply`, `This week`,
`Conversion funnel` (discovered → P0 → applied → reply → interview).

**Write surface:** upsert by key each cycle (`list records → patch or create`).
Rate-limit aware (5 req/s). One batch per cycle.

**Metrics the mirror enables** (from the build guide section 27): P0 jobs/week,
P0→application, application→reply, application→interview, source conversion,
freshness conversion.

## Implementation plan (when approved)

1. Add `integrations/asana.py` + `integrations/airtable.py`, each a thin
   idempotent upsert client using the connector, no-op when its env flag is off.
2. Add `asana_gid` / `airtable_record_id` columns to the relevant SQLite tables.
3. Call `sync_all(store)` at the end of `run_pipeline` and `gmail.watcher.run_once`,
   wrapped so failures only log.
4. Tests with a fake connector client (no live calls in CI).

Approve one (`Asana` or `Airtable`) and I will implement just that one behind its
flag.
