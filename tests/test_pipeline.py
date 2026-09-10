from __future__ import annotations

from pathlib import Path

from orchestrator.pipeline import run_pipeline
from state.store import SqliteStore


FIXTURE = Path("tests/fixtures/golden_jobs.json")


def test_pipeline_dry_run_stage_counts() -> None:
    summary = run_pipeline(mode="scan", dry_run=True, fixture=FIXTURE, store=SqliteStore("state/runtime/test-dry"))
    assert summary.counts["raw"] == 8
    assert summary.counts["duplicates"] == 1
    assert summary.counts["unique"] == 7
    assert summary.counts["new_or_changed"] > 0


def test_pipeline_idempotent_real_run(tmp_path) -> None:
    store = SqliteStore(tmp_path)
    first = run_pipeline(mode="scan", dry_run=False, fixture=FIXTURE, store=store)
    second = run_pipeline(mode="scan", dry_run=False, fixture=FIXTURE, store=store)
    assert first.counts["new_or_changed"] > 0
    assert second.counts["new_or_changed"] == 0

