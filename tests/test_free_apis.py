from __future__ import annotations

from orchestrator import pipeline
from sources.free_apis import ArbeitnowSource, RemoteOKSource, RemotiveSource


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


# ---- RemoteOK ---------------------------------------------------------------

def test_remoteok_skips_legal_header_and_filters_by_keyword():
    payload = [
        {"legal": "https://remoteok.com/legal"},
        {"id": "1", "position": "Machine Learning Engineer", "company": "Acme",
         "location": "Worldwide", "tags": ["python", "ml"], "description": "Build ML pipelines",
         "url": "https://remoteok.com/remote-jobs/1", "date": "2026-09-10T00:00:00+00:00"},
        {"id": "2", "position": "Sales Rep", "company": "Beta",
         "location": "Worldwide", "tags": ["sales"], "description": "Sell widgets",
         "url": "https://remoteok.com/remote-jobs/2", "date": "2026-09-10T00:00:00+00:00"},
    ]

    class S:
        def get(self, url, headers=None, timeout=None):
            return Resp(payload)

    src = RemoteOKSource({"enabled": True, "min_keyword_hits": 1}, session=S())
    jobs = src.fetch()
    assert len(jobs) == 1
    assert jobs[0].canonical_key == "remoteok:1"
    assert jobs[0].company == "Acme"


def test_remoteok_disabled_by_default():
    src = RemoteOKSource()
    assert src.enabled is False
    assert src.fetch() == []


# ---- Remotive -----------------------------------------------------------

def test_remotive_maps_and_filters():
    payload = {"jobs": [
        {"id": 55, "title": "AI Engineer", "company_name": "Acme",
         "candidate_required_location": "Worldwide", "url": "https://remotive.com/job/55",
         "publication_date": "2026-09-10T00:00:00", "description": "LLM RAG systems", "category": "Software Dev"},
    ]}

    class S:
        def get(self, url, params=None, headers=None, timeout=None):
            return Resp(payload)

    src = RemotiveSource({"enabled": True, "queries": ["ai"], "min_keyword_hits": 1}, session=S())
    jobs = src.fetch()
    assert len(jobs) == 1
    assert jobs[0].canonical_key == "remotive:55"
    assert jobs[0].company == "Acme"


# ---- Arbeitnow ------------------------------------------------------------

def test_arbeitnow_maps_and_filters():
    payload = {"data": [
        {"slug": "ml-engineer-acme", "title": "ML Engineer", "company_name": "Acme",
         "location": "Remote", "url": "https://arbeitnow.com/view/ml-engineer-acme",
         "created_at": 1757500800, "tags": ["python", "machine-learning"],
         "description": "PyTorch and data engineering", "remote": True, "job_types": ["Full-time"]},
    ]}

    class S:
        def get(self, url, headers=None, timeout=None):
            return Resp(payload)

    src = ArbeitnowSource({"enabled": True, "min_keyword_hits": 1}, session=S())
    jobs = src.fetch()
    assert len(jobs) == 1
    assert jobs[0].canonical_key == "arbeitnow:ml-engineer-acme"
    assert jobs[0].company == "Acme"


# ---- disabled by default + wiring -----------------------------------------

def test_free_apis_disabled_by_default():
    for cls in (RemoteOKSource, RemotiveSource, ArbeitnowSource):
        assert cls().enabled is False


def test_build_sources_includes_free_apis_when_enabled():
    cfg = {"sources": {
        "ats": {"greenhouse": {"enabled": False}, "lever": {"enabled": False}, "ashby": {"enabled": False}},
        "free_apis": {
            "remoteok": {"enabled": True},
            "remotive": {"enabled": True},
            "arbeitnow": {"enabled": True},
        },
    }}
    names = [s.name for s in pipeline.build_sources(cfg)]
    assert "remoteok" in names and "remotive" in names and "arbeitnow" in names


def test_build_sources_excludes_career_ops_apify_when_no_token(monkeypatch):
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    cfg = {"sources": {
        "ats": {"greenhouse": {"enabled": False}, "lever": {"enabled": False}, "ashby": {"enabled": False}},
        "career_ops": {"enabled": False},
    }}
    sources = pipeline.build_sources(cfg)
    career_ops = next(s for s in sources if s.name == "career_ops")
    assert career_ops.fetch() == []
