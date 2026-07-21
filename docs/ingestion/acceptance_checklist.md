# Ingestion Acceptance Checklist

Use this checklist before considering a raw ingestion script ready.
The raw-writer scope below applies to the raw table scripts. The separately
approved `ingest_pregame_team_features.py` derived writer is governed by the
Pregame Team Features section in this document.

## Scope

- The script writes only raw tables.
- The script does not write derived stats.
- The script does not write feature tables.
- The script does not write model training rows.
- The script does not write predictions or bet recommendations.

## Configuration

- Credentials are read from environment variables or local secret files, not hardcoded.
- Credentials point to the intended Supabase project before running.
- Service-role credentials are never exposed to frontend/client code.
- Ingestion runs from a project-local virtual environment installed from the
  fully pinned `requirements-ingestion.txt`; `supabase-py` is not installed as
  an unpinned global dependency.
- The command supports a single date.
- The command supports a date range before broad backfills.
- The routine results/log invocation targets only the previous calendar day.
- The pregame invocation supports `--today`, explicit dates, and short future
  ranges; results/log date ranges remain reserved for backfills, recovery, and
  audits.

## Idempotency

- Running the same date twice does not create duplicates.
- Upserts use documented primary keys.
- Missing optional data does not crash the whole run.
- Partial failures can be retried.
- Logs identify the date, game, table, and source involved in failures.

## Shared Postgame Workflow

- `--yesterday` resolves through an explicit logged IANA timezone and defaults
  to `America/Los_Angeles`.
- Timezone selection affects only date resolution, not MLB official dates or
  stored UTC timestamps.
- The four postgame stages share one schedule payload hydrated with
  `probablePitcher,venue,team` per bounded date chunk.
- Team and pitcher transforms share one boxscore payload per unique `gamePk`.
- In-memory cache state is discarded after the command exits.
- Physical MLB request and cache-hit totals are logged.
- A failed games stage skips dependent stages for that date.
- Probable recovery processes only postgame-safe finals, inserts only missing
  composite keys, and never updates or deletes an existing assignment.
- Recovered rows are labeled `capture_type=postgame_recovery`; normal pregame
  rows are labeled `capture_type=pregame`.
- Rows predating the current writer are labeled `capture_type=legacy_unknown`
  rather than being retroactively claimed as pregame observations.
- A failed recovery person lookup skips that assignment and makes the command
  exit nonzero so a rerun can complete it safely.
- `--steps probable-recovery` supports a recovery-only historical range.
- Existing table-specific commands remain usable for targeted recovery.

## Shared Pregame Workflow

- `--today` resolves through an explicit logged IANA timezone and defaults to
  `America/Los_Angeles`.
- The games and probable-pitcher stages share one schedule payload hydrated with
  `probablePitcher,venue,team` per bounded date chunk.
- The games stage runs before the probable-pitcher stage.
- The feature stage runs after the games and probable-pitcher stages.
- A failed games stage skips the probable-pitcher and feature stages for that
  date. A failed probable-pitcher stage skips the feature stage.
- A malformed probable game or failed person enrichment makes the command exit
  nonzero while preserving safe writes for retry.
- Physical MLB request and cache-hit totals are logged.
- `--steps games`, `--steps probable-pitchers`, and `--steps team-features`
  support targeted recovery.
- Live feature processing skips games at or after scheduled first pitch.
- Historical feature processing simulates the stored scheduled start cutoff.
- Feature summaries report games found, started games skipped, game failures,
  rows ready, and rows upserted.

## Pregame Team Features

- Produces exactly two rows per eligible game and upserts by
  `(game_id, team_id)`.
- Paginates all Supabase source reads beyond the Data API row limit.
- Uses only same-season regular-season raw data.
- Excludes every same-day game from version-1 history.
- Uses all available prior games when fewer than five or ten exist; rolling
  values are null when no prior game exists and records begin at `0-0`.
- Calculates OPS from aggregate window inputs rather than averaging per-game
  OPS values.
- Calculates opposing pitcher ERA from prior same-season earned runs and outs.
- Accepts all probable-pitcher capture types for the approved historical
  reconstruction policy.
- Treats a missing expected prior team-log pair as a failure rather than a
  shorter valid window.
- Does not write the generated win-percentage columns.
- A same-date rerun replaces the existing snapshot without adding duplicates.

## Current Raw Tables

### `teams`

