from __future__ import annotations

from datetime import datetime, timezone

from orchestrator import pipeline
from orchestrator.models import Job
from sources.ashby import AshbySource
from sources.greenhouse import GreenhouseSource
from sources.lever import LeverSource

NOW = datetime.now(timezone.utc)


def test_build_sources_reads_sources_ats_shape() -> None:
    config = {
        "sources": {
            "ats": {
                "greenhouse": {"enabled": True, "boards": ["acme"]},
                "lever": {"enabled": True, "companies": ["beta"]},
                "ashby": {"enabled": False, "companies": ["gamma"]},
            },
            "portals": {"naukri": {"enabled": True}},
        }
    }
    built = pipeline.build_sources(config)
    names = [s.name for s in built]
    assert "greenhouse" in names and "lever" in names
    assert "ashby" not in names  # disabled
    gh = next(s for s in built if s.name == "greenhouse")
    assert gh.board_tokens == ["acme"]


def test_build_sources_backward_compatible_with_flat_shape() -> None:
    config = {"sources": {"greenhouse": {"enabled": True, "boards": ["legacy"]}}}
    built = pipeline.build_sources(config)
    gh = next(s for s in built if s.name == "greenhouse")
    assert gh.board_tokens == ["legacy"]


def test_one_malformed_posting_does_not_break_a_board() -> None:
    src = GreenhouseSource([])
    good = {"id": 1, "title": "MLE", "absolute_url": "https://x/1", "content": "python"}
    bad = {"nothing": "useful"}  # no id/url -> Job validation fails
    jobs = src._map_all("acme", [good, bad], NOW)
    assert len(jobs) == 1
    assert src.errors and "acme" in src.errors[0]


def test_lever_and_ashby_have_error_lists() -> None:
    assert LeverSource(["x"]).errors == []
    assert AshbySource(["x"]).errors == []


def test_fetch_all_sources_isolates_a_failing_source(monkeypatch) -> None:
    class BoomSource:
        name = "boom"

        def fetch(self):
            raise RuntimeError("network down")

    class OkSource:
        name = "ok"
        errors = ["ok:company-z: skipped 1 posting: ValueError"]

        def fetch(self):
            return [Job(source="ok", source_job_id="1", company="Z", title="MLE", url="https://z/1")]

    monkeypatch.setattr(pipeline, "build_sources", lambda cfg: [BoomSource(), OkSource()])
    raw, results = pipeline.fetch_all_sources({})
    assert len(raw) == 1
    by_name = {r.source: r for r in results}
    assert by_name["boom"].errors and by_name["boom"].fetched == 0
    assert by_name["ok"].fetched == 1 and by_name["ok"].errors
