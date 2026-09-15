from __future__ import annotations

from linkedin.people_search import guess_company_domain, guess_emails, search_people

HITS = [
    {
        "title": "Aditya Samadhiya - Engineering Manager - Acme Cloud",
        "href": "https://in.linkedin.com/in/adityasamadhiya",
        "body": "We're hiring at Acme Cloud!",
    },
    {
        "title": "Acme Cloud hiring Engineering Manager - Backend",
        "href": "https://in.linkedin.com/jobs/view/engineering-manager-backend-at-acme-1234",
        "body": "Use LinkedIn Jobs to boost your chances.",
    },
    {
        "title": "Priya Sharma - Senior Recruiter - Acme Cloud",
        "href": "https://www.linkedin.com/in/priya-sharma-1234",
        "body": "Recruiter at Acme Cloud.",
    },
    {
        "title": "Aditya Samadhiya - Engineering Manager - Acme Cloud",
        "href": "https://in.linkedin.com/in/adityasamadhiya",
        "body": "duplicate of the first hit",
    },
]


def _fake_search(query, *, max_results):
    return HITS


def test_search_people_keeps_only_profile_urls_and_dedupes() -> None:
    people = search_people("Acme Cloud", "Engineering Manager", search_fn=_fake_search)
    assert [p["url"] for p in people] == [
        "https://in.linkedin.com/in/adityasamadhiya",
        "https://www.linkedin.com/in/priya-sharma-1234",
    ]
    assert people[0]["name"] == "Aditya Samadhiya"
    assert people[0]["title"] == "Engineering Manager - Acme Cloud"


def test_search_people_never_raises_on_search_failure() -> None:
    def boom(query, *, max_results):
        raise RuntimeError("blocked")

    assert search_people("Acme Cloud", search_fn=boom) == []


def test_search_people_returns_empty_without_company() -> None:
    assert search_people("", search_fn=_fake_search) == []


DOMAIN_HITS = [
    {"title": "Acme Cloud on LinkedIn", "href": "https://linkedin.com/company/acme-cloud", "body": ""},
    {"title": "Acme Cloud - Official Site", "href": "https://www.acmecloud.io/about", "body": ""},
]


def test_guess_company_domain_skips_non_company_hosts() -> None:
    domain = guess_company_domain("Acme Cloud", search_fn=lambda q, **kw: DOMAIN_HITS)
    assert domain == "acmecloud.io"


def test_guess_company_domain_blocks_subdomains_of_blocked_hosts() -> None:
    hits = [
        {"title": "Acme Cloud - Wikipedia", "href": "https://en.wikipedia.org/wiki/Acme_Cloud", "body": ""},
        {"title": "Acme Cloud - Official Site", "href": "https://www.acmecloud.io/about", "body": ""},
    ]
    assert guess_company_domain("Acme Cloud", search_fn=lambda q, **kw: hits) == "acmecloud.io"


def test_guess_company_domain_returns_none_on_failure() -> None:
    def boom(q, **kw):
        raise RuntimeError("blocked")

    assert guess_company_domain("Acme Cloud", search_fn=boom) is None


def test_guess_emails_builds_common_patterns() -> None:
    emails = guess_emails("Priya Sharma", "acmecloud.io")
    assert emails == [
        "priya.sharma@acmecloud.io",
        "priyasharma@acmecloud.io",
        "psharma@acmecloud.io",
        "priya@acmecloud.io",
    ]


def test_guess_emails_needs_a_domain_and_full_name() -> None:
    assert guess_emails("Priya Sharma", None) == []
    assert guess_emails("Priya", "acmecloud.io") == []


def test_search_people_attaches_guessed_emails() -> None:
    def fake_search(query, *, max_results):
        if "official website" in query:
            return DOMAIN_HITS
        return HITS

    people = search_people("Acme Cloud", search_fn=fake_search)
    assert people[0]["guessed_emails"][0] == "aditya.samadhiya@acmecloud.io"
