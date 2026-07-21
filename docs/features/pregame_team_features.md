# Pregame Team Features

## Purpose

`public.pregame_team_features` stores the model-ready, pregame feature snapshot
for each team in an MLB game. A normally populated game has exactly two rows:
one for the home team and one for the away team.

The table was created in Supabase on 2026-07-18 through migration
`create_pregame_team_features` (`20260718234709`). Population is implemented by
`scripts/ingest_pregame_team_features.py` and by the final stage of
`scripts/ingest_pregame.py`.

The initial 2026 historical backfill completed on 2026-07-18 with 2,948 rows
for 1,474 regular-season games from 2026-03-25 through 2026-07-18. The audit
found exactly two rows per game, no duplicate composite keys, and no formula,
probable-pitcher, metadata, or generated-percentage discrepancies.

## Row Identity And Updates

Primary key:

- `(game_id, team_id)`

`feature_schema_version` records the feature-definition version but is not part
of row identity. Adding a feature later means adding a column and populating it
on the existing team rows. The current table is not a multi-version experiment
or repeated intraday snapshot store.

If repeated snapshots or competing definitions are needed later, add a separate
history/experiment table rather than changing this primary key.

## Columns

Identity and snapshot metadata:

- `game_id bigint`
- `team_id integer`
- `opponent_team_id integer`
- `season smallint`
- `scheduled_start_time_at_cutoff timestamptz`
- `is_home boolean`
- `feature_cutoff_at timestamptz`
- `computed_at timestamptz`
- `feature_schema_version smallint`

Initial rolling offense features:

- `runs_avg_last_5 double precision`
- `hits_avg_last_5 double precision`
- `ops_last_5 double precision`
- `runs_avg_last_10 double precision`
- `hits_avg_last_10 double precision`
- `ops_last_10 double precision`

Opposing probable-pitcher features:

- `opposing_probable_pitcher_id integer`
- `opposing_pitcher_season_era double precision`
- `opposing_pitcher_hand text`

Pregame records:

- `team_wins_before_game smallint`
- `team_losses_before_game smallint`
- `team_win_pct_before_game double precision` (generated)
- `opponent_wins_before_game smallint`
- `opponent_losses_before_game smallint`
- `opponent_win_pct_before_game double precision` (generated)

The win-percentage columns are stored generated columns. They return null when
wins plus losses is zero and otherwise calculate `wins / (wins + losses)`.
Writers must supply the counts and must not attempt to write the generated
percentage columns.

## Feature Definitions

The writer has two explicit timing modes:

- Live mode uses the actual calculation time as `feature_cutoff_at` and skips
  a game when that time is at or after its stored scheduled start.
- Historical mode reconstructs features now while setting `feature_cutoff_at`
  to the target game's stored scheduled start. `computed_at` still records the
  actual later execution time.

`scheduled_start_time_at_cutoff` preserves the scheduled first-pitch time known
when the snapshot was generated. It is intentionally duplicated from
`games_raw` because the canonical schedule time can later change.

Rolling runs and hits:

- Use the most recent eligible completed games from the same season.
- Use only games completed before the cutoff.
- Use all available games when fewer than five or ten exist.
- Do not borrow games from the previous season.
- Treat missing expected raw game logs as a data-quality failure, not as a
  shorter valid window.

Games played can be inferred from the stored wins and losses, so separate
last-5 and last-10 sample-size columns are intentionally omitted.

Rolling OPS:

- Calculate aggregate window OBP plus aggregate window SLG; do not average
  per-game OPS values.
- Exact OBP requires hits, walks, hit by pitch, at-bats, and sacrifice flies.
- Exact SLG requires total bases and at-bats.
- Use `team_game_logs.hits`, `walks`, `hit_by_pitch`, `at_bats`,
  `sacrifice_flies`, and `total_bases` as the exact raw OPS inputs.

Opposing pitcher ERA:

- Resolve the opponent's pitcher from the pregame `probable_pitchers` state.
- Sum the pitcher's same-season completed appearances before the cutoff,
  including appearances for an earlier team after a trade.
- Calculate `earned_runs_allowed * 27 / outs_recorded` from
  `pitcher_game_logs`.
- Store null when no probable pitcher is known or the pitcher has no prior outs.
- Store hand as `R`, `L`, `S`, or null.
- Historical reconstruction accepts `pregame`, `legacy_unknown`, and
  `postgame_recovery` assignments as the best available probable-pitcher value
  for the target game. Capture provenance remains in the raw table.

## Doubleheaders

The first implementation must not use Game 1 results in Game 2 features. This
conservative rule avoids leakage because the current raw schema does not retain
a trustworthy game-completion timestamp. Same-day Game 1 information can be
considered later only when its final state before the Game 2 cutoff can be
proven.

Version 1 implements this rule by excluding every same-day game from the
target's prior-game history, not only identified doubleheaders.

The raw schema does not retain a trustworthy finalization timestamp. Rare
suspended games can therefore create historical completion-time ambiguity; the
known tradeoff is documented rather than hidden by an invented timestamp.

## Dependencies And Population Prerequisites

Foreign keys require:

- `game_id` in `games_raw`
- `team_id` in `teams`
- `opponent_team_id` in `teams`

`scripts/ingest_pregame.py` loads today's games into `games_raw`, refreshes
probable pitchers, and then invokes the live feature writer. A failed games or
probable-pitcher stage prevents the dependent feature stage for that date.

The job order is:

1. Load today's schedule into `games_raw`.
2. Refresh today's `probable_pitchers`.
3. Generate the two `pregame_team_features` rows per eligible game.
4. Update the same `games_raw` rows postgame and ingest final team/pitcher logs.

Standalone commands:

```bash
python scripts/ingest_pregame_team_features.py --date YYYY-MM-DD --mode historical --dry-run
python scripts/ingest_pregame_team_features.py --season 2026 --mode historical
```

The writer paginates Supabase reads, calculates one season in memory, treats a
missing expected prior team-log pair as a game-level failure, and upserts each
game's two rows together by `(game_id, team_id)`. It deliberately omits the two
generated win-percentage columns from writes.

## Constraints And Indexes

The table enforces:

- One row per `(game_id, team_id)`.
- Different team and opponent IDs.
- Nonnegative records and feature values.
- Positive feature-schema versions.
- Feature cutoffs no later than the scheduled start observed at the cutoff.
- Pitcher hand limited to `R`, `L`, `S`, or null.
- No pitcher ERA or hand without an opposing probable-pitcher ID.

Indexes:

- Primary-key index on `(game_id, team_id)`.
- `pregame_team_features_team_id_idx` on `(team_id)`.
- `pregame_team_features_opponent_team_id_idx` on `(opponent_team_id)`.
- `pregame_team_features_season_start_idx` on
  `(season, scheduled_start_time_at_cutoff)`.

## Security

Row Level Security is enabled. No `anon` or `authenticated` policies exist, so
the table is intentionally closed to client access while service-role ingestion
is being developed. Define explicit policies before exposing it through the
Data API.
