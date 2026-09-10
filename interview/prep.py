"""Interview prep pack generation.

Deterministic scaffold that works in ``CLAUDE_MODE=mock``. Every STAR story and
every matrix row is built from ``profile/evidence_bank.yaml`` only; anything the
job description asks for that the evidence bank does not support is written as
``NEEDS_CONFIRMATION`` rather than invented. When ``CLAUDE_MODE=claude`` and a
provider is supplied, its ``prepare_interview`` output is merged in as prose,
but the evidence citations below are authoritative.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from orchestrator.policies import load_evidence

_STOPWORDS = {"the", "and", "for", "with", "you", "our", "are", "will", "have", "this", "that"}


def _jd_terms(jd: str) -> set[str]:
    return {w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9+.#/-]{2,}", (jd or "").lower()) if w not in _STOPWORDS}


def _evidence_hits(jd_terms: set[str], evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hits = []
    for item in evidence:
        techs = {str(t).lower() for t in item.get("technologies", [])}
        overlap = sorted(techs & jd_terms)
        if overlap:
            hits.append({"id": item.get("id"), "title": item.get("title"),
                         "overlap": overlap, "claims": item.get("claims", [])})
    return hits


def jd_evidence_matrix(jd: str, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    terms = _jd_terms(jd)
    hits = _evidence_hits(terms, evidence)
    covered = {t for h in hits for t in h["overlap"]}
    rows = [
        {"requirement": ", ".join(h["overlap"]), "evidence_id": h["id"],
         "support": h["claims"][0] if h["claims"] else "see evidence bank"}
        for h in hits
    ]
    # Notable JD asks with no verified evidence -> NEEDS_CONFIRMATION
    notable = {"kubernetes", "terraform", "spark", "kafka", "pytorch", "tensorflow",
               "airflow", "snowflake", "aws", "gcp", "azure", "llm", "rag", "fastapi"}
    for ask in sorted((notable & terms) - covered):
        rows.append({"requirement": ask, "evidence_id": "NEEDS_CONFIRMATION",
                     "support": f"JD mentions {ask}; no verified evidence — confirm before claiming"})
    return rows


def star_stories(jd: str, evidence: list[dict[str, Any]], limit: int = 4) -> list[dict[str, str]]:
    hits = _evidence_hits(_jd_terms(jd), evidence)
    stories = []
    for h in hits[:limit]:
        claims = h["claims"]
        stories.append({
            "evidence_id": h["id"],
            "situation": f"{h['title']} (verified evidence: {h['id']}).",
            "task": claims[0] if claims else "NEEDS_CONFIRMATION — add a claim to the evidence bank",
            "action": claims[1] if len(claims) > 1 else (claims[0] if claims else "NEEDS_CONFIRMATION"),
            "result": "State only outcomes present in the evidence bank; otherwise say 'impact not quantified'.",
            "relevant_to": ", ".join(h["overlap"]),
        })
    if not stories:
        stories.append({"evidence_id": "NEEDS_CONFIRMATION",
                        "situation": "No verified evidence overlaps this JD.",
                        "task": "", "action": "", "result": "",
                        "relevant_to": "update profile/evidence_bank.yaml"})
    return stories


def technical_questions(jd: str, evidence: list[dict[str, Any]]) -> list[str]:
    terms = sorted({t for h in _evidence_hits(_jd_terms(jd), evidence) for t in h["overlap"]})
    base = [
        "Walk through a system you built end to end and the trade-offs you made.",
        "How do you decide when an LLM/heuristic split is the right design?",
        "How do you test and monitor a data or ML pipeline in production?",
    ]
    return base + [f"Deep-dive: your hands-on experience with {t} and its failure modes." for t in terms[:6]]


def revision_plan_30min(jd: str, evidence: list[dict[str, Any]]) -> list[str]:
    terms = sorted({t for h in _evidence_hits(_jd_terms(jd), evidence) for t in h["overlap"]})[:4]
    plan = ["0-5m: re-read the JD, note the 3 hardest requirements",
            "5-15m: rehearse 2 STAR stories out loud from the evidence bank"]
    for i, t in enumerate(terms):
        plan.append(f"{15 + i * 3}-{18 + i * 3}m: refresh {t} fundamentals + one concrete example")
    plan.append("last 5m: prepare 3 questions to ask; check logistics/timezone")
    return plan


def questions_to_ask(company: str) -> list[str]:
    return [
        f"What does the first 90 days look like for this role at {company}?",
        "What is the biggest technical risk the team is carrying right now?",
        "How is success measured for this role after 6 months?",
        "How do data/ML and product decisions get made here?",
    ]


def thank_you_draft(company: str, role: str, matrix: list[dict[str, Any]]) -> str:
    point = next((r for r in matrix if r["evidence_id"] != "NEEDS_CONFIRMATION"), None)
    line = (
        f" I especially enjoyed discussing {point['requirement']}, which connects to my {point['evidence_id']} work."
        if point else ""
    )
    return (
        f"Hi <name>,\n\nThank you for the time today discussing the {role} role at {company}."
        f"{line} I'm excited about the problem space and happy to share anything else that would help.\n\n"
        f"Best,\nSrinivas"
    )


def build_prep_pack(
    job: Any,
    evidence: list[dict[str, Any]] | None = None,
    event: dict[str, Any] | None = None,
    provider: Any | None = None,
) -> dict[str, Any]:
    evidence = evidence if evidence is not None else load_evidence()
    company = getattr(job, "company", None) or (job.get("company") if isinstance(job, dict) else "the company")
    role = getattr(job, "title", None) or (job.get("title") if isinstance(job, dict) else "the role")
    jd = getattr(job, "description", None) or (job.get("description", "") if isinstance(job, dict) else "")

    matrix = jd_evidence_matrix(jd, evidence)
    pack = {
        "status": "prepared",
        "company": company,
        "role": role,
        "company_brief": f"NEEDS_CONFIRMATION — research {company} (recent news, product, funding) "
                         f"manually or via an approved connector before the interview.",
        "jd_evidence_matrix": matrix,
        "technical_questions": technical_questions(jd, evidence),
        "star_stories": star_stories(jd, evidence),
        "revision_plan_30min": revision_plan_30min(jd, evidence),
        "questions_to_ask": questions_to_ask(company),
        "thank_you_draft": thank_you_draft(company, role, matrix),
        "scheduled_for": (event or {}).get("confirmed_datetime_iso"),
    }
    if provider is not None:
        try:
            enrich = provider.prepare_interview({"company": company, "role": role, "jd": jd})
            if isinstance(enrich, dict) and enrich.get("status") not in {"mock", None}:
                pack["claude_notes"] = enrich
        except NotImplementedError:
            pass
        except Exception as exc:  # noqa: BLE001
            pack["claude_error"] = str(exc)
    return pack


def render_prep_pack(pack: dict[str, Any]) -> str:
    lines = [f"# Interview Prep — {pack['company']} · {pack['role']}", ""]
    if pack.get("scheduled_for"):
        lines += [f"**Scheduled:** {pack['scheduled_for']}", ""]
    lines += ["## Company brief", pack["company_brief"], "", "## JD → evidence matrix", ""]
    lines += ["| Requirement | Evidence id | Support |", "|---|---|---|"]
    for row in pack["jd_evidence_matrix"]:
        lines.append(f"| {row['requirement']} | {row['evidence_id']} | {row['support']} |")
    lines += ["", "## Likely technical questions", ""]
    lines += [f"- {q}" for q in pack["technical_questions"]]
    lines += ["", "## STAR stories (evidence bank only)", ""]
    for s in pack["star_stories"]:
        lines += [f"### {s['evidence_id']} — relevant to {s['relevant_to']}",
                  f"- **S:** {s['situation']}", f"- **T:** {s['task']}",
                  f"- **A:** {s['action']}", f"- **R:** {s['result']}", ""]
    lines += ["## 30-minute revision plan", ""]
    lines += [f"- {p}" for p in pack["revision_plan_30min"]]
    lines += ["", "## Questions to ask", ""]
    lines += [f"- {q}" for q in pack["questions_to_ask"]]
    lines += ["", "## Thank-you draft", "", "```", pack["thank_you_draft"], "```", ""]
    return "\n".join(lines)


def write_prep_pack(pack: dict[str, Any], root: Path | str = "artifacts/generated") -> Path:
    from application.artifacts import slugify

    path = Path(root) / slugify(str(pack["company"])) / slugify(str(pack["role"]))
    path.mkdir(parents=True, exist_ok=True)
    out = path / "interview_prep.md"
    out.write_text(render_prep_pack(pack), encoding="utf-8")
    return out


# Back-compat
def prepare_interview_pack(application: dict) -> dict[str, str]:
    pack = build_prep_pack(application)
    return {"status": pack["status"], "company": str(pack["company"]), "role": str(pack["role"])}
