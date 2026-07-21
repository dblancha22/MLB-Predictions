# Supabase Table Catalog

Project inspected: `BagBrainOfficial`

Project ID: `soakgdpuvtxadjextekg`

Latest schema inspection: 2026-07-18. Existing row-count observations retain
their individually stated inspection dates.

This catalog reflects the current public schema as inspected through the Supabase connector. It should be refreshed whenever migrations are applied.

## Security Note

Supabase reported Row Level Security disabled on the existing raw public tables.
This can be acceptable for private service-role ingestion, but it is risky if
anon or authenticated client keys can access these tables.

`pregame_team_features` was created with RLS enabled and no client policies. It
is closed to `anon` and `authenticated` access while its service-role writer is
being developed.

Do not enable RLS blindly. Enabling RLS without policies can block expected access. Before exposing data to frontend/client code, define access policies intentionally.

## Existing Tables

### `public.teams`

Purpose: MLB team dimension table.

Observed row count: 30 as of 2026-07-14.

Primary key: `team_id`

Important columns:

- `team_id integer`
- `name text`
- `team_name text`
- `franchise_name text`
- `abbreviation text`
- `team_code text`
- `file_code text`
- `location_name text`
- `league_id integer`
- `division_id integer`
- `sport_id integer`
- `first_year_of_play integer`
- `active boolean`
- `venue_id integer`
- `created_at timestamp`
- `updated_at timestamp`

Ingestion notes:

- Populate from MLB Stats API `/teams`.
- Should be loaded before `games_raw`, `probable_pitchers`, `team_game_logs`, and `pitcher_game_logs`.
- Use MLB `team.id` as `team_id`.

### `public.venues`

Purpose: venue dimension table.

Observed row count: 32 as of 2026-07-14.

Observed completeness on 2026-07-14:

- All 32 rows have names, cities, and countries. One international venue has no
  state value from MLB.
- One venue is missing coordinates; two are missing altitude, roof type, center
  distance, and field orientation.
- All 32 rows have null `timezone`.
- Left-field distance is null for 19 rows and right-field distance is null for
  21 rows.

Primary key: `venue_id`

Important columns:

- `venue_id integer`
- `name text`
- `city text`
- `state text`
- `country text`
- `latitude double precision`
- `longitude double precision`
- `altitude_ft double precision`
- `timezone text`
- `roof_type text`
- `left_field_distance integer`
- `center_field_distance integer`
- `right_field_distance integer`
- `field_orientation_degrees double precision`
- `created_at timestamp`

Ingestion notes:

- Basic venue identity can come from MLB schedule/team responses.
- Missing venue IDs are enriched from MLB `/venues/{venueId}?hydrate=location`
  before insertion by `scripts/ingest_games_raw.py`.
- Enriched park factors, altitude, dimensions, roof type, and orientation may require manual curation or a separate trusted source.
- Load before `games_raw` when `venue_id` foreign keys are present.

### `public.games_raw`

Purpose: canonical MLB game schedule/result table. Rows are created pregame for
the current schedule and updated postgame with final state and scores.

Observed row count: 1,444 as of 2026-07-14, covering `2026-03-25` through
`2026-07-12`. This is the unique `game_id` count after documented cross-date
postponement skips and deduplication of one suspended game repeated on its
resume date.

All 1,444 rows in this coverage range have `pitcher_logs_processed=true` after
the completed pitcher-log backfill on 2026-07-14.

Primary key: `game_id`

Foreign keys:

- `home_team_id` -> `teams.team_id`
- `away_team_id` -> `teams.team_id`
- `venue_id` -> `venues.venue_id`

Foreign-key indexes:

- `games_raw_home_team_id_idx` on `(home_team_id)`
- `games_raw_away_team_id_idx` on `(away_team_id)`
- `games_raw_venue_id_idx` on `(venue_id)`

These B-tree indexes were added by migration `index_raw_foreign_keys` on
2026-07-14 so joins, filters, and parent-row referential checks do not require
full scans of `games_raw` as the table grows.

Important columns:

- `game_id bigint`
- `game_date date`
- `home_team_id integer`
- `away_team_id integer`
- `venue_id integer`
- `home_score integer`
- `away_score integer`
- `status text`
- `scheduled_time_utc timestamptz`
- `game_type text`
- `season smallint`
- `day_night text`
- `doubleheader_code text`
- `game_number smallint`
- `series_game_number smallint`
- `games_in_series smallint`
- `pitcher_logs_processed boolean`
- `created_at timestamptz`
- `updated_at timestamptz`

