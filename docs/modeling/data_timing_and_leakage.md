# Data Timing And Leakage

This document defines timing rules for future derived stats, feature tables, model training, and predictions. Raw ingestion should preserve enough data to enforce these rules later.

## Current Ingestion Cadence

The routine morning workflow has separate pregame and postgame commands:

- `scripts/ingest_pregame.py --today` loads today's schedule into `games_raw`
  and then refreshes `probable_pitchers` from one shared schedule response.
- `scripts/ingest_postgame.py --yesterday` processes the previous calendar day
  and updates `games_raw`, `team_game_logs`, and `pitcher_game_logs` in
  dependency order. Historical postgame ranges remain for backfills, recovery,
  and audits.

Therefore:

- `games_raw` receives today's games before feature generation and the same
  canonical rows are updated after finalization.
- The postgame workflow remains rerunnable, timestamp-aware, and safe across
  explicit backfill ranges.
- `probable_pitchers` remains a latest-state table and its standalone writer
  remains available for targeted recovery. The orchestrated games stage now
  creates the parent `games_raw` rows needed by `pregame_team_features`.
- `pregame_team_features` population remains unimplemented. When added, it must
  run only after both current pregame stages succeed.

## Timing Categories

### Pregame-Known

Usually safe before first pitch:

- scheduled game date/time
- home and away teams
- venue
- probable pitchers when available
- team records derived from prior completed games
- prior pitcher/team logs

Mutable before first pitch:

- probable pitchers
- game status
- scheduled start time
- postponements
- odds, when added later
- weather forecast, when added later

### Live Mutable

Should not be used for pregame predictions unless explicitly building live models:

- current score
- live linescore
- live boxscore stats
- in-game pitcher usage
- live game status

### Postgame Final

Safe for future games after finalization:

- final score
- team game logs
- pitcher game logs
- actual starter from boxscore
- final game status

Postgame data may still receive corrections, so ingestion should support lookback updates.

## Leakage Rules

For a target game, features must not use:

- the target game's final score
- the target game's boxscore stats
- postgame pitcher logs from the target game
- standings that include the target game result
- odds or weather snapshots taken after the chosen prediction cutoff, once those are stored

For completed historical training rows:

- Feature generation should simulate what was knowable before the game.
- The label/target can use final result data.
- The feature row and target row should be conceptually separate.

## Pregame Feature Snapshots

`pregame_team_features` preserves one feature row per game/team. Every row must
store:

- `feature_cutoff_at`, defining the latest allowed source information
- `scheduled_start_time_at_cutoff`, preserving the mutable scheduled start that
  was known when features were computed
- `computed_at`, recording when the calculation ran
- `feature_schema_version`, identifying the calculation definitions

The primary key is `(game_id, team_id)`. The schema version is metadata, not a
second row dimension. Adding future features populates new columns on the
existing row.

Probable-pitcher ID, hand, and entering ERA are copied into the feature row so
later changes to the latest-state `probable_pitchers` table cannot alter the
training record.

## Doubleheaders

Doubleheaders need special handling.

Game 1:

- Can use only information known before game 1.

Game 2:

- Version 1 must not use same-day game 1 information.
- A future version may use game 1 only if a trustworthy timestamp proves it was
  completed before the game 2 prediction cutoff.
- Bullpen and lineup/catcher rest effects may make game 2 meaningfully different.

Current raw schema:

- `game_id` uniquely identifies games.
- `doubleheader_code` distinguishes regular, traditional-doubleheader, and
  split-doubleheader schedule records.
- `game_number` identifies game 1 or 2 when MLB supplies that context.
- `series_game_number` and `games_in_series` preserve the broader series position.

## Probable Pitchers

Current decision:

- No separate actual-starter table yet.
- `probable_pitchers` contains only MLB's latest observed pregame assignment.
- Actual starters remain in `pitcher_game_logs` through `is_starter=true`.

Timing caution:

- Probable pitchers can change.
- Future prediction snapshots may need to preserve what pitcher was known at prediction time.
- The current writer updates an announced pitcher and deletes the assignment
  when a valid pregame response no longer names one. It does not retain change
  history, so `updated_at` alone cannot reconstruct every earlier assignment.
- Live/final schedule responses do not update or clear pregame assignments.

## Odds

Current decision:

- Odds will be stored later, not in the current raw baseball ingestion phase.

Future timing need:

- Odds must have source and timestamp.
- Line movement should not leak later market information into earlier predictions.
- Model-vs-market comparisons should use odds available at the prediction cutoff.

## Weather

Current decision:

- Weather is a placeholder for now.

Future timing need:

- Forecast weather and observed weather should not be mixed without explicit labels.
- Pregame predictions should use forecast snapshots available before the cutoff.

## Recovery Lookbacks

The normal morning run stays previous-day only. A separate explicit recovery
run may use a wider range when needed for:

Reasons:

- late finals
- suspended games
- postponed games
- stat corrections
- doubleheader complications

Recovery ranges should be invoked deliberately and logged; they do not change
the routine daily cadence.
