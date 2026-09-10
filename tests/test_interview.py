from __future__ import annotations

from datetime import datetime, timezone

from interview.prep import build_prep_pack, jd_evidence_matrix, render_prep_pack, star_stories, write_prep_pack
from interview.schedule import extract_interview_datetime, propose_calendar_event
from orchestrator.models import Job
from orchestrator.policies import load_evidence

NOW = datetime(2026, 9, 10, tzinfo=timezone.utc)

JD = (
    "We need an AI/ML engineer with strong Python, FastAPI, Docker, AWS and RAG "
    "experience. Kubernetes and Spark are a plus. You will build LLM pipelines."
)


def test_extract_interview_datetime_formats() -> None:
    assert extract_interview_datetime("Let's meet 2026-09-15 15:00 UTC") == datetime(2026, 9, 15, 15, 0, tzinfo=timezone.utc)
    assert extract_interview_datetime("How about Sept 15 at 3 PM?", now=NOW) == datetime(2026, 9, 15, 15, 0, tzinfo=timezone.utc)
    assert extract_interview_datetime("15/09/2026 at 3:30 pm") == datetime(2026, 9, 15, 15, 30, tzinfo=timezone.utc)
    assert extract_interview_datetime("sometime next week") is None


def test_jd_matrix_cites_evidence_and_flags_gaps() -> None:
    rows = jd_evidence_matrix(JD, load_evidence())
    ids = {r["evidence_id"] for r in rows}
    assert any(i not in {"NEEDS_CONFIRMATION"} for i in ids)  # real citations
    assert "NEEDS_CONFIRMATION" in ids  # kubernetes/spark unsupported -> flagged
    for row in rows:
        assert row["evidence_id"]


def test_star_stories_only_from_evidence_bank() -> None:
    evidence = load_evidence()
    valid = {e["id"] for e in evidence} | {"NEEDS_CONFIRMATION"}
    for story in star_stories(JD, evidence):
        assert story["evidence_id"] in valid


def test_build_and_render_prep_pack(tmp_path) -> None:
    job = Job(source="fixture", source_job_id="1", company="Acme", title="AI Engineer",
              url="https://x", description=JD)
    pack = build_prep_pack(job, load_evidence())
    assert pack["status"] == "prepared"
    assert "NEEDS_CONFIRMATION" in pack["company_brief"]
    assert pack["questions_to_ask"] and pack["thank_you_draft"]
    md = render_prep_pack(pack)
    assert "JD → evidence matrix" in md and "STAR stories" in md
    out = write_prep_pack(pack, tmp_path)
    assert out.exists() and out.name == "interview_prep.md"


def test_calendar_proposal_is_approval_only() -> None:
    proposal = propose_calendar_event("Acme", "AI Engineer", NOW)
    assert proposal["requires_approval"] is True
    assert proposal["action"] == "create_calendar_event"
    # nothing here calls a connector; it only returns a dict
    assert proposal["start"] == NOW.isoformat()