Ingestion notes:

- Populate from MLB Stats API `/schedule`.
- Use MLB `gamePk` as `game_id`.
- `scripts/ingest_postgame.py` is the routine postgame orchestrator and invokes
  the `games_raw` writer with a shared schedule payload.
- `scripts/ingest_pregame.py` is the routine same-day pregame orchestrator. It
  creates today's canonical game rows before synchronizing probable pitchers.
- `scripts/ingest_games_raw.py` remains the standalone writer for targeted
  recovery.
- `doubleheader_code` preserves MLB's `doubleHeader` source code rather than
  reducing traditional and split doubleheaders to one boolean value.
- Store the requested MLB schedule date as `game_date` for ingested records.
  Cross-date postponed records are skipped on the original date and enter the
  table when their rescheduled date is ingested. Same-day or not-yet-rescheduled
  postponements remain on the requested date.
- Suspended games repeated on a resume date retain their original `game_date`,
  scheduled time, and series metadata while accepting later status/score updates.
- Routine pregame runs request today; routine postgame runs request yesterday.
  Explicit short pregame ranges are for testing and recovery, while broad
  postgame ranges remain for historical backfills, recovery, and audits.
- Pregame upserts include every schedule occurrence for the requested source
  date and omit score fields until MLB reports the configured final status.
- `pitcher_logs_processed` is ingestion bookkeeping for the pitcher-log stage
  used by both `scripts/ingest_postgame.py` and the standalone
  `scripts/ingest_pitcher_game_logs.py` command, not a modeling feature.

### `public.probable_pitchers`

Purpose: probable or known starting pitcher assignment by game/team.

Observed row count before implementation: 782 rows across 391 games. All
observed rows had non-null pitcher IDs, names, and hands. Their `updated_at`
values were from an earlier 2026-04-24 load; the current writer does not
reinterpret those completed-game rows as timestamped pregame snapshots.

After the initial `2026-07-17` validation and idempotency rerun on 2026-07-14,
the table contained 786 rows across 395 games and 786 distinct composite keys.
The four new rows matched MLB pitcher IDs, names, and hand codes.

After the postgame recovery backfill through 2026-07-18, the table contained
2,942 distinct composite keys: 782 `legacy_unknown` rows, eight `pregame`
rows, and 2,152 `postgame_recovery` rows. All rows had non-null pitcher IDs,
names, and hands.
Of 1,474 games in the audited range, 1,470 had both assignments, two final
games had one MLB-retained assignment, and two July 18 games that were still in
progress had none; the next successful postgame run can recover those if MLB
retains the assignments after final.

Primary key: `(game_id, team_id)`

Foreign keys: none. The routine pregame orchestrator nevertheless writes
`games_raw` first because its future feature-table stage requires that parent
row and because the shared ordering makes failures explicit.

Important columns:

- `game_id bigint`
- `team_id integer`
- `pitcher_id integer`
- `pitch_hand text`
- `full_name text`
- `updated_at timestamptz`
- `capture_type text NOT NULL DEFAULT 'pregame'`, constrained to
  `legacy_unknown`, `pregame`, or `postgame_recovery`

Ingestion notes:

- Prefer MLB schedule `probablePitcher` fields when available.
- `scripts/ingest_probable_pitchers.py` is the current writer.
- `scripts/ingest_pregame.py` is the routine entry point and passes its shared
  combined schedule payload into this writer.
- Process only games with `status.abstractGameState=Preview`.
- Morning rows are mutable because probable pitchers can change. Upsert
  announced assignments by `(game_id, team_id)` and label them `pregame`.
- When a valid pregame response has no probable for a game/team, delete that
  existing assignment. Do not clear data after a failed or malformed response.
- Enrich `pitch_hand` with MLB `/people/{personId}`. A failed enrichment stores
  null rather than carrying another pitcher's hand across an assignment change.
- `scripts/ingest_postgame.py` uses MLB's final schedule response only to insert
  a missing `(game_id, team_id)` assignment. It labels the row
  `postgame_recovery`, ignores primary-key conflicts, never overwrites or
  deletes an existing assignment, and never substitutes the boxscore starter.
- Actual starters are represented by `pitcher_game_logs.is_starter`.
- The table stores latest state, not assignment history. `updated_at` records
  when the current announced assignment was observed. `capture_type` separates
  a true pregame observation from a retrospectively recovered MLB assignment;
  rows predating the current writer are conservatively labeled
  `legacy_unknown`.

