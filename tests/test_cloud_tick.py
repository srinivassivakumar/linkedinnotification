from __future__ import annotations

from orchestrator.models import Candidate, Job, ScoreResult
from state.store import SqliteStore
from telegram.callback_worker import drain_callbacks


class FakeBot:
    configured = True

    def __init__(self, updates):
        self._updates = updates
        self.sent = []
        self.answers = []

    def get_updates(self, offset=None, timeout=30):
        self._last_offset = offset
        if offset is not None:
            return {"result": [u for u in self._updates if u["update_id"] >= offset]}
        return {"result": list(self._updates)}

    def answer_callback_query(self, cid, text=None):
        self.answers.append(text)
        return {"ok": True}

    def send_message(self, text, reply_markup=None):
        self.sent.append(text)
        return {"ok": True}


def _cb(update_id, data):
    return {"update_id": update_id, "callback_query": {"id": f"c{update_id}", "data": data}}


def _persist_job(store):
    cand = Candidate(
        job=Job(source="greenhouse", source_job_id="1", company="Acme", title="MLE", url="https://x"),
        score=ScoreResult(pre_score=70, bucket="strong_candidate", signals={"freshness": 15}),
    )
    store.persist([cand])
    return cand.job_key


def test_drain_processes_pending_and_advances_offset(tmp_path):
    store = SqliteStore(tmp_path)
    job_key = _persist_job(store)
    bot = FakeBot([_cb(10, f"skip:{job_key}"), _cb(11, f"why:{job_key}")])

    out = drain_callbacks(bot, store, None)
    assert out["status"] == "ok" and out["processed"] == 2
    assert store.get_runtime("telegram_callback_offset") == "12"

    # a second run with the same updates must not reprocess them
    out2 = drain_callbacks(bot, store, None)
    assert out2["processed"] == 0


def test_drain_skips_when_telegram_not_configured(tmp_path):
    class Off(FakeBot):
        configured = False

    store = SqliteStore(tmp_path)
    out = drain_callbacks(Off([]), store, None)
    assert out["status"] == "skipped"
