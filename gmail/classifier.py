"""Deterministic inbound-email classifier.

Runs offline, no model needed - this is the base classifier the Gmail watcher
always uses. When ``CLAUDE_MODE=claude`` the watcher additionally asks
``ClaudeProvider.classify_reply`` to enrich the result, but the safety rules
here always win: offers, compensation and ambiguous mail are never auto-handled.
"""

from __future__ import annotations

from dataclasses import dataclass

EVENT_TYPES = {
    "application_receipt",
    "recruiter_reply",
    "assessment",
    "interview_invite",
    "rejection",
    "offer",
    "naukri_alert",
    "linkedin_accepted",
    "unknown",
}

# type -> (recommended_action, needs_human)
_ACTIONS = {
    "application_receipt": ("mark_acknowledged", False),
    "recruiter_reply": ("draft_reply", True),
    "assessment": ("create_task", True),
    "interview_invite": ("prepare_interview", True),
    "rejection": ("record_and_stop", False),
    "offer": ("escalate", True),
    "naukri_alert": ("manual_review", True),
    "linkedin_accepted": ("manual_review", True),
    "unknown": ("manual_review", True),
}


@dataclass(frozen=True)
class GmailMessage:
    sender: str = ""
    subject: str = ""
    snippet: str = ""


def _match(text: str, *needles: str) -> bool:
    return any(n in text for n in needles)


def classify_email(sender: str = "", subject: str = "", snippet: str = "") -> dict:
    """Return {type, confidence, recommended_action, needs_human, company, role}."""
    text = f"{sender} {subject} {snippet}".lower()

    if "accepted your invitation" in text or ("linkedin" in sender.lower() and "invitation" in text):
        kind, conf = "linkedin_accepted", 0.95
    elif "naukri" in sender.lower() or _match(text, "job alert", "recommended jobs", "jobs for you"):
        kind, conf = "naukri_alert", 0.85
    elif _match(text, "offer letter", "compensation", "ctc", "salary details", "we are pleased to offer", "your offer"):
        kind, conf = "offer", 0.8
    elif _match(text, "unfortunately", "not moving forward", "decided not to proceed", "will not be proceeding", "other candidates"):
        kind, conf = "rejection", 0.8
    elif _match(text, "assessment", "coding test", "coding challenge", "take-home", "hackerrank", "codility", "online test"):
        kind, conf = "assessment", 0.9
    elif _match(text, "interview", "schedule a call", "availability", "book a slot", "meet the team", "screening call"):
        kind, conf = "interview_invite", 0.9
    elif _match(text, "thank you for applying", "received your application", "application received", "we have received"):
        kind, conf = "application_receipt", 0.85
    elif _match(text, "recruiter", "talent", "hiring", "reached out", "opportunity", "your profile", "role at"):
        kind, conf = "recruiter_reply", 0.6
    else:
        kind, conf = "unknown", 0.0

    action, needs_human = _ACTIONS[kind]
    # Safety: never let confidence override the human gate for money/ambiguous mail.
    if kind in {"offer", "unknown"} or conf < 0.5:
        needs_human = True
    return {
        "type": kind,
        "confidence": conf,
        "recommended_action": action,
        "needs_human": needs_human,
        "company": None,
        "role": None,
        "provider": "deterministic",
    }


def classify_message(msg: GmailMessage, known_apps: list[dict] | None = None) -> dict:
    """Back-compat wrapper used by older callers/tests."""
    result = classify_email(msg.sender, msg.subject, msg.snippet)
    if result["type"] == "unknown" and known_apps:
        text = f"{msg.sender} {msg.subject} {msg.snippet}".lower()
        if any(str(app.get("company", "")).lower() in text for app in known_apps if app.get("company")):
            result.update({"type": "recruiter_reply", "confidence": 0.65, "needs_human": True})
    return result
