# Codex Project Instructions

## Current Scope

This repo is currently focused on MLB raw data ingestion and Supabase storage planning.

Codex should ignore these folders unless the user explicitly asks otherwise:

- `backend/`
- `frontend/`

The current source notebook is reference material only:

- Do not edit `mlb_daily_clean copy 2.ipynb` unless explicitly asked.
- Treat notebook behavior as prototype context, not as approved architecture.

## Ingestion Direction

- Focus on raw data ingestion before derived stats, feature tables, model training, predictions, or bet recommendations.
- Use MLB Stats API for MLB baseball data.
- Do not scrape websites.
- If an API does not provide required data, document the gap and discuss an approved provider/API.
- Keep Supabase docs in `docs/ingestion/` aligned with live schema changes.

## Key Docs

Before implementing ingestion scripts, read:

- `docs/agents/raw_ingestion_agents.md`
- `docs/ingestion/script_implementation_playbook.md`
- `docs/ingestion/raw_data_plan.md`
- `docs/ingestion/supabase_table_catalog.md`
- `docs/ingestion/mlb_stats_api_sources.md`
- `docs/ingestion/acceptance_checklist.md`
- `docs/modeling/data_timing_and_leakage.md`

@RTK.md
