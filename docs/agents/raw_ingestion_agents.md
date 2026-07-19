# Raw Ingestion Agent Setup

This project should treat the existing notebook as a modeling prototype, not as the ingestion system. Agents should build memory in repo docs and use Supabase as the source of truth for stored raw baseball data.

## Current Boundary

- Do not edit `mlb_daily_clean copy 2.ipynb`.
- Ignore `frontend/` and `backend/` for current ingestion planning.
- Focus only on scripts that populate raw Supabase tables.
- Do not build derived stats, feature tables, model-training tables, or prediction tables yet.
- The routine morning postgame workflow uses `scripts/ingest_postgame.py` to
  ingest only the previous calendar day's `games_raw`, insert missing
  `probable_pitchers` assignments retained by MLB, and populate
  `team_game_logs` and `pitcher_game_logs` in dependency order. Date ranges
  remain available for historical backfills and recovery runs.
- The orchestrator shares one schedule payload per bounded date chunk and one
  boxscore per unique final `gamePk`. Preserve its run-scoped response cache and
  physical-request metrics when changing postgame ingestion.
- Keep `scripts/ingest_games_raw.py`, `scripts/ingest_team_game_logs.py`, and
  `scripts/ingest_pitcher_game_logs.py` usable as targeted recovery commands.
- `scripts/ingest_pregame.py` is the routine same-day pregame workflow. It
  shares one schedule payload while loading every game for today's MLB schedule
  date into `games_raw`, then synchronizing only MLB `Preview` probable-pitcher
  assignments. The standalone games and probable-pitcher writers remain
  available for targeted recovery.

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
- Keep the previous-day `ingest_postgame.py` results/log workflow separate from
  the same-day `ingest_pregame.py` schedule/probable workflow.
- Preserve pregame dependency ordering: `games_raw`, then `probable_pitchers`,
  then the future `pregame_team_features` stage when it is implemented.
- Maintain the shared request budget: one schedule response per bounded chunk
  and one boxscore response per unique final game in a process run.
- Preserve dependency ordering: `games_raw`, then `team_game_logs`, then
  insert-only `probable_pitchers` recovery, then `team_game_logs`, then
  `pitcher_game_logs` and its processed marker.
- Avoid model leakage concerns later by labeling data timing now.
- Keep scripts narrow, testable, and resumable.

Key questions this agent answers:

- What should the previous-day morning run do?
- What should a postgame/yesterday update do?
- How do we safely rerun the same date?
- Does a change preserve shared-payload reuse and request-count observability?
- Does a failed pregame games stage prevent dependent pregame stages?
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
8. Use `scripts/ingest_postgame.py` for routine previous-day validation and the
   table-specific commands only for targeted recovery or isolated testing.

For each new raw table or source:

1. Document source endpoint or URL.
2. Document upsert key.
3. Document whether it is pregame-safe or postgame-only.
4. Document expected nulls and known edge cases.
5. Only then implement ingestion code.
