from __future__ import annotations

from linkedin.people_search import search_people

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
