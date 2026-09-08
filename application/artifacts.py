from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from orchestrator.models import Candidate, Job


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "unknown"


def create_artifact_directory(job: Job, root: Path | str = "artifacts/generated") -> Path:
    path = Path(root) / slugify(job.company) / slugify(job.title)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def write_evidence_matrix(path: Path, candidate: Candidate, evidence: list[dict[str, Any]]) -> None:
    matched = set(candidate.score.matched_evidence_ids)
    lines = [
        "# Deterministic Evidence Matrix",
        "",
        "This file is generated before Claude. Use it as a grounding aid, not as final application copy.",
        "",
        f"Job: {candidate.job.company} - {candidate.job.title}",
        f"Score: {candidate.score.pre_score} ({candidate.score.bucket})",
        "",
        "## Matched Terms",
    ]
    lines.extend(f"- {term}" for term in candidate.score.matched_terms)
    if not candidate.score.matched_terms:
        lines.append("- No verified deterministic overlap yet")
    lines.extend(["", "## Verified Evidence"])
    for item in evidence:
        if str(item.get("id")) in matched:
            lines.append(f"- {item.get('id')}: {item.get('title')}")
    if not matched:
        lines.append("- None matched. Update `profile/evidence_bank.yaml` with real verified evidence.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

