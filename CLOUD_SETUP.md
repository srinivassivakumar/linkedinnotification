# Run the agent in the cloud — phone = remote, cloud = automation

Goal: the automation runs on a schedule in the cloud with **no device online**.
Your phone is only the dashboard + approval screen (Telegram cards, and Claude's
own "needs approval / work finished" notifications).

`run_agent.py cloud` is the headless tick: **ATS scan → Gmail pass → drain
pending Telegram approvals → commit SQLite state back to git**. It is idempotent
and device-independent.

There are two ways to schedule it. Do the shared prerequisites, then pick one.

---

## Shared prerequisites (you must do these — I can't)

### 1. Put this repo on GitHub (private)

```powershell
cd E:\sri\X-Pent-Dev\ClaudeJob
gh repo create x-pent-career-agent --private --source . --remote origin
git push -u origin HEAD          # pushes the current branch
```

The local branch is currently **`integrated-career-agent`**. If you want it named
`claudeautomation` (as discussed elsewhere), rename first:
`git branch -m integrated-career-agent claudeautomation`, then push. Whatever
branch you push, the schedule runs against it — keep working on that same branch.

`.env` and `secrets/` are gitignored, so no secrets go to GitHub.

### 2. Collect the values the cloud runner needs

| Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | from `.env` |
| `TELEGRAM_CHAT_ID` | from `.env` |
| `APPROVAL_SECRET` | from `.env` |
| `GMAIL_CREDENTIALS_JSON` | the **entire contents** of `secrets/credentials.json` |
| `GMAIL_TOKEN_JSON` | the **entire contents** of `secrets/token.json` |

The Gmail token's `refresh_token` is long-lived; the runner refreshes the access
token itself each tick, so you only set this once.

---

## Path A — GitHub Actions (recommended: free, reliable, no Claude / API usage)

The workflow `.github/workflows/agent.yml` runs `run_agent.py cloud` **twice a
day (07:00 and 19:00 IST)** and commits `state/career_agent.db` back to the
branch in a workflow step. `CLAUDE_MODE` is pinned to `mock`, so it never calls
the Anthropic API and costs nothing beyond GitHub's free Actions minutes. The
5-runs/day limit some people mention is a *Claude Routines* (Path B) thing — it
does not apply here.

1. In the GitHub repo: **Settings → Secrets and variables → Actions → New
   repository secret**, add all 5 names from the table above.
2. **Settings → Actions → General → Workflow permissions →** "Read and write
   permissions" (needed for the state commit).
3. **Actions tab → Career Agent - Cloud Tick → Run workflow** to test by hand
   (the button exists because of `workflow_dispatch`). Read the run log before
   trusting the cron.
4. Watch Telegram — a real scan sends cards for non-weak jobs.
5. It then runs on its own at 07:00 / 19:00 IST. Change the two numbers in the
   `cron` line to move the times (GitHub cron is always UTC; current value
   `30 1,13 * * *` = 01:30 & 13:30 UTC).

Approvals: press a Telegram button any time; the **next scheduled tick**
processes it (so up to ~12 h latency — add more `cron` entries if you want faster).

---

## Path B — Claude scheduled cloud agent (native "Cowork" routine)

Runs Claude itself in Anthropic's cloud on this repo, on a cron, with phone
notifications and the ability to pause for your approval. Uses your Claude Pro
usage and is subject to the routine run-count limit (~5/day on Pro), so keep the
schedule light. Also needs the repo on GitHub (prereq 1). Do **not** also enable
Path A on the same branch with the same commit target, or the two fight over the
state commit — pick one persister.

In this Claude Code project run:

```
/schedule
```

and create a routine roughly like:

- **Schedule:** twice a day (matches the run-count limit comfortably)
- **Task prompt:** "Run `python run_agent.py cloud` in the repo. Summarise the
  scan counts, any Gmail events, and anything marked needs_human. Do NOT send
  emails, create calendar events, run Apify actors, or automate LinkedIn/Naukri.
  If a P0 job or an offer/interview email needs my decision, stop and ask me."
- **Environment / secrets:** add the 5 values from the prerequisites table so the
  cloud agent's shell has them; set `CLAUDE_MODE=mock` (or `claude` once audited)
  and `AGENT_PERSIST_GIT=1`.

Claude then pings your phone when a tick finishes or needs approval. You can also
approve via the Telegram buttons as in Path A.

You can run **both** paths (Actions for the deterministic tick, a lighter Claude
routine for a daily review) but keep only one doing `AGENT_PERSIST_GIT=1` writes,
or they will fight over the state commit.

---

## Gmail token expiry (recurring)

If the Google OAuth app is in "Testing" status, the refresh token **expires
after 7 days** and the cloud tick logs
`invalid_grant: Token has been expired or revoked` for the Gmail phase (the rest
of the tick still runs). To fix:

1. Locally: `python -m gmail.auth` → browser → sign in → consent. Rewrites
   `secrets/token.json`.
2. `gh secret set GMAIL_TOKEN_JSON --repo srinivassivakumar/linkedinnotification < secrets/token.json`

**Permanent fix:** Google Cloud Console → APIs & Services → OAuth consent screen →
**Publish app** (Testing → In production). Refresh tokens then stop expiring.

## What still needs YOU, per tick / occasionally

- Press Telegram buttons: PREPARE / SKIP / drafts / APPROVE connection.
- Approve calendar events (never auto-created).
- Send every email / LinkedIn message / Naukri application manually.
- Once: audit live Claude output, then flip `CLAUDE_MODE=claude` in the secret.
- Once: fill India-relevant boards in `config/sources.yaml`.

## What must never move to the cloud unattended

Email sends, calendar writes, Apify actor runs, LinkedIn/Naukri automation,
auto-replies to offers/ambiguous mail. The code refuses these; keep it that way.
