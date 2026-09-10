from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from orchestrator.models import Job


class GreenhouseSource:
    name = "greenhouse"

    def __init__(self, board_tokens: list[str], timeout_seconds: int = 15):
        self.board_tokens = board_tokens
        self.timeout_seconds = timeout_seconds
        self.errors: list[str] = []

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        self.errors = []
        for token in self.board_tokens:
            try:
                jobs.extend(self._fetch_board(token))
            except Exception as exc:  # noqa: BLE001 - one bad board must not break the scan
                message = f"greenhouse:{token}: {type(exc).__name__}: {exc}"
                self.errors.append(message)
                print(message, flush=True)
        return jobs

    def _fetch_board(self, token: str) -> list[Job]:
        url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
        response = requests.get(url, params={"content": "true"}, timeout=self.timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        fetched_at = datetime.now(timezone.utc)
        return self._map_all(token, payload.get("jobs", []), fetched_at)

    def _map_all(self, token: str, items: list[Any], fetched_at: datetime) -> list[Job]:
        out: list[Job] = []
        for item in items:
            try:
                out.append(self._map_job(token, item, fetched_at))
            except Exception as exc:  # noqa: BLE001 - skip a single malformed posting
                self.errors.append(f"greenhouse:{token}: skipped 1 posting: {type(exc).__name__}")
        return out

    def _map_job(self, token: str, item: dict[str, Any], fetched_at: datetime) -> Job:
        location = item.get("location") or {}
        return Job(
            source=self.name,
            source_job_id=str(item.get("id")),
            company=token,
            title=item.get("title") or "",
            location=location.get("name") if isinstance(location, dict) else None,
            description=item.get("content") or "",
            url=item.get("absolute_url") or item.get("url") or "",
            posted_at=_parse_datetime(item.get("first_published") or item.get("updated_at")),
            fetched_at=fetched_at,
            employment_type=item.get("employment_type"),
            department=_department_name(item.get("departments")),
            raw=item,
        )


def _department_name(value: Any) -> str | None:
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, dict):
            return first.get("name")
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None

