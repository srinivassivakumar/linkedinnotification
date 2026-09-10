from __future__ import annotations

import json

from application import drafts
from application.drafts import deliver_one, list_pending
from intelligence.mock import MockProvider
from orchestrator.models import Candidate, Job, ScoreResult
from orchestrator.policies import load_evidence
from state.store import SqliteStore
from telegram import callback_worker
from telegram.callback_worker import handle_callback

EVIDENCE = load_evidence()


class FakeBot:
    configured = True

    def __init__(self):
        self.sent = []
        self.answers = []
        self.docs = []

    def answer_callback_query(self, cid, text=None):
        self.answers.append((cid, text))
        return {"ok": True}

    def send_message(self, text, reply_markup=None):
        self.sent.append(text)
        return {"ok": True}

    def send_document(self, path, caption=""):
        self.docs.append((str(path), caption))
        return {"ok": True}


def _candidate() -> Candidate:
    job = Job(
        source="greenhouse", source_job_id="ai1", company="Acme Cloud", title="AI Engineer",
        url="https://jobs.example.com/acme/ai", description="Python FastAPI Docker AWS RAG LLM " * 20,
    )
    return Candidate(
        job=job,
        score=ScoreResult(pre_score=88, bucket="strong_candidate", signals={"evidence_overlap": 20},
                          matched_evidence_ids=["aws_backup_infrastructure"], matched_terms=["python", "aws"]),
        intelligence={"provider": "claude", "priority": "P0", "verdict": "evaluated"},
    )


def _store(tmp_path) -> SqliteStore:
    store = SqliteStore(tmp_path / "s.db")
    store.persist([_candidate()])
    return store


def test_mock_button_queues_instead_of_placeholder(tmp_path):
    store = _store(tmp_path)
    bot = FakeBot()
    key = _candidate().job_key

    result = handle_callback(f"resume:{key}", "cb1", bot, store, MockProvider())

    assert result == "queued:resume"
    assert store.pending_draft_requests()[0]["kind"] == "resume"
    assert "QUEUED FOR CLAUDE" in bot.sent[0]
    # a second press does not pile up
    handle_callback(f"resume:{key}", "cb2", bot, store, MockProvider())
    assert len(store.pending_draft_requests()) == 1


def test_list_pending_carries_job_and_evidence(tmp_path):
    store = _store(tmp_path)
    store.enqueue_draft_request(_candidate().job_key, "email")

    payload = list_pending(store, artifact_root=tmp_path / "art")

    assert payload["pending_count"] == 1
    item = payload["pending"][0]
    assert item["kind"] == "email"
    assert item["job"]["company"] == "Acme Cloud"
    assert item["write_files"] == ["recruiter_email.txt"]
    assert item["matched_evidence_ids"] == ["aws_backup_infrastructure"]
    assert payload["evidence_bank"], "evidence bank should be included for grounding"


def test_deliver_uses_written_files_and_marks_delivered(tmp_path, monkeypatch):
    store = _store(tmp_path)
    art_root = tmp_path / "artifacts" / "generated"
    monkeypatch.setattr(callback_worker, "ROOT", tmp_path)
    rid = store.enqueue_draft_request(_candidate().job_key, "email")

    # not ready before the Claude session writes anything
    early = deliver_one(store, FakeBot(), MockProvider(), rid, artifact_root=art_root)
    assert early["status"] == "not_ready"

    # the Claude session writes the real file
    written_dir = art_root / "acme-cloud" / "ai-engineer"
    written_dir.mkdir(parents=True, exist_ok=True)
    (written_dir / "recruiter_email.txt").write_text(
        "Hi - I built AWS backup infrastructure (aws_backup_infrastructure) and would love to discuss the AI Engineer role.",
        encoding="utf-8",
    )

    bot = FakeBot()
    result = deliver_one(store, bot, MockProvider(), rid, artifact_root=art_root)

    assert result["status"] == "ok"
    assert result["result"] == "email_draft_sent"
    assert any("RECRUITER EMAIL DRAFT" in m for m in bot.sent)
    assert any("aws_backup_infrastructure" in m for m in bot.sent)
    assert (written_dir / drafts.MARKER).exists()
    assert store.get_draft_request(rid)["status"] == "delivered"
    assert store.pending_draft_requests() == []

    # once tailored (marker present under the patched ROOT), the button serves
    # the real draft immediately instead of queueing again
    assert callback_worker._has_real_draft(_candidate()) is True
    again = handle_callback(f"email:{_candidate().job_key}", "cb9", bot, store, MockProvider())
    assert again == "email_draft_sent"
    assert store.pending_draft_requests() == []
