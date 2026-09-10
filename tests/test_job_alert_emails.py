from __future__ import annotations

from sources.job_alert_emails import (
    alert_provider,
    jobs_from_alert,
    jobs_from_indeed_alert,
    jobs_from_instahyre_alert,
    jobs_from_linkedin_alert,
)

LINKEDIN_HTML = """
<div>
  <a href="https://www.linkedin.com/comm/jobs/view/3901234567/?trk=alert">Machine Learning Engineer</a>
  <span>Acme AI · Bengaluru, India</span>
  <a href="https://www.linkedin.com/comm/jobs/view/3901234567/?trk=dup">Machine Learning Engineer</a>
  <a href="https://www.linkedin.com/comm/jobs/view/3907654321/">Data Engineer</a>
</div>
"""

INDEED_HTML = """
<a href="https://www.indeed.com/rc/clk?jk=a1b2c3d4e5f6&from=alert">Senior AI Engineer</a>
<a href="https://www.indeed.com/pagead/clk?jk=a1b2c3d4e5f6">Apply now</a>
"""

INSTAHYRE_HTML = '<a href="https://www.instahyre.com/job/44567/ml-engineer-acme?utm=alert">ML Engineer at Acme</a>'


def test_linkedin_alert_parser_dedupes_by_job_id():
    jobs = jobs_from_linkedin_alert(LINKEDIN_HTML)
    assert {j.source_job_id for j in jobs} == {"3901234567", "3907654321"}
    assert all(j.source == "linkedin" for j in jobs)
    assert jobs[0].url == "https://www.linkedin.com/jobs/view/3901234567/"


def test_indeed_alert_parser_skips_apply_buttons():
    jobs = jobs_from_indeed_alert(INDEED_HTML)
    assert len(jobs) == 1
    assert jobs[0].source_job_id == "a1b2c3d4e5f6"
    assert jobs[0].url == "https://www.indeed.com/viewjob?jk=a1b2c3d4e5f6"


def test_instahyre_alert_parser():
    jobs = jobs_from_instahyre_alert(INSTAHYRE_HTML)
    assert len(jobs) == 1
    assert jobs[0].source == "instahyre"
    assert jobs[0].source_job_id == "44567"


def test_alert_provider_routing():
    assert alert_provider("LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>", "3 new jobs for you") == "linkedin"
    assert alert_provider("alert@indeed.com", "new jobs") == "indeed"
    assert alert_provider("noreply@instahyre.com", "Job matches") == "instahyre"
    assert alert_provider("recruiter@acme.com", "Following up") is None


def test_jobs_from_alert_dispatch():
    provider, jobs = jobs_from_alert("jobalerts-noreply@linkedin.com", "jobs for you", LINKEDIN_HTML, "")
    assert provider == "linkedin"
    assert len(jobs) == 2
