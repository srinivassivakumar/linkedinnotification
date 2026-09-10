"""Draft-request queue - the bridge that lets the mock/cloud setup produce real
Claude-tailored artifacts.

Flow (Path B):

1. In the cloud (GitHub Actions, ``CLAUDE_MODE=mock``) a PREPARE / RESUME /
   EMAIL / LINKEDIN button press is *queued* - :meth:`SqliteStore.enqueue_draft_request` -
   instead of returning placeholder text. The row is committed back to the repo
   with the rest of the state.
2. A Claude Code session runs ``python run_agent.py drafts --list``. That prints,
   for every pending request, the job snapshot, the verified evidence bank and
   the exact files to write. Claude writes those files into the artifact dir,
   grounding every claim in an evidence id (or ``NEEDS_CONFIRMATION``).
3. ``python run_agent.py drafts --deliver <id>`` reads the written files back
   through :class:`_WrittenFilesProvider`, runs the normal P0 artifact factory
   (so the deterministic fit report / evidence matrix are generated too), pushes
   the requested draft to Telegram and marks the request delivered.

No Anthropic API key is involved anywhere - the "intelligence" in step 2 is the
Claude Code session itself.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from application.artifacts import create_artifact_directory
from orchestrator.pipeline import ROOT
from orchestrator.policies import load_evidence
from state.store import SqliteStore

MARKER = "_claude_tailored.json"

# Which files a Claude drafting run must write for each button kind.
KIND_FILES: dict[str, list[str]] = {
    "prepare": [
        "resume.md",
        "cover_letter.md",
        "recruiter_email.txt",
        "referral_message.txt",
        "linkedin_message.txt",
        "application_answers.md",
    ],
    "resume": ["resume.md"],
    "email": ["recruiter_email.txt"],
    "linkedin": ["linkedin_message.txt", "referral_message.txt"],
}

RULES = [
    "Every claim in every file must trace to an `id` in evidence_bank, or be written as NEEDS_CONFIRMATION.",
    "Never invent a technology, metric, outcome, employer or duration. You may reorder, shorten and rephrase evidence.",
    "If the JD asks for something the evidence bank does not support, do not claim it - note it as NEEDS_CONFIRMATION.",
    "resume.md is one page of markdown. The *.txt drafts are short and plain. The LinkedIn / referral note is sent manually by the user - keep it under 90 words.",
    "Write every file in `write_files` into `artifact_dir`, then run `deliver_command`.",
]


DEFAULT_ARTIFACT_ROOT = ROOT / "artifacts" / "generated"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _candidate(store: SqliteStore, job_key: str) -> Any:
    return store.load_latest_jobs().get(job_key)


def list_pending(store: SqliteStore, artifact_root: Path | str = DEFAULT_ARTIFACT_ROOT) -> dict[str, Any]:
    """Everything a Claude Code session needs to fulfil the queue, as one JSON blob."""
    latest = store.load_latest_jobs()
    items: list[dict[str, Any]] = []
    for req in store.pending_draft_requests():
        candidate = latest.get(req["job_key"])
        if candidate is None:
            items.append(
                {
                    "request_id": req["id"],
                    "kind": req["kind"],
                    "job_key": req["job_key"],
                    "error": "job is no longer in current state - cancel with --deliver is not possible; leave it, it will age out",
                }
            )
            continue
        path = create_artifact_directory(candidate.job, artifact_root)
        matched = [str(i) for i in candidate.score.matched_evidence_ids]
        items.append(
            {
                "request_id": req["id"],
                "kind": req["kind"],
                "job_key": req["job_key"],
                "requested_at": req["requested_at"],
                "artifact_dir": str(path),
                "already_tailored": (path / MARKER).exists(),
                "write_files": KIND_FILES[req["kind"]],
                "deliver_command": f"python run_agent.py drafts --deliver {req['id']}",
                "job": {
                    "company": candidate.job.company,
                    "title": candidate.job.title,
                    "location": candidate.job.location,
                    "url": candidate.job.url,
                    "description": candidate.job.description,
                },
                "matched_evidence_ids": matched,
            }
        )
    return {
        "pending_count": len(items),
        "pending": items,
        "rules": RULES,
        "evidence_bank": load_evidence(ROOT / "profile" / "evidence_bank.yaml"),
    }


class _WrittenFilesProvider:
    """Feeds the files a Claude session already wrote back into the artifact
    factory, so the deterministic scaffold is still generated and nothing is
    overwritten with a mock placeholder."""

    is_live = True

    def __init__(self, path: Path) -> None:
        self._path = path

    def tailor_application(self, job: Any, evidence: list[dict[str, Any]]) -> dict[str, Any]:
        files: dict[str, str] = {}
        for name in KIND_FILES["prepare"]:
            target = self._path / name
            if target.exists():
                files[name] = target.read_text(encoding="utf-8")
        return {
            "status": "prepared",
            "provider": "written_files",
            "base_track": "NEEDS_CONFIRMATION",
            "evidence_used": [],
            "warnings": [] if files else ["no tailored files were written before delivery"],
            "files": files,
        }

    def __getattr__(self, name: str) -> Any:  # pragma: no cover - other provider methods are unused here
        raise NotImplementedError(f"_WrittenFilesProvider does not implement {name!r}")


def deliver_one(
    store: SqliteStore,
    bot: Any,
    provider: Any,
    request_id: int,
    *,
    dry_run: bool = False,
    artifact_root: Path | str = DEFAULT_ARTIFACT_ROOT,
) -> dict[str, Any]:
    from telegram.callback_worker import deliver_draft

    req = store.get_draft_request(request_id)
    if req is None:
        return {"status": "error", "error": f"no draft request #{request_id}"}
    if req["status"] != "pending":
        return {"status": "skipped", "reason": f"request #{request_id} is already {req['status']}"}

    candidate = _candidate(store, req["job_key"])
    if candidate is None:
        store.mark_draft_request(request_id, "failed", "job not in current state")
        return {"status": "error", "error": "job is no longer in current state"}

    path = create_artifact_directory(candidate.job, artifact_root)
    kind = req["kind"]
    written = [name for name in KIND_FILES[kind] if (path / name).exists()]
    missing = [name for name in KIND_FILES[kind] if not (path / name).exists()]

    live_button = getattr(provider, "is_live", False)
    if missing and not live_button and not written:
        return {
            "status": "not_ready",
            "error": f"no tailored files written yet for #{request_id}",
            "artifact_dir": str(path),
            "expected_files": KIND_FILES[kind],
        }

    if dry_run:
        return {
            "status": "dry_run",
            "request_id": request_id,
            "kind": kind,
            "artifact_dir": str(path),
            "written": written,
            "missing": missing,
        }

    # A live provider (real Claude) tailors now; otherwise use the files the
    # Claude Code session just wrote.
    effective_provider = provider if live_button else _WrittenFilesProvider(path)
    result = deliver_draft(kind, candidate, store, effective_provider, bot)

    if result == "prepare_refused":
        store.mark_draft_request(request_id, "failed", "artifact factory refused this job")
        return {"status": "refused", "request_id": request_id, "kind": kind}

    (path / MARKER).write_text(
        json.dumps({"request_id": request_id, "kind": kind, "delivered_at": _now()}, indent=2),
        encoding="utf-8",
    )
    store.mark_draft_request(request_id, "delivered", f"deliver_draft -> {result}")
    store.append_event(
        "draft_delivered", req["job_key"], {"kind": kind, "request_id": request_id, "result": result}
    )
    return {
        "status": "ok",
        "request_id": request_id,
        "kind": kind,
        "result": result,
        "artifact_dir": str(path),
    }
