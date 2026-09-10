"""Claude intelligence provider (R1: connector-first architecture).

This provider satisfies :class:`IntelligenceProvider`. In R1 only
:meth:`evaluate_jobs` is implemented end to end. It reasons *only* over the
deterministic pre-score, the verified job snapshot, and verified evidence from
``profile/evidence_bank.yaml``. Claude is asked for one strict JSON object per
candidate and the result is validated before it is attached to the candidate.

Design rules (from the revised connector-first build guide):
- Claude is the reasoning layer, not an acquisition or action layer.
- Only serious/uncertain candidates are sent to Claude, never every raw job.
- Claude may reorder, shorten and rephrase evidence. It must never invent a
  technology, metric, outcome, responsibility or experience duration, so any
  evidence id it cites that is not in the verified bank is dropped and flagged.
- Keep ``CLAUDE_MODE=mock`` until this path is validated against real runs.

The Anthropic client is imported lazily and can be injected, so the pipeline and
tests never require network access or an API key unless a real evaluation runs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from intelligence.provider import IntelligenceProvider, candidate_payload
from orchestrator.models import Candidate, Job
from orchestrator.policies import load_evidence

ROOT = Path(__file__).resolve().parents[1]

# Deterministic buckets (see orchestrator/scorer.py) that are worth a Claude call.
DEFAULT_EVALUATE_BUCKETS = ("strong_candidate", "review")
DEFAULT_MODEL = "claude-opus-5"
DEFAULT_MAX_EVALUATIONS = 25

PRIORITIES = ("P0", "P1", "P2")

SYSTEM_PROMPT = """\
You are the reasoning layer of a deterministic job-hunt pipeline. Python already
fetched, deduped, filtered and pre-scored this job. Your only task is to judge
fit for ONE candidate against verified evidence and return a single JSON object.

Hard rules:
- Reason only over the job snapshot and the verified evidence provided. Do not
  use outside knowledge about the company or invent facts about the applicant.
- You may reorder, shorten or rephrase evidence. You must never invent a
  technology, metric, outcome, responsibility or experience duration.
- Only cite evidence via the exact `id` values present in `verified_evidence`.
- Be conservative: if the evidence does not clearly support a core requirement,
  record it as a gap, not a fit.
- Output ONLY the JSON object, no prose, no markdown fences.

JSON schema (all fields required):
{
  "score": integer 0-100 — your fit score, independent of the pre-score,
  "priority": "P0" | "P1" | "P2" — P0 act now, P1 prepare, P2 store/skip,
  "evidence_fit": [ "<evidence_id>: <one line on why it supports a requirement>" ],
  "gaps": [ "<requirement the verified evidence does not cover>" ],
  "risks": [ "<seniority / location / recency / credibility risk>" ],
  "human_path_hint": "<who to reach and the angle, or 'none obvious'>",
  "recommended_next_action": "act_now" | "prepare" | "store" | "archive"
}
"""

NEXT_ACTIONS = ("act_now", "prepare", "store", "archive")

TAILOR_SYSTEM = """\
You tailor a job application for ONE role using only verified evidence. Return a
single JSON object, no prose, no markdown fences.

Rules:
- Every claim in every file must trace to a `verified_evidence` id. Never invent a
  technology, metric, outcome, responsibility or duration.
- You may reorder, shorten and rephrase evidence.
- If the JD requires something the evidence does not support, do NOT claim it -
  list it in `warnings`.
- Keep the recruiter email and referral/LinkedIn messages short and truthful.

JSON schema (all fields required):
{
  "base_track": "AI/GenAI" | "ML" | "Data" | "MLOps" | "DevOps/Cloud",
  "evidence_used": [ "<evidence_id>: <how it is used>" ],
  "resume_markdown": "<tailored one-page resume in markdown>",
  "cover_letter": "<short cover letter>",
  "recruiter_email": "<short outreach email to a recruiter>",
  "referral_message": "<short message asking an employee for a referral>",
  "linkedin_message": "<short LinkedIn note; will be sent manually>",
  "application_answers": "<markdown: common application questions with truthful answers>",
  "warnings": [ "<JD requirement not supported by verified evidence>" ]
}
"""

CLASSIFY_SYSTEM = """\
You classify one inbound email in a job-hunt pipeline. Return a single JSON
object, no prose, no fences.

