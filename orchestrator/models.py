from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Job(BaseModel):
    source: str
    source_job_id: str
    company: str
    title: str
    location: str | None = None
    description: str = ""
    url: str
    posted_at: datetime | None = None
    fetched_at: datetime = Field(default_factory=utc_now)
    employment_type: str | None = None
    department: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source", "source_job_id", "company", "title", "url")
    @classmethod
    def required_text(cls, value: str) -> str:
        cleaned = " ".join(str(value or "").split())
        if not cleaned:
            raise ValueError("required text field is empty")
        return cleaned

    @field_validator("location", "employment_type", "department")
    @classmethod
    def optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(str(value).split())
        return cleaned or None

    @field_validator("posted_at", "fetched_at")
    @classmethod
    def ensure_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @property
    def canonical_key(self) -> str:
        return f"{self.source}:{self.source_job_id}"


class FilterDecision(BaseModel):
    keep: bool
    stage: str
    reason: str
    warnings: list[str] = Field(default_factory=list)


class ScoreResult(BaseModel):
    pre_score: int
    bucket: str
    signals: dict[str, int]
    matched_evidence_ids: list[str] = Field(default_factory=list)
    matched_terms: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Candidate(BaseModel):
    job: Job
    score: ScoreResult
    filter_warnings: list[str] = Field(default_factory=list)
    intelligence: dict[str, Any] | None = None

    @property
    def job_key(self) -> str:
        return self.job.canonical_key


class SourceResult(BaseModel):
    source: str
    fetched: int = 0
    errors: list[str] = Field(default_factory=list)


class RunSummary(BaseModel):
    mode: str
    dry_run: bool = False
    counts: dict[str, int]
    source_results: list[SourceResult] = Field(default_factory=list)
    new_or_changed: list[str] = Field(default_factory=list)
    notified: list[str] = Field(default_factory=list)
    prepared_artifacts: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
