from __future__ import annotations

import base64

import pytest

from gmail.classifier import classify_email
from gmail.watcher import process_message
from state.store import SqliteStore

CASES = [
    ("recruiter reply", "recruiter@acme.com", "A role at Acme for you",
     "Our recruiter reached out about your profile", "recruiter_reply", True),
    ("assessment", "no-reply@acme.com", "Coding challenge for MLE role",
     "Please complete this HackerRank take-home", "assessment", True),
    ("interview invite", "ta@acme.com", "Interview with Acme",
     "Can we schedule a call for a screening call?", "interview_invite", True),
    ("rejection", "no-reply@acme.com", "Update on your application",
     "Unfortunately we are not moving forward with other candidates", "rejection", False),
    ("offer", "hr@acme.com", "Your offer from Acme",
     "We are pleased to offer you. CTC and compensation details attached", "offer", True),
    ("naukri alert", "alerts@naukri.com", "12 new jobs for you",
     "Recommended jobs matching AI Engineer", "naukri_alert", True),
    ("linkedin accepted", "invitations@linkedin.com", "Priya accepted your invitation to connect",
     "You can now message Priya", "linkedin_accepted", True),
    ("application receipt", "no-reply@acme.com", "We have received your application",
     "Thank you for applying to Acme", "application_receipt", False),
    ("unknown", "friend@example.com", "lunch?", "are you free thursday", "unknown", True),
]


@pytest.mark.parametrize("label,sender,subject,snippet,expected,needs_human", CASES)
def test_deterministic_classifier_covers_every_class(label, sender, subject, snippet, expected, needs_human):
    result = classify_email(sender, subject, snippet)
    assert result["type"] == expected, label
    assert result["needs_human"] is needs_human, label
    assert result["recommended_action"]


def test_offer_and_ambiguous_always_need_human():
    assert classify_email("hr@x.com", "compensation discussion", "")["needs_human"] is True
    assert classify_email("x@x.com", "???", "")["needs_human"] is True


# -- end-to-end through the watcher (deterministic mode) --------------------

def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


class FakeBot:
    configured = True

    def __init__(self):
        self.sent: list[str] = []

    def send_message(self, text, reply_markup=None):
        self.sent.append(text)
        return {"ok": True}


class FakeProvider:
    def classify_reply(self, message):  # not used in mock mode
        raise AssertionError("Claude must not be called in mock mode")

    def research_connection(self, connection, company_jobs=None):
        return {"person_type": "unknown", "company": None, "matched_job_key": None,
                "job_match_score": 0.0, "draft_kind": "networking", "draft_message": "",
                "confidence": 0.0, "needs_human": True, "status": "awaiting_approval"}


class FakeGmail:
    def __init__(self, messages):
        self._messages = messages

    def users(self):
        return self

    def messages(self):
        return self

    def get(self, userId, id, format):
        self._last = self._messages[id]
        return self

    def execute(self):
        return self._last


def _msg(subject, sender, plain=""):
    return {
        "snippet": plain[:120],
        "payload": {
            "headers": [{"name": "Subject", "value": subject}, {"name": "From", "value": sender}],
            "parts": [{"mimeType": "text/plain", "body": {"data": _b64(plain)}}] if plain else [],
        },
    }


def test_interview_invite_builds_prep_pack_and_no_calendar(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_MODE", "mock")
    monkeypatch.chdir(tmp_path)
    gmail = FakeGmail({
        "i1": _msg(
            "Interview with Acme for AI Engineer",
            "ta@acme.com",
            "Can we schedule a call on 2026-09-20 15:00 for a screening call?",
        )
    })
    store = SqliteStore(tmp_path / "s.db")
    bot = FakeBot()
    result = process_message(gmail, "i1", store, FakeProvider(), bot)
    assert result == "reply:interview_invite"
    prep = tmp_path / "artifacts" / "generated"
    assert list(prep.rglob("interview_prep.md"))
    assert any("Calendar event is NOT created" in s for s in bot.sent)
    types = [e["type"] for e in store.recent_events()]
    assert "interview_prep_ready" in types


def test_watcher_persists_event_and_escalates_offer(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_MODE", "mock")
    gmail = FakeGmail({"o1": _msg("Your offer from Acme", "hr@acme.com", "compensation and CTC details")})
    store = SqliteStore(tmp_path)
    bot = FakeBot()
    result = process_message(gmail, "o1", store, FakeProvider(), bot)
    assert result == "reply:offer"
    assert any("ESCALATE" in s for s in bot.sent)
    events = [e for e in store.recent_events() if e["type"] == "email_classified"]
    assert events and store.email_processed("o1")
