"""Unified SQLite state store - the single source of truth.

Replaces the earlier JSONL store. One SQLite database holds jobs, applications,
events, contacts, LinkedIn connections and processed-email ids, following the
schema in the connector-first build guide (section 20). The public method
surface is unchanged from the JSONL store so the pipeline and callers do not
care about the backend.

`JsonlStore` remains as an alias for backward compatibility with older imports.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from orchestrator.models import Candidate, Job, ScoreResult


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_key         TEXT PRIMARY KEY,
    source          TEXT,
    company         TEXT,
    title           TEXT,
    location        TEXT,
    url             TEXT,
    posted_at       TEXT,
    signature       TEXT NOT NULL,
    pre_score       INTEGER,
    bucket          TEXT,
    priority        TEXT,
    job_json        TEXT NOT NULL,
    score_json      TEXT NOT NULL,
    intelligence_json TEXT,
    status          TEXT DEFAULT 'discovered',
    first_seen_at   TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS applications (
    id           TEXT PRIMARY KEY,
    job_key      TEXT NOT NULL,
    company      TEXT,
    title        TEXT,
    status       TEXT NOT NULL,
    artifact_dir TEXT,
    payload_json TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    event_id   TEXT PRIMARY KEY,
    type       TEXT NOT NULL,
    job_key    TEXT,
    payload_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contacts (
    id                TEXT PRIMARY KEY,
    job_key           TEXT,
    company           TEXT,
    name              TEXT,
    title             TEXT,
    role_type         TEXT,
    public_profile_url TEXT,
    email             TEXT,
    email_confidence  TEXT,
    source            TEXT,
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS connections (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL,
    current_title    TEXT,
    linkedin_url     TEXT,
    person_type      TEXT,
    company          TEXT,
    matched_job_key  TEXT,
    draft_kind       TEXT,
    generated_message TEXT,
    job_match_score  REAL,
    status           TEXT DEFAULT 'pending',
    gmail_message_id TEXT UNIQUE,
    created_at       TEXT NOT NULL,
    approved_at      TEXT
);

CREATE TABLE IF NOT EXISTS processed_emails (
    gmail_message_id TEXT PRIMARY KEY,
    kind             TEXT,
    processed_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


class SqliteStore:
    def __init__(self, root: Path | str = "state") -> None:
        path = Path(root)
        if path.suffix == ".db":
            self.db_path = path
        else:
            self.db_path = path / "career_agent.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # -- connection helpers -------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    # -- jobs / candidates -------------------------------------------------
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
        with self._connect() as conn:
            seen = {
                row["job_key"]: row["signature"]
                for row in conn.execute("SELECT job_key, signature FROM jobs")
            }
        return [
            candidate
            for candidate in candidates
            if seen.get(candidate.job_key) != self.candidate_signature(candidate)
        ]

    def persist(self, candidates: list[Candidate]) -> None:
        now = _now()
        with self._connect() as conn:
            for candidate in candidates:
                signature = self.candidate_signature(candidate)
                existing = conn.execute(
                    "SELECT job_key FROM jobs WHERE job_key = ?", (candidate.job_key,)
                ).fetchone()
                priority = (candidate.intelligence or {}).get("priority")
                job_json = candidate.job.model_dump(mode="json")
                score_json = candidate.score.model_dump()
                conn.execute(
                    """
                    INSERT INTO jobs (job_key, source, company, title, location, url,
                        posted_at, signature, pre_score, bucket, priority, job_json,
                        score_json, intelligence_json, first_seen_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(job_key) DO UPDATE SET
                        signature=excluded.signature, pre_score=excluded.pre_score,
                        bucket=excluded.bucket, priority=excluded.priority,
                        job_json=excluded.job_json, score_json=excluded.score_json,
                        intelligence_json=excluded.intelligence_json,
                        location=excluded.location, url=excluded.url,
                        posted_at=excluded.posted_at, updated_at=excluded.updated_at
                    """,
                    (
                        candidate.job_key,
                        candidate.job.source,
                        candidate.job.company,
                        candidate.job.title,
                        candidate.job.location,
                        candidate.job.url,
                        candidate.job.posted_at.isoformat() if candidate.job.posted_at else None,
                        signature,
                        candidate.score.pre_score,
                        candidate.score.bucket,
                        priority,
                        json.dumps(job_json, default=str),
                        json.dumps(score_json, default=str),
                        json.dumps(candidate.intelligence, default=str) if candidate.intelligence else None,
                        now,
                        now,
                    ),
                )
                self._append_event(
                    conn,
                    "job_discovered" if existing is None else "job_changed",
                    candidate.job_key,
                    {"pre_score": candidate.score.pre_score, "bucket": candidate.score.bucket},
                )
            conn.execute(
                "INSERT INTO runtime (key, value) VALUES ('last_run', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (now,),
            )

    def load_latest_jobs(self) -> dict[str, Candidate]:
        latest: dict[str, Candidate] = {}
        with self._connect() as conn:
            for row in conn.execute("SELECT job_json, score_json, intelligence_json FROM jobs"):
                job = Job.model_validate(json.loads(row["job_json"]))
                score = ScoreResult.model_validate(json.loads(row["score_json"]))
                intelligence = json.loads(row["intelligence_json"]) if row["intelligence_json"] else None
                latest[job.canonical_key] = Candidate(job=job, score=score, intelligence=intelligence)
        return latest

    def open_jobs_for_company(self, company: str, limit: int = 10) -> list[dict[str, Any]]:
        if not company:
            return []
        like = f"%{company.strip().lower()}%"
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT job_key, company, title, location, url, pre_score, bucket, priority "
                "FROM jobs WHERE lower(company) LIKE ? AND COALESCE(status,'') != 'skipped' "
                "ORDER BY pre_score DESC LIMIT ?",
                (like, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def set_job_status(self, job_key: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET status = ?, updated_at = ? WHERE job_key = ?",
                (status, _now(), job_key),
            )

    # -- applications ----------------------------------------------------
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
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO applications (id, job_key, company, title, status, "
                "payload_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    application["id"],
                    application["job_key"],
                    job.company,
                    job.title,
                    status,
                    None,
                    application["created_at"],
                    application["updated_at"],
                ),
            )
            self._append_event(
                conn, "application_created", job.canonical_key,
                {"application_id": application["id"], "status": status},
            )
        return application

    def update_application(
        self, application_id: str, job_key: str, status: str, payload: dict[str, Any] | None = None
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE applications SET status = ?, artifact_dir = COALESCE(?, artifact_dir), "
                "payload_json = ?, updated_at = ? WHERE id = ?",
                (
                    status,
                    (payload or {}).get("artifact_dir"),
                    json.dumps(payload or {}, default=str),
                    _now(),
                    application_id,
                ),
            )
            self._append_event(
                conn, "application_updated", job_key,
                {"application_id": application_id, "status": status, **(payload or {})},
            )

    # -- events --------------------------------------------------------
    def append_event(
        self, event_type: str, job_key: str | None, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        with self._connect() as conn:
            return self._append_event(conn, event_type, job_key, payload)

    def _append_event(
        self, conn: sqlite3.Connection, event_type: str, job_key: str | None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "event_id": str(uuid.uuid4()),
            "type": event_type,
            "job_key": job_key,
            "timestamp": _now(),
            "payload": payload or {},
        }
        conn.execute(
            "INSERT INTO events (event_id, type, job_key, payload_json, created_at) VALUES (?,?,?,?,?)",
            (event["event_id"], event_type, job_key, json.dumps(payload or {}, default=str), event["timestamp"]),
        )
        return event

    def recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    # -- contacts (human path) ---------------------------------------
    def add_contact(self, contact: dict[str, Any]) -> str:
        contact_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO contacts (id, job_key, company, name, title, role_type, "
                "public_profile_url, email, email_confidence, source, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    contact_id,
                    contact.get("job_key"),
                    contact.get("company"),
                    contact.get("name"),
                    contact.get("title"),
                    contact.get("role_type"),
                    contact.get("public_profile_url"),
                    contact.get("email"),
                    contact.get("email_confidence"),
                    contact.get("source"),
                    _now(),
                ),
            )
        return contact_id

    def contacts_for_company(self, company: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM contacts WHERE lower(company) = lower(?)", (company,)
            ).fetchall()
        return [dict(row) for row in rows]

    # -- LinkedIn connections --------------------------------------
    def connection_by_gmail_id(self, gmail_message_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM connections WHERE gmail_message_id = ?", (gmail_message_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_connection(self, connection_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM connections WHERE id = ?", (connection_id,)
            ).fetchone()
        return dict(row) if row else None

    def save_connection(self, person: dict[str, Any], gmail_message_id: str | None = None) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO connections (name, current_title, linkedin_url, "
                "gmail_message_id, status, created_at) VALUES (?,?,?,?,?,?)",
                (
                    person.get("name"),
                    person.get("current_title"),
                    person.get("linkedin_url"),
                    gmail_message_id,
                    "pending",
                    _now(),
                ),
            )
            return int(cursor.lastrowid)

    def update_connection_result(self, connection_id: int, result: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE connections SET person_type = ?, company = ?, matched_job_key = ?, "
                "draft_kind = ?, generated_message = ?, job_match_score = ?, status = ? WHERE id = ?",
                (
                    result.get("person_type"),
                    result.get("company"),
                    result.get("matched_job_key"),
                    result.get("draft_kind"),
                    result.get("draft_message") or result.get("generated_message"),
                    result.get("job_match_score"),
                    result.get("status", "awaiting_approval"),
                    connection_id,
                ),
            )

    def set_connection_status(self, connection_id: int, status: str) -> None:
        approved = _now() if status == "approved" else None
        with self._connect() as conn:
            conn.execute(
                "UPDATE connections SET status = ?, approved_at = COALESCE(?, approved_at) WHERE id = ?",
                (status, approved, connection_id),
            )

    # -- processed emails (idempotency) ---------------------------
    def email_processed(self, gmail_message_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM processed_emails WHERE gmail_message_id = ?", (gmail_message_id,)
            ).fetchone()
        return row is not None

    def mark_email_processed(self, gmail_message_id: str, kind: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO processed_emails (gmail_message_id, kind, processed_at) "
                "VALUES (?,?,?)",
                (gmail_message_id, kind, _now()),
            )

    # -- runtime ------------------------------------------------
    def get_runtime(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM runtime WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_runtime(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO runtime (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )


# Backward-compatible alias for older imports.
JsonlStore = SqliteStore
