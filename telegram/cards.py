from __future__ import annotations

from orchestrator.models import Candidate


def candidate_card(candidate: Candidate) -> str:
    job = candidate.job
    score = candidate.score
    matched = ", ".join(score.matched_terms[:8]) or "No verified deterministic overlap yet"
    warnings = "\n".join(f"- {item}" for item in score.warnings[:6]) or "- None"
    return "\n".join(
        [
            f"{score.bucket.upper()} - {score.pre_score} deterministic points",
            job.company,
            job.title,
            job.location or "Location unknown",
            "",
            "Evidence overlap:",
            matched,
            "",
            "Warnings:",
            warnings,
            "",
            "Status: awaiting later intelligence / human review",
            job.url,
        ]
    )


def inline_buttons(candidate: Candidate) -> dict[str, list[list[dict[str, str]]]]:
    return {
        "inline_keyboard": [
            [{"text": "VIEW JOB", "url": candidate.job.url}],
            [
                {"text": "PREPARE", "callback_data": f"prepare:{candidate.job_key}"},
                {"text": "SKIP", "callback_data": f"skip:{candidate.job_key}"},
            ],
        ]
    }

