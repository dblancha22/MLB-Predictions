# Notebook To Raw Tables Map

This maps important notebook behaviors to the raw tables that should eventually replace notebook-local CSVs and legacy scraped inputs.

Future ingestion should not scrape websites. Legacy scraped inputs are documented only to explain the prototype's behavior.

Notebook source: `mlb_daily_clean copy 2.ipynb`

## Schedule And Matchups

Notebook concepts:

- `get_pitchers`
- `get_starting_pitchers`
- `combine_pitchers_and_odds`
- `games`
- `final_matchups`
- `day_entries`

Raw table targets:

- `games_raw`
- `probable_pitchers`
- `teams`
- `venues`

API sources:

- `/schedule?hydrate=probablePitcher,venue,team`
- `/people/{personId}` for `pitch_hand`

Current boundary:

- Keep `probable_pitchers` pregame-only. Store actual starters in
  `pitcher_game_logs` with `is_starter=true`; do not overwrite probable rows
  from postgame boxscores.
- A valid pregame omission removes the existing game/team probable assignment,
  while request failures, malformed games, and live/final records never clear it.

## Team Records

Notebook concepts:

- `get_team_record`
- `Win %`
- `Opponent Win %`
- `fix_pregame_records`

Raw table targets:

- `games_raw`

Future derived tables:

- team standings entering game date
- team rolling win percentage

Notes:

- Current raw ingestion should not store derived win percentage.
- Pregame records can be derived from final games before the target game date.
- Doubleheaders need careful ordering because game 2 should know game 1 if game 1 is final before game 2.

## Scores And Team Game Stats

Notebook concepts:

- `Score`
- `get_game_stats`
- `yesterday_entries`
- archive result updates

Raw table targets:

- `games_raw`
- `team_game_logs`

API sources:

- `/schedule` for final scores/status
- `/game/{gamePk}/linescore` for compact totals
- `/game/{gamePk}/boxscore` for batting totals

## Pitcher Stats

Notebook concepts:

- `get_pitcher_era`
- `get_last_x_innings_era`
- `get_pitcher_stats`
- opposing pitcher season/recent ERA
- opposing pitcher appearances
- opposing pitcher hand

Raw table targets:

- `probable_pitchers`
- `pitcher_game_logs`

API sources:

- `/schedule` for probable pitcher ID/name
- `/people/{personId}` for pitch hand
- `/game/{gamePk}/boxscore` for pitcher appearance logs
- `/people/{personId}/stats?stats=gameLog&group=pitching` as fallback/history source

Future derived tables:

- pitcher season ERA entering game
- pitcher last N innings ERA entering game
- starter workload and rest
- bullpen usage/fatigue

## Odds

Notebook concepts:

- `fetch_mlbodds_for_date`
- moneyline odds
- spread odds
- total line and over/under odds
- devig expected win probability
- expected scores

Current raw table targets:

- None.

Notes:

- Odds storage is deferred until betting/prediction storage is in scope.
- Current baseball-only raw ingestion should not attempt to populate odds.

## Model Outputs And Bet Picks

Notebook concepts:

- `final_lgb`
- `final_win_lgb`
- predicted runs
- predicted win probability
- `bet_data`
- `best_bets`
- `all_predictions_fixed.csv`

Current raw table targets:

- None.

Notes:

- Excluded from current raw ingestion scope.
- Later tables should preserve prediction run timestamp and model version.
