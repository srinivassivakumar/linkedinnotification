from __future__ import annotations

import pytest

from orchestrator.models import Candidate
from orchestrator.policies import load_evidence, load_preferences
from orchestrator.scorer import score_job
from sources.naukri import job_from_manual, jobs_from_alert_email
from telegram.cards import naukri_buttons, naukri_card

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


def test_jobs_from_alert_email_extracts_plain_text_links() -> None:
    jobs = jobs_from_alert_email(
        "Recommended role: https://www.naukri.com/job-listings-ai-engineer-acme-pune-123?src=mail"
    )
    assert len(jobs) == 1
    assert jobs[0].source == "naukri"
    assert jobs[0].title.startswith("Ai Engineer")
    assert "?" not in jobs[0].url


def test_alert_email_dedupes_anchor_and_text_forms() -> None:
    same = "https://www.naukri.com/job-listings-mle-acme-123"
    html = f'<a href="{same}?x=1">MLE</a> and again {same}?y=2'
    jobs = jobs_from_alert_email(html)
    assert len(jobs) == 1


def _naukri_candidate() -> Candidate:
    job = job_from_manual(
        "https://www.naukri.com/job-listings-ml-engineer-acme-123",
        title="ML Engineer",
        company="Acme",
        description="Python, MLOps, Docker, AWS, FastAPI, LLM, RAG " * 20,
        location="Pune",
    )
    return Candidate(job=job, score=score_job(job, load_preferences(), load_evidence()))


def test_naukri_card_is_manual_only() -> None:
    candidate = _naukri_candidate()
    text = naukri_card(candidate)
    assert "NAUKRI" in text and "Manual only" in text
    flat = [b for row in naukri_buttons(candidate)["inline_keyboard"] for b in row]
    labels = " ".join(b["text"] for b in flat)
    assert "OPEN / APPLY ON NAUKRI" in labels
    assert "PREPARE" not in labels  # no automation / auto-apply affordance
    # the OPEN button is a plain URL link, not a callback action
    open_btn = next(b for b in flat if "OPEN" in b["text"])
    assert open_btn["url"].startswith("https://www.naukri.com/")