### `public.team_game_logs`

Purpose: postgame team-level batting/result stats by game/team.

Primary key: `(game_id, team_id)`

Observed row count: 2,888 as of 2026-07-14, covering 1,444 games from
`2026-03-25` through `2026-07-12` with exactly two rows per game.

Foreign keys:

- `game_id` -> `games_raw.game_id`
- `team_id` -> `teams.team_id`
- `opponent_id` -> `teams.team_id`

Foreign-key indexes:

- The primary-key index on `(game_id, team_id)` covers `game_id`.
- `idx_team_logs_team` covers `team_id`.
- `team_game_logs_opponent_id_idx` covers `opponent_id`.

The three foreign keys and the opponent index were added by migration
`add_team_game_logs_foreign_keys` on 2026-07-14, after confirming that the
table was empty and had no existing integrity violations.

Important columns:

- `game_id bigint`
- `team_id integer`
- `opponent_id integer`
- `runs_scored integer`
- `hits integer`
- `home_runs integer`
- `strikeouts integer`
- `walks integer`
- `hit_by_pitch integer`
- `sacrifice_flies integer`
- `plate_appearances integer`
- `at_bats integer`
- `total_bases integer`
- `left_on_base integer`
- `grounded_into_double_play integer`
- `doubles integer`
- `triples integer`

Ingestion notes:

- Populate after games are final.
- Source: MLB Stats API `/game/{gamePk}/boxscore`.
- `scripts/ingest_postgame.py` is the routine entry point and passes its cached
  boxscores into the team-log writer.
- `scripts/ingest_team_game_logs.py` remains the standalone writer for targeted
  recovery.
- Upsert one row per team per game.
- Should not be expected to exist for future scheduled games.
- MLB `codedGameState=F` is the postgame eligibility signal used by this writer;
  this includes `statusCode=FR` / `Completed Early` games.
- The completed backfill audit found no duplicate keys, missing mapped stats,
  invalid team/opponent pairs, negative values, or score mismatches.
- `hit_by_pitch` and `sacrifice_flies` preserve MLB boxscore
  `hitByPitch` and `sacFlies` so exact aggregate-window OBP and OPS can be
  calculated downstream.
- Both columns were added on 2026-07-18 through migration
  `add_team_game_logs_ops_inputs` (`20260719000353`). The full documented
  2026 season-to-date range was backfilled, leaving zero nulls across 2,888
  rows.

### `public.pitcher_game_logs`

Purpose: postgame pitcher appearance stats by game/pitcher.

Observed row count: 12,234 as of 2026-07-14, covering all 1,444 canonical games
from `2026-03-25` through `2026-07-12`.

Primary key: `(game_id, pitcher_id)`

Foreign keys:

- `game_id` -> `games_raw.game_id`
- `team_id` -> `teams.team_id`

Foreign-key indexes:

- `pitcher_game_logs_team_id_idx` on `(team_id)`

The game foreign key was added on 2026-07-14 before implementation of the
pitcher-log writer. The primary-key index on `(game_id, pitcher_id)` covers
`game_id`. The team B-tree index was added by migration
`index_raw_foreign_keys` on 2026-07-14.

Important columns:

- `game_id bigint`
- `pitcher_id integer`
- `team_id integer`
- `outs_recorded smallint`
- `strikeouts integer`
- `walks integer`
- `home_runs_allowed integer`
- `hits_allowed integer`
- `runs_allowed integer`
- `earned_runs_allowed integer`
- `pitches_thrown integer`
- `batters_faced integer`
- `fly_outs smallint`
- `ground_outs smallint`
- `is_starter boolean`

Ingestion notes:

- Populate after games are final.
- Source can be MLB Stats API boxscore/game feed, or player game logs if needed.
- Store all pitchers, not only starters, because future derived features may need bullpen usage and fatigue.
- Store only actual appearances whose game stats report `gamesPitched>0`, and
  use `gamesStarted>0` for `is_starter`. MLB can list an announced pitcher who
  did not appear before the actual starter.
- Use `outs_recorded` as the canonical calculation field. MLB `inningsPitched` notation is not decimal math and is not stored in this table.
- Upsert by `(game_id, pitcher_id)`.
- After a complete game upsert, set `games_raw.pitcher_logs_processed=true`.
  Retry a failed marker update with bounded backoff; if it still fails, report
  the game as incomplete and exit nonzero. Explicit recovery runs may refresh
  already-marked games.
