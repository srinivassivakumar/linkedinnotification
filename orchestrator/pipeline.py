from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from application.factory import prepare_application
from intelligence.provider import get_intelligence_provider
from orchestrator.dedupe import dedupe_jobs
from orchestrator.freshness import freshness_status
from orchestrator.live_check import live_status
from orchestrator.models import Candidate, Job, RunSummary, SourceResult
from orchestrator.policies import apply_conservative_filters, load_evidence, load_preferences, load_yaml
from orchestrator.scorer import score_job
from sources.adzuna import AdzunaSource
from sources.ashby import AshbySource
from sources.career_ops import CareerOpsSource
from sources.greenhouse import GreenhouseSource
from sources.hackernews import HackerNewsWhoIsHiringSource
from sources.lever import LeverSource
from sources.smartrecruiters import SmartRecruitersSource
from sources.workday import WorkdaySource
from state.store import SqliteStore


ROOT = Path(__file__).resolve().parents[1]


def load_sources_config(path: Path | None = None) -> dict[str, Any]:
    return load_yaml(path or ROOT / "config" / "sources.yaml")


def build_sources(config: dict[str, Any]) -> list[Any]:
    sources_cfg = config.get("sources", {})
    ats_cfg = sources_cfg.get("ats", sources_cfg)
    output: list[Any] = []
    greenhouse = ats_cfg.get("greenhouse", {})
    if greenhouse.get("enabled", True):
        output.append(GreenhouseSource(greenhouse.get("boards", [])))
    lever = ats_cfg.get("lever", {})
    if lever.get("enabled", True):
        output.append(LeverSource(lever.get("companies", [])))
    ashby = ats_cfg.get("ashby", {})
    if ashby.get("enabled", True):
        output.append(AshbySource(ashby.get("companies", [])))
    workday = ats_cfg.get("workday", {})
    if workday.get("enabled", False) and workday.get("companies"):
        output.append(WorkdaySource(workday["companies"], per_company_limit=int(workday.get("per_company_limit", 20))))
    smartrecruiters = ats_cfg.get("smartrecruiters", {})
    if smartrecruiters.get("enabled", False) and smartrecruiters.get("companies"):
        output.append(SmartRecruitersSource(smartrecruiters["companies"], fetch_details=bool(smartrecruiters.get("fetch_details", True))))

    hn = sources_cfg.get("hackernews", {})
    if hn.get("enabled", False):
        output.append(HackerNewsWhoIsHiringSource(hn))
    adzuna = sources_cfg.get("adzuna", {})
    if adzuna.get("enabled", False):
        output.append(AdzunaSource(adzuna))

    career_ops = sources_cfg.get("career_ops", {})
    output.append(CareerOpsSource(career_ops))
    return output


def fetch_all_sources(config: dict[str, Any], limit: int | None = None) -> tuple[list[Job], list[SourceResult]]:
    raw: list[Job] = []
    results: list[SourceResult] = []
    for source in build_sources(config):
        try:
            jobs = source.fetch()
            if limit is not None:
                remaining = max(0, limit - len(raw))
                jobs = jobs[:remaining]
            raw.extend(jobs)
            results.append(
                SourceResult(
                    source=source.name,
                    fetched=len(jobs),
                    errors=list(getattr(source, "errors", [])),
                )
            )
        except Exception as exc:
            results.append(SourceResult(source=getattr(source, "name", "unknown"), fetched=0, errors=[str(exc)]))
        if limit is not None and len(raw) >= limit:
            break
    return raw, results


def load_fixture(path: Path) -> list[Job]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [Job.model_validate(item) for item in payload]


