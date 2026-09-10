"""Career Ops - pinned Apify actors consumed as a normal deterministic source.

This is Option B of the Apify integration: instead of Claude driving Apify through
MCP, the Python scanner calls one or more **explicitly pinned** Apify actors over
the REST API (``run-sync-get-dataset-items``), maps their dataset output to
:class:`~orchestrator.models.Job`, and hands the jobs to the same dedupe / filter
/ score / notify pipeline as Greenhouse, Lever and Ashby.

Guard rails (per the project safety rules - Apify is "discovery only until a
reviewed actor is explicitly approved"):

* Disabled by default (`sources.career_ops.enabled: false`).
* Runs nothing without ``APIFY_TOKEN`` in the environment.
* Every actor is pinned by id in ``config/sources.yaml`` with its own
  ``max_items`` and price; nothing is auto-selected.
* A rolling monthly spend estimate is tracked in the ``runtime`` table and a
  ``monthly_cost_cap_usd`` stops further runs once the cap is reached.
* ``maxItems`` is also sent as a query parameter so Apify itself caps the
  billable dataset size even if an actor ignores its own input field.
"""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from orchestrator.models import Job

ROOT = Path(__file__).resolve().parents[1]
_API_BASE = "https://api.apify.com/v2/acts"
_DEFAULT_CAP_USD = 10.0
_DEFAULT_PRICE_PER_1000 = 5.0
_DEFAULT_MAX_ITEMS = 25


def _clean_url(value: Any) -> str:
    text = str(value or "").strip()
    return re.sub(r"[?#].*$", "", text)


def _stable_id(raw: dict[str, Any], url: str, title: str, company: str, location: str) -> str:
    for key in ("jobId", "job_id", "id", "jobKey", "job_key"):
        if raw.get(key):
            return str(raw[key])
    if url:
        return _clean_url(url)
    digest = hashlib.sha1(f"{title}|{company}|{location}".encode("utf-8")).hexdigest()
    return digest[:16]


