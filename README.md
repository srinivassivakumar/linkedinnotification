# Career Agent Pre-Claude MVP

This repository implements the deterministic pre-Claude job hunt automation
spine from `builmanual.pdf`.

## What Works Now
- Greenhouse, Lever and Ashby public ATS adapters behind a common `Job` model.
- Conservative normalization, dedupe, freshness, live, location, seniority and role-family filtering.
- Deterministic pre-score with explainable signal breakdown.
- JSONL state and `seen_jobs.json` for idempotent runs.
- Telegram message sender and candidate cards.
- Telegram operations-console cards for home, job queue, focus, today, human path,
  application state, interview, follow-up, and settings views.
- Mock intelligence provider for end-to-end testing before Claude Pro.
- Application artifact skeleton behind a manual PREPARE action.
- Gmail reply classifier skeleton.
- GitHub Actions workflows for tests and scheduled scans.

## Setup

```powershell
cd E:\sri\X-Pent-Dev\ClaudeJob
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Add real ATS board IDs in `config/sources.yaml`. Keep `.env` private.

## Useful Commands

```powershell
python -m orchestrator.main --mode fetch-only --limit 20
python -m orchestrator.main --mode scan --dry-run --fixture tests/fixtures/golden_jobs.json
python -m orchestrator.main --mode scan --fixture tests/fixtures/golden_jobs.json
python -m orchestrator.main --mode notify-test
python -m orchestrator.main --mode dashboard-test --fixture tests/fixtures/golden_jobs.json
python -m orchestrator.main --mode prepare --job-key fixture:perfect-junior
pytest -q
```

## Current Boundary
Claude, Career Ops, Apify, Gmail sending and LinkedIn actions are not faked.
Those are connector/setup tasks documented in `CLAUDE.md`.
