# MLB Stats API Source Map

Base URL: `https://statsapi.mlb.com/api/v1`

This document maps raw ingestion needs to MLB Stats API endpoints. The existing notebook may show legacy approaches, but future ingestion should not inherit scraping or notebook-era shortcuts.

## Principles

- Use MLB Stats API for MLB baseball data whenever it provides the required field.
- Do not scrape websites as an ingestion strategy.
- If MLB Stats API does not provide required data, document the gap and choose a proper API/provider instead of scraping.
- Store MLB IDs as canonical identifiers.
- Treat pregame data as mutable.
- Treat postgame stat data as unavailable until game final unless the script explicitly handles live updates.
- Avoid derived calculations in raw ingestion scripts except small type conversions needed to fit existing raw tables.

## Probe Summary

Probed dates and games on 2026-07-14:

- `2026-07-10`: 15 games, sample `gamePk=824252`
- `2026-07-11`: 16 games, sample doubleheader records present
- `2026-07-12`: 15 games
- `2026-07-13` through `2026-07-15`: 0 games, likely All-Star break window
- `2025-07-18`: 15 games, sample `gamePk=777101`
- `2026-07-17`: 15 scheduled games in `abstractGameState=Preview`; only 4 of
  30 game/team slots had a hydrated probable pitcher at probe time.

Most useful endpoints from probing:

- `/schedule` for schedule, scores, status, teams, venue IDs, league records, and probable pitcher IDs/names.
- `/game/{gamePk}/boxscore` for team batting/pitching totals and pitcher appearance logs.
- `/game/{gamePk}/linescore` for compact final runs/hits/errors/LOB by team.
- `/people/{personId}` for pitcher handedness.

`/game/{gamePk}/feed/live` returned `404` for sampled completed games, so it should not be assumed as the primary postgame source.

## Endpoints Already Used In Notebook

### `/teams`

Observed use:

- Finds team IDs and team names.
- Called with `sportId=1` and `season`.

Expected table targets:

- `teams`
- partially `venues` when venue identity is included

Suggested params:

- `sportId=1`
- `season=YYYY`

Timing:

- Pregame-safe.
- Mostly stable.

### `/schedule`

Observed use:

- Finds games by date and team.
- Retrieves game IDs, home/away teams, game number, game status, and probable pitcher data when available.

Expected table targets:

- `games_raw`
- `probable_pitchers`
- partially `venues`

Suggested params:

- `sportId=1`
- `date=YYYY-MM-DD`
- `startDate=YYYY-MM-DD` and `endDate=YYYY-MM-DD` for bounded postgame ranges
- `gameType=R`
- optional `teamId`
- recommended `hydrate=probablePitcher,venue,team`
- optional `hydrate=probablePitcher,venue,team,linescore`

Timing:

- Pregame-safe for schedule fields.
- Mutable for status, start time, probables, postponements, and scores.

Observed fields useful for `games_raw`:

- `gamePk`
- `gameDate`
- `officialDate`
- `gameType`
- `season`
- `dayNight`
- `doubleHeader`
- `gameNumber`
- `seriesGameNumber`
- `gamesInSeries`
- `scheduledInnings`
- `status.abstractGameState`
- `status.detailedState`
- `status.statusCode`
- `teams.home.team.id`
- `teams.away.team.id`
- `teams.home.score`
- `teams.away.score`
- `venue.id`

Observed fields useful for `probable_pitchers`:

- `teams.home.probablePitcher.id`
- `teams.home.probablePitcher.fullName`
- `teams.away.probablePitcher.id`
- `teams.away.probablePitcher.fullName`

Observed limitations:

- `scripts/ingest_pregame.py` hydrates `probablePitcher,venue,team` once per
  bounded pregame date chunk. The same source-date payload first populates
  `games_raw` and then synchronizes `probable_pitchers`; person and missing-
  venue lookups use the same run-scoped MLB client.
