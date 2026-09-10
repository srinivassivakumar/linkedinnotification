from __future__ import annotations

from linkedin.connections import guess_company
from linkedin.email_parser import parse_acceptance_email

SAMPLE = """
<html><body>
<p>Priya Sharma</p>
<p>Senior ML Engineer at Acme Cloud</p>
<p>India</p>
<a href="https://www.linkedin.com/comm/in/priya-sharma-1234">View profile</a>
<a href="https://www.linkedin.com/comm/messaging/compose/?connId=987">Message</a>
</body></html>
"""


def test_parse_acceptance_email_extracts_core_fields() -> None:
    parsed = parse_acceptance_email(SAMPLE, "Priya Sharma via LinkedIn")
    assert parsed["name"] == "Priya Sharma"
    assert parsed["headline"] == "Senior ML Engineer at Acme Cloud"
    assert parsed["location"] == "India"
    assert parsed["linkedin_profile_url"] == "https://www.linkedin.com/in/priya-sharma-1234"
    assert parsed["linkedin_message_url"].endswith("connId=987")


def test_own_profile_link_is_ignored() -> None:
    html = '<a href="https://www.linkedin.com/comm/in/srinivas-s-abc">me</a>'
    parsed = parse_acceptance_email(html, "Someone Else")
    assert parsed["linkedin_profile_url"] is None


def test_guess_company() -> None:
    assert guess_company("Senior ML Engineer at Acme Cloud") == "Acme Cloud"
    assert guess_company("Data Scientist @ Contoso | Ex-Google") == "Contoso"
    assert guess_company("Freelance consultant") is None
