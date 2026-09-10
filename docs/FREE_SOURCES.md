# Free job sources — no key, no cost, no scraping

The scanner pulls from these in addition to Greenhouse / Lever / Ashby. All are
official APIs or your own inbox — nothing is scraped, nothing is metered past a
free tier.

| Source | Cost | Key | Config key |
|---|---|---|---|
| **Workday** (CXS JSON API) | free, unlimited | none | `sources.ats.workday` |
| **SmartRecruiters** postings API | free, unlimited | none | `sources.ats.smartrecruiters` |
| **Adzuna** API | free tier ~250 calls/mo | `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` | `sources.adzuna` |
| **Hacker News** "Who is hiring?" | free | none | `sources.hackernews` |
| **Job-alert emails** (LinkedIn / Indeed / Instahyre / Naukri) | free | none | Gmail watcher |

## Workday

Every Workday careers site exposes `POST /wday/cxs/{tenant}/{site}/jobs`. Add
companies in `config/sources.yaml`:

```yaml
sources:
  ats:
    workday:
      enabled: true
      per_company_limit: 20
      companies:
        - { name: NVIDIA, host: nvidia.wd5.myworkdayjobs.com, tenant: nvidia, site: NVIDIAExternalCareerSite, search_text: "engineer india" }
```

`host` / `tenant` / `site` are visible in the careers URL
`https://{tenant}.wdN.myworkdayjobs.com/en-US/{site}`. `search_text` narrows the
query server-side; `facets: {}` is passed through as `appliedFacets` if you work
out a tenant's location facet ids. Seeded: NVIDIA, Citi (both verified returning
India roles). Workday only gives a relative posting age ("Posted 3 Days Ago"),
mapped to an approximate date.

## SmartRecruiters

`GET /v1/companies/{identifier}/postings`. The identifier is the slug in
`careers.smartrecruiters.com/{identifier}`. Add them as a plain list:

```yaml
    smartrecruiters:
      enabled: true
      companies:
        - Bosch
        - Square
```

Seeded empty — add identifiers as you find companies you care about.

## Adzuna

Official aggregator API with a real India index. Get free credentials at
<https://developer.adzuna.com>, put them in `.env`:

```
ADZUNA_APP_ID=...
ADZUNA_APP_KEY=...
```

Disabled automatically if unset (logged, scan continues). Config sets the India
country code, `max_days_old`, and the keyword `queries`. Free tier is ~250
calls/month — one call per query per scan, so 4 queries on a 12-hourly `live`
loop ≈ 240/month. Keep the query list short.

## Hacker News "Who is hiring?"

The monthly thread, via the free Algolia API. Each top-level comment becomes a
job if it mentions ≥ `min_keyword_hits` of the relevant tech terms. Posting date
is left unknown (the thread is monthly, roles stay open all month), so the stable
key is what stops repeats. Remote / startup heavy; most months it adds little,
then a burst on the 1st.

## Job-alert emails

Set up job alerts on **LinkedIn** (Jobs → set alert), **Indeed**, **Instahyre**,
and **Naukri** with your criteria. The platforms email you matching jobs; the
Gmail watcher (`gmail/watcher.py`) parses those emails into cards — scored and
filtered like any other source. This is the only zero-cost, ToS-clean way to get
LinkedIn and Naukri: you are reading mail you subscribed to, not scraping.

Parsers live in `sources/job_alert_emails.py` (LinkedIn / Indeed / Instahyre) and
`sources/naukri.py` (Naukri). They are best-effort — alert HTML changes — and
extract the job URL + title reliably, leaving company/location to confirm on
click. The `DEFAULT_QUERY` in the watcher already matches these senders.