- `scripts/ingest_postgame.py` hydrates `probablePitcher,venue,team` once per
  bounded postgame date chunk and splits the response back into MLB source-date
  entries before applying postponement and resumption rules.
- `probablePitcher` hydration includes pitcher ID/name/link, but not `pitchHand`.
- `pitchHand` should be fetched from `/people/{personId}` when needed.
- Probables can be missing, and scripts should treat that as a normal pregame condition.
- `scripts/ingest_probable_pitchers.py` uses only
  `status.abstractGameState=Preview`. A valid missing probable deletes an
  existing row for that game/team; live/final games and malformed responses do
  not clear assignments.
- Postgame recovery uses only final games (`statusCode=F` or
  `codedGameState=F`). It inserts retained schedule assignments only when the
  composite key is absent, labels them `postgame_recovery`, and never updates
  or deletes an existing assignment.
- A 2026-07-18 retention probe checked six completed games from May 15, June
  15, and July 10; all still exposed both probable-pitcher IDs. Four additional
  April games had a captured pregame probable different from the actual
  starter, and the completed-game schedule response still returned the earlier
  captured probable in every case. This supports recovery use while the
  provenance label prevents treating the recovery timestamp as a pregame
  observation timestamp.
- The pregame games stage intentionally writes every schedule occurrence for
  its requested date, not only `Preview` games. This keeps `games_raw` current
  if the command runs after a status change; the probable stage remains strict.
- July 17 included a Boston/Tampa Bay doubleheader. The two games had different
  `gamePk` values, and one response contained an away probable while the other
  contained no probable assignments, confirming that synchronization must key
  by `gamePk` plus team rather than matchup alone.
- Doubleheaders should use `gamePk` as the canonical game key. `doubleHeader` and `gameNumber` are worth storing or preserving for diagnostics.
- `status.detailedState` is the correct readable status field. On `2026-07-10`, MLB returned both a completed game and a postponed game with `abstractGameState=Final`; `detailedState` distinguished `Final` from `Postponed`.
- Only status code `F` is treated as score-final by the current games ingestion script. The postponed sample used status code `DI` and did not contain scores.
- Team-log ingestion must also use `status.codedGameState=F`. Rain-shortened
  completed game `gamePk=824295` used `statusCode=FR`,
  `codedGameState=F`, and `detailedState=Completed Early`; its final boxscore is
  postgame-safe. An exact `statusCode=F` filter would incorrectly omit it.
- A postponed `2026-07-10` game returned `officialDate=2026-07-11`, plus `rescheduleDate=2026-07-11T16:05:00Z` and `rescheduleGameDate=2026-07-11`. The July 11 schedule returned the same `gamePk=823357` as final with `rescheduledFromDate=2026-07-10`.
- The ingestion script skips a postponed record only when `rescheduleGameDate` differs from the requested schedule date. Same-day postponements are retained with `rescheduleDate` as the updated start time. If no new date is assigned, the postponed record remains on the requested date.
- Suspended game `gamePk=824912` appeared on both the `2026-06-16` and
  `2026-06-17` schedule responses. The original occurrence supplied
  `resumeDate`/`resumeGameDate`; the later occurrence supplied
  `resumedFrom`/`resumedFromDate` and different series-position values. The
  canonical row retains the original date, start time, and series metadata while
  accepting final status and scores from the resumed occurrence.
- `games_raw` stores `doubleHeader`, `gameNumber`, `seriesGameNumber`, and
  `gamesInSeries`. It intentionally does not store postponement reason,
  reschedule date, or `scheduledInnings`.

### `/venues/{venueId}`

Observed use:

- Enrich a venue identity that appears in schedule/team hydration but does not
  yet exist in `venues`.

Suggested params:

- `hydrate=location`

Expected table target:

- `venues`

Timing:

- Pregame-safe and mostly stable.

Observed fields:

