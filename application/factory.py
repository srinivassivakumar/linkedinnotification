from __future__ import annotations

from pathlib import Path
from typing import Any

from application.artifacts import create_artifact_directory, write_evidence_matrix, write_json
from intelligence.provider import IntelligenceProvider
from orchestrator.models import Candidate
from state.store import JsonlStore


def prepare_application(
    candidate: Candidate,
    evidence: list[dict[str, Any]],
    store: JsonlStore,
    provider: IntelligenceProvider,
    artifact_root: Path | str = "artifacts/generated",
) -> Path:
    application = store.create_application(candidate.job, status="preparing")
    paths = create_artifact_directory(candidate.job, artifact_root)
    write_json(paths / "job.json", candidate.job.model_dump(mode="json"))
    write_json(paths / "fit_report.json", {"score": candidate.score.model_dump(), "intelligence": candidate.intelligence})
    write_evidence_matrix(paths / "evidence_matrix.md", candidate, evidence)

    generated = provider.tailor_application(candidate.job, evidence)
    for name, content in generated.get("files", {}).items():
        (paths / name).write_text(str(content).rstrip() + "\n", encoding="utf-8")

    store.update_application(application["id"], candidate.job_key, "prepared", {"artifact_dir": str(paths)})
    return paths