Never recommend an automatic reply to an offer, compensation discussion, or an
ambiguous message - set needs_human true and recommended_action "escalate".

JSON schema (all fields required):
{
  "type": "application_receipt" | "recruiter_reply" | "assessment" |
          "interview_invite" | "rejection" | "offer" | "unknown",
  "company": "<company or null>",
  "role": "<role or null>",
  "confidence": number 0-1,
  "recommended_action": "mark_acknowledged" | "draft_reply" | "create_task" |
                        "prepare_interview" | "record_and_stop" | "escalate" | "manual_review",
  "needs_human": boolean
}
"""

CONNECTION_SYSTEM = """\
An accepted LinkedIn connection needs a short, honest draft message. Use only the
connection's headline and OUR open jobs at their company. Return a single JSON
object, no prose, no fences.

- Infer person_type from the headline only.
- If one of our open jobs is a genuine fit, set matched_job_key to that job_key
  and write a referral-oriented draft. Otherwise leave it null and write a
  networking-only draft.
- Never fabricate a job, a mutual connection, or applicant experience.
- The message is sent manually by the user; keep it under 90 words.

JSON schema (all fields required):
{
  "person_type": "employee" | "founder" | "recruiter" | "unknown",
  "company": "<company or null>",
  "matched_job_key": "<job_key from the provided list, or null>",
  "job_match_score": number 0-100,
  "draft_message": "<the message>",
  "confidence": number 0-1
}
"""


class ClaudeEvaluation(BaseModel):
    """Validated structured output for a single candidate."""

    score: int = Field(ge=0, le=100)
    priority: str
    evidence_fit: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    human_path_hint: str = ""
    recommended_next_action: str = "store"

    @field_validator("priority")
    @classmethod
    def _priority(cls, value: str) -> str:
        cleaned = str(value or "").strip().upper()
        if cleaned not in PRIORITIES:
            raise ValueError(f"priority must be one of {PRIORITIES}")
        return cleaned

    @field_validator("recommended_next_action")
    @classmethod
    def _next_action(cls, value: str) -> str:
        cleaned = str(value or "").strip().lower().replace(" ", "_")
        return cleaned if cleaned in NEXT_ACTIONS else "store"

    @field_validator("evidence_fit", "gaps", "risks", mode="before")
    @classmethod
    def _string_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return [str(item) for item in value]


class TailoredApplication(BaseModel):
    base_track: str = "AI/GenAI"
    evidence_used: list[str] = Field(default_factory=list)
    resume_markdown: str
    cover_letter: str
    recruiter_email: str
    referral_message: str
    linkedin_message: str
    application_answers: str = ""
    warnings: list[str] = Field(default_factory=list)

    @field_validator("evidence_used", "warnings", mode="before")
    @classmethod
    def _lists(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return [str(v) for v in value]


REPLY_TYPES = (
    "application_receipt",
    "recruiter_reply",
    "assessment",
    "interview_invite",
    "rejection",
    "offer",
    "unknown",
)


class ReplyClassification(BaseModel):
    type: str
    company: str | None = None
    role: str | None = None
    confidence: float = 0.0
    recommended_action: str = "manual_review"
    needs_human: bool = True

    @field_validator("type")
    @classmethod
    def _type(cls, value: str) -> str:
        cleaned = str(value or "").strip().lower()
        return cleaned if cleaned in REPLY_TYPES else "unknown"


class ConnectionResearch(BaseModel):
    person_type: str = "unknown"
    company: str | None = None
    matched_job_key: str | None = None
    job_match_score: float = 0.0
    draft_message: str = ""
    confidence: float = 0.0

    @field_validator("person_type")
    @classmethod
    def _ptype(cls, value: str) -> str:
        cleaned = str(value or "").strip().lower()
        return cleaned if cleaned in {"employee", "founder", "recruiter", "unknown"} else "unknown"


def _profile_snapshot() -> dict[str, Any]:
    from orchestrator.policies import load_yaml

    data = load_yaml(ROOT / "profile" / "master_profile.yaml")
    return {
        "name": data.get("name"),
        "headline": data.get("headline"),
        "location": data.get("location"),
        "experience_years": data.get("experience_years"),
        "summary": data.get("summary"),
        "skills": data.get("skills"),
    }


def _normalize_message(message: Any) -> dict[str, str]:
    if isinstance(message, dict):
        return {
            "sender": str(message.get("sender", message.get("from", ""))),
            "subject": str(message.get("subject", "")),
            "snippet": str(message.get("snippet", message.get("body", ""))),
        }
    return {
        "sender": str(getattr(message, "sender", "")),
        "subject": str(getattr(message, "subject", "")),
        "snippet": str(getattr(message, "snippet", "")),
    }


def _strip_json(text: str) -> str:
    body = (text or "").strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[-1].rsplit("```", 1)[0]
    start, end = body.find("{"), body.rfind("}")
    if start != -1 and end != -1 and end > start:
        return body[start : end + 1]
    return body


class ClaudeProvider(IntelligenceProvider):
    def __init__(
        self,
        *,
        client: Any | None = None,
        model: str | None = None,
        evaluate_buckets: tuple[str, ...] | None = None,
        max_evaluations: int | None = None,
        evidence: list[dict[str, Any]] | None = None,
    ) -> None:
        self._client = client
        self.model = model or os.getenv("CLAUDE_MODEL", DEFAULT_MODEL)
        self.evaluate_buckets = tuple(evaluate_buckets or DEFAULT_EVALUATE_BUCKETS)
        env_cap = os.getenv("CLAUDE_MAX_EVALUATIONS")
        self.max_evaluations = (
            max_evaluations
            if max_evaluations is not None
            else int(env_cap) if env_cap else DEFAULT_MAX_EVALUATIONS
        )
        self._evidence_override = evidence

    # -- client ---------------------------------------------------------------
    @property
    def client(self) -> Any:
        if self._client is None:
            import anthropic  # lazy: no import cost / API key needed for mock mode

            self._client = anthropic.Anthropic()
        return self._client

    def _evidence_bank(self, evidence: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        if evidence:
            return evidence
        if self._evidence_override is not None:
            return self._evidence_override
        return load_evidence(ROOT / "profile" / "evidence_bank.yaml")

    # -- IntelligenceProvider ----------------------------------------------------
    def evaluate_jobs(
        self, candidates: list[Candidate], evidence: list[dict[str, Any]]
    ) -> list[Candidate]:
        bank = self._evidence_bank(evidence)
        valid_ids = {str(item.get("id")) for item in bank}
        evaluated_count = 0
        output: list[Candidate] = []

        for candidate in candidates:
            updated = candidate.model_copy(deep=True)
            if candidate.score.bucket not in self.evaluate_buckets:
                updated.intelligence = self._skip_verdict(
                    candidate, "below_evaluation_threshold"
                )
                output.append(updated)
                continue
            if evaluated_count >= self.max_evaluations:
                updated.intelligence = self._skip_verdict(candidate, "capacity_reached")
                output.append(updated)
                continue

            evaluated_count += 1
            updated.intelligence = self._evaluate_one(candidate, bank, valid_ids)
            output.append(updated)

        return output

    def tailor_application(self, job: Job, evidence: list[dict[str, Any]]) -> dict[str, Any]:
        bank = self._evidence_bank(evidence)
        valid_ids = {str(item.get("id")) for item in bank}
        user_content = json.dumps(
            {
                "job": {
                    "company": job.company,
                    "title": job.title,
                    "location": job.location,
                    "url": job.url,
                    "jd": job.description,
                },
                "verified_evidence": _evidence_for_prompt(bank),
                "profile": _profile_snapshot(),
            },
            sort_keys=True,
            default=str,
        )
        try:
            raw = self._call_claude(user_content, system=TAILOR_SYSTEM, max_tokens=4000)
            tailored = TailoredApplication.model_validate_json(_strip_json(raw))
        except NotImplementedError:
            raise
        except (ValidationError, json.JSONDecodeError, ValueError) as exc:
            return {"status": "error", "provider": "claude", "error": f"invalid_structured_output: {exc}", "files": {}}
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "provider": "claude", "error": f"claude_call_failed: {exc}", "files": {}}

        _, dropped = _partition_evidence_fit(tailored.evidence_used, valid_ids)
        warnings = list(tailored.warnings)
        if dropped:
            warnings.append("dropped unverified evidence references: " + ", ".join(dropped))
        return {
            "status": "prepared",
            "provider": "claude",
            "model": self.model,
            "base_track": tailored.base_track,
            "evidence_used": [e for e in tailored.evidence_used if e.split(":", 1)[0].strip() in valid_ids],
            "warnings": warnings,
            "files": {
                "resume.md": tailored.resume_markdown,
                "cover_letter.md": tailored.cover_letter,
                "recruiter_email.txt": tailored.recruiter_email,
                "referral_message.txt": tailored.referral_message,
                "linkedin_message.txt": tailored.linkedin_message,
                "application_answers.md": tailored.application_answers,
            },
        }

    def classify_reply(self, message: Any) -> dict[str, Any]:
        normalized = _normalize_message(message)
        user_content = json.dumps(normalized, sort_keys=True)
        try:
            raw = self._call_claude(user_content, system=CLASSIFY_SYSTEM, max_tokens=800)
            result = ReplyClassification.model_validate_json(_strip_json(raw))
        except NotImplementedError:
            raise
        except Exception as exc:  # noqa: BLE001 - fall back to the deterministic classifier
            from gmail.classifier import GmailMessage, classify_message

            fallback = classify_message(
                GmailMessage(
                    sender=normalized.get("sender", ""),
                    subject=normalized.get("subject", ""),
                    snippet=normalized.get("snippet", ""),
                )
            )
            fallback.update({"provider": "deterministic_fallback", "error": str(exc)})
            return fallback

        never_auto = result.type in {"offer", "unknown"}
        return {
            "type": result.type,
            "company": result.company,
            "role": result.role,
            "confidence": result.confidence,
            "recommended_action": result.recommended_action,
            "needs_human": result.needs_human or never_auto,
            "provider": "claude",
            "model": self.model,
        }

    def research_connection(
        self, connection: dict[str, Any], company_jobs: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        jobs = company_jobs or []
        user_content = json.dumps(
            {
                "connection": {
                    "name": connection.get("name"),
                    "headline": connection.get("headline") or connection.get("current_title"),
                    "location": connection.get("location"),
                },
                "our_open_jobs_at_their_company": [
                    {"job_key": j.get("job_key"), "title": j.get("title"), "company": j.get("company"),
                     "location": j.get("location"), "url": j.get("url")}
                    for j in jobs
                ],
                "profile": _profile_snapshot(),
            },
            sort_keys=True,
            default=str,
        )
        try:
            raw = self._call_claude(user_content, system=CONNECTION_SYSTEM, max_tokens=1500)
            result = ConnectionResearch.model_validate_json(_strip_json(raw))
        except NotImplementedError:
            raise
        except Exception as exc:  # noqa: BLE001
            return {
                "person_type": "unknown",
                "company": None,
                "matched_job_key": None,
                "draft_kind": "networking",
                "draft_message": "",
                "confidence": 0.0,
                "needs_human": True,
                "status": "manual_review",
                "error": f"claude_call_failed: {exc}",
                "provider": "claude",
            }

        valid_keys = {j.get("job_key") for j in jobs}
        matched = result.matched_job_key if result.matched_job_key in valid_keys else None
        return {
            "person_type": result.person_type,
            "company": result.company,
            "matched_job_key": matched,
            "job_match_score": result.job_match_score,
            "draft_kind": "referral" if matched else "networking",
            "draft_message": result.draft_message,
            "confidence": result.confidence,
            "needs_human": True,
            "status": "awaiting_approval",
            "provider": "claude",
            "model": self.model,
        }

    def prepare_interview(self, application: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(
            "prepare_interview is an R4 target (interview mode). Keep CLAUDE_MODE=mock."
        )

    # -- internals -------------------------------------------------------------
    def _skip_verdict(self, candidate: Candidate, reason: str) -> dict[str, Any]:
        pre_score = candidate.score.pre_score
        priority = "P1" if pre_score >= 68 else "P2"
        return {
            "provider": "claude",
            "model": self.model,
            "verdict": "not_evaluated",
            "reason": reason,
            "priority": priority,
            "pre_score": pre_score,
            "needs_human": reason == "capacity_reached",
        }

    def _evaluate_one(
        self,
        candidate: Candidate,
        bank: list[dict[str, Any]],
        valid_ids: set[str],
    ) -> dict[str, Any]:
        payload = candidate_payload(candidate, bank)
        user_content = json.dumps(
            {"candidate": payload, "verified_evidence": _evidence_for_prompt(bank)},
            sort_keys=True,
            default=str,
        )
        try:
            raw_text = self._call_claude(user_content)
            evaluation = ClaudeEvaluation.model_validate_json(_strip_json(raw_text))
        except NotImplementedError:
            raise
        except (ValidationError, json.JSONDecodeError, ValueError) as exc:
            return self._error_verdict(candidate, f"invalid_structured_output: {exc}")
        except Exception as exc:  # noqa: BLE001 - surface transport failures, keep the job
            return self._error_verdict(candidate, f"claude_call_failed: {exc}")

        kept_fit, dropped_fit = _partition_evidence_fit(evaluation.evidence_fit, valid_ids)
        warnings: list[str] = []
        if dropped_fit:
            warnings.append(
                "dropped unverified evidence references: " + ", ".join(dropped_fit)
            )

        return {
            "provider": "claude",
            "model": self.model,
            "verdict": "evaluated",
            "priority": evaluation.priority,
            "score": evaluation.score,
            "pre_score": candidate.score.pre_score,
            "evidence_fit": kept_fit,
            "gaps": evaluation.gaps,
            "risks": evaluation.risks,
            "human_path_hint": evaluation.human_path_hint,
            "recommended_next_action": evaluation.recommended_next_action,
            "needs_human": evaluation.priority in {"P0", "P1"},
            "reason": _summarise(evaluation),
            "warnings": warnings,
        }

    def _error_verdict(self, candidate: Candidate, error: str) -> dict[str, Any]:
        return {
            "provider": "claude",
            "model": self.model,
            "verdict": "error",
            "error": error,
            "priority": "P2",
            "pre_score": candidate.score.pre_score,
            "needs_human": True,
            "reason": "Claude evaluation failed; deterministic pre-score only. Human review required.",
        }

    def _call_claude(self, user_content: str, system: str = SYSTEM_PROMPT, max_tokens: int = 2000) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_content}],
        )
        parts = [
            block.text
            for block in getattr(response, "content", [])
            if getattr(block, "type", None) == "text"
        ]
        if not parts:
            raise ValueError("Claude response contained no text block")
        return "".join(parts)


def _evidence_for_prompt(bank: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trimmed: list[dict[str, Any]] = []
    for item in bank:
        trimmed.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "type": item.get("type"),
                "claims": item.get("claims", []),
                "technologies": item.get("technologies", []),
                "metrics": item.get("metrics", []),
            }
        )
    return trimmed


def _partition_evidence_fit(
    fit: list[str], valid_ids: set[str]
) -> tuple[list[str], list[str]]:
    kept: list[str] = []
    dropped: list[str] = []
    for line in fit:
        head = line.split(":", 1)[0].strip()
        if head and head not in valid_ids and head.lower() not in {i.lower() for i in valid_ids}:
            dropped.append(head)
        else:
            kept.append(line)
    return kept, dropped


def _summarise(evaluation: ClaudeEvaluation) -> str:
    lead = evaluation.evidence_fit[0] if evaluation.evidence_fit else "No clear verified fit."
    gap = f" Gap: {evaluation.gaps[0]}." if evaluation.gaps else ""
    return f"{evaluation.priority} · Claude score {evaluation.score}. {lead}{gap}"
