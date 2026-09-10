from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from orchestrator.models import Candidate
from telegram.cards import (
    candidate_card,
    demo_dashboard_messages,
    inline_buttons,
    naukri_buttons,
    naukri_card,
)


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

    def send_document(
        self,
        path: Path | str,
        caption: str | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.configured:
            return {"ok": False, "skipped": True, "reason": "Telegram not configured"}
        target = Path(path)
        payload: dict[str, Any] = {"chat_id": self.chat_id}
        if caption:
            payload["caption"] = caption[:1024]
        if reply_markup:
            payload["reply_markup"] = reply_markup
        with target.open("rb") as fh:
            response = requests.post(
                f"https://api.telegram.org/bot{self.token}/sendDocument",
                data=payload,
                files={"document": (target.name, fh)},
                timeout=self.timeout_seconds,
            )
        response.raise_for_status()
        return response.json()

    def get_updates(self, offset: int | None = None, timeout: int = 30) -> dict[str, Any]:
        if not self.configured:
            return {"ok": False, "result": [], "skipped": True}
        params: dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        response = requests.get(
            f"https://api.telegram.org/bot{self.token}/getUpdates",
            params=params,
            timeout=timeout + 5,
        )
        response.raise_for_status()
        return response.json()

    def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> dict[str, Any]:
        if not self.configured:
            return {"ok": False, "skipped": True}
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        response = requests.post(
            f"https://api.telegram.org/bot{self.token}/answerCallbackQuery",
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def _try_send(self, text: str, markup: dict[str, Any] | None) -> dict[str, Any]:
        try:
            return self.send_message(text, markup)
        except Exception as exc:  # noqa: BLE001 - one failed card must not abort a run
            print(f"telegram send failed: {type(exc).__name__}: {exc}", flush=True)
            return {"ok": False, "error": str(exc)}

    def send_candidates(self, candidates: list[Candidate]) -> list[str]:
        sent: list[str] = []
        for candidate in candidates:
            if candidate.score.bucket == "weak":
                continue
            if self._try_send(candidate_card(candidate), inline_buttons(candidate)).get("ok"):
                sent.append(candidate.job_key)
        return sent

    def send_naukri_candidates(self, candidates: list[Candidate]) -> list[str]:
        """Naukri cards carry OPEN/APPLY links only - no prepare/automation buttons."""
        sent: list[str] = []
        for candidate in candidates:
            if candidate.score.bucket == "weak":
                continue
            if self._try_send(naukri_card(candidate), naukri_buttons(candidate)).get("ok"):
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
