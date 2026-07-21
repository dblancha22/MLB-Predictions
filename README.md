# MLB Predictions Ingestion

This repository currently focuses on populating MLB data tables in Supabase. The
routine morning workflow loads today's schedule and probable pitchers, builds
the two pregame team-feature rows per eligible game, and then updates
yesterday's completed game logs.

## Morning workflow

Run commands from the repository root:

```bash
cd /Users/austinblanchard/MLB-Predictions
```

### 1. Load today's pregame data

Run the pregame orchestrator:

```bash
.venv/bin/python scripts/ingest_pregame.py --today --dry-run
.venv/bin/python scripts/ingest_pregame.py --today
```

`--today` resolves the current calendar date in `America/Los_Angeles`. The
orchestrator shares one MLB schedule response while it first upserts every game
for the date into `games_raw`, then synchronizes probable pitchers for games
still in MLB's `Preview` state. It can be rerun before first pitch because the
schedule and probable assignments are mutable. The final stage reads prior raw
game logs from Supabase and upserts `pregame_team_features`; games that have
already started are skipped in this live mode.

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
- probable-pitcher rows written or deleted
- pregame feature rows ready and written
- team-log rows written
- pitcher-log rows written
- pitcher-log processing markers completed

A nonzero exit means the run is incomplete. Investigate the reported failure and rerun the relevant command. The writers are idempotent, so rerunning the same date should not create duplicate rows.

## Targeted recovery

The table-specific scripts remain available for isolated recovery:

```bash
.venv/bin/python scripts/ingest_games_raw.py --date YYYY-MM-DD
.venv/bin/python scripts/ingest_probable_pitchers.py --date YYYY-MM-DD
.venv/bin/python scripts/ingest_team_game_logs.py --date YYYY-MM-DD
.venv/bin/python scripts/ingest_pitcher_game_logs.py --date YYYY-MM-DD
.venv/bin/python scripts/ingest_pregame_team_features.py --date YYYY-MM-DD --mode historical
```

The feature writer also supports a full-season historical reconstruction:

```bash
.venv/bin/python scripts/ingest_pregame_team_features.py --season 2026 --mode historical --dry-run
.venv/bin/python scripts/ingest_pregame_team_features.py --season 2026 --mode historical
```

Use the pregame and postgame orchestrators for the normal daily run. Explicit
dates and short ranges on the pregame command are available for testing and
recovery; postgame ranges remain for historical backfills, recovery, or audits.

## Environment

Ingestion requires the project-local virtual environment and the ignored `.env` file with the configured Supabase credentials. Install the pinned dependencies with:

```bash
.venv/bin/python -m pip install -r requirements-ingestion.txt
```

Do not expose the Supabase service-role key to frontend or client code.

## Scope

The current scope is raw MLB ingestion. Derived statistics, feature tables, model training, predictions, betting recommendations, and weather ingestion are not part of the routine workflow yet.
