from __future__ import annotations

import pytest

from application.factory import ARTIFACT_FILES, NotP0Error, candidate_priority, prepare_application
from intelligence.mock import MockProvider
from orchestrator.models import Candidate, Job, ScoreResult
from orchestrator.policies import load_evidence
from state.store import SqliteStore

EVIDENCE = load_evidence()


def _candidate(pre_score: int, bucket: str, priority: str | None = None) -> Candidate:
    job = Job(
        source="greenhouse", source_job_id="p0", company="Acme Cloud", title="AI Engineer",
        url="https://jobs.example.com/acme/ai", description="Python FastAPI Docker AWS RAG LLM " * 20,
    )
    intel = {"provider": "claude", "priority": priority, "verdict": "evaluated",
             "evidence_fit": ["aws_backup_infrastructure: infra"], "gaps": ["k8s"], "risks": []} if priority else None
    return Candidate(
        job=job,
        score=ScoreResult(pre_score=pre_score, bucket=bucket, signals={"evidence_overlap": 20},
                          matched_evidence_ids=["aws_backup_infrastructure"], matched_terms=["python", "aws"]),
        intelligence=intel,
    )


def test_priority_resolution() -> None:
    assert candidate_priority(_candidate(90, "strong_candidate")) == "P0"
    assert candidate_priority(_candidate(64, "review")) == "P1"
    assert candidate_priority(_candidate(40, "weak")) == "P2"
    assert candidate_priority(_candidate(40, "weak", priority="P0")) == "P0"


def test_p0_generates_all_artifacts_with_citations(tmp_path) -> None:
    store = SqliteStore(tmp_path / "s.db")
    candidate = _candidate(88, "strong_candidate", priority="P0")
    out = prepare_application(candidate, EVIDENCE, store, MockProvider(), tmp_path / "art")
    produced = {p.name for p in out.iterdir()}
    for name in ARTIFACT_FILES:
        assert name in produced, name
    fit = (out / "fit_report.md").read_text()
    assert "aws_backup_infrastructure" in fit
    matrix = (out / "evidence_matrix.md").read_text()
    assert "aws_backup_infrastructure" in matrix
    notes = (out / "application_notes.md").read_text()
    assert "Checklist before submitting" in notes


def test_weak_job_gets_no_artifacts(tmp_path) -> None:
    store = SqliteStore(tmp_path / "s.db")
    with pytest.raises(NotP0Error):
        prepare_application(_candidate(30, "weak"), EVIDENCE, store, MockProvider(), tmp_path / "art")
    assert not (tmp_path / "art").exists()


def test_p2_job_blocked_without_force(tmp_path) -> None:
    store = SqliteStore(tmp_path / "s.db")
    c = _candidate(50, "review", priority="P2")
    with pytest.raises(NotP0Error):
        prepare_application(c, EVIDENCE, store, MockProvider(), tmp_path / "art")
    # explicit manual override is allowed for non-weak jobs
    out = prepare_application(c, EVIDENCE, store, MockProvider(), tmp_path / "art", force=True)
    assert out.exists()