- `id`
- `name`
- `location.city`
- `location.stateAbbrev`
- `location.country`
- `location.defaultCoordinates.latitude`
- `location.defaultCoordinates.longitude`
- `location.elevation`, suitable for `altitude_ft`
- `location.azimuthAngle`, suitable for `field_orientation_degrees`

Observed limitations:

- The probed response did not provide timezone, roof type, or field distances.
- The games ingestion script calls this endpoint only for missing venue IDs,
  inserts the available MLB fields, and leaves unavailable columns null.
- Existing venue rows should not be overwritten by this fallback lookup.

### `/game/{gamePk}/boxscore`

Observed use:

- Confirms the actual starting pitcher from each player's game-level
  `gamesStarted` value.
- Provides player/team boxscore data.

Expected table targets:

- `team_game_logs`
- `pitcher_game_logs`

Timing:

- Postgame source for final logs.
- Can be live/mutable during game.

Observed fields useful for `team_game_logs`:

- `teams.{home,away}.teamStats.batting.runs`
- `teams.{home,away}.teamStats.batting.hits`
- `teams.{home,away}.teamStats.batting.homeRuns`
- `teams.{home,away}.teamStats.batting.strikeOuts`
- `teams.{home,away}.teamStats.batting.baseOnBalls`
- `teams.{home,away}.teamStats.batting.hitByPitch`
- `teams.{home,away}.teamStats.batting.sacFlies`
- `teams.{home,away}.teamStats.batting.plateAppearances`
- `teams.{home,away}.teamStats.batting.atBats`
- `teams.{home,away}.teamStats.batting.totalBases`
- `teams.{home,away}.teamStats.batting.leftOnBase`
- `teams.{home,away}.teamStats.batting.groundIntoDoublePlay`
- `teams.{home,away}.teamStats.batting.doubles`
- `teams.{home,away}.teamStats.batting.triples`

Observed fields useful for `pitcher_game_logs`:

- `teams.{home,away}.pitchers`, ordered by appearance
- `teams.{home,away}.players.ID{pitcher_id}.person.id`
- `teams.{home,away}.players.ID{pitcher_id}.person.fullName`
- `teams.{home,away}.players.ID{pitcher_id}.stats.pitching.inningsPitched`
- `strikeOuts`
- `baseOnBalls`
- `homeRuns`
- `hits`
- `runs`
- `earnedRuns`
- `numberOfPitches`
- `pitchesThrown`
- `battersFaced`
- `flyOuts`
- `groundOuts`
- `outs`, which should populate `pitcher_game_logs.outs_recorded`

Observed limitations:

- The shared postgame workflow requests one boxscore per unique final
  `gamePk` per process run. Team and pitcher transforms consume the same cached
  payload; standalone recovery commands can still fetch independently.
- Store pitcher-list entries only when their game pitching stats report
  `gamesPitched>0`, and use `gamesStarted>0` to set `is_starter=true`.
- Innings pitched is MLB notation like `6.0`, `5.1`, `5.2`; use MLB's `outs` field as the canonical stored calculation value.
- Do not overwrite the pregame probable assignment with actual-starter logic;
  actual starters belong in `pitcher_game_logs`.
- Normal game `824252`, completed-early game `824295`, and suspended/resumed
  game `824912` were checked on 2026-07-14. Every listed pitcher contained the
  required raw fields for the current schema, and the first listed pitcher for
  each team had `gamesStarted=1`.
- Use `pitchesThrown` for `pitcher_game_logs.pitches_thrown`; sampled responses
  also exposed `numberOfPitches`, but the writer does not need a fallback.
- Game `823317` listed announced pitcher Kyle Freeland first even though his
  game stats reported `gamesPitched=0`, `gamesStarted=0`, zero batters faced,
  and no `pitchesThrown`. Jimmy Herget was the next listed pitcher and had
  `gamesStarted=1`. Non-appearances like Freeland's must not create pitcher-log
  rows or determine the starter.

