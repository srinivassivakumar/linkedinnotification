from __future__ import annotations

from sources.career_ops import CareerOpsSource
from state.store import SqliteStore


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.calls = []

    def post(self, url, params=None, json=None, timeout=None):
        self.calls.append({"url": url, "params": params, "json": json})
        return FakeResp(self._payloads.pop(0) if self._payloads else [])


NAUKRI_ITEMS = [
    {
        "jobId": "naukri-1",
        "title": "AI Engineer",
        "companyName": "Acme India",
        "location": "Bengaluru",
        "jobUrl": "https://www.naukri.com/job-listings/ai-engineer-acme-1?src=alert",
        "jobDescription": "Python, LLM, RAG, FastAPI",
        "salary": "20-30 LPA",
        "experienceMin": 2,
        "experienceMax": 5,
        "skills": ["Python", "LLM"],
        "scrapedAt": "2026-09-10T10:00:00Z",
    },
    {"title": "", "jobUrl": ""},  # malformed -> skipped
]


def _config(**over):
    cfg = {
        "enabled": True,
        "monthly_cost_cap_usd": 15,
        "actors": [
            {
                "id": "fervent_bus~naukri-job-scraper-mcp",
                "adapter": "naukri",
                "source": "naukri",
                "price_per_1000_usd": 5.0,
                "max_items": 25,
                "searches": [{"searchQuery": "AI Engineer", "location": ""}],
            }
        ],
    }
    cfg.update(over)
    return cfg


def test_disabled_returns_nothing(tmp_path):
    src = CareerOpsSource({"enabled": False}, token="x", store=SqliteStore(tmp_path / "s.db"))
    assert src.fetch() == []


def test_enabled_without_token_is_skipped_with_error(tmp_path):
    src = CareerOpsSource(_config(), token="", store=SqliteStore(tmp_path / "s.db"))
    assert src.fetch() == []
    assert any("APIFY_TOKEN" in e for e in src.errors)


def test_maps_naukri_items_to_jobs(tmp_path):
    session = FakeSession([NAUKRI_ITEMS])
    src = CareerOpsSource(_config(), token="tok", session=session, store=SqliteStore(tmp_path / "s.db"))
    jobs = src.fetch()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "naukri"
    assert job.canonical_key == "naukri:naukri-1"
    assert job.company == "Acme India"
    assert job.location == "Bengaluru"
    assert job.posted_at is None
    assert job.raw["experience"] == "2-5 yrs"
    # token is a query param, never in the body/url
    assert session.calls[0]["params"]["token"] == "tok"
    assert session.calls[0]["params"]["maxItems"] == 25
    assert "run-sync-get-dataset-items" in session.calls[0]["url"]


def test_monthly_cost_cap_stops_further_searches(tmp_path):
    store = SqliteStore(tmp_path / "s.db")
    cfg = _config(monthly_cost_cap_usd=0.01)  # any run exceeds this
    cfg["actors"][0]["searches"] = [
        {"searchQuery": "AI Engineer"},
        {"searchQuery": "Data Engineer"},
    ]
    session = FakeSession([NAUKRI_ITEMS, NAUKRI_ITEMS])
    src = CareerOpsSource(cfg, token="tok", session=session, store=store)
    jobs = src.fetch()

    assert jobs == []
    assert session.calls == []  # never even called Apify
    assert any("cost cap" in e for e in src.errors)


MUH_ITEMS = [
    {
        "jobId": "110926000001",
        "title": "AI / Machine Learning Engineer",
        "companyName": "Acme Labs",
        "location": "Hybrid - Hyderabad, Bengaluru",
        "jobDescription": "<p>Strong <strong>Python</strong> &amp; PyTorch. Build <br/>LLM pipelines.</p>",
        "createdDate": "2026-09-10 18:30:07",
        "experienceText": "3-8 Yrs",
        "minimumExperience": 3,
        "maximumExperience": 8,
        "salary": "8-18 Lacs PA",
        "footerPlaceholderLabel": "Just Now",
    }
]


def _muh_config(**over):
    cfg = {
        "enabled": True,
        "monthly_cost_cap_usd": 4.0,
        "actors": [
            {
                "id": "muhammetakkurtt~naukri-job-scraper",
                "adapter": "naukri_muhammetakkurtt",
                "source": "naukri",
                "max_charge_usd": 1.0,
                "est_charge_per_run_usd": 0.35,
                "input": {"maxJobs": 50},
                "searches": [{"keyword": "AI Engineer"}],
            }
        ],
    }
    cfg.update(over)
    return cfg


def test_muhammetakkurtt_adapter_maps_url_date_and_strips_html(tmp_path):
    session = FakeSession([MUH_ITEMS])
    src = CareerOpsSource(_muh_config(), token="tok", session=session, store=SqliteStore(tmp_path / "s.db"))
    jobs = src.fetch()

    assert len(jobs) == 1
    job = jobs[0]
    assert job.canonical_key == "naukri:110926000001"
    assert job.url == "https://www.naukri.com/job-listings-110926000001"
    assert job.posted_at is not None and job.posted_at.year == 2026
    assert "<" not in job.description and "Python" in job.description
    assert job.raw["experience"] == "3-8 Yrs"
    # pay-per-event: maxTotalChargeUsd, not maxItems
    assert session.calls[0]["params"]["maxTotalChargeUsd"] == 1.0
    assert "maxItems" not in session.calls[0]["params"]
    assert session.calls[0]["json"]["maxJobs"] == 50
    assert session.calls[0]["json"]["keyword"] == "AI Engineer"


def test_min_interval_blocks_a_second_run(tmp_path):
    store = SqliteStore(tmp_path / "s.db")
    cfg = _muh_config()
    cfg["actors"][0]["min_interval_hours"] = 48

    src1 = CareerOpsSource(cfg, token="tok", session=FakeSession([MUH_ITEMS]), store=store)
    assert len(src1.fetch()) == 1

    src2 = CareerOpsSource(cfg, token="tok", session=FakeSession([MUH_ITEMS]), store=store)
    assert src2.fetch() == []
    assert any("min_interval" in e for e in src2.errors)


def test_spend_is_tracked_across_runs(tmp_path):
    store = SqliteStore(tmp_path / "s.db")
    session = FakeSession([NAUKRI_ITEMS, NAUKRI_ITEMS])
    src = CareerOpsSource(_config(), token="tok", session=session, store=store)
    src.fetch()

    key = CareerOpsSource._month_key()
    spend = float(store.get_runtime(key))
    assert spend > 0  # 1 valid result * $5/1000
    # a second source instance sees the accumulated spend
    src2 = CareerOpsSource(_config(), token="tok", session=FakeSession([NAUKRI_ITEMS]), store=store)
    src2.fetch()
    assert float(store.get_runtime(key)) > spend
