# Apify Actor Review — discovery only

**Status: DISCOVERY, NOT APPROVED. No actor here has been run, scheduled, or
wired into the pipeline.**

The Apify plugin/MCP is **not connected to this Claude Code session** (`claude mcp
list` shows Airtable, Asana, Google Drive, Google Calendar, Gmail — no Apify;
`claude plugin list` shows none). The candidate actors below were found via public
web search of `apify.com/store`. Actor ids, pricing, input schemas and output
fields **must be re-verified inside the Apify console / Apify MCP** before any run.

## Decision gate (do all of this before enabling any actor)

1. Open the actor in the Apify console. Confirm it still exists and is maintained.
2. Read its README + input schema + example output. Record the real fields.
3. Check pricing (rental vs pay-per-result vs pay-per-event) and set a hard
   `maxItems` + monthly cost cap.
4. Check the target site's Terms of Service. **Naukri and LinkedIn ToS prohibit
   automated scraping** — do not proceed on those without explicit legal comfort.
   LinkedIn is out of scope by project rule regardless.
5. Run once manually with a tiny `maxItems` (5–10) and inspect the output.
6. Only then pin `{actor_id, input_schema, field_map, maxItems, cost_cap}` in a
   Career Ops `portals.yml` entry and let the deterministic scanner consume it.

## Portal-by-portal candidates (UNVERIFIED)

### Indeed India — priority P0
| Field | Notes |
|---|---|
| Candidate actors | `misceres/indeed-scraper` (~$0.05/1k, cheapest), `curious_coder/indeed-scraper` ($20/mo + ~$0.73/1k), `factden/indeed-jobs-scraper` ($2/1k, $5 starter credit), `automation-lab/indeed-scraper` ($0.003/listing + $0.005/run) |
| Collects | job title, company, location, salary (when shown), posted date, JD text, job URL |
| Input schema (verify) | search query / job title, location ("India" or city), country=IN, maxItems, date-posted filter |
| Output fields (verify) | title, company, location, salary, description, url, postedAt |
| Pricing / cost risk | Low–moderate. Prefer pay-per-result; cap `maxItems` at 50–100/run. |
| ToS / compliance risk | Moderate. Indeed discourages scraping; use low volume, no login, respect robots. |
| maxItems recommendation | 50 per run, 2–4 runs/day max |
| Test recommendation | Run `misceres/indeed-scraper` with maxItems=5, query "AI Engineer", location "Pune"; inspect field_map |

### Naukri — priority P0 (⚠ ToS risk)
| Field | Notes |
|---|---|
| Candidate actors | `memo23/naukri-scraper` (from ~$0.6/1k), `easyapi/naukri-jobs-scraper`, `logiover/naukri-job-scraper` ("no login or browser"), `bovi/naukri-jobs-scraper` (PPE), `sian.agency/naukri-jobs-scraper` |
| Collects | job id, title, company, location, experience range, salary (if disclosed), skills, posted date, JD snippet, job URL |
| Input schema (verify) | keyword, location, experience, maxItems |
| Output fields (verify) | jobId, title, company, location, experienceRange, salary, skills[], postedDate, url, description |
| Pricing / cost risk | Low ($0.6/1k typical). Cap `maxItems` at 25. |
| ToS / compliance risk | **HIGH — Naukri ToS prohibits automated access.** Do not enable without explicit approval and legal comfort. Project rule already forbids Naukri automation; discovery only. |
| maxItems recommendation | 25 per run *if ever approved* |
| Test recommendation | **Do not test-run yet.** Only inspect schema/pricing in the console. |

### Foundit (ex-Monster India) — priority P1
| Field | Notes |
|---|---|
| Candidate actors | Covered by multi-portal India actors (see below); no strong dedicated actor confirmed in search |
| Collects | title, company, location, experience, JD, url |
| Pricing / cost risk | Unknown — verify |
| ToS / compliance risk | Moderate–high; verify Foundit ToS |
| maxItems recommendation | 25 per run |
| Test recommendation | Inspect the multi-portal actor's Foundit coverage first |

### Hirist — priority P1
| Field | Notes |
|---|---|
| Candidate actors | dedicated "Hirist Jobs Scraper" (per search: full JD HTML+text, mandatory/optional skills, AmbitionBox rating, salary, applies/views, recruiter info) — verify id/author in console |
| Collects | title, company, skills (mandatory/optional), salary, JD, recruiter info, WFH flag |
| Pricing / cost risk | Unknown — verify |
| ToS / compliance risk | Moderate; verify Hirist ToS |
| maxItems recommendation | 25 per run |
| Test recommendation | maxItems=5, tech keyword; check recruiter-info fields aren't PII-risky to store |

