# AGENTS.md

## Goal
Build the pre-Claude Career Agent V3 infrastructure.

## Non-Negotiable Architecture
- Python handles deterministic work.
- IntelligenceProvider is the only AI boundary.
- MockProvider is the active provider before Claude Pro.
- No embeddings, reranker, local LLM, vector DB, VPS, Selenium or auto-apply.
- No secret values in source control.
- Every source adapter returns the same normalized Job model.
- Every pipeline run must be idempotent.
- Conservative filters: uncertain cases survive for later reasoning.

## Quality
- Add tests for deterministic logic.
- Keep functions small and typed.
- Log counts at every pipeline stage.
- Do not silently catch exceptions; report source-level failures and continue where safe.

