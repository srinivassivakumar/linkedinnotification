from __future__ import annotations

import base64

from gmail.watcher import process_message
from state.store import SqliteStore


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


class FakeBot:
    configured = True

    def __init__(self):
        self.sent = []

    def send_message(self, text, reply_markup=None):
        self.sent.append(text)
        return {"ok": True}


class FakeProvider:
    def classify_reply(self, message):
        return {
            "type": "interview_invite",
            "company": "Acme",
            "role": "MLE",
            "confidence": 0.9,
            "recommended_action": "prepare_interview",
            "needs_human": True,
            "provider": "fake",
        }

    def research_connection(self, connection, company_jobs=None):
        return {
            "person_type": "employee", "company": "Acme Cloud", "matched_job_key": None,
            "job_match_score": 0.0, "draft_kind": "networking", "draft_message": "hi",
            "confidence": 0.5, "needs_human": True, "status": "awaiting_approval",
        }


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


def _msg(subject, sender, html="", plain=""):
    parts = []
    if html:
        parts.append({"mimeType": "text/html", "body": {"data": _b64(html)}})
    if plain:
        parts.append({"mimeType": "text/plain", "body": {"data": _b64(plain)}})
    return {
        "snippet": "snippet text",
        "payload": {
            "headers": [{"name": "Subject", "value": subject}, {"name": "From", "value": sender}],
            "parts": parts,
        },
    }


LINKEDIN_HTML = """
<p>Priya Sharma</p><p>ML Engineer at Acme Cloud</p><p>India</p>
<a href="https://www.linkedin.com/comm/in/priya-sharma-1">profile</a>
"""


def test_linkedin_acceptance_is_routed_to_connection_card(tmp_path):
    gmail = FakeGmail({
        "m1": _msg("Priya accepted your invitation to connect", "LinkedIn <invitations@linkedin.com>", html=LINKEDIN_HTML),
    })
    store = SqliteStore(tmp_path)
    bot = FakeBot()
    result = process_message(gmail, "m1", store, FakeProvider(), bot)
    assert result == "linkedin:carded"
    assert store.email_processed("m1")
    assert any("LINKEDIN CONNECTION" in s for s in bot.sent)


def test_recruiter_reply_is_classified_and_escalated(tmp_path):
    gmail = FakeGmail({
        "m2": _msg("Interview with Acme", "recruiter@acme.com", plain="Can we schedule a call?"),
    })
    store = SqliteStore(tmp_path)
    bot = FakeBot()
    result = process_message(gmail, "m2", store, FakeProvider(), bot)
    assert result == "reply:interview_invite"
    assert any("ESCALATE" in s for s in bot.sent)
    # idempotent
    assert process_message(gmail, "m2", store, FakeProvider(), bot) == "skipped:already_processed"
