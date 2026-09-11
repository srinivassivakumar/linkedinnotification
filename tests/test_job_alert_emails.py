from __future__ import annotations

from sources.job_alert_emails import (
    alert_provider,
    jobs_from_alert,
    jobs_from_cutshort_alert,
    jobs_from_google_alert,
    jobs_from_indeed_alert,
    jobs_from_instahyre_alert,
    jobs_from_linkedin_alert,
    unwrap_google_redirect,
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

CUTSHORT_HTML = '<a href="https://cutshort.io/job/ml-engineer-acme-9f8a">ML Engineer at Acme</a>'

GOOGLE_ALERT_HTML = """
<div>
  <a href="https://www.google.com/url?q=https://boards.greenhouse.io/acme/jobs/6001122&sa=D">
    Acme is hiring: Machine Learning Engineer - Bengaluru
  </a>
  <a href="https://www.google.com/url?q=https://jobs.lever.co/beta/1e2d3c4b-5a69-7f80-9c1d-2e3f4a5b6c7d&sa=D">
    Beta Corp Data Engineer
  </a>
  <a href="https://www.google.com/url?q=https://blog.example.com/we-are-hiring&sa=D">
    Example Blog: We're hiring!
  </a>
</div>
"""


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
    assert alert_provider("noreply@cutshort.io", "New matches for you") == "cutshort"
    assert alert_provider("googlealerts-noreply@google.com", "Google Alert - AI Engineer") == "google_alerts"
    assert alert_provider("recruiter@acme.com", "Following up") is None


def test_jobs_from_alert_dispatch():
    provider, jobs = jobs_from_alert("jobalerts-noreply@linkedin.com", "jobs for you", LINKEDIN_HTML, "")
    assert provider == "linkedin"
    assert len(jobs) == 2


def test_cutshort_alert_parser():
    jobs = jobs_from_cutshort_alert(CUTSHORT_HTML)
    assert len(jobs) == 1
    assert jobs[0].source == "cutshort"
    assert jobs[0].source_job_id == "ml-engineer-acme-9f8a"
    assert jobs[0].url == "https://cutshort.io/job/ml-engineer-acme-9f8a"


def test_unwrap_google_redirect():
    wrapped = "https://www.google.com/url?q=https://boards.greenhouse.io/acme/jobs/6001122&sa=D"
    assert unwrap_google_redirect(wrapped) == "https://boards.greenhouse.io/acme/jobs/6001122"
    # non-redirect links pass through unchanged
    plain = "https://example.com/careers"
    assert unwrap_google_redirect(plain) == plain


def test_google_alert_only_keeps_recognized_ats_links():
    jobs = jobs_from_google_alert(GOOGLE_ALERT_HTML)
    # the blog link is dropped; only the two ATS-recognized links survive
    assert len(jobs) == 2
    by_source = {j.source: j for j in jobs}
    assert by_source["greenhouse"].source_job_id == "6001122"
    assert by_source["greenhouse"].company == "Acme"
    assert by_source["greenhouse"].url == "https://boards.greenhouse.io/acme/jobs/6001122"
    assert by_source["lever"].source_job_id == "1e2d3c4b-5a69-7f80-9c1d-2e3f4a5b6c7d"
    assert by_source["lever"].company == "Beta"


def test_jobs_from_alert_dispatch_google_alerts():
    provider, jobs = jobs_from_alert("googlealerts-noreply@google.com", "Google Alert - AI Engineer", GOOGLE_ALERT_HTML, "")
    assert provider == "google_alerts"
    assert len(jobs) == 2
