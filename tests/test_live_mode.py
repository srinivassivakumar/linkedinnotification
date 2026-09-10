from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from intelligence.provider import get_intelligence_provider
from orchestrator import live
from orchestrator.live import LiveAgent, live_scan
from orchestrator.models import Job, SourceResult
from state.store import SqliteStore


class FakeBot:
    configured = True

    def __init__(self):
        self.sent = []
        self.cards = []
        self.answers = []

    def _try_send(self, text, markup=None):
        self.sent.append(text)
        return {"ok": True}

    def send_message(self, text, markup=None):
        self.sent.append(text)
        return {"ok": True}

    def answer_callback_query(self, cid, text=None):
        self.answers.append((cid, text))
        return {"ok": True}

    def send_candidates(self, candidates):
        keys = [c.job_key for c in candidates if c.score.bucket != "weak"]
        self.cards.extend(keys)
        return keys

    def get_updates(self, offset=None, timeout=0):
        return {"ok": True, "result": []}


def _job(jid: str, title: str = "Machine Learning Engineer") -> Job:
    return Job(
        source="greenhouse",
        source_job_id=jid,
        company="Acme Cloud",
        title=title,
        location="Remote India",
        url=f"https://boards.greenhouse.io/acme/jobs/{jid}",
        description="Python FastAPI Docker AWS RAG LLM PostgreSQL machine learning " * 12,
        posted_at=datetime.now(timezone.utc) - timedelta(hours=3),
    )


@pytest.fixture
def patched_sources(monkeypatch):
    jobs = [_job("100", "Machine Learning Engineer"), _job("200", "Data Engineer")]

    def fake_fetch(config, limit=None):
        return list(jobs), [SourceResult(source="greenhouse", fetched=len(jobs))]

    monkeypatch.setattr(live, "fetch_all_sources", fake_fetch)
    return jobs


def test_live_scan_surfaces_each_job_once(tmp_path, patched_sources):
    store = SqliteStore(tmp_path / "s.db")
    bot = FakeBot()
    provider = get_intelligence_provider("mock")

    first = live_scan(store, bot, provider, window_hours=168)
    assert first["new_jobs"] == 2
    assert len(first["notified"]) == 2
    assert store.known_job_keys() == {"greenhouse:100", "greenhouse:200"}

    # same jobs on the next pass -> nothing new, no new cards
    bot.cards.clear()
    second = live_scan(store, bot, provider, window_hours=12)
    assert second["new_jobs"] == 0
    assert bot.cards == []


def test_skipped_job_never_resurfaces(tmp_path, patched_sources):
    store = SqliteStore(tmp_path / "s.db")
    bot = FakeBot()
    provider = get_intelligence_provider("mock")

    live_scan(store, bot, provider, window_hours=168)
    store.set_job_status("greenhouse:100", "skipped")

    bot.cards.clear()
    result = live_scan(store, bot, provider, window_hours=12)
    assert result["new_jobs"] == 0
    assert bot.cards == []


def test_window_widens_only_for_first_scan(tmp_path):
    store = SqliteStore(tmp_path / "s.db")
    agent = LiveAgent(
        store, FakeBot(), scan_provider=get_intelligence_provider("mock"),
        action_provider=get_intelligence_provider("mock"),
        first_window_days=7, scan_window_hours=12,
    )
    assert agent._window_hours() == 7 * 24
    store.set_runtime("live_first_scan_done", "1")
    assert agent._window_hours() == 12


def test_scan_now_callback_is_intercepted(tmp_path, patched_sources, monkeypatch):
    store = SqliteStore(tmp_path / "s.db")
    bot = FakeBot()
    agent = LiveAgent(
        store, bot, scan_provider=get_intelligence_provider("mock"),
        action_provider=get_intelligence_provider("mock"),
    )
    calls = []
    monkeypatch.setattr(agent, "_run_scan", lambda trigger: calls.append(trigger))

    agent._handle_callback({"id": "cb1", "data": "scan:now"})
    assert calls == ["SCAN NOW button"]
    assert bot.answers == [("cb1", "Scanning now…")]


def test_slash_scan_message_triggers_scan(tmp_path, monkeypatch):
    store = SqliteStore(tmp_path / "s.db")
    agent = LiveAgent(
        store, FakeBot(), scan_provider=get_intelligence_provider("mock"),
        action_provider=get_intelligence_provider("mock"),
    )
    calls = []
    monkeypatch.setattr(agent, "_run_scan", lambda trigger: calls.append(trigger))
    agent._handle_message({"text": "/scan"})
    assert calls == ["/scan command"]


def test_claude_cli_provider_parses_envelope(monkeypatch):
    from intelligence import claude_cli

    monkeypatch.setattr(claude_cli, "find_claude_binary", lambda: "claude")
    provider = claude_cli.ClaudeCliProvider()

    class _Proc:
        returncode = 0
        stdout = json.dumps({"type": "result", "subtype": "success", "is_error": False,
                             "result": '{"score": 71, "priority": "P1", "evidence_fit": [], "gaps": [], "risks": [], "human_path_hint": "none obvious", "recommended_next_action": "prepare"}'})
        stderr = ""

    monkeypatch.setattr(claude_cli.subprocess, "run", lambda *a, **k: _Proc())
    text = provider._call_claude("input here")
    assert json.loads(text)["score"] == 71
