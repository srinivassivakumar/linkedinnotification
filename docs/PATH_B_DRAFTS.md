# Path B — real Claude drafts for the P0 buttons

`PREPARE APPLICATION`, `UPDATED RESUME`, `EMAIL DRAFT`, and `LINKEDIN DRAFT` need
Claude to actually write something. The cloud (GitHub Actions) runs
`CLAUDE_MODE=mock` and has no Anthropic API key, so it cannot tailor. Path B
splits the work:

| Step | Where | Device on? |
|---|---|---|
| Capture the button press into a queue | GitHub Actions `Callbacks` workflow | No |
| Write the tailored files, deliver to Telegram | a **Claude Code session** | Yes, while it runs |

The "intelligence" in step 2 is the Claude Code session itself — no API key, it
runs on your Claude Pro subscription.

## What a button press does now

With a non-live provider (`mock`), pressing one of the four buttons:

1. adds a row to the `draft_requests` table (`enqueue_draft_request`, delivered
   to the repo by the `Commit state` step);
2. replies on Telegram: **"✍️ QUEUED FOR CLAUDE — <kind>. Request #N is in the
   queue."**

Repeated presses of the same button for the same job reuse the pending row.

Once a drafting run has delivered real files for that job (a
`_claude_tailored.json` marker sits in the artifact dir), the button serves the
real draft immediately instead of queueing.

## Draining the queue (the Claude Code session)

From the repo root, on a machine where `claude` is signed in:

```
python run_agent.py drafts --list
```

This prints one JSON blob: every pending request with the job snapshot, the
`matched_evidence_ids`, the full `evidence_bank`, the `write_files` list, and the
`deliver_command`. For each pending request:

1. Write every file in `write_files` into `artifact_dir`.
   - Every claim traces to an evidence `id`, or is written as `NEEDS_CONFIRMATION`.
   - Never invent a technology, metric, outcome, employer or duration.
   - `resume.md` = one page of markdown. The `.txt` drafts are short and plain.
   - The LinkedIn / referral note is sent manually by the user — keep it < 90 words.
2. Run the `deliver_command`, e.g. `python run_agent.py drafts --deliver 7`.

`--deliver` reads the written files back through `_WrittenFilesProvider`, runs the
normal P0 artifact factory (so `fit_report.md` / `evidence_matrix.md` are
generated deterministically), pushes the requested draft to Telegram, writes the
`_claude_tailored.json` marker, and marks the request `delivered`.

Set `AGENT_PERSIST_GIT=1` to have `--deliver` commit `state/career_agent.db` and
`artifacts/generated/` back to the branch so the cloud stops showing the request
as pending.

`python run_agent.py drafts --deliver <id> --dry-run` reports what it would send
without touching Telegram.

## Automated draining

A Claude Code session with a scheduled job (`CronCreate`, every ~2h) can run the
drain unattended — but only while that session and its machine are alive, and the
schedule expires after 7 days. For a longer-lived setup, run the drain from any
always-on machine where `claude` is authorised, or re-arm the schedule.

There is no way to run the tailoring inside GitHub Actions: it would require an
API key, which this project does not use.
