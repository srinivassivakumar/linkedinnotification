"""Career Ops - pinned Apify actors consumed as a normal deterministic source.

Option B of the Apify integration: instead of Claude driving Apify through MCP,
the Python scanner calls one or more **explicitly pinned** Apify actors over the
REST API (``run-sync-get-dataset-items``), maps their dataset output to
:class:`~orchestrator.models.Job`, and hands the jobs to the same dedupe / filter
/ score / notify pipeline as Greenhouse, Lever and Ashby.

Guard rails (Apify is "discovery only until a reviewed actor is explicitly
approved"):

* Disabled by default (`sources.career_ops.enabled: false`).
* Runs nothing without ``APIFY_TOKEN`` in the environment.
* Every actor is pinned by id in ``config/sources.yaml`` with its own cost knobs.
* ``min_interval_hours`` per actor stops it re-running on every scan (paid
  scrapers should not fire every 2 hours).
* A rolling monthly spend estimate is tracked in the ``runtime`` table and
  ``monthly_cost_cap_usd`` stops further runs once the cap is reached.
* ``max_charge_usd`` is sent to Apify as ``maxTotalChargeUsd`` (pay-per-event
  actors), or ``max_items`` as ``maxItems`` (pay-per-result actors), so Apify
  itself also caps the bill.
"""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from orchestrator.models import Job

ROOT = Path(__file__).resolve().parents[1]
_API_BASE = "https://api.apify.com/v2/acts"
_DEFAULT_CAP_USD = 10.0
_DEFAULT_PRICE_PER_1000 = 5.0
_DEFAULT_MAX_ITEMS = 25
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]*\n[ \t]*")


def _strip_html(value: Any) -> str:
    text = _TAG_RE.sub(" ", str(value or ""))
    text = (
        text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
        .replace("&gt;", ">").replace("&#39;", "'").replace("&quot;", '"')
    )
    text = re.sub(r"[ \t]{2,}", " ", text)
    return _WS_RE.sub("\n", text).strip()


def _clean_url(value: Any) -> str:
    return re.sub(r"[?#].*$", "", str(value or "").strip())


def _stable_id(raw: dict[str, Any], url: str, title: str, company: str, location: str) -> str:
    for key in ("jobId", "job_id", "id", "jobKey", "job_key"):
        if raw.get(key):
            return str(raw[key])
    if url:
        return _clean_url(url)
    return hashlib.sha1(f"{title}|{company}|{location}".encode("utf-8")).hexdigest()[:16]


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
        return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None


# -- output adapters: dataset item -> Job kwargs --------------------------------


def _naukri_muhammetakkurtt(raw: dict[str, Any]) -> dict[str, Any]:
    """``muhammetakkurtt~naukri-job-scraper`` dataset item -> Job kwargs."""
    job_id = raw.get("jobId")
    url = f"https://www.naukri.com/job-listings-{job_id}" if job_id else _clean_url(raw.get("jobUrl"))
    return {
        "title": str(_first(raw, "title", "jobTitle") or "").strip(),
        "company": str(_first(raw, "companyName", "company", "hiringFor") or "").strip(),
        "location": _first(raw, "location", "placeholders"),
        "description": _strip_html(_first(raw, "jobDescription", "description")),
        "url": url,
        "posted_at": _parse_dt(_first(raw, "createdDate", "postedDate", "createdOn")),
        "raw": {
            "salary": raw.get("salary"),
            "experience": raw.get("experienceText"),
            "min_exp": raw.get("minimumExperience"),
            "max_exp": raw.get("maximumExperience"),
            "freshness_label": raw.get("footerPlaceholderLabel"),
            "mode": raw.get("mode"),
        },
    }


def _naukri_fervent_bus(raw: dict[str, Any]) -> dict[str, Any]:
    """``fervent_bus~naukri-job-scraper-mcp`` dataset item -> Job kwargs."""
    exp_min, exp_max = raw.get("experienceMin"), raw.get("experienceMax")
    experience = None
    if exp_min is not None or exp_max is not None:
        experience = f"{exp_min if exp_min is not None else '?'}-{exp_max if exp_max is not None else '?'} yrs"
    return {
        "title": str(_first(raw, "title", "jobTitle") or "").strip(),
        "company": str(_first(raw, "companyName", "company") or "").strip(),
        "location": _first(raw, "location", "jobLocation"),
        "description": _strip_html(_first(raw, "jobDescription", "description")),
        "url": _clean_url(_first(raw, "jobUrl", "url", "link")),
        "posted_at": None,  # actor returns scrapedAt (run time), not the posting date
        "raw": {"salary": raw.get("salary"), "experience": experience, "skills": raw.get("skills")},
    }


def _generic_adapter(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": str(_first(raw, "title", "jobTitle", "position", "name") or "").strip(),
        "company": str(_first(raw, "companyName", "company", "organization", "employer") or "").strip(),
        "location": _first(raw, "location", "jobLocation", "city", "place"),
        "description": _strip_html(_first(raw, "descriptionText", "jobDescription", "description", "jobDescriptionText")),
        "url": _clean_url(_first(raw, "jobUrl", "url", "link", "applyUrl", "jobPostingUrl")),
        "posted_at": _parse_dt(_first(raw, "postedAt", "postedDate", "publishedAt", "datePosted", "listedAt", "createdDate")),
        "raw": {k: raw.get(k) for k in ("salary", "experience", "skills", "seniority", "employmentType") if raw.get(k) is not None},
    }


