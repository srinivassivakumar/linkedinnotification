# Claude Handoff

This project is intentionally pre-Claude. The deterministic pipeline, state,
Telegram card formatting, mock provider and application artifact skeleton are
implemented locally.

## Later Claude Tasks
1. Read `builmanual.pdf` and the connector-first architecture PDF.
2. Replace only `intelligence/claude.py` so it satisfies `IntelligenceProvider`.
3. Keep `CLAUDE_MODE=mock` until Claude output is structured, grounded and tested.
4. Evaluate only serious/uncertain candidates, not every raw job.
5. Use only verified evidence from `profile/evidence_bank.yaml`.
6. Do not add LinkedIn automation, auto-apply, embeddings, rerankers or paid scraping unless the pipeline metrics prove the need.

## Connector Work Claude Should Do Later
- Inspect Career Ops and configure a real `sources/career_ops.py` path if available.
- Use Apify MCP/plugin only for actor discovery; pin reviewed actors before production.
- Use Google Workspace connectors for interactive Gmail/Calendar work.
- Keep background Gmail work behind explicit OAuth setup and approval gates.