- `scripts/ingest_postgame.py` is the routine entry point and passes its cached
  boxscores into the pitcher-log writer.
- `scripts/ingest_pitcher_game_logs.py` remains the standalone writer for
  targeted recovery.
- The completed backfill audit found no duplicate keys, missing required stats,
  negative values, invalid game/team pairs, missing team coverage, or
  starter-count anomalies.

### `public.pregame_team_features`

Purpose: frozen, model-ready pregame features from each team's perspective.
Normally contains exactly two rows per game.

Created on 2026-07-18 through migration `create_pregame_team_features`
(`20260718234709`). `scripts/ingest_pregame_team_features.py` is the standalone
writer, and `scripts/ingest_pregame.py` invokes it after its two raw pregame
stages.

Observed row count: 2,948 rows for 1,474 2026 regular-season games as of
2026-07-18, covering `2026-03-25` through `2026-07-18` with exactly two rows per
game. The completed backfill audit found zero duplicate keys, formula
mismatches, probable-pitcher mismatches, generated-percentage mismatches,
metadata mismatches, or invalid negative values.

Primary key: `(game_id, team_id)`

Foreign keys:

- `game_id` -> `games_raw.game_id`
- `team_id` -> `teams.team_id`
- `opponent_team_id` -> `teams.team_id`

Indexes:

- The primary-key index on `(game_id, team_id)` covers `game_id`.
- `pregame_team_features_team_id_idx` covers `team_id`.
- `pregame_team_features_opponent_team_id_idx` covers `opponent_team_id`.
- `pregame_team_features_season_start_idx` covers
  `(season, scheduled_start_time_at_cutoff)`.

Important columns:

- `game_id bigint`
- `team_id integer`
- `opponent_team_id integer`
- `season smallint`
- `scheduled_start_time_at_cutoff timestamptz`
- `is_home boolean`
- `feature_cutoff_at timestamptz`
- `computed_at timestamptz`
- `feature_schema_version smallint`
- `runs_avg_last_5 double precision`
- `hits_avg_last_5 double precision`
- `ops_last_5 double precision`
- `runs_avg_last_10 double precision`
- `hits_avg_last_10 double precision`
- `ops_last_10 double precision`
- `opposing_probable_pitcher_id integer`
- `opposing_pitcher_season_era double precision`
- `opposing_pitcher_hand text`
- `team_wins_before_game smallint`
- `team_losses_before_game smallint`
- `team_win_pct_before_game double precision` (generated)
- `opponent_wins_before_game smallint`
- `opponent_losses_before_game smallint`
- `opponent_win_pct_before_game double precision` (generated)

Feature notes:

- `feature_schema_version` is metadata and is not part of uniqueness. Future
  feature columns are populated on the existing game/team row.
- Win percentages are generated from the stored wins and losses and are null
  before either team has a decision.
- Early-season rolling windows use all available same-season games. Separate
  window sample-size columns are omitted because games played can be inferred
  from wins and losses.
- OPS is aggregate window OBP plus aggregate window SLG, not an average of
  per-game OPS values.
- Opposing pitcher ERA uses prior same-season earned runs and outs:
  `earned_runs_allowed * 27 / outs_recorded`.
- Version 1 excludes same-day Game 1 results from Game 2 features.
- `scheduled_start_time_at_cutoff` preserves the mutable schedule value known
  at calculation time.
- Live mode uses the actual computation cutoff and skips started games;
  historical mode uses the stored scheduled start as a simulated cutoff.
- Historical version 1 accepts every probable-pitcher capture type under the
  approved reconstruction assumption.
- The writer paginates raw-table reads and upserts each two-row game pair by the
  composite primary key while omitting generated percentage columns.

Security:

- RLS is enabled.
- No client policies exist; service-role ingestion remains possible.

See [Pregame Team Features](../features/pregame_team_features.md) for the full
population contract and prerequisites.

### `public.weather_raw`

Purpose: game-level weather snapshot.

Primary key: `game_id`

Important columns:

- `game_id bigint`
- `temperature_f double precision`
- `wind_speed_mph double precision`
- `wind_direction text`
- `humidity double precision`
- `precipitation_prob double precision`
- `precipitation_amount double precision`
- `pressure double precision`
- `dew_point double precision`
- `weather_snapshot_time timestamp`
- `conditions text`

Ingestion notes:

- Source is not decided yet.
- For morning predictions, weather should be a pregame forecast snapshot with a timestamp.
- For historical analysis, distinguish forecast weather from observed weather if both are ever stored.
