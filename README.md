# MLB Predictions Ingestion

This repository currently focuses on populating the raw MLB data tables in Supabase. The routine morning workflow updates today's probable pitchers and yesterday's completed game logs.

## Morning workflow

Run commands from the repository root:

```bash
cd /Users/austinblanchard/MLB-Predictions
```

### 1. Update today's probable pitchers

Use today's MLB schedule date. For example:

```bash
.venv/bin/python scripts/ingest_probable_pitchers.py --date YYYY-MM-DD --dry-run
.venv/bin/python scripts/ingest_probable_pitchers.py --date YYYY-MM-DD
```

The probable-pitcher job processes MLB preview games, stores the current assignment by game/team, and can be rerun near first pitch because assignments may change.

### 2. Populate yesterday's game logs

Run the postgame orchestrator:

```bash
.venv/bin/python scripts/ingest_postgame.py --yesterday --dry-run
.venv/bin/python scripts/ingest_postgame.py --yesterday
```

`--yesterday` resolves the previous calendar day in `America/Los_Angeles`. The orchestrator updates, in dependency order:

- `games_raw`
- `team_game_logs`
- `pitcher_game_logs`

It reuses one schedule response and one boxscore per unique completed game for all stages.

## Verify the run

Review the command summary for:

- failed schedule, boxscore, transform, or database operations
- games discovered and upserted
- team-log rows written
- pitcher-log rows written
- pitcher-log processing markers completed

A nonzero exit means the run is incomplete. Investigate the reported failure and rerun the relevant command. The writers are idempotent, so rerunning the same date should not create duplicate rows.

## Targeted recovery

The table-specific scripts remain available for isolated recovery:

```bash
.venv/bin/python scripts/ingest_games_raw.py --date YYYY-MM-DD
.venv/bin/python scripts/ingest_team_game_logs.py --date YYYY-MM-DD
.venv/bin/python scripts/ingest_pitcher_game_logs.py --date YYYY-MM-DD
```

Use the postgame orchestrator for the normal daily run. Use date ranges only for historical backfills, recovery, or explicit audits.

## Environment

Ingestion requires the project-local virtual environment and the ignored `.env` file with the configured Supabase credentials. Install the pinned dependencies with:

```bash
.venv/bin/python -m pip install -r requirements-ingestion.txt
```

Do not expose the Supabase service-role key to frontend or client code.

## Scope

The current scope is raw MLB ingestion. Derived statistics, feature tables, model training, predictions, betting recommendations, and weather ingestion are not part of the routine workflow yet.
