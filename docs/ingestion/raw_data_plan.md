# Raw Data Ingestion Plan

This plan covers only raw Supabase table population. It intentionally excludes derived stats, feature tables, model training, predictions, and bet recommendations.

## Current Source Of Truth

- Prototype/modeling behavior: `mlb_daily_clean copy 2.ipynb`
- Supabase project: `BagBrainOfficial`
- Supabase project ID: `soakgdpuvtxadjextekg`

The notebook should remain unchanged.

## Local Environment Setup

Use a project-local virtual environment for ingestion commands. Do not install
`supabase-py` globally or install it separately from the pinned dependency set.
The repository ignores `.venv/`.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-ingestion.txt
```

Run ingestion with the virtual-environment interpreter:

```bash
.venv/bin/python scripts/ingest_postgame.py --yesterday --dry-run
.venv/bin/python scripts/ingest_postgame.py --yesterday
```

The remaining `python scripts/...` examples in this document assume the virtual
environment has already been activated. The pinned requirements currently use
`supabase==2.31.0`; update the full pinned requirements file together rather
than upgrading only one Supabase package.

## First Implementation

Implemented on 2026-07-14:

- `scripts/ingest_games_raw.py` populates `games_raw` from MLB `/schedule`.
- It inserts team and venue identities only when their MLB IDs are not already present.
- Before inserting a missing venue, it fetches
  `/venues/{venueId}?hydrate=location` and stores the available MLB location,
  coordinates, elevation, and azimuth fields.
- It upserts games by `game_id` and is safe to rerun.
- It preserves MLB doubleheader and series position metadata in
  `doubleheader_code`, `game_number`, `series_game_number`, and
  `games_in_series`.
- It stores scheduled instants as UTC-aware `timestamptz` values while retaining
  MLB's local schedule date separately in `game_date`.
- It stores scores only for MLB status code `F`.
- It skips postponed games only when MLB explicitly moves them to a different
  `rescheduleGameDate`.
- It retains same-day postponements and uses MLB `rescheduleDate` as the updated
  scheduled time. Postponements without an assigned new date are also retained.
- When MLB repeats a suspended game on its resume date, the later occurrence
  updates status/scores without replacing the original `game_date`, scheduled
  time, or series metadata.
- It supports dry runs, a single date, and an inclusive date range.

Commands:

```bash
python scripts/ingest_games_raw.py --date YYYY-MM-DD
python scripts/ingest_games_raw.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD
python scripts/ingest_games_raw.py --date YYYY-MM-DD --dry-run
```

Install the pinned dependencies from `requirements-ingestion.txt` before a live run.

Season-to-date backfill completed on 2026-07-14:

- Covered `2026-03-25` through `2026-07-12`.
- Stored 1,444 unique games after cross-date postponement handling and canonical
  `game_id` deduplication.
- Added two missing MLB venues encountered in the extended schedule.
- Verified complete scores, schedule metadata, scheduled timestamps, and
  team/venue references for all stored games in the range.

## Team Game Logs Implementation

Implemented on 2026-07-14:

- `scripts/ingest_team_game_logs.py` populates `team_game_logs` from MLB
  `/game/{gamePk}/boxscore` after discovering postgame-safe games from
  `/schedule`.
- It writes only `team_game_logs`; pitcher logs are handled separately by
  `scripts/ingest_pitcher_game_logs.py`.
- It upserts by `(game_id, team_id)` and produces home and away rows with the
  other club stored as `opponent_id`.
- It stores MLB `hitByPitch` and `sacFlies` as `hit_by_pitch` and
  `sacrifice_flies`, completing the raw inputs required for exact downstream
  OBP and OPS calculations.
- It accepts MLB's final coded game state, including completed-early games whose
  specific `statusCode` is not exactly `F`.
- If one boxscore or transform fails, the script processes other games, logs the
  failed game, and exits nonzero so the run is visibly incomplete and retryable.
- It verifies `games_raw` and `teams` dependencies before writing. The database
  also enforces foreign keys for `game_id`, `team_id`, and `opponent_id`.
- It supports dry runs, one date, and inclusive date ranges. It does not modify
  `games_raw.pitcher_logs_processed`.
- It remains available as a standalone recovery command, but now imports shared
  environment, date, Supabase-client, and MLB request utilities. The routine
  postgame orchestrator injects its shared schedule and boxscore payloads into
  this writer.

Commands:

```bash
python scripts/ingest_team_game_logs.py --date YYYY-MM-DD
python scripts/ingest_team_game_logs.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD
python scripts/ingest_team_game_logs.py --date YYYY-MM-DD --dry-run
```

Season-to-date backfill completed on 2026-07-14:

- Covered `2026-03-25` through `2026-07-12` in bounded ranges with an audit
  after each range.
- Stored 2,888 distinct rows for 1,444 canonical games, exactly two rows per
  game.
- Verified zero duplicate keys, missing mapped stats, invalid team/opponent
  pairs, negative values, or final-score mismatches.
- Verified an idempotent rerun on `2026-07-10`.
- Confirmed that suspended game `gamePk=824912`, which appears as final on both
  its original and resume-date schedule responses, safely converges on one pair
  of canonical rows.

OPS-input extension completed on 2026-07-18:

- Added `hit_by_pitch` and `sacrifice_flies` through migration
  `add_team_game_logs_ops_inputs` (`20260719000353`).
- Backfilled all 2,888 existing rows from `2026-03-25` through `2026-07-12`.
- Verified zero nulls, negative values, or duplicate composite keys after the
  backfill and matched sampled stored values to MLB boxscore fields.

## Pitcher Game Logs Implementation

Implemented on 2026-07-14:

- `scripts/ingest_pitcher_game_logs.py` populates `pitcher_game_logs` from MLB
  `/game/{gamePk}/boxscore` after discovering postgame-safe games from
  `/schedule`.
- It stores every actual pitcher appearance, using `gamesPitched>0` to exclude
  announced or listed pitchers who did not appear and `gamesStarted>0` to mark
  the actual starter.
- It maps MLB `outs` to `outs_recorded` and does not store or calculate with
  decimal innings notation.
- It verifies `games_raw` and `teams` dependencies, upserts one complete game
  at a time by `(game_id, pitcher_id)`, and continues other games after a
  game-level failure.
- After a complete game upsert, it sets
  `games_raw.pitcher_logs_processed=true`. The marker update uses bounded
  retries; an exhausted update leaves the idempotently written pitcher rows in
  place, reports the game incomplete, and causes a nonzero exit.
- It supports dry runs, one date, and inclusive date ranges. Explicit reruns
  refresh games even when their processing marker is already true.

Commands:

```bash
python scripts/ingest_pitcher_game_logs.py --date YYYY-MM-DD
python scripts/ingest_pitcher_game_logs.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD
python scripts/ingest_pitcher_game_logs.py --date YYYY-MM-DD --dry-run
```

Season-to-date backfill completed on 2026-07-14:

- Covered `2026-03-25` through `2026-07-12` in bounded ranges.
- Stored 12,234 distinct `(game_id, pitcher_id)` rows for all 1,444 canonical
  games and marked all 1,444 games processed.
- Verified zero duplicate keys, missing required stats, negative values,
  invalid game/team pairs, missing team coverage, or starter-count anomalies.
- Verified an idempotent rerun on `2026-07-10`.
- Confirmed that suspended game `gamePk=824912` converges on nine canonical
  pitcher rows even though MLB exposes it on both the original and resume dates.
- Added a regression for `gamePk=823317`, where MLB listed an announced pitcher
  with `gamesPitched=0` before the actual starter.

## Probable Pitchers Implementation

Implemented on 2026-07-14:

- `scripts/ingest_probable_pitchers.py` synchronizes `probable_pitchers` from
  MLB `/schedule` with `hydrate=probablePitcher,team` and enriches handedness
  from `/people/{personId}`.
- It processes only games whose `status.abstractGameState` is `Preview`. Live
  and completed games are not used to update or clear pregame assignments.
- It upserts announced pitchers by `(game_id, team_id)`. When a valid pregame
  response omits a team's probable pitcher, it deletes that existing assignment
  so the table reflects MLB's current response exactly.
- A malformed game or failed schedule request never triggers deletion. A failed
  person lookup writes the current assignment with a null `pitch_hand`, reports
  the enrichment failure, and causes a nonzero exit so a rerun can repair it.
- The writer validates referenced team IDs but intentionally does not require a
  `games_raw` row. Live inspection confirmed that `probable_pitchers` has no
  foreign keys, so upcoming games remain separate from the previous-day
  `games_raw` cadence.
- The table represents the latest pregame assignment observed for each
  game/team, not an assignment-snapshot history and not the actual starter.

Commands:

```bash
python scripts/ingest_probable_pitchers.py --date YYYY-MM-DD
python scripts/ingest_probable_pitchers.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD
python scripts/ingest_probable_pitchers.py --date YYYY-MM-DD --dry-run
```

Routine use should request today's official MLB schedule date and may refresh
near first pitch because assignments are mutable. Short future ranges are
allowed when explicitly requested; missing assignments are normal. Historical
completed-game backfills are intentionally skipped by the pregame-state filter.

Initial live validation completed on 2026-07-14:

- Dry-ran `2026-07-17`: 15 pregame games, 4 announced assignments, 26 normal
  missing slots, and zero source or enrichment failures.
- Ran the date live twice. Both runs converged on the same four composite keys;
  the second run created no duplicates.
- Verified the stored pitcher IDs, names, and `R` hand codes against MLB. The
  table contained 786 rows and 786 distinct `(game_id, team_id)` keys after the
  validation write.

## Shared Pregame Orchestration

Implemented on 2026-07-18:

- `scripts/ingest_pregame.py` is the routine same-day entry point for
  `games_raw`, `probable_pitchers`, and `pregame_team_features`.
- `--today` resolves the current calendar date in `America/Los_Angeles` by
  default. Explicit dates and short ranges remain available for testing and
  targeted recovery.
- One `/schedule` response hydrated with `probablePitcher,venue,team` is shared
  across the two MLB-backed stages for each bounded date chunk. The feature
  stage reads the stored raw tables from Supabase and makes no MLB request.
- The games stage writes every schedule occurrence for the target date. The
  probable-pitcher stage remains restricted to MLB `Preview` games.
- Missing venues and pitcher hands use the same run-scoped MLB client, and the
  command reports physical request and cache-hit totals.
- The feature stage runs after games and probable pitchers. A failure in either
  selected dependency skips features for that date. Feature transform/write
  failures make the final command exit nonzero while preserving safe writes
  for retry.
- Live feature mode skips games that have reached scheduled first pitch.
- `--steps games`, `--steps probable-pitchers`, and `--steps team-features`
  remain available for targeted recovery. The table-specific scripts also
  remain supported.

Commands:

```bash
python scripts/ingest_pregame.py --today
python scripts/ingest_pregame.py --today --dry-run
python scripts/ingest_pregame.py --date YYYY-MM-DD
python scripts/ingest_pregame.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD
python scripts/ingest_pregame.py --date YYYY-MM-DD --steps team-features
```

`scripts/ingest_pregame_team_features.py` is the standalone historical and
targeted feature command. `--mode historical` uses the stored scheduled start
as the simulated cutoff and accepts `pregame`, `legacy_unknown`, and
`postgame_recovery` probable assignments under the approved reconstruction
policy.

```bash
python scripts/ingest_pregame_team_features.py --date YYYY-MM-DD --mode historical
python scripts/ingest_pregame_team_features.py --season 2026 --mode historical
```

The 2026 season backfill completed on 2026-07-18 with 2,948 feature rows for
1,474 games and no audit discrepancies.

## Shared Postgame Orchestration

Implemented on 2026-07-15:

- `scripts/ingest_postgame.py` is the routine postgame entry point for
  `games_raw`, insert-only `probable_pitchers` recovery, `team_game_logs`, and
  `pitcher_game_logs`.
- `--yesterday` resolves the prior calendar date in
  `America/Los_Angeles` by default. This timezone selects the requested date;
  it does not change MLB `officialDate` or UTC-normalized `gameDate` values.
- One `/schedule` response hydrated with `probablePitcher,venue,team` is shared
  across all four stages. Date ranges use bounded schedule requests and retain
  MLB's individual source-date entries for postponement and resumption handling.
- Each unique final `gamePk` boxscore is requested once per command run and the
  same response is passed to both team- and pitcher-log transforms.
- Successful responses and exhausted request failures are cached only in
  process memory. The cache is discarded when the command exits, so a later
  rerun refreshes MLB corrections.
- Missing venue lookups use the same run-scoped client and remain conditional
  on the venue not already existing in Supabase.
- Missing probable assignments on postgame-safe finals use the same schedule
  payload and person cache. Recovery uses conflict-ignore inserts, never
  updates or deletes an existing row, and labels inserted rows
  `postgame_recovery`.
- A failed `games_raw` stage prevents dependent log stages for that date. A
  game-level log failure remains isolated, is reported, and produces a nonzero
  final exit.
- Existing table-specific scripts remain supported for targeted recovery.
- The recovery addition keeps all existing table keys and adds only the
  constrained `probable_pitchers.capture_type` provenance column.

Commands:

```bash
python scripts/ingest_postgame.py --yesterday
python scripts/ingest_postgame.py --date YYYY-MM-DD
python scripts/ingest_postgame.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD
python scripts/ingest_postgame.py --yesterday --dry-run
python scripts/ingest_postgame.py --date YYYY-MM-DD --steps team-logs,pitcher-logs
python scripts/ingest_postgame.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD --steps probable-recovery
```

The default schedule chunk is seven days. `--schedule-chunk-days` may be used
for a deliberately bounded recovery or backfill request.

Live validation completed on 2026-07-15:

- All 88 unit and orchestration tests passed.
- `--yesterday --dry-run` and the live `--yesterday` command both resolved
  `2026-07-14` in `America/Los_Angeles`, made one schedule request, handled the
  All-Star-break no-game date successfully, and performed no table writes.
- A `2026-07-12` dry run processed 15 final games with 16 physical MLB
  requests: one schedule plus 15 unique boxscores. The pitcher stage reused all
  15 boxscores from memory.
- Two consecutive live `2026-07-12` runs produced the same successful summary:
  15 `games_raw` upserts, 30 `team_game_logs` upserts, 143
  `pitcher_game_logs` upserts, and 15 games marked processed, with zero date or
  game failures. Existing primary/composite keys made the rerun convergent
  without duplicate rows.

Postgame probable recovery validation completed on 2026-07-18:

- A May 15 recovery-only dry run found all 30 retained assignments with no
  malformed games or missing source values.
- The bounded April 25 through July 18 run found 2,158 announced assignments,
  preserved six existing rows, inserted 2,152 missing rows, observed two normal
  missing MLB assignments, and had zero game or person failures.
- The immediate idempotency rerun found all 2,158 assignments already present,
  inserted zero rows, and made only the 13 bounded schedule requests.
- The final audit contained 2,942 rows and 2,942 distinct composite keys: 782
  `legacy_unknown`, eight `pregame`, and 2,152 `postgame_recovery`, with no null
  pitcher IDs, names, or hands. Four recovered assignments differed from the
  actual starter, further confirming that recovery does not simply copy
  boxscore starters.

## Morning Workflow

Run the same-day pregame job first:

1. Run `python scripts/ingest_pregame.py --today`.
2. Request today's MLB schedule once with probable pitchers, venues, and teams.
3. Insert missing team or venue identities and upsert every game occurrence
   into `games_raw`.
4. Synchronize probable-pitcher assignments for games still in `Preview`.

The separate postgame job processes only the previous calendar day:

1. Run `python scripts/ingest_postgame.py --yesterday`.
2. Request yesterday's MLB schedule once.
3. Insert any missing team or venue identities referenced by those games.
4. Upsert yesterday's games into `games_raw`, including final status and scores
   when MLB reports status code `F`.
5. Insert missing MLB-retained probable assignments for postgame-safe finals,
   labeling them `postgame_recovery` without changing existing rows.
6. Request one boxscore for each unique postgame-safe final.
7. Populate `team_game_logs` and `pitcher_game_logs` from shared boxscores.
8. Mark pitcher logs processed after each complete pitcher row set writes.

The routine pregame command loads today. Explicit short pregame ranges are for
testing and recovery; broad postgame ranges remain reserved for historical
backfills, recovery, and explicit audits.

After the previous-day `games_raw` update succeeds, the orchestrator runs the
team-log stage for that same previous calendar day. A nonzero exit must be
treated as an incomplete run and retried after the reported failures are
investigated. `scripts/ingest_team_game_logs.py` remains available for targeted
recovery.

The orchestrated pitcher-log stage then uses those same cached boxscores. It
refreshes all final games even when `pitcher_logs_processed` is already true,
upserts every pitcher appearance, and marks each game processed only after its
complete pitcher row set is written. `scripts/ingest_pitcher_game_logs.py`
remains available for recovery. A final marker failure leaves idempotently
written rows in place and causes a nonzero exit.

The pregame workflow is separate from this previous-day sequence and may be
refreshed before first pitch as operational scheduling permits. Its first stage
creates the `games_raw` parent rows required by the feature writer.

## Suggested Ingestion Order

### Phase 1: Previous-Day Game Results Foundation

Tables:

- `teams`
- `venues`
- `games_raw`

Purpose:

- Establish canonical game, team, and venue IDs.
- Populate the previous day's schedule and results.
- Make reruns idempotent.

Success criteria:

- Running the same date twice updates rows without duplicates.
- Every game has home and away team IDs.
- Final games have scores when MLB supplies them with final status code `F`.
- Non-final, suspended, postponed, and missing-score records are handled without
  inventing postgame values.

### Phase 2: Previous-Day Team And Pitcher Logs

Tables:

- `games_raw`
- `team_game_logs`
- `pitcher_game_logs`

Purpose:

- Update final scores.
- Store final team batting/result logs.
- Store final pitcher appearance logs.

Success criteria:

- Final games have status and scores.
- Each final game has two `team_game_logs` rows.
- Pitcher logs include all pitchers, with starters marked by `is_starter`.
- Rerunning a date updates rows without duplicates.

Historical implementation sequencing decision from 2026-07-14, completed and
superseded by the shared orchestration refactor on 2026-07-15:

1. Implement `team_game_logs` as a standalone writer first.
2. Continue processing other games when one final boxscore fails, but report the
   failed game and exit nonzero so the incomplete run remains visible and safe
   to retry.
3. Defer shared-code extraction until the table-specific writers are stable.
4. Validate a small live date and an idempotent rerun before beginning a bounded
   season-to-date backfill. Stop on unexplained discrepancies.
5. Preserve each table-specific command for recovery and keep pitcher writes
   isolated by game so a boxscore, dependency, write, or marker failure does
   not block other games.

The deferred extraction is now complete. `scripts/ingest_postgame.py` is the
routine entry point, while all three table-specific postgame commands remain
supported for targeted recovery.

### Phase 3: Pregame Probable Pitchers

Table:

- `probable_pitchers`

Purpose:

- Store MLB's current pregame pitcher assignment for each game/team.
- Keep today's and future assignments independent from `games_raw`.

Success criteria:

- Announced pitchers are enriched with MLB handedness when available.
- Valid pregame omissions remove stale assignments.
- Source or transform failures never cause destructive clearing.
- Live/final games do not mutate the pregame table.
- Repeated runs converge without duplicate keys.

### Phase 4: Weather

Tables:

- `weather_raw`

Purpose:

- Add pregame forecast or observed weather once a source is chosen.

Open decision:

- Pick weather source.
- Decide whether current schema should distinguish forecast snapshots from observed weather.

## Idempotency Rules

Use existing primary keys:

- `teams`: `team_id`
- `venues`: `venue_id`
- `games_raw`: `game_id`
- `probable_pitchers`: `(game_id, team_id)`
- `team_game_logs`: `(game_id, team_id)`
- `pitcher_game_logs`: `(game_id, pitcher_id)`
- `weather_raw`: `game_id`

Scripts should use upsert behavior and should be safe to rerun for the same date.

Known cross-date postponed records are omitted from their original schedule date.
They enter `games_raw` when the rescheduled date is ingested, using the same MLB
`gamePk`/`game_id`.

Suspended games retain their original game date and scheduled time. MLB can
repeat the same `gamePk` on the resume date with `resumedFrom` fields and
different series-position metadata; that later occurrence must not replace the
original schedule identity.

## Data Timing Labels

Even though raw tables do not currently include explicit timing labels, ingestion docs and code should treat fields according to timing:

- Pregame-safe: team IDs, scheduled games, venue IDs, scheduled time, known probables.
- Mutable pregame: probable pitchers, scheduled time, status, postponements.
- Live mutable: scores, boxscore stats before final.
- Postgame-only: final team game logs, final pitcher game logs.

This distinction will matter later when building derived stats and feature tables.

## Raw API Response Table Decision

A generic `raw_api_responses` table is optional and not required for the first implementation.

What it would be used for:

- Debugging transform bugs by preserving the exact source payload.
- Replaying ingestion transforms without calling the external API again.
- Auditing when a value came from a specific endpoint response.
- Recovering if we later realize an unmodeled field matters.
- Comparing response shape changes over time.

Why it may not be worth it right now:

- It adds storage and schema surface area.
- Existing tables already capture the core raw baseball facts needed first.
- If scripts are simple and date windows are small, refetching from MLB may be acceptable.
- It can distract from the immediate goal: populate current raw tables reliably.

Current recommendation:

- Do not add `raw_api_responses` in the first pass.
- Reconsider it when ingestion expands to many seasons, unreliable sources, paid APIs, or complex transforms.

## Environment Configuration

A root-level `.env` is present and ignored by Git. The ingestion script accepts the
current `SUPABASE_SECRET_KEY` name and the legacy `SUPABASE_SERVICE_ROLE_KEY` name.

`backend/supabaseInfo.txt` contains a direct Postgres `DATABASE_URL`, but it should be treated as a secret and not copied into docs or committed elsewhere. At the time of inspection, that connection string appeared to reference the older `BagBrain` project ref rather than the active `BagBrainOfficial` project ID used for this plan.

Expected variables:

```text
SUPABASE_URL=
SUPABASE_SECRET_KEY=
```

Recommendation:

- The current script uses the Supabase Python API client.
- The script refuses to write unless `SUPABASE_URL` points to `BagBrainOfficial`.
- Use a secret/service-role key only in local/server ingestion scripts.
- Do not expose service-role keys to frontend/client code.
- Keep `.env` ignored and use `.env.example` for variable names only.

## Open Decisions

- Whether to add a player dimension table before pitcher ingestion expands.
- Whether odds should get raw storage now or wait until prediction/betting tables are designed.
- Which weather source should populate `weather_raw`.
- Whether `venues` should use MLB-only data first or include curated park metadata.
- Whether a separate recovery job should use a configurable lookback for
  suspended games, late finals, or MLB corrections. The normal morning
  `games_raw` run remains previous-day only.

## Missing Venue Enrichment

When a schedule references a venue ID not present in `venues`, fetch
`/venues/{venueId}?hydrate=location` and insert the available MLB identity,
location, coordinates, elevation, and azimuth fields. Do not overwrite existing
venue rows, and leave timezone, roof type, and field distances null when MLB does
not provide them. This fallback is implemented in `scripts/ingest_games_raw.py`.
