from __future__ import annotations

from pathlib import Path

from intelligence.provider import get_intelligence_provider
from orchestrator.pipeline import build_candidates, load_evidence, load_fixture, load_preferences, load_sources_config
from telegram.cards import (
    DashboardSnapshot,
    FocusItem,
    candidate_card,
    demo_dashboard_messages,
    focus_card,
    home_buttons,
    home_card,
    inline_buttons,
    today_card,
)


FIXTURE = Path("tests/fixtures/golden_jobs.json")


def _candidates():
    jobs = load_fixture(FIXTURE)
    candidates, _ = build_candidates(jobs, load_preferences(), load_evidence(), load_sources_config())
    return get_intelligence_provider("mock").evaluate_jobs(candidates, load_evidence())


def test_candidate_card_uses_operations_console_structure() -> None:
    candidate = _candidates()[0]
    text = candidate_card(candidate)
    buttons = inline_buttons(candidate)

    assert "JOB ·" in text
    assert "Human Path" in text
    assert "Application" in text
    assert buttons["inline_keyboard"][0][0]["text"] == "🚀 PREPARE APPLICATION"
    assert buttons["inline_keyboard"][1][0]["text"] == "🌐 OPEN JOB"


def test_home_today_and_focus_cards_are_compact() -> None:
    snapshot = DashboardSnapshot(p0_jobs=2, p1_jobs=4, replies=1, interviews=1, followups=2, applied_today=3)

    assert "SRI CAREER AGENT" in home_card(snapshot)
    assert len(home_buttons()["inline_keyboard"]) == 4
    assert "TODAY" in today_card(snapshot, "Red Hat · Tomorrow 3 PM")
    assert "Claude recommendation" in focus_card(
        [FocusItem("Reply to recruiter", "Waiting 42m")],
        "Handle the recruiter reply first.",
    )


def test_dashboard_preview_contains_main_mini_apps() -> None:
    messages = demo_dashboard_messages(_candidates())
    texts = "\n".join(text for text, _ in messages)

    assert "SRI CAREER AGENT" in texts
    assert "JOB QUEUE" in texts
    assert "WHAT SHOULD I DO NOW?" in texts
    assert "SETTINGS" in texts
