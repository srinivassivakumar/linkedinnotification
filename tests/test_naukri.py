from __future__ import annotations

import pytest

from sources.naukri import job_from_manual, jobs_from_alert_email

ALERT = """
<html><body>
<a href="https://www.naukri.com/job-listings-ml-engineer-acme-pune-123?src=alert">ML Engineer - Acme (Pune)</a>
<a href="https://www.naukri.com/job-listings-data-engineer-contoso-456">Data Engineer - Contoso</a>
<a href="https://www.linkedin.com/jobs/view/999">unrelated</a>
</body></html>
"""


def test_job_from_manual_requires_naukri_url() -> None:
    with pytest.raises(ValueError):
        job_from_manual("https://linkedin.com/jobs/1", "X", "Y")
    job = job_from_manual(
        "https://www.naukri.com/job-listings-mle-acme-123",
        title="ML Engineer",
        company="Acme",
        description="Python, MLOps",
        location="Pune",
    )
    assert job.source == "naukri"
    assert job.company == "Acme"
    assert job.url.startswith("https://www.naukri.com/")


def test_jobs_from_alert_email_extracts_only_naukri_links() -> None:
    jobs = jobs_from_alert_email(ALERT)
    assert len(jobs) == 2
    assert all(j.source == "naukri" for j in jobs)
    assert "naukri.com" in jobs[0].url and "?" not in jobs[0].url
