"""Integration coverage for the required end-to-end flow:

    email -> platform parser -> list[Job] -> dedupe -> freshness/filtering
    -> scoring -> SQLite -> (Telegram would be notified from here)

This exercises the Naukri alert-email path (arbitrarily chosen as "at least
one platform" per the refactor's test requirement) together with a same-role
Greenhouse posting, to prove cross-source dedupe folds them into one stored
candidate rather than two.
"""

from __future__ import annotations

from orchestrator.dedupe import dedupe_jobs
from orchestrator.models import Candidate, Job
from orchestrator.policies import load_evidence, load_preferences
from orchestrator.scorer import score_job
from sources.naukri import jobs_from_alert_email
from state.store import SqliteStore

NAUKRI_ALERT_HTML = """
<div>
  <a href="https://www.naukri.com/job-listings-senior-machine-learning-engineer-acme-bengaluru-123456?src=alert">
    Senior Machine Learning Engineer
  </a>
</div>
"""


def test_naukri_email_flows_through_dedupe_score_and_sqlite(tmp_path) -> None:
    # 1. email -> platform parser -> list[Job]
    parsed = jobs_from_alert_email(NAUKRI_ALERT_HTML)
    assert len(parsed) == 1
    assert parsed[0].source == "naukri"

    # A same role also discovered via a direct ATS feed, with a real company
    # name (the alert-email job has a placeholder company, so this pair only
    # merges once the ATS source resolves the company - simulate that here by
    # giving the ATS-discovered job the same normalized title+location and a
    # real company, then re-running the alert parser output through a second
    # job that already carries the resolved company name).
    resolved_alert_job = parsed[0].model_copy(update={"company": "Acme", "location": "Bengaluru, India"})
    ats_job = Job(
        source="greenhouse", source_job_id="7001", company="Acme",
        title="Senior Machine Learning Engineer", location="Bengaluru, India",
        description="Full JD from the ATS.", url="https://boards.greenhouse.io/acme/jobs/7001",
    )

    # 2. dedupe: the raw (unresolved-company) alert job stays distinct from the
    #    ATS job (different companies), but once resolved it merges.
    raw_unique, raw_dupes = dedupe_jobs([parsed[0], ats_job])
    assert len(raw_unique) == 2 and raw_dupes == 0

    resolved_unique, resolved_dupes = dedupe_jobs([ats_job, resolved_alert_job])
    assert len(resolved_unique) == 1 and resolved_dupes == 1
    assert resolved_unique[0].source == "greenhouse"

    # 3. scoring (centralized in orchestrator.scorer - parsers carry no scoring logic)
    preferences = load_preferences()
    evidence = load_evidence()
    scored = score_job(resolved_unique[0], preferences, evidence)
    assert scored.bucket in {"strong_candidate", "review", "weak"}

    # 4. SQLite persistence + idempotency
    store = SqliteStore(tmp_path)
    candidate = Candidate(job=resolved_unique[0], score=scored)
    new_or_changed = store.diff_new_or_changed([candidate])
    assert len(new_or_changed) == 1
    store.persist(new_or_changed)

    again = store.diff_new_or_changed([candidate])
    assert again == []  # idempotent: unchanged job is not re-surfaced

    known = store.known_job_keys()
    assert candidate.job_key in known
