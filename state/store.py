from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from orchestrator.models import Candidate, Job


class JsonlStore:
    def __init__(self, root: Path | str = "state"):
        self.root = Path(root)
        self.runtime = self.root / "runtime"
        self.root.mkdir(parents=True, exist_ok=True)
        self.runtime.mkdir(parents=True, exist_ok=True)
        for name in ("jobs.jsonl", "applications.jsonl", "contacts.jsonl", "events.jsonl"):
            (self.root / name).touch(exist_ok=True)
        self.seen_path = self.runtime / "seen_jobs.json"
        if not self.seen_path.exists():
            self.seen_path.write_text("{}", encoding="utf-8")

    def _append(self, filename: str, payload: dict[str, Any]) -> None:
        with (self.root / filename).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")

    def _seen(self) -> dict[str, str]:
        return json.loads(self.seen_path.read_text(encoding="utf-8") or "{}")

    def _write_seen(self, seen: dict[str, str]) -> None:
        self.seen_path.write_text(json.dumps(seen, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def candidate_signature(self, candidate: Candidate) -> str:
        payload = {
            "url": candidate.job.url,
            "posted_at": candidate.job.posted_at.isoformat() if candidate.job.posted_at else None,
            "pre_score": candidate.score.pre_score,
            "bucket": candidate.score.bucket,
            "title": candidate.job.title,
            "company": candidate.job.company,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    def diff_new_or_changed(self, candidates: list[Candidate]) -> list[Candidate]:
        seen = self._seen()
        changed: list[Candidate] = []
        for candidate in candidates:
            signature = self.candidate_signature(candidate)
            if seen.get(candidate.job_key) != signature:
                changed.append(candidate)
        return changed

    def persist(self, candidates: list[Candidate]) -> None:
        seen = self._seen()
        for candidate in candidates:
            signature = self.candidate_signature(candidate)
            self._append(
                "jobs.jsonl",
                {
                    "job_key": candidate.job_key,
                    "signature": signature,
                    "job": candidate.job.model_dump(mode="json"),
                    "score": candidate.score.model_dump(),
                    "intelligence": candidate.intelligence,
                    "timestamp": _now(),
                },
            )
            previous = seen.get(candidate.job_key)
            seen[candidate.job_key] = signature
            self.append_event(
                "job_discovered" if previous is None else "job_changed",
                candidate.job_key,
                {"pre_score": candidate.score.pre_score, "bucket": candidate.score.bucket},
            )
        self._write_seen(seen)
        (self.runtime / "last_run.json").write_text(json.dumps({"timestamp": _now()}, indent=2), encoding="utf-8")

    def append_event(self, event_type: str, job_key: str | None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        event = {
            "event_id": str(uuid.uuid4()),
            "type": event_type,
            "job_key": job_key,
            "timestamp": _now(),
            "payload": payload or {},
        }
        self._append("events.jsonl", event)
        return event

    def create_application(self, job: Job, status: str = "preparing") -> dict[str, Any]:
        application = {
            "id": str(uuid.uuid4()),
            "job_key": job.canonical_key,
            "company": job.company,
            "title": job.title,
            "status": status,
            "created_at": _now(),
            "updated_at": _now(),
        }
        self._append("applications.jsonl", application)
        self.append_event("application_created", job.canonical_key, {"application_id": application["id"], "status": status})
        return application

    def update_application(self, application_id: str, job_key: str, status: str, payload: dict[str, Any] | None = None) -> None:
        self._append(
            "applications.jsonl",
            {"id": application_id, "job_key": job_key, "status": status, "updated_at": _now(), "payload": payload or {}},
        )
        self.append_event("application_updated", job_key, {"application_id": application_id, "status": status, **(payload or {})})

    def load_latest_jobs(self) -> dict[str, Candidate]:
        latest: dict[str, Candidate] = {}
        path = self.root / "jobs.jsonl"
        if not path.exists():
            return latest
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            job = Job.model_validate(record["job"])
            from orchestrator.models import ScoreResult

            latest[record["job_key"]] = Candidate(
                job=job,
                score=ScoreResult.model_validate(record["score"]),
                intelligence=record.get("intelligence"),
            )
        return latest


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

