# Raw Ingestion Acceptance Checklist

Use this checklist before considering a raw ingestion script ready.

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
- The separate probable-pitcher invocation supports today's date and explicit
  short future ranges; results/log date ranges remain reserved for backfills,
  recovery, and audits.

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
- The three postgame stages share one schedule payload per bounded date chunk.
- Team and pitcher transforms share one boxscore payload per unique `gamePk`.
- In-memory cache state is discarded after the command exits.
- Physical MLB request and cache-hit totals are logged.
- A failed games stage skips dependent stages for that date.
- Existing table-specific commands remain usable for targeted recovery.

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
- Does not routinely load today's or future schedule.
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
- Continues after person-enrichment failures, stores a null hand for the current
  assignment, and exits nonzero so the metadata can be retried.

### `team_game_logs`

- Populated only for final or postgame-safe games.
- Recognizes MLB completed-early finals whose `codedGameState` is `F` even when
  the more specific `statusCode` is not exactly `F`.
- Produces two rows per completed game when boxscore data is available.
- Uses team and opponent IDs.
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