_ADAPTERS = {
    "naukri_muhammetakkurtt": _naukri_muhammetakkurtt,
    "muhammetakkurtt~naukri-job-scraper": _naukri_muhammetakkurtt,
    "naukri": _naukri_fervent_bus,          # back-compat alias
    "naukri_fervent_bus": _naukri_fervent_bus,
    "fervent_bus~naukri-job-scraper-mcp": _naukri_fervent_bus,
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
        self.timeout_seconds = int(self.config.get("timeout_seconds", 300))
        self._session = session or requests
        self._store = store
        self.errors: list[str] = []
        self.last_spend_estimate_usd = 0.0

    # -- spend / interval state (runtime table) --------------------------
    def _store_or_none(self) -> Any:
        if self._store is not None:
            return self._store
        try:
            from state.store import SqliteStore

            self._store = SqliteStore(ROOT / "state")
        except Exception as exc:  # noqa: BLE001 - best-effort
            self.errors.append(f"career_ops: state unavailable: {exc}")
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
        if store is not None:
            store.set_runtime(self._month_key(), f"{self._month_spend() + amount_usd:.4f}")

    def _last_run_at(self, actor_id: str) -> datetime | None:
        store = self._store_or_none()
        if store is None:
            return None
        return _parse_dt(store.get_runtime(f"apify_last_run_{actor_id}"))

    def _mark_run(self, actor_id: str) -> None:
        store = self._store_or_none()
        if store is not None:
            store.set_runtime(f"apify_last_run_{actor_id}", datetime.now(timezone.utc).isoformat())

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

        already_spent = self._month_spend()
        jobs: list[Job] = []
        for actor_cfg in actors:
            try:
                jobs.extend(self._run_actor(actor_cfg, already_spent))
            except Exception as exc:  # noqa: BLE001 - one actor must not break the scan
                message = f"career_ops:{actor_cfg.get('id', '?')}: {type(exc).__name__}: {exc}"
                self.errors.append(message)
                print(message, flush=True)
        return jobs

    def _run_actor(self, actor_cfg: dict[str, Any], already_spent: float) -> list[Job]:
        actor_id = str(actor_cfg["id"]).replace("/", "~")
        source_label = str(actor_cfg.get("source") or actor_cfg.get("adapter") or "career_ops")
        adapter = _ADAPTERS.get(str(actor_cfg.get("adapter") or actor_id), _generic_adapter)
        field_map = actor_cfg.get("field_map") or {}
        base_input = dict(actor_cfg.get("input", {}))
        searches = actor_cfg.get("searches") or [{}]

        # cost per run: prefer an observed estimate, else the pay-per-result math
        price_per_1000 = float(actor_cfg.get("price_per_1000_usd", _DEFAULT_PRICE_PER_1000))
        max_items = int(actor_cfg["max_items"]) if actor_cfg.get("max_items") is not None else None
        max_charge_usd = actor_cfg.get("max_charge_usd")
        est_per_run = float(
            actor_cfg.get("est_charge_per_run_usd")
            or max_charge_usd
            or ((max_items or _DEFAULT_MAX_ITEMS) * price_per_1000 / 1000.0)
        )

        # don't re-run a paid scraper more often than min_interval_hours
        interval_h = float(actor_cfg.get("min_interval_hours", 0) or 0)
        if interval_h > 0:
            last = self._last_run_at(actor_id)
            if last and datetime.now(timezone.utc) - last < timedelta(hours=interval_h):
                mins = int((timedelta(hours=interval_h) - (datetime.now(timezone.utc) - last)).total_seconds() // 60)
                self.errors.append(f"career_ops:{actor_id}: skipped (min_interval_hours={interval_h:g}, ~{mins} min left)")
                return []

        params: dict[str, Any] = {"token": self.token}
        if max_charge_usd is not None:
            params["maxTotalChargeUsd"] = float(max_charge_usd)
        elif max_items is not None:
            params["maxItems"] = max_items

        collected: list[Job] = []
        seen: set[str] = set()
        ran_any = False
        for search in searches:
            if already_spent + self.last_spend_estimate_usd + est_per_run > self.cap_usd:
                self.errors.append(
                    f"career_ops:{actor_id}: monthly cost cap ${self.cap_usd:.2f} would be exceeded "
                    f"(≈${already_spent + self.last_spend_estimate_usd:.2f} spent); skipping remaining searches"
                )
                break
            items = self._call_apify(actor_id, {**base_input, **(search or {})}, params)
            ran_any = True
            self.last_spend_estimate_usd += est_per_run
            self._add_spend(est_per_run)
            for raw in items:
                job = self._to_job(raw, source_label, adapter, field_map)
                if job is None or job.canonical_key in seen:
                    continue
                seen.add(job.canonical_key)
                collected.append(job)

        if ran_any:
            self._mark_run(actor_id)
        return collected

    def _call_apify(self, actor_id: str, actor_input: dict[str, Any], params: dict[str, Any]) -> list[dict[str, Any]]:
        url = f"{_API_BASE}/{actor_id}/run-sync-get-dataset-items"
        response = self._session.post(url, params=params, json=actor_input, timeout=self.timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            if payload.get("error"):
                raise RuntimeError(str(payload["error"])[:300])
            return payload.get("items", []) or []
        return []

    def _to_job(self, raw: dict[str, Any], source_label: str, adapter: Any, field_map: dict[str, str]) -> Job | None:
        try:
            fields = adapter(raw)
            for job_field, raw_key in field_map.items():
                if raw.get(raw_key) not in (None, ""):
                    fields[job_field] = raw[raw_key]
            title = str(fields.get("title") or "").strip()
            url = _clean_url(fields.get("url"))
            company = str(fields.get("company") or "").strip()
            if not title or not url:
                return None
            location = fields.get("location")
            return Job(
                source=source_label,
                source_job_id=_stable_id(raw, url, title, company, str(location or "")),
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
