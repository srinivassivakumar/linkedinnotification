from __future__ import annotations

from orchestrator.dedupe import dedupe_jobs, normalize_url
from orchestrator.models import Job


def test_normalize_url_removes_tracking_params() -> None:
    assert normalize_url("HTTPS://Example.com/jobs/1/?utm_source=x&keep=y") == "https://example.com/jobs/1?keep=y"


def test_dedupe_same_source_id_url_and_fingerprint() -> None:
    jobs = [
        Job(source="greenhouse", source_job_id="1", company="Acme", title="DevOps Engineer", location="Pune", description="same", url="https://x.test/a"),
        Job(source="greenhouse", source_job_id="1", company="Acme", title="DevOps Engineer", location="Pune", description="same", url="https://x.test/b"),
        Job(source="lever", source_job_id="2", company="Acme", title="DevOps Engineer", location="Pune", description="same", url="https://x.test/a?utm_source=y"),
        Job(source="ashby", source_job_id="3", company="Other", title="Cloud Engineer", location="Pune", description="different", url="https://x.test/c"),
    ]
    unique, duplicates = dedupe_jobs(jobs)
    assert [job.canonical_key for job in unique] == ["greenhouse:1", "ashby:3"]
    assert duplicates == 2


def test_dedupe_merges_cross_source_via_company_title_location_fallback() -> None:
    """Same role discovered via a direct ATS fetch and a LinkedIn alert email
    (different source ids, different URLs, different description snippets)
    must merge on normalized company+title+location."""
    jobs = [
        Job(source="greenhouse", source_job_id="900", company="Acme Corp", title="Senior ML Engineer",
            location="Bengaluru, India", description="Full JD text from Greenhouse...",
            url="https://boards.greenhouse.io/acme/jobs/900"),
        Job(source="linkedin", source_job_id="778899", company="Acme Corp", title="Senior ML Engineer",
            location="Bengaluru, India", description="short alert-email snippet",
            url="https://www.linkedin.com/jobs/view/778899/"),
    ]
    unique, duplicates = dedupe_jobs(jobs)
    assert len(unique) == 1
    assert duplicates == 1
    assert unique[0].source == "greenhouse"  # first-seen wins


def test_dedupe_does_not_merge_different_roles_at_same_company() -> None:
    jobs = [
        Job(source="greenhouse", source_job_id="1", company="Acme", title="Backend Engineer", location="Pune", url="https://x.test/a"),
        Job(source="lever", source_job_id="2", company="Acme", title="Frontend Engineer", location="Pune", url="https://x.test/b"),
    ]
    unique, duplicates = dedupe_jobs(jobs)
    assert len(unique) == 2
    assert duplicates == 0


def test_dedupe_placeholder_company_never_merges_on_fallback() -> None:
    """Alert-email jobs stuck with a '(from X alert - confirm)' placeholder
    company must never fingerprint-merge with each other or with a real job
    that happens to share a title."""
    jobs = [
        Job(source="linkedin", source_job_id="1", company="(from LinkedIn alert - confirm)",
            title="Data Engineer", location=None, url="https://www.linkedin.com/jobs/view/1/"),
        Job(source="indeed", source_job_id="2", company="(from Indeed alert - confirm)",
            title="Data Engineer", location=None, url="https://www.indeed.com/viewjob?jk=2"),
    ]
    unique, duplicates = dedupe_jobs(jobs)
    assert len(unique) == 2
    assert duplicates == 0

