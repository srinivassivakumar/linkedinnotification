from __future__ import annotations

import json

import pytest

from orchestrator import pipeline
from sources.adzuna import AdzunaSource
from sources.hackernews import HackerNewsWhoIsHiringSource
from sources.smartrecruiters import SmartRecruitersSource
from sources.workday import WorkdaySource, parse_posted_on


class Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.ok = status < 400

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


# ---- Workday ---------------------------------------------------------------

def test_parse_posted_on():
    from datetime import datetime, timezone

    now = datetime(2026, 9, 11, tzinfo=timezone.utc)
    assert parse_posted_on("Posted Today", now).date() == now.date()
    assert (now - parse_posted_on("Posted 5 Days Ago", now)).days == 5
    assert parse_posted_on("Posted 30+ Days Ago", now) < now
    assert parse_posted_on("Posted Yesterday", now).day == 10


def test_workday_maps_postings(monkeypatch):
    listing = {"jobPostings": [
        {"title": "ML Engineer", "externalPath": "/job/India-Bengaluru/ML-Engineer_JR100",
         "locationsText": "India, Bengaluru", "postedOn": "Posted 2 Days Ago", "bulletFields": ["JR100"]},
    ]}

    def fake_post(url, **kw):
        assert url.endswith("/wday/cxs/nvidia/Site/jobs")
        return Resp(listing)

    monkeypatch.setattr("sources.workday.requests.post", fake_post)
    src = WorkdaySource([{"name": "NVIDIA", "host": "nvidia.wd5.myworkdayjobs.com",
                          "tenant": "nvidia", "site": "Site", "fetch_details": False}])
    jobs = src.fetch()
    assert len(jobs) == 1
    j = jobs[0]
    assert j.source == "workday" and j.company == "NVIDIA"
    assert j.canonical_key == "workday:JR100"
    assert j.location == "India, Bengaluru"
    assert j.url == "https://nvidia.wd5.myworkdayjobs.com/en-US/Site/job/India-Bengaluru/ML-Engineer_JR100"
    assert j.posted_at is not None


# ---- SmartRecruiters ------------------------------------------------------

def test_smartrecruiters_maps_postings(monkeypatch):
    listing = {"content": [
        {"id": "abc123", "name": "Data Engineer", "company": {"identifier": "Acme", "name": "Acme"},
         "location": {"city": "Bengaluru", "country": "in", "fullLocation": "Bengaluru, India"},
         "releasedDate": "2026-09-10T00:00:00.000Z", "refNumber": "R1"},
    ]}

    def fake_get(url, **kw):
        return Resp(listing) if url.endswith("/postings") else Resp({"jobAd": {"sections": {"jobDescription": {"text": "<p>Python</p>"}}}})

    monkeypatch.setattr("sources.smartrecruiters.requests.get", fake_get)
    src = SmartRecruitersSource(["Acme"])
    jobs = src.fetch()
    assert len(jobs) == 1
    assert jobs[0].canonical_key == "smartrecruiters:abc123"
    assert jobs[0].location == "Bengaluru, India"
    assert "Python" in jobs[0].description


# ---- Adzuna -------------------------------------------------------------

def test_adzuna_skips_without_credentials():
    src = AdzunaSource({"enabled": True}, app_id="", app_key="")
    assert src.fetch() == []
    assert any("ADZUNA_APP" in e for e in src.errors)


def test_adzuna_maps_results():
    class S:
        def get(self, url, params=None, timeout=None):
            return Resp({"results": [
                {"id": "77", "title": "AI Engineer", "company": {"display_name": "Acme"},
                 "location": {"display_name": "Bengaluru, Karnataka"}, "created": "2026-09-10T10:00:00Z",
                 "redirect_url": "https://www.adzuna.in/job/77", "description": "LLM RAG"},
            ]})

    src = AdzunaSource({"enabled": True, "queries": ["ai"]}, app_id="x", app_key="y", session=S())
    jobs = src.fetch()
    assert len(jobs) == 1
    assert jobs[0].canonical_key == "adzuna:77"
    assert jobs[0].company == "Acme"


# ---- Hacker News ------------------------------------------------------

def test_hackernews_keyword_gate_and_mapping(monkeypatch):
    search = {"hits": [{"objectID": "999", "title": "Ask HN: Who is hiring? (September 2026)"}]}
    item = {"children": [
        {"id": 1, "author": "a", "created_at": "2026-09-01T15:00:00Z",
         "text": "Acme | Senior ML Engineer | Remote | We use Python, PyTorch and build LLM/RAG pipelines. https://acme.example/careers"},
        {"id": 2, "author": "b", "created_at": "2026-09-01T15:01:00Z",
         "text": "Beta Corp | Sales Rep | NYC | selling widgets"},  # no keywords -> dropped
    ]}

    def fake_get(url, **kw):
        return Resp(search) if "search_by_date" in url else Resp(item)

    monkeypatch.setattr("sources.hackernews.requests.get", fake_get)
    src = HackerNewsWhoIsHiringSource({"min_keyword_hits": 2})
    jobs = src.fetch()
    assert len(jobs) == 1
    assert jobs[0].source == "hackernews"
    assert jobs[0].canonical_key == "hackernews:1"
    assert jobs[0].company == "Acme"
    assert jobs[0].url == "https://acme.example/careers"


# ---- wiring -----------------------------------------------------------

def test_build_sources_includes_free_sources():
    cfg = {"sources": {
        "ats": {
            "greenhouse": {"enabled": False},
            "lever": {"enabled": False},
            "ashby": {"enabled": False},
            "workday": {"enabled": True, "companies": [{"name": "X", "host": "x", "tenant": "x", "site": "x"}]},
        },
        "hackernews": {"enabled": True},
        "adzuna": {"enabled": True},
    }}
    names = [s.name for s in pipeline.build_sources(cfg)]
    assert "workday" in names and "hackernews" in names and "adzuna" in names
