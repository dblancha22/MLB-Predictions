# Feature Planning

This document captures likely future feature families so raw ingestion can collect enough data without prematurely building derived stats or model tables.

## Current Modeling Direction

Primary prediction goals:

- Win probability
- Runs scored

Primary betting markets:

- Moneyline
- Totals

Run line/spread may be useful later, but it is not a current design driver.

## Guiding Principle

Collect richer raw data than the first model needs. Derived features can start simple, but raw ingestion should preserve enough game, team, pitcher, venue, and eventually odds context to support more complex features later.

## Implemented Feature Storage

`public.pregame_team_features` was created on 2026-07-18 as the first derived
feature table. It stores one team-perspective row per game/team, normally two
rows per game, with primary key `(game_id, team_id)`.

The initial columns cover rolling runs, hits, aggregate OPS, opposing probable
pitcher ERA and hand, pregame team/opponent records, and home/away context.
Population is not implemented yet. See
[Pregame Team Features](pregame_team_features.md) for the exact schema and
feature rules.

## Candidate Feature Families

### Team Performance

Likely derived from:

- `games_raw`
- `team_game_logs`

Potential features:

- Win percentage entering game
- Rolling run differential
- Rolling runs scored
- Rolling runs allowed
- Rolling hits, home runs, strikeouts, walks
- Home/away splits
- Recent form over configurable windows
- Season-to-date offensive production
- Opponent-adjusted performance later

Timing notes:

- Features must use only games completed before the target game.
- The first feature writer will exclude same-day Game 1 results from Game 2.
- Early-season windows use the available same-season games; games played is
  inferred from the stored pregame wins and losses.

### Starting Pitcher Form

Likely derived from:

- `probable_pitchers`
- `pitcher_game_logs`

Potential features:

- Season ERA entering game
- Recent ERA over last N outs
- Strikeout rate
- Walk rate
- Home runs allowed rate
- Runs/earned runs allowed rate
- Pitches per appearance
- Rest days since last appearance
- Starter workload trend

Important raw design note:

- Use `outs_recorded` as the canonical workload field.
- Do not treat MLB innings notation as decimal math.
- The initial opposing-pitcher ERA feature is season-to-date ERA entering the
  game: `earned_runs_allowed * 27 / outs_recorded`.

### Bullpen Usage And Fatigue

Likely derived from:

- `pitcher_game_logs`
- `games_raw`

Potential features:

- Bullpen outs thrown yesterday
- Bullpen pitches thrown yesterday
- Bullpen usage over last 3 days
- High-leverage relievers unavailable proxy
- Consecutive-day pitcher usage
- Starter short-outing pressure on bullpen

Raw data need:

- Store all pitcher appearances, not just starters.

### Schedule Context

Likely derived from:

- `games_raw`

Potential features:

- Home/away
- Rest days
- Travel context later
- Doubleheader game number
- Series position later
- Day/night
- Scheduled innings

Current schema note:

- `game_id` uniquely handles doubleheaders.
- `game_number` may become useful for projections, especially game 2 of a doubleheader.

### Venue And Park Context

Likely derived from:

- `venues`
- future curated venue metadata

Potential features:

- Park identity
- Altitude
- Roof type
- Field dimensions
- Park factor later

Current status:

- Venue table exists.
- Enriched park metadata can be deferred.

### Weather

Likely derived from:

- `weather_raw`

Potential features:

- Temperature
- Wind speed/direction
- Humidity
- Precipitation
- Conditions

Current status:

- Placeholder for now.
- Do not over-design until a weather source is selected.

### Odds And Market Context

Likely future raw storage:

- moneyline odds
- total line
- over/under odds
- sportsbook/source
- odds timestamp

Potential features or downstream comparisons:

- Implied win probability
- Devigged market probability
- Implied total
- Market-vs-model edge
- Line movement later

Current status:

- Odds will be stored later.
- Odds are excluded from the current raw baseball ingestion phase.

## Open Modeling Decisions

- Whether win probability should be modeled as team-level rows, game-level home win probability, or both.
- Whether odds should eventually be a model input, a post-model comparison tool, or both.
- What exact cutoff time should define "known before prediction" once run cadence is decided.
- Whether run line/spread should become a first-class target later.