def _first(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _naukri_adapter(raw: dict[str, Any]) -> dict[str, Any]:
    """``fervent_bus~naukri-job-scraper-mcp`` dataset item -> Job kwargs."""
    url = _clean_url(_first(raw, "jobUrl", "url", "link"))
    exp_min, exp_max = raw.get("experienceMin"), raw.get("experienceMax")
    experience = None
    if exp_min is not None or exp_max is not None:
        experience = f"{exp_min if exp_min is not None else '?'}-{exp_max if exp_max is not None else '?'} yrs"
    return {
        "title": str(_first(raw, "title", "jobTitle") or "").strip(),
        "company": str(_first(raw, "companyName", "company") or "").strip(),
        "location": _first(raw, "location", "jobLocation"),
        "description": str(_first(raw, "jobDescription", "description") or ""),
        "url": url,
        # The actor returns scrapedAt (when it ran), not the posting date. Leave
        # posted_at unknown - freshness falls back to "unknown" (kept, warned),
        # and the stable job key stops repeat notifications.
        "posted_at": None,
        "raw": {
            "salary": raw.get("salary"),
            "experience": experience,
            "skills": raw.get("skills"),
            "scrapedAt": raw.get("scrapedAt"),
        },
    }


def _generic_adapter(raw: dict[str, Any]) -> dict[str, Any]:
    url = _clean_url(_first(raw, "jobUrl", "url", "link", "applyUrl", "jobPostingUrl"))
    return {
        "title": str(_first(raw, "title", "jobTitle", "position", "name") or "").strip(),
        "company": str(_first(raw, "companyName", "company", "companyName", "organization", "employer") or "").strip(),
        "location": _first(raw, "location", "jobLocation", "city", "place"),
        "description": str(_first(raw, "descriptionText", "jobDescription", "description", "jobDescriptionText") or ""),
        "url": url,
        "posted_at": _parse_dt(_first(raw, "postedAt", "postedDate", "publishedAt", "datePosted", "listedAt")),
        "raw": {k: raw.get(k) for k in ("salary", "salaryInfo", "experience", "skills", "seniority", "employmentType") if raw.get(k) is not None},
    }


_ADAPTERS = {
    "naukri": _naukri_adapter,
    "fervent_bus~naukri-job-scraper-mcp": _naukri_adapter,
    "generic": _generic_adapter,
}


class CareerOpsSource:
    name = "career_ops"

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        token: str | None = None,
        session: Any | None = None,
        store: Any | None = None,
    ) -> None:
        self.config = config or {}
        self.enabled = bool(self.config.get("enabled", False))
        self.token = token if token is not None else os.getenv("APIFY_TOKEN", "")
        self.cap_usd = float(self.config.get("monthly_cost_cap_usd", _DEFAULT_CAP_USD))
        self.timeout_seconds = int(self.config.get("timeout_seconds", 240))
        self._session = session or requests
        self._store = store
        self.errors: list[str] = []
        self.last_spend_estimate_usd = 0.0

    # -- spend tracking --------------------------------------------------
    def _store_or_none(self) -> Any:
        if self._store is not None:
            return self._store
        try:
            from state.store import SqliteStore

            self._store = SqliteStore(ROOT / "state")
        except Exception as exc:  # noqa: BLE001 - spend tracking is best-effort
            self.errors.append(f"career_ops: spend tracking unavailable: {exc}")
            self._store = None
        return self._store

    @staticmethod
    def _month_key() -> str:
        return "apify_spend_" + datetime.now(timezone.utc).strftime("%Y-%m")

    def _month_spend(self) -> float:
        store = self._store_or_none()
        if store is None:
            return 0.0
        raw = store.get_runtime(self._month_key())
        try:
            return float(raw) if raw else 0.0
        except ValueError:
            return 0.0

    def _add_spend(self, amount_usd: float) -> None:
        if amount_usd <= 0:
            return
        store = self._store_or_none()
        if store is None:
            return
        store.set_runtime(self._month_key(), f"{self._month_spend() + amount_usd:.4f}")

    # -- fetch --------------------------------------------------------
    def fetch(self) -> list[Job]:
        self.errors = []
        self.last_spend_estimate_usd = 0.0
        if not self.enabled:
            print("career_ops: disabled", flush=True)
            return []
        if not self.token:
            self.errors.append("career_ops: APIFY_TOKEN not set; skipped")
            print("career_ops: APIFY_TOKEN not set; skipped", flush=True)
            return []

        actors = [a for a in self.config.get("actors", []) if a.get("enabled", True)]
        if not actors:
            self.errors.append("career_ops: enabled but no actors configured")
            return []

        spent_this_month = self._month_spend()
        jobs: list[Job] = []
        for actor_cfg in actors:
            try:
                jobs.extend(self._run_actor(actor_cfg, spent_this_month + self.last_spend_estimate_usd))
            except Exception as exc:  # noqa: BLE001 - one actor must not break the scan
                message = f"career_ops:{actor_cfg.get('id', '?')}: {type(exc).__name__}: {exc}"
                self.errors.append(message)
                print(message, flush=True)
        return jobs

    def _run_actor(self, actor_cfg: dict[str, Any], already_spent: float) -> list[Job]:
        actor_id = str(actor_cfg["id"]).replace("/", "~")
        source_label = str(actor_cfg.get("source") or actor_cfg.get("adapter") or "career_ops")
        price_per_1000 = float(actor_cfg.get("price_per_1000_usd", _DEFAULT_PRICE_PER_1000))
        max_items = int(actor_cfg.get("max_items", _DEFAULT_MAX_ITEMS))
        base_input = dict(actor_cfg.get("input", {}))
        searches = actor_cfg.get("searches") or [{}]
        adapter = _ADAPTERS.get(str(actor_cfg.get("adapter") or actor_id), _generic_adapter)
        field_map = actor_cfg.get("field_map") or {}

        collected: list[Job] = []
        seen_keys: set[str] = set()
        for search in searches:
            projected = already_spent + self.last_spend_estimate_usd + (max_items * price_per_1000 / 1000.0)
            if projected > self.cap_usd:
                self.errors.append(
                    f"career_ops:{actor_id}: monthly cost cap ${self.cap_usd:.2f} would be exceeded "
                    f"(≈${already_spent + self.last_spend_estimate_usd:.2f} so far); skipping remaining searches"
                )
                break
            actor_input = {**base_input, **(search or {})}
            items = self._call_apify(actor_id, actor_input, max_items)
            run_cost = len(items) * price_per_1000 / 1000.0
            self.last_spend_estimate_usd += run_cost
            self._add_spend(run_cost)
            for raw in items:
                job = self._to_job(raw, source_label, adapter, field_map)
                if job is None or job.canonical_key in seen_keys:
                    continue
                seen_keys.add(job.canonical_key)
                collected.append(job)
        return collected

    def _call_apify(self, actor_id: str, actor_input: dict[str, Any], max_items: int) -> list[dict[str, Any]]:
        url = f"{_API_BASE}/{actor_id}/run-sync-get-dataset-items"
        response = self._session.post(
            url,
            params={"token": self.token, "maxItems": max_items, "timeout": self.timeout_seconds - 30},
            json=actor_input,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            return payload.get("items", []) or []
        return []

    def _to_job(
        self,
        raw: dict[str, Any],
        source_label: str,
        adapter: Any,
        field_map: dict[str, str],
    ) -> Job | None:
        try:
            fields = adapter(raw)
            for job_field, raw_key in field_map.items():
                if raw.get(raw_key) not in (None, ""):
                    fields[job_field] = raw[raw_key]
            title = str(fields.get("title") or "").strip()
            company = str(fields.get("company") or "").strip()
            url = _clean_url(fields.get("url"))
            if not title or not url:
                return None
            location = fields.get("location")
            source_job_id = _stable_id(raw, url, title, company, str(location or ""))
            return Job(
                source=source_label,
                source_job_id=source_job_id,
                company=company or "(company from Apify - confirm)",
                title=title,
                location=str(location) if location else None,
                description=str(fields.get("description") or ""),
                url=url,
                posted_at=fields.get("posted_at"),
                raw={"apify_actor": True, **(fields.get("raw") or {})},
            )
        except Exception as exc:  # noqa: BLE001 - skip a single malformed item
            self.errors.append(f"career_ops:{source_label}: skipped 1 item: {type(exc).__name__}")
            return None