### Cutshort — priority P1
| Field | Notes |
|---|---|
| Candidate actors | Only via multi-portal India actors in search results; no strong dedicated actor confirmed |
| Collects | startup/product roles, title, company, skills, location |
| Pricing / cost risk | Unknown — verify |
| ToS / compliance risk | Moderate; Cutshort is login-walled for much content — a compliant actor may be limited |
| maxItems recommendation | 25 per run |
| Test recommendation | Verify whether the actor needs login (reject if it does) |

### Instahyre — priority P1
| Field | Notes |
|---|---|
| Candidate actors | `getascraper/instahyre-jobs-scraper`, `automation-lab/instahyre-jobs-scraper` |
| Collects | title, skills, city, apply URL, company profile; "only-new" tracking; filter by skill/city/company/size |
| Input schema (verify) | skills, city, company, size, onlyNew, maxItems |
| Output fields (verify) | title, skills[], city, applyUrl, companyProfile |
| Pricing / cost risk | Unknown — verify; likely pay-per-result |
| ToS / compliance risk | Moderate–high; Instahyre is heavily login-walled — verify the actor is compliant and not credential-based |
| maxItems recommendation | 25 per run |
| Test recommendation | maxItems=5; confirm no login/credentials in input schema |

### Wellfound (ex-AngelList Talent) — priority P1
| Field | Notes |
|---|---|
| Candidate actors | `igolaizola/wellfound-jobs-scraper` ($0.5/1k), `orgupdate/wellfound-jobs-scraper`, `xtracto/wellfound-jobs-scraper`, `radeance/wellfound-job-listings-scraper` |
| Collects | title, company, remote status, compensation, equity, company funding, posted date, job URL |
| Input schema (verify) | role, location, company URL, remote filter, maxItems |
| Output fields (verify) | title, company, remote, compensation, equity, postedAt, url |
| Pricing / cost risk | Low ($0.5/1k). Cap `maxItems` at 50. |
| ToS / compliance risk | Moderate; Wellfound ToS restricts scraping — low volume, no login |
| maxItems recommendation | 50 per run |
| Test recommendation | `igolaizola/wellfound-jobs-scraper`, maxItems=5, role "Machine Learning Engineer", remote India |

## Multi-portal option (verify carefully)

Search surfaced an aggregated "India job-market data" actor claiming coverage of
Naukri, Indeed India, Foundit, Shine, Apna, CutShort, Hirist, Instahyre,
Internshala (+ LinkedIn candidate sourcing — **do not use that part**). If real
and compliant it could replace several single-portal actors, but the LinkedIn
component and the Naukri ToS problem make it higher-risk. Inspect before trusting.

## Recommendation

- **Enable at most one actor first: `misceres/indeed-scraper` for Indeed India**
  (cheapest, lowest ToS risk of the P0 set), behind a pinned config with
  `maxItems=50` and a monthly cost cap.
- **Wellfound** (`igolaizola/wellfound-jobs-scraper`) as the second.
- **Do not enable Naukri or any login-walled portal actor** without explicit
  written approval; project rules already forbid Naukri automation.
- Nothing is scheduled until you approve a specific reviewed actor.

## Sources (web search, 2026-09-10 — verify in the Apify console)

- https://apify.com/muhammetakkurtt/naukri-job-scraper
- https://apify.com/epicscrapers/naukri-scraper
- https://apify.com/valig/naukri-jobs-scraper
- https://apify.com/easyapi/naukri-jobs-scraper
- https://apify.com/bovi/naukri-jobs-scraper
- https://apify.com/sian.agency/naukri-jobs-scraper
- https://apify.com/logiover/naukri-job-scraper
- https://apify.com/memo23/naukri-scraper
- https://apify.com/misceres/indeed-scraper
- https://apify.com/curious_coder/indeed-scraper
- https://apify.com/factden/indeed-jobs-scraper
- https://apify.com/automation-lab/indeed-scraper
- https://apify.com/valig/indeed-jobs-scraper
- https://apify.com/radeance/wellfound-job-listings-scraper
- https://apify.com/igolaizola/wellfound-jobs-scraper
- https://apify.com/orgupdate/wellfound-jobs-scraper
- https://apify.com/xtracto/wellfound-jobs-scraper
- https://apify.com/getascraper/instahyre-jobs-scraper
- https://apify.com/automation-lab/instahyre-jobs-scraper
