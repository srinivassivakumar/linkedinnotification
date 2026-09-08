from __future__ import annotations

from dataclasses import dataclass


EVENT_TYPES = {
    "application_receipt",
    "recruiter_reply",
    "assessment",
    "interview_invite",
    "rejection",
    "offer",
    "unknown",
}


@dataclass(frozen=True)
class GmailMessage:
    sender: str = ""
    subject: str = ""
    snippet: str = ""


def classify_message(msg: GmailMessage, known_apps: list[dict] | None = None) -> dict:
    text = f"{msg.sender} {msg.subject} {msg.snippet}".lower()
    if "offer" in text or "compensation" in text:
        return {"type": "offer", "confidence": 0.8, "needs_human": True}
    if "thank you for applying" in text or "received your application" in text:
        return {"type": "application_receipt", "confidence": 0.85, "needs_human": False}
    if "interview" in text or "schedule a call" in text:
        return {"type": "interview_invite", "confidence": 0.9, "needs_human": True}
    if "assessment" in text or "coding test" in text or "take-home" in text:
        return {"type": "assessment", "confidence": 0.9, "needs_human": True}
    if "unfortunately" in text and "application" in text:
        return {"type": "rejection", "confidence": 0.8, "needs_human": False}
    if known_apps and any(str(app.get("company", "")).lower() in text for app in known_apps):
        return {"type": "recruiter_reply", "confidence": 0.65, "needs_human": True}
    return {"type": "unknown", "confidence": 0.0, "needs_human": True}

