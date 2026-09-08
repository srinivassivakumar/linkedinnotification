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

