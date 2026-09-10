# Career Ops — pinned Apify actors as a normal source (Option B)

`sources/career_ops.py` calls one or more **explicitly pinned** Apify actors over
the REST API and feeds their results into the same pipeline as Greenhouse / Lever
/ Ashby: dedupe → conservative filters → score → Telegram card. Claude is not in
the discovery loop. `run_agent.py live` (and `scan`, `cloud`) pick it up
automatically.

## Activating it

1. **Get an Apify API token** — apify.com → Settings → Integrations → API tokens.
   This is an Apify token, not an LLM key.
2. Put it in `.env`:
   ```
   APIFY_TOKEN=apify_api_xxx
   ```
3. In `config/sources.yaml`, under `sources.career_ops`, set `enabled: true`.
4. Accept the cost and the target site's Terms of Service yourself — Naukri's ToS
   prohibits automated access; you are choosing to run this.

Disabled by default, and a missing `APIFY_TOKEN` also disables it (with a logged
note) — the scan still runs on the ATS sources.

## Configuration (`config/sources.yaml`)

```yaml
career_ops:
  enabled: true
  monthly_cost_cap_usd: 15      # hard stop once the rolling monthly estimate hits this
  timeout_seconds: 240
  actors:
    - id: fervent_bus~naukri-job-scraper-mcp   # owner~name (slash also accepted)
      adapter: naukri            # naukri | generic  (output field mapping)
      source: naukri             # becomes Job.source -> stable key "naukri:<id>"
      enabled: true
      price_per_1000_usd: 5.0    # from the actor's pricing page; used for the spend estimate
      max_items: 25              # cap per search; also sent as Apify ?maxItems=
      input:                     # base actor input, merged under each search
        maxResults: 25
      searches:                  # one Apify run per entry
        - { searchQuery: "AI Engineer", location: "" }
        - { searchQuery: "Machine Learning Engineer", location: "" }
        - { searchQuery: "Data Engineer", location: "" }
        - { searchQuery: "LLM Engineer", location: "" }
```

### Pinned actor: `fervent_bus~naukri-job-scraper-mcp`

- Input: `searchQuery` (string), `location` (string, empty = all India), `maxResults` (int).
- Output per job: `jobId, title, companyName, salary, experienceMin, experienceMax,
  location, skills, jobDescription, jobUrl, scrapedAt`.
- Pricing: pay-per-event, ~$5.00 / 1,000 results (re-verify in the Apify console).
- The actor returns `scrapedAt`, not the posting date, so `Job.posted_at` is left
  unknown — freshness falls back to "unknown" (kept, with a warning) and the
  stable job key stops repeat notifications.

## Cost control

- `max_items` caps each search and is sent to Apify as `?maxItems=` so billing is
  bounded even if the actor ignores its own input.
- After each run, `results × price_per_1000_usd / 1000` is added to a rolling
  monthly counter in the `runtime` table (`apify_spend_YYYY-MM`).
- Before each search, if `spent_so_far + worst_case_next_run > monthly_cost_cap_usd`
  the remaining searches are skipped and an entry is added to `source.errors`
  (surfaced in the scan summary).
- Worst case with the config above: 4 searches × 25 items × $5/1000 = **$0.50 per
  full scan**. At the default 2-hourly `live` cadence that is ~$6/day if every run
  is full — the `$15` monthly cap will trip quickly, so tune `max_items`, the
  number of searches, or raise the cap deliberately.

## First run

Naukri has no posting date, so the first scan after enabling can surface up to
`searches × max_items` new cards at once. Start with one search and
`max_items: 10`, confirm the data quality, then widen.

## Adding a LinkedIn actor

Add another entry to `actors:` with the reviewed actor id, `adapter: generic`
(or a new adapter), `source: linkedin`, its price and `max_items`. The `generic`
adapter maps common field names (`title/jobTitle`, `company/companyName`,
`url/jobUrl/link`, `location`, `description/descriptionText`, `postedAt/postedDate`).
Use `field_map: { <job_field>: <raw_key> }` to override any single field.