### `/game/{gamePk}/linescore`

Observed use:

- Not used in the notebook, but probing shows it is available for compact game totals.

Expected table targets:

- `games_raw` for final score verification.

Timing:

- Mutable during live games.
- Final after game completion.

Observed fields:

- `teams.home.runs`
- `teams.home.hits`
- `teams.home.errors`
- `teams.home.leftOnBase`
- `teams.home.isWinner`
- `teams.away.runs`
- `teams.away.hits`
- `teams.away.errors`
- `teams.away.leftOnBase`
- `teams.away.isWinner`

### `/people/{personId}`

Observed use:

- Not currently used directly in the notebook for probable pitchers, but useful for pitcher metadata.

Expected table targets:

- `probable_pitchers.pitch_hand`
- future player/person dimension if added

Timing:

- Pregame-safe.
- Mostly stable.

Observed fields:

- `id`
- `fullName`
- `pitchHand.code`
- `pitchHand.description`
- `batSide.code`
- `primaryPosition`
- `mlbDebutDate`
- `active`

Observed example:

- Pitcher `643377` returned `pitchHand.code=R` and
  `pitchHand.description=Right` on 2026-07-14. The raw code populates
  `probable_pitchers.pitch_hand`.

### `/people/search`

Observed use:

- Maps pitcher names to MLB player IDs.

Expected table targets:

- Supporting lookup only for current schema.
- No player dimension table currently exists.

Timing:

- Pregame-safe.
- Useful fallback when a source provides names but not IDs.

### `/people/{player_id}/stats`

Observed use:

- Fetches pitching game logs with `stats=gameLog`, `group=pitching`, `season`, `gameType=R`.
- Notebook uses this to calculate season ERA and recent-innings ERA.

Expected table targets:

- `pitcher_game_logs` if boxscore/game feed is insufficient.

Timing:

- Historical/postgame source.
- Not a raw feature table; raw ingestion should store game-level logs, and derived ERA should be built later.

### `/standings`

Observed use:

- Retrieves team record entering a date.

Expected table targets:

- No current raw table exists for standings.

Timing:

- Pregame-safe when queried as of previous day.
- For future derived stats, standings can be recomputed from `games_raw` results or stored as a separate raw snapshot if needed.

## Legacy Non-MLB Sources Observed In Notebook

These are documented only so future work knows what the prototype depended on. They are not approved ingestion sources.

### MLB probable pitchers page

URL pattern:

- `https://www.mlb.com/probable-pitchers/{date}`

Notebook use:

- Scrapes probable pitchers.

Future approach:

- Use MLB Stats API schedule probable pitcher hydration first.
- Do not scrape this page.
- If schedule hydration is insufficient, look for another MLB Stats API endpoint or an approved provider API.

### ESPN scoreboard and odds APIs

Observed URLs:

- `https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard`
- `https://sports.core.api.espn.com/v2/sports/baseball/leagues/mlb/events/{event_id}/competitions/{competition_id}/odds`

Notebook use:

- Moneyline odds.
- Spread line and odds.
- Total line and over/under odds.

Current schema target:

- No current raw odds table exists.

Planning note:

- Odds are required for betting decisions, but the current stated focus is raw baseball data first.
- When odds storage is added, choose an approved odds provider/API and store source/timestamp explicitly.
- Do not treat notebook ESPN endpoints as the default future source without reviewing reliability and terms.

### StatMuse

Observed use:

- Scraped for pitcher ERA and team-vs-team game stats.

Preferred future approach:

- Do not use StatMuse scraping for ingestion.
- ERA, recent ERA, team form, and matchup stats should become derived stats from raw tables.

## Open Source Questions

- Which weather provider should populate `weather_raw`?
- Should odds be stored in Supabase during the raw-data phase, or deferred until prediction/betting tables are designed?
- Is a player dimension table needed before pitcher log ingestion grows?
