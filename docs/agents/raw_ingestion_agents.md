# Raw Ingestion Agent Setup

This project should treat the existing notebook as a modeling prototype, not as the ingestion system. Agents should build memory in repo docs and use Supabase as the source of truth for stored raw baseball data.

## Current Boundary

- Do not edit `mlb_daily_clean copy 2.ipynb`.
- Ignore `frontend/` and `backend/` for current ingestion planning.
- Focus only on scripts that populate raw Supabase tables.
- Do not build derived stats, feature tables, model-training tables, or prediction tables yet.
- The routine morning `games_raw` workflow ingests only the previous calendar
  day's schedule/results. Date ranges remain available for historical backfills
  and recovery runs.
- Upcoming games are not routinely written to `games_raw`.
  `scripts/ingest_probable_pitchers.py` is the separately documented pregame
  workflow: it synchronizes only MLB `Preview` assignments without creating
  future `games_raw` rows.

## Agent Roles

### MLB Stats API Agent

Purpose: understand what the MLB Stats API can provide and how each endpoint maps to raw tables.

Responsibilities:

- Maintain endpoint inventory in `docs/ingestion/mlb_stats_api_sources.md`.
- Track endpoint parameters, response fields, and quirks.
- Use MLB Stats API sources for MLB baseball data.
- Do not scrape websites.
- Identify whether data is pregame-safe, postgame-only, or mutable.
- Call out gaps where MLB Stats API does not provide required data so a proper provider/API decision can be made.

Key questions this agent answers:

- Which endpoint populates each raw table?
- Is a field available before first pitch?
- Does the field change after the game starts or ends?
- What identifiers should be used for idempotent upserts?

### Supabase Schema Agent

Purpose: maintain an accurate memory of the BagBrainOfficial raw schema.

Responsibilities:

- Maintain `docs/ingestion/supabase_table_catalog.md`.
- Track primary keys, foreign keys, nullable fields, and row counts when inspected.
- Recommend schema changes only when the current schema blocks durable ingestion.
- Keep ingestion scripts aligned with existing table names and keys.
- Flag security and access concerns, especially RLS.

Key questions this agent answers:

- What rows can be safely upserted?
- What tables must be populated before dependent tables?
- Which IDs are canonical?
- What schema changes are worth discussing before implementation?

### Raw Pipeline Agent

Purpose: convert source knowledge and schema knowledge into reliable ingestion jobs.

Responsibilities:

- Maintain `docs/ingestion/raw_data_plan.md`.
- Define ingestion order, idempotency rules, and update windows.
- Keep the previous-day `games_raw` results job separate from the
  `ingest_probable_pitchers.py` pregame job.
- Avoid model leakage concerns later by labeling data timing now.
- Keep scripts narrow, testable, and resumable.

Key questions this agent answers:

- What should the previous-day morning run do?
- What should a postgame/yesterday update do?
- How do we safely rerun the same date?
- Which tables should be populated in the first implementation slice?

## Collaboration Rules For Future Codex Work

Before creating or editing ingestion scripts:

1. Re-read this file.
2. Follow `docs/ingestion/script_implementation_playbook.md`.
3. Re-read the Supabase table catalog.
4. Re-read the MLB source map.
5. Inspect the notebook only as reference behavior.
6. Confirm whether any proposed schema changes are necessary.
7. Do not implement scraping as an ingestion strategy.

For each new raw table or source:

1. Document source endpoint or URL.
2. Document upsert key.
3. Document whether it is pregame-safe or postgame-only.
4. Document expected nulls and known edge cases.
5. Only then implement ingestion code.
