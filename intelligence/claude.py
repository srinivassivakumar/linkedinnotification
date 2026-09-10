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
        raise NotImplementedError(
            "tailor_application is an R2 target (application factory). Keep CLAUDE_MODE=mock."
        )

    def classify_reply(self, message: Any) -> dict[str, Any]:
        raise NotImplementedError(
            "classify_reply is an R4 target (Gmail reply classifier). Keep CLAUDE_MODE=mock."
        )

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

    def _call_claude(self, user_content: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
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
