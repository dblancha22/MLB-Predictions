# Data Timing And Leakage

This document defines timing rules for future derived stats, feature tables, model training, and predictions. Raw ingestion should preserve enough data to enforce these rules later.

## Current Ingestion Cadence

The routine morning `games_raw` job processes only the previous calendar day.
Historical date ranges are used only for backfills, recovery, and audits.

Therefore:

- `games_raw` normally receives a game after its scheduled day, not as a
  same-day pregame schedule feed.
- Today's and future matchups must come from a separately documented pregame
  source or table if prediction work needs them.
- The job remains rerunnable, timestamp-aware, and safe across explicit
  backfill ranges.
- `probable_pitchers` has a separate pregame writer for today's or explicitly
  requested future MLB schedule dates. It does not require or create future
  `games_raw` rows.

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

## Doubleheaders

Doubleheaders need special handling.

Game 1:

- Can use only information known before game 1.

Game 2:

- May use game 1 information only if game 1 was completed before the game 2 prediction cutoff.
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
