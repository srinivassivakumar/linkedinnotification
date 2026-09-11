#!/usr/bin/env pwsh
# One-command launcher for the career agent's live mode.
#
# First run ever: scans job sources for the last 7 days.
# Every scheduled scan after that: only the last 12 hours, so you only see new jobs
# (already-seen job keys are never re-shown - see orchestrator/live.py).
# The process stays running and rescans automatically every 12 hours; leave it open
# (or run it under a scheduler / `pm2` / Task Scheduler if you want it survive reboots).
#
# Usage:  .\start.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

Write-Host "Installing/checking dependencies..."
& $venvPython -m pip install --quiet -r requirements.txt

if (-not (Test-Path ".env")) {
    Write-Host ""
    Write-Host "No .env found. Copy .env.example to .env and fill in:" -ForegroundColor Yellow
    Write-Host "  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, APPROVAL_SECRET" -ForegroundColor Yellow
    Write-Host "before this will be able to notify you." -ForegroundColor Yellow
    Write-Host ""
}

if (-not (Test-Path "secrets\credentials.json")) {
    Write-Host "No secrets\credentials.json found. Gmail alert parsing (LinkedIn/Naukri/Indeed/" -ForegroundColor Yellow
    Write-Host "Instahyre/Cutshort/Google Alerts emails) will stay off until Gmail OAuth is set up" -ForegroundColor Yellow
    Write-Host "(see README.md / MANUAL_SETUP.md). Direct ATS + free-API sources still work." -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "Starting live agent (first scan: last 7 days, then every 12h)..."
& $venvPython run_agent.py live --scan-interval 12 --first-window-days 7 --scan-window-hours 12
