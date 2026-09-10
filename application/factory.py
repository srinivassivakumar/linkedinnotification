"""P0-only application artifact factory.

Generates a truthful application package for a single job and saves it under
``artifacts/generated/<company>/<role>/``. Runs only for P0 candidates - weak and
P2 jobs never get artifacts (do not spend effort or tokens on them). Every claim
in every generated file must trace to an id in ``profile/evidence_bank.yaml``;
anything the JD asks for that the evidence bank does not support is written as
``NEEDS_CONFIRMATION``.

Output stays local. A Google Drive copy is opt-in only (``to_drive=True``) and is
left to an explicit, approved step - this module never calls a connector.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from application.artifacts import create_artifact_directory, slugify, write_evidence_matrix, write_json
from intelligence.provider import IntelligenceProvider
from orchestrator.models import Candidate
from state.store import SqliteStore

ARTIFACT_FILES = (
    "fit_report.md",
    "evidence_matrix.md",
    "recruiter_email.txt",
    "referral_message.txt",
    "application_notes.md",
)


class NotP0Error(RuntimeError):
    """Raised when the factory is asked to prepare a non-P0 job."""


def candidate_priority(candidate: Candidate) -> str:
    priority = str((candidate.intelligence or {}).get("priority") or "").upper()
    if priority in {"P0", "P1", "P2"}:
        return priority
    score = candidate.score.pre_score
    return "P0" if score >= 75 else "P1" if score >= 60 else "P2"


def _fit_report_md(candidate: Candidate, evidence: list[dict[str, Any]]) -> str:
    intel = candidate.intelligence or {}
    matched = {str(i) for i in candidate.score.matched_evidence_ids}
    lines = [
        f"# Fit report — {candidate.job.company} · {candidate.job.title}",
        "",
        f"- Deterministic pre-score: {candidate.score.pre_score} ({candidate.score.bucket})",
        f"- Priority: {candidate_priority(candidate)}",
        f"- Claude verdict: {intel.get('verdict', 'not evaluated')}"
        + (f" (score {intel['score']})" if intel.get("score") is not None else ""),
        "",
        "## Evidence that supports this role",
    ]
    for item in evidence:
        if str(item.get("id")) in matched:
            lines.append(f"- `{item['id']}` — {item.get('title')}")
    if not matched:
        lines.append("- NEEDS_CONFIRMATION: no verified evidence overlap; do not apply as a strong fit")
    if intel.get("gaps"):
        lines += ["", "## Gaps (Claude)"] + [f"- {g}" for g in intel["gaps"]]
    if intel.get("risks"):
        lines += ["", "## Risks (Claude)"] + [f"- {r}" for r in intel["risks"]]
    if intel.get("evidence_fit"):
        lines += ["", "## Evidence fit (Claude, verified ids only)"] + [f"- {e}" for e in intel["evidence_fit"]]
    return "\n".join(lines) + "\n"


def _application_notes_md(candidate: Candidate, tailored: dict[str, Any]) -> str:
    lines = [
        f"# Application notes — {candidate.job.company} · {candidate.job.title}",
        "",
        f"- Base resume track: {tailored.get('base_track', 'NEEDS_CONFIRMATION')}",
        f"- Apply at: {candidate.job.url}",
        "",
        "## Evidence used (verified ids only)",
    ]
    lines += [f"- {e}" for e in tailored.get("evidence_used", [])] or ["- NEEDS_CONFIRMATION"]
    if tailored.get("warnings"):
        lines += ["", "## Unsupported JD asks — do NOT claim these"]
        lines += [f"- {w}" for w in tailored["warnings"]]
    lines += [
        "",
        "## Checklist before submitting",
        "- [ ] Every bullet in resume.md traces to an evidence id above",
        "- [ ] No NEEDS_CONFIRMATION text left in any file",
        "- [ ] Recruiter email / referral message reviewed and personalised",
        "- [ ] Applied manually on the job URL",
    ]
    return "\n".join(lines) + "\n"


def prepare_application(
    candidate: Candidate,
    evidence: list[dict[str, Any]],
    store: SqliteStore,
    provider: IntelligenceProvider,
    artifact_root: Path | str = "artifacts/generated",
    *,
    force: bool = False,
    to_drive: bool = False,
) -> Path:
    priority = candidate_priority(candidate)
    if candidate.score.bucket == "weak":
        raise NotP0Error(f"{candidate.job_key} scored weak; no artifacts are generated for weak jobs.")
    if priority == "P2" and not force:
        raise NotP0Error(f"{candidate.job_key} is P2; the factory runs for P0 (or force=True for a manual override).")
    if priority != "P0" and not force:
        raise NotP0Error(
            f"{candidate.job_key} is {priority}; the application factory runs for P0 only "
            f"(pass force=True for an explicit manual override)."
        )

    application = store.create_application(candidate.job, status="preparing")
    paths = create_artifact_directory(candidate.job, artifact_root)

    write_json(paths / "job.json", candidate.job.model_dump(mode="json"))
    write_evidence_matrix(paths / "evidence_matrix.md", candidate, evidence)
    (paths / "fit_report.md").write_text(_fit_report_md(candidate, evidence), encoding="utf-8")

    tailored = provider.tailor_application(candidate.job, evidence)
    files = tailored.get("files", {})
    for name in ("recruiter_email.txt", "referral_message.txt"):
        content = files.get(name) or "NEEDS_CONFIRMATION: provider did not produce this file."
        (paths / name).write_text(str(content).rstrip() + "\n", encoding="utf-8")
    for name in ("resume.md", "cover_letter.md", "linkedin_message.txt", "application_answers.md"):
        if files.get(name):
            (paths / name).write_text(str(files[name]).rstrip() + "\n", encoding="utf-8")

    (paths / "application_notes.md").write_text(_application_notes_md(candidate, tailored), encoding="utf-8")

    payload = {"artifact_dir": str(paths), "priority": priority, "warnings": tailored.get("warnings", [])}
    if to_drive:
        payload["drive"] = "requested — upload via the Google Drive connector as an approved step"
    store.update_application(application["id"], candidate.job_key, "prepared", payload)
    return paths


# Back-compat name
prepare_p0_application = prepare_application