def build_candidates(
    jobs: list[Job],
    preferences: dict[str, Any],
    evidence: list[dict[str, Any]],
    sources_config: dict[str, Any],
    max_age_hours: int | None = None,
) -> tuple[list[Candidate], dict[str, int]]:
    counts = {"raw": len(jobs), "normalized": len(jobs)}
    unique, duplicates = dedupe_jobs(jobs)
    counts["unique"] = len(unique)
    counts["duplicates"] = duplicates
    live_cfg = sources_config.get("sources", {}).get("live_check", {})
    if not live_cfg:
        live_cfg = sources_config.get("live_check", {})
    kept: list[Candidate] = []
    stage_counts = {
        "live_or_unknown": 0,
        "fresh_or_unknown": 0,
        "location_ok_or_unknown": 0,
        "seniority_ok_or_unknown": 0,
        "role_family_ok_or_unknown": 0,
        "strong_or_review": 0,
    }
    freshness_cfg = preferences.get("freshness", {})
    effective_max_age = int(max_age_hours if max_age_hours is not None else freshness_cfg.get("max_age_hours", 168))
    for job in unique:
        live = live_status(job.url, bool(live_cfg.get("enabled", False)), int(live_cfg.get("timeout_seconds", 8)))
        if live != "dead":
            stage_counts["live_or_unknown"] += 1
        fresh = freshness_status(job, max_age_hours=effective_max_age)
        if fresh != "stale":
            stage_counts["fresh_or_unknown"] += 1
        keep, warnings, decisions = apply_conservative_filters(job, preferences, live, fresh)
        if not keep:
            continue
        stages = {decision.stage for decision in decisions if decision.keep}
        if "location" in stages:
            stage_counts["location_ok_or_unknown"] += 1
        if "seniority" in stages:
            stage_counts["seniority_ok_or_unknown"] += 1
        if "role_family" in stages:
            stage_counts["role_family_ok_or_unknown"] += 1
        score = score_job(job, preferences, evidence, warnings)
        candidate = Candidate(job=job, score=score, filter_warnings=warnings)
        kept.append(candidate)
        if score.bucket in {"strong_candidate", "review"}:
            stage_counts["strong_or_review"] += 1
    counts.update(stage_counts)
    return kept, counts


def run_pipeline(
    mode: str = "scan",
    dry_run: bool = False,
    limit: int | None = None,
    fixture: Path | None = None,
    notifier: Any | None = None,
    store: SqliteStore | None = None,
    prepare_key: str | None = None,
    intelligence_mode: str | None = None,
) -> RunSummary:
    preferences = load_preferences()
    evidence = load_evidence()
    sources_config = load_sources_config()
    source_results: list[SourceResult] = []
    if fixture:
        raw = load_fixture(fixture)
        if limit is not None:
            raw = raw[:limit]
        source_results.append(SourceResult(source="fixture", fetched=len(raw)))
    else:
        raw, source_results = fetch_all_sources(sources_config, limit)
    if mode == "fetch-only":
        return RunSummary(mode=mode, dry_run=dry_run, counts={"raw": len(raw)}, source_results=source_results)

    candidates, counts = build_candidates(raw, preferences, evidence, sources_config)
    store = store or SqliteStore(ROOT / "state")
    resolved_mode = intelligence_mode or os.getenv("CLAUDE_MODE", "mock")
    provider = get_intelligence_provider(resolved_mode)
    new_or_changed = store.diff_new_or_changed(candidates)
    evaluated = provider.evaluate_jobs(new_or_changed, evidence)
    counts["new_or_changed"] = len(evaluated)

    notified: list[str] = []
    prepared_artifacts: list[str] = []
    if not dry_run:
        store.persist(evaluated)
        if notifier is not None:
            notified = notifier.send_candidates(evaluated)
        if prepare_key:
            latest = {candidate.job_key: candidate for candidate in evaluated}
            latest.update(store.load_latest_jobs())
            if prepare_key in latest:
                # An explicit --job-key request is a manual operator decision; still
                # blocked for weak jobs inside the factory.
                path = prepare_application(
                    latest[prepare_key], evidence, store, provider,
                    ROOT / "artifacts" / "generated", force=True,
                )
                prepared_artifacts.append(str(path))
            else:
                raise ValueError(f"No stored candidate found for job key: {prepare_key}")
    return RunSummary(
        mode=mode,
        dry_run=dry_run,
        counts=counts,
        source_results=source_results,
        new_or_changed=[candidate.job_key for candidate in evaluated],
        notified=notified,
        prepared_artifacts=prepared_artifacts,
    )
