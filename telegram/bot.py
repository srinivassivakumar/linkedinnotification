from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv

from orchestrator.models import Candidate
from telegram.cards import candidate_card, demo_dashboard_messages, inline_buttons


class TelegramBot:
    def __init__(self, token: str | None = None, chat_id: str | None = None, timeout_seconds: int = 10):
        load_dotenv()
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def send_message(self, text: str, reply_markup: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.configured:
            return {"ok": False, "skipped": True, "reason": "Telegram not configured"}
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        response = requests.post(url, json=payload, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.json()

    def send_candidates(self, candidates: list[Candidate]) -> list[str]:
        sent: list[str] = []
        for candidate in candidates:
            if candidate.score.bucket == "weak":
                continue
            result = self.send_message(candidate_card(candidate), inline_buttons(candidate))
            if result.get("ok"):
                sent.append(candidate.job_key)
        return sent

    def send_dashboard_preview(self, candidates: list[Candidate]) -> list[str]:
        sent: list[str] = []
        for index, (text, reply_markup) in enumerate(demo_dashboard_messages(candidates), start=1):
            result = self.send_message(text, reply_markup)
            if result.get("ok"):
                sent.append(f"dashboard:{index}")
        return sent

    def notify_test(self) -> dict[str, Any]:
        return self.send_message("Career Agent notify-test: Telegram configured reachable.")
