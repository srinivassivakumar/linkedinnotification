# Integration Handoff

## Career Ops
- Reference repo: `https://github.com/career-ops-hq/career-ops`
- Reference commit inspected locally: `8a20e491fdde2c928a54ff17a7bfe07ca5d2ab40`
- Current status: `sources/career_ops.py` is a disabled boundary.
- Useful Career Ops entry points found: `scan.mjs`, `prepare-application.mjs`,
  `application-artifacts.mjs`, `contacts.mjs`, `reply-watch.mjs`,
  `linkedin-join.mjs`, `jd-skill-gap.mjs`, `portals.yml`, and
  `plugins/apify/index.mjs`.
- Next step for Claude/Career Ops: decide whether this repo should call
  `node scan.mjs`, consume exported artifacts, or configure `portals.yml` with
  `provider: apify`.
- Do not invent an actor ID or a Career Ops API contract. Pin a reviewed actor/schema before production.

## linkedinnotification
- Reference repo: `https://github.com/srinivassivakumar/linkedinnotification`
- Reference commit inspected locally: `5a6a13d8980cf565641d1d2a7e159b655a76b6c1`
- Current status: this repo implements only Telegram cards and a Gmail classifier skeleton.
- Useful existing entry points found: `worker.py`, `run_assistant.py`,
  `save_connections.py`, `telegram_callback_worker.py`,
  `linkedin_email_parser.py`, `app/services/gmail_service.py`,
  `app/services/telegram_service.py`, `app/services/connection_processor.py`,
  and `app/db.py`.
- Next step: reuse Gmail OAuth, Telegram approval callbacks,
  accepted-connection parsing, processed-message idempotency, and manual
  LinkedIn-open behavior from `linkedinnotification`.
- LinkedIn sending remains manual. Store profile URLs and prepared messages only.

## Claude
- Current status: `CLAUDE_MODE=mock` and `intelligence/claude.py` intentionally raises.
- Next step: implement only the `IntelligenceProvider` methods, starting with `evaluate_jobs`.
- Claude must consume `candidate_payload(...)`, deterministic score output, and verified evidence only.
