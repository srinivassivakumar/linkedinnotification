# Career Ops — pinned Apify actors as a normal source (Option B)

`sources/career_ops.py` calls one or more **explicitly pinned** Apify actors over
the REST API and feeds their results into the same pipeline as Greenhouse / Lever
/ Ashby: dedupe → conservative filters → score → Telegram card. Claude is not in
the discovery loop. `run_agent.py live` (and `scan`, `cloud`) pick it up
automatically.

## Status (2026-09-11)

| Portal | Actor | State |
|---|---|---|
| Naukri | `muhammetakkurtt~naukri-job-scraper` | **live** — ~$0.26/run for 50 jobs, one run per 48 h |
| Naukri | `fervent_bus~naukri-job-scraper-mcp` | abandoned — runs but its page parser returns 0 jobs |
| LinkedIn | — | not added; needs an actor review + sign-off |

## Activating / changing it

1. **Apify API token** — console.apify.com → Settings → API & Integrations →
   copy a Personal API token. Put it in `.env`:
   ```
   APIFY_TOKEN=apify_api_xxx
   ```
   This is an Apify token, not an LLM key.
2. `config/sources.yaml` → `sources.career_ops.enabled: true` (already set).
3. You are choosing to run a scraper against Naukri — that is your ToS / cost call.

Disabled by default; a missing `APIFY_TOKEN` also disables it (logged) and the
scan still runs on the ATS sources.

## Configuration (`config/sources.yaml`)

```yaml
career_ops:
  enabled: true
  monthly_cost_cap_usd: 4.0        # backstop; free Apify plan self-limits at ~$5
  timeout_seconds: 300
  actors:
    - id: muhammetakkurtt~naukri-job-scraper
      adapter: naukri_muhammetakkurtt   # naukri_muhammetakkurtt | naukri_fervent_bus | generic
      source: naukri                     # -> Job.source -> stable key "naukri:<jobId>"
      enabled: true
      min_interval_hours: 48             # at most one run per this window, regardless of scan cadence
      max_charge_usd: 1.0                # -> Apify ?maxTotalChargeUsd (this actor's minimum is $0.50)
      est_charge_per_run_usd: 0.35       # used for the monthly spend estimate (observed ~$0.26)
      input:                             # base actor input, merged under each search
        maxJobs: 50                      # this actor's minimum
        freshness: "15"                  # Naukri "last 15 days"
        sortBy: date
      searches:                          # one Apify run per entry
        - { keyword: "AI Engineer" }
        # - { keyword: "Machine Learning Engineer" }   # each keyword = another ~$0.3 run
```

### `muhammetakkurtt~naukri-job-scraper`

- Input: `keyword` (string), `maxJobs` (int, **≥ 50**), `freshness` (`"all"`,
  `"1"`, `"3"`, `"7"`, `"15"`, `"30"`), `sortBy` (`relevance` | `date`),
  `experience`, `cities` (Naukri numeric ids — leave unset, filter by location
  downstream).
- Output mapped: `jobId → naukri:<id>`, `title`, `companyName`, `location`,
  `jobDescription` (HTML → text), `createdDate → posted_at`, `experienceText`,
  `salary`, `footerPlaceholderLabel`. The job URL is built as
  `https://www.naukri.com/job-listings-<jobId>`.
- Pricing: pay-per-event, ~$0.26 per 50-job run (re-verify in the console).

## Cost control

Free Apify plan = ~$5/month usage credit. Each Naukri run is ~$0.26.

- **`min_interval_hours`** — the actor's last run time is stored in the `runtime`
  table (`apify_last_run_<actor-id>`); a scan inside that window skips the actor
  with a note in the scan summary. This is what stops a 2-hourly `live` loop from
  running the scraper 12×/day.
- **`monthly_cost_cap_usd`** — `est_charge_per_run_usd` is added to a rolling
  monthly counter (`apify_spend_YYYY-MM`); once `spent + next-run > cap` the
  remaining searches skip.
- **`max_charge_usd`** — sent to Apify as `maxTotalChargeUsd` so Apify caps the
  bill itself. For pay-per-result actors set `max_items` instead (sent as
  `maxItems`).

With the shipped config (1 keyword, 48 h interval): ~15 runs/month ≈ **$4–5** —
right at the free-tier ceiling. Add keywords or shorten the interval only after
upgrading the Apify plan or accepting the spend.

## First run

Naukri "AI Engineer" search is loose (returns .NET / BI / analyst roles too), so
of ~50 raw jobs roughly 10–12 survive the India-location + role-family filters,
with ~4 landing in strong/review. Watch the first `live` scan summary, then widen
`searches` if the yield is good.

## Adding a LinkedIn actor

Add another entry under `actors:` with the reviewed actor id, `adapter: generic`
(or a new adapter in `sources/career_ops.py`), `source: linkedin`, its cost knobs
(`max_charge_usd` or `max_items`, `min_interval_hours`), and `field_map:
{ <job_field>: <raw_key> }` for any field the generic adapter does not guess
(`title/jobTitle`, `company/companyName`, `url/jobUrl/link`, `location`,
`description/descriptionText`, `postedAt/postedDate/createdDate`).