- Uses MLB `team.id` as `team_id`.
- Can be rerun for a season.
- Preserves active team metadata from MLB.

### `venues`

- Uses MLB `venue.id` as `venue_id`.
- Calls MLB `/venues/{venueId}?hydrate=location` only for missing venue IDs.
- Inserts available MLB location, coordinate, elevation, and azimuth fields.
- Does not invent enriched park metadata unless source is documented.
- Allows nullable fields for metadata not available from MLB.

### `games_raw`

- Uses MLB `gamePk` as `game_id`.
- Stores game date and scheduled UTC time.
- Stores home and away team IDs.
- Stores venue ID when available.
- Stores status.
- Stores MLB doubleheader code, game number, series game number, and games in series.
- Updates final scores after games complete.
- Routinely loads today's schedule through `scripts/ingest_pregame.py` and
  accepts explicit short future ranges for testing or recovery.
- Handles no-game dates without failure.
- Handles doubleheaders by `game_id` and preserves their source metadata.
- Deduplicates suspended/resumed occurrences by `game_id` and preserves the
  original game date, scheduled time, and series metadata.

### `probable_pitchers`

- Upserts by `(game_id, team_id)`.
- Stores pitcher ID and full name when available.
- Missing probable pitcher is treated as normal.
- Pitch hand is populated from `/people/{personId}` when available.
- Processes only games in MLB's `Preview` state.
- Deletes a stale game/team assignment when a valid pregame schedule response
  currently omits that probable.
- Never deletes assignments because of a failed request, malformed game, or a
  live/final schedule record.
- Validates team IDs but does not require future games in `games_raw`.
- Keeps actual-starter logic in `pitcher_game_logs`.
- Postgame recovery inserts an MLB-retained probable only when no row exists,
  uses conflict-ignore semantics, and never substitutes an actual starter.
- `capture_type` distinguishes `pregame` observations from
  `postgame_recovery` rows and conservatively labels older rows
  `legacy_unknown`.
- Continues after person-enrichment failures, stores a null hand for the current
  assignment, and exits nonzero so the metadata can be retried.

### `team_game_logs`

- Populated only for final or postgame-safe games.
- Recognizes MLB completed-early finals whose `codedGameState` is `F` even when
  the more specific `statusCode` is not exactly `F`.
- Produces two rows per completed game when boxscore data is available.
- Uses team and opponent IDs.
- Stores MLB team batting `hitByPitch` and `sacFlies` as integer raw values.
- Does not calculate derived rolling stats.
- Continues other games after a game-level source/transform failure and exits
  nonzero when any game failed.
- Verifies referenced games and teams before writing; database foreign keys
  enforce `game_id`, `team_id`, and `opponent_id` integrity.

### `pitcher_game_logs`

- Populated only for final or postgame-safe games.
- Recognizes completed-early games from `codedGameState=F`.
- Stores all actual pitcher appearances, not only starters, and ignores listed
  pitchers whose game stats report `gamesPitched=0`.
- Uses MLB `gamesStarted` to mark the actual starter for each team.
- Uses `outs_recorded` from MLB pitching stats.
- Does not store or calculate using decimal innings notation.
- Upserts by `(game_id, pitcher_id)` and can safely refresh an already-marked
  game during an explicit rerun.
- Verifies `games_raw` and `teams` dependencies; database foreign keys enforce
  both references.
- Sets `games_raw.pitcher_logs_processed=true` only after the complete game row
  set is upserted. Marker updates receive bounded retries, and a final failure
  causes a nonzero exit without discarding successfully written rows.
- Continues other games after a game-level failure and exits nonzero when any
  game remains incomplete.
- The completed 2026 season-to-date backfill contains 12,234 distinct rows for
  all 1,444 canonical games, with every game marked processed and no unexplained
  integrity discrepancies.

### `weather_raw`

- Deferred until a source is chosen.
- If implemented later, documents whether values are forecast or observed.

## Data Timing

- Pregame schedule/probable data is allowed to be mutable.
- Final score/log data is only written from postgame-safe sources.
- Scripts can update prior dates to catch corrections.
- Future feature logic must be able to distinguish pregame-known data from postgame labels.

## Verification

For a small sample date or a backfill range:

- `games_raw` row count matches MLB schedule game count after documented
  cross-date postponement skips.
- final games have scores.
- no duplicate primary keys are produced.
- rerunning the command produces the same row counts.
- team and venue foreign keys resolve.
- doubleheader and series metadata matches MLB source values.
