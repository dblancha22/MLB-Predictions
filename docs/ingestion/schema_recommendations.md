# Raw Schema Recommendations

These are recommendations from inspecting the current Supabase schema and probing MLB Stats API behavior. They are not applied changes.

## Keep For First Script Pass

The existing raw tables are good enough to start:

- `teams`
- `venues`
- `games_raw`
- `probable_pitchers`
- `team_game_logs`
- `pitcher_game_logs`
- `weather_raw`

No schema change is required before implementing the first ingestion scripts.

## Worth Considering Soon

### Index Declared Foreign Keys

Applied on 2026-07-14 through migration `index_raw_foreign_keys`:

```sql
create index games_raw_home_team_id_idx
  on public.games_raw (home_team_id);

create index games_raw_away_team_id_idx
  on public.games_raw (away_team_id);

create index games_raw_venue_id_idx
  on public.games_raw (venue_id);

create index pitcher_game_logs_team_id_idx
  on public.pitcher_game_logs (team_id);
```

Decision:

- Added B-tree indexes covering every currently declared foreign key.
- Verified that Supabase's `unindexed_foreign_keys` performance findings cleared.
- Treat immediate `unused_index` findings for the new indexes as expected until
  representative query traffic exists; do not remove them based only on early
  usage statistics.
- Review index coverage whenever additional log-table foreign keys are added.

### Doubleheader/Series Diagnostics In `games_raw`

MLB schedule exposes:

- `doubleHeader`
- `gameNumber`
- `seriesGameNumber`
- `gamesInSeries`

Current `games_raw` has `game_id`, so doubleheaders can still be uniquely stored. But storing `doubleHeader` and `gameNumber` would make debugging and matchup grouping easier.

Projection impact:

- `game_number` can matter indirectly for doubleheaders because game 2 may have different bullpen availability, lineup substitutions, catcher rest, and same-day travel/rest effects.
- `doubleheader_code` is more useful as a grouping/debugging field than as a standalone feature.
- `series_game_number` and `games_in_series` are lower priority. They may eventually help with travel/rest/context features, but they are not necessary for the first raw ingestion pass.

Applied columns on 2026-07-14:

```sql
doubleheader_code text,
game_number smallint,
series_game_number smallint,
games_in_series smallint
```

Decision:

- Added the four fields above and populated them from MLB `/schedule`.
- Kept `doubleheader_code` as text to preserve MLB's `N`, `Y`, and `S` codes.
- Did not add `scheduled_innings` or series description.

### Store Pitcher Outs Recorded Instead Of Innings Pitched

Previous column: `innings_pitched double precision`

Applied change:

- Added `public.pitcher_game_logs.outs_recorded smallint` on 2026-07-14.
- Removed `public.pitcher_game_logs.innings_pitched` on 2026-07-14.

MLB innings notation uses `.1` for one out and `.2` for two outs. That is not a decimal fraction. Storing `5.1` as a float can be okay for display, but dangerous for math.

Preferred direction:

- Use `outs_recorded smallint` as the canonical stored value.
- Do not rely on `innings_pitched double precision` for calculations.
- If display innings are needed later, derive them from outs or store MLB notation as text.

Canonical calculation field:

```sql
outs_recorded smallint
```

Decision:

- Use `outs_recorded` for ingestion and downstream calculations.
- Do not store MLB innings notation in `pitcher_game_logs`.
- If display innings are needed later, derive them from `outs_recorded`.

### Distinguish Probable Pitcher From Actual Starter

Current table: `probable_pitchers`

The current writer keeps this table pregame-only. It updates MLB's current
probable assignment and deletes the row when a valid pregame response no longer
names one. It does not overwrite the row with a postgame actual starter.

This avoids mixing pregame and postgame meanings, but the latest-state table
still cannot reconstruct pitcher changes that occurred before first pitch.

Possible additions:

```sql
source_status text -- probable, confirmed_starter
as_of timestamptz
```

Or later split into:

- `probable_pitchers`
- `starting_pitchers`

Decision:

- No schema change for now.
- Keep `probable_pitchers` pregame-only and use
  `pitcher_game_logs.is_starter=true` for the actual starter.
- Revisit snapshot/history storage when prediction timing requires reconstructing
  every assignment that was known before first pitch.

### Add Player Dimension Table

Pitcher handedness comes from `/people/{personId}`, not schedule probable hydration.

A future `players` table would prevent repeated calls and provide a clean home for:

- `player_id`
- `full_name`
- `pitch_hand`
- `bat_side`
- `primary_position`
- `active`
- `mlb_debut_date`

Decision:

- No-op for now.
- Populate `probable_pitchers.pitch_hand` directly from `/people/{personId}`.
- Revisit a player dimension table only when repeated person lookups or broader player metadata become painful.

### Add Foreign Keys To Log Tables

Applied to `team_game_logs` on 2026-07-14 through migration
`add_team_game_logs_foreign_keys`:

- `team_game_logs.game_id` -> `games_raw.game_id`
- `team_game_logs.team_id` -> `teams.team_id`
- `team_game_logs.opponent_id` -> `teams.team_id`
- `team_game_logs_opponent_id_idx` on `(opponent_id)`

The existing primary-key index covers `game_id`, and the existing
`idx_team_logs_team` index covers `team_id`. The table had zero rows when the
constraints were applied, and all three constraints were verified as valid.

Applied on 2026-07-14 before implementing the pitcher-log writer:

- `pitcher_game_logs.game_id` -> `games_raw.game_id`

The existing primary-key index on `(game_id, pitcher_id)` covers `game_id`, so
no additional game index was required.

### Shared Ingestion Utilities

Completed on 2026-07-15 after the table-specific writers stabilized:

- Centralized environment loading, project-ref validation, date parsing,
  Supabase-client creation, and MLB request/retry behavior under
  `scripts/ingestion/`.
- Added `scripts/ingest_postgame.py` as the routine shared postgame orchestrator.
- Retained the standalone table writers for targeted recovery.
- Added run-scoped schedule, boxscore, venue, and failure caching.
- Preserved existing behavior with the original regression suite plus new
  orchestration and request-budget tests.

This refactor required no schema changes.

## Defer

### Generic `raw_api_responses`

Do not add for the first pass. It is useful for replay/debug/audit, but existing normalized raw tables are enough for the current ingestion scope.

### Odds Tables

Odds are required for betting decisions, but current focus is raw baseball data. Add odds raw storage when prediction/betting storage is in scope.

### Weather Schema Changes

Current `weather_raw` is game-level. Before implementing weather ingestion, decide whether it stores:

- pregame forecast
- observed game-time weather
- both, with multiple snapshots

Do not change now.
