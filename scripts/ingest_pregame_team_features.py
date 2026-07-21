#!/usr/bin/env python3
"""Build leakage-aware MLB pregame team features from Supabase raw tables."""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:
    from scripts.ingestion.common import (
        DEFAULT_ENV_FILE,
        DEFAULT_TIMEZONE,
        IngestionError,
        build_date_range,
        create_supabase_client,
        parse_iso_date,
        resolve_today,
    )
except ModuleNotFoundError:  # Support direct `python scripts/...` execution.
    from ingestion.common import (  # type: ignore[no-redef]
        DEFAULT_ENV_FILE,
        DEFAULT_TIMEZONE,
        IngestionError,
        build_date_range,
        create_supabase_client,
        parse_iso_date,
        resolve_today,
    )


LOGGER = logging.getLogger("ingest_pregame_team_features")

FEATURE_SCHEMA_VERSION = 1
PAGE_SIZE = 1_000
MODE_LIVE = "live"
MODE_HISTORICAL = "historical"
MODES = (MODE_LIVE, MODE_HISTORICAL)
FINAL_STATUSES = {"final", "completed early", "game over"}

GAME_COLUMNS = (
    "game_id,game_date,home_team_id,away_team_id,home_score,away_score,status,"
    "scheduled_time_utc,game_type,season"
)
TEAM_LOG_COLUMNS = (
    "game_id,team_id,opponent_id,runs_scored,hits,walks,hit_by_pitch,"
    "sacrifice_flies,at_bats,total_bases"
)
PITCHER_LOG_COLUMNS = "game_id,pitcher_id,outs_recorded,earned_runs_allowed"
PROBABLE_COLUMNS = (
    "game_id,team_id,pitcher_id,pitch_hand,capture_type,updated_at"
)


@dataclass
class FeatureBuildResult:
    rows_by_game: Dict[int, List[Dict[str, Any]]]
    games_found: int
    games_skipped_started: int
    games_failed: int


def _required_int(row: Mapping[str, Any], key: str, context: str) -> int:
    value = row.get(key)
    if value is None or isinstance(value, bool):
        raise IngestionError(f"missing required value {context}.{key}")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise IngestionError(f"invalid integer {context}.{key}={value!r}") from exc


def _required_nonnegative_int(
    row: Mapping[str, Any], key: str, context: str
) -> int:
    value = _required_int(row, key, context)
    if value < 0:
        raise IngestionError(f"negative value {context}.{key}={value}")
    return value


def _required_date(row: Mapping[str, Any], key: str, context: str) -> date:
    value = row.get(key)
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise IngestionError(f"invalid date {context}.{key}={value!r}") from exc


def _required_datetime(
    row: Mapping[str, Any], key: str, context: str
) -> datetime:
    value = row.get(key)
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise IngestionError(
                f"invalid timestamp {context}.{key}={value!r}"
            ) from exc
    else:
        raise IngestionError(f"missing required timestamp {context}.{key}")
    if parsed.tzinfo is None:
        raise IngestionError(f"timestamp lacks timezone {context}.{key}={value!r}")
    return parsed.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise IngestionError("feature timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def paginated_select(
    client: Any,
    table: str,
    columns: str,
    *,
    filters: Sequence[Tuple[str, str, Any]] = (),
    order_by: Sequence[str] = (),
    page_size: int = PAGE_SIZE,
) -> List[Dict[str, Any]]:
    """Read every matching row despite the Data API response-row limit."""
    if page_size <= 0:
        raise IngestionError("page size must be positive")
    rows: List[Dict[str, Any]] = []
    start = 0
    while True:
        query = client.table(table).select(columns)
        for operator, column, value in filters:
            method = getattr(query, operator, None)
            if method is None:
                raise IngestionError(f"unsupported Supabase filter {operator!r}")
            query = method(column, value)
        for column in order_by:
            query = query.order(column)
        response = query.range(start, start + page_size - 1).execute()
        page = response.data or []
        if not isinstance(page, list):
            raise IngestionError(f"unexpected Supabase response for {table}")
        rows.extend(dict(row) for row in page)
        if len(page) < page_size:
            break
        start += page_size
    return rows


def load_feature_source_rows(
    client: Any, season: int, game_type: str
) -> Tuple[
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
]:
    games = paginated_select(
        client,
        "games_raw",
        GAME_COLUMNS,
        filters=(("eq", "season", season), ("eq", "game_type", game_type)),
        order_by=("game_id",),
    )
    game_ids = {int(row["game_id"]) for row in games if row.get("game_id") is not None}
    team_logs = [
        row
        for row in paginated_select(
            client,
            "team_game_logs",
            TEAM_LOG_COLUMNS,
            order_by=("game_id", "team_id"),
        )
        if row.get("game_id") is not None and int(row["game_id"]) in game_ids
    ]
    pitcher_logs = [
        row
        for row in paginated_select(
            client,
            "pitcher_game_logs",
            PITCHER_LOG_COLUMNS,
            order_by=("game_id", "pitcher_id"),
        )
        if row.get("game_id") is not None and int(row["game_id"]) in game_ids
    ]
    probables = [
        row
        for row in paginated_select(
            client,
            "probable_pitchers",
            PROBABLE_COLUMNS,
            order_by=("game_id", "team_id"),
        )
        if row.get("game_id") is not None and int(row["game_id"]) in game_ids
    ]
    return games, team_logs, pitcher_logs, probables


def _is_final_game(game: Mapping[str, Any]) -> bool:
    status = str(game.get("status") or "").strip().casefold()
    return status in FINAL_STATUSES or (
        game.get("home_score") is not None and game.get("away_score") is not None
    )


def _rolling_values(
    history: Sequence[Mapping[str, Any]], window_size: int
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    window = list(history[-window_size:])
    if not window:
        return None, None, None
    runs = sum(int(row["runs_scored"]) for row in window) / len(window)
    hits = sum(int(row["hits"]) for row in window) / len(window)
    total_hits = sum(int(row["hits"]) for row in window)
    walks = sum(int(row["walks"]) for row in window)
    hit_by_pitch = sum(int(row["hit_by_pitch"]) for row in window)
    sacrifice_flies = sum(int(row["sacrifice_flies"]) for row in window)
    at_bats = sum(int(row["at_bats"]) for row in window)
    total_bases = sum(int(row["total_bases"]) for row in window)
    obp_denominator = at_bats + walks + hit_by_pitch + sacrifice_flies
    if at_bats == 0 or obp_denominator == 0:
        ops = None
    else:
        ops = (
            (total_hits + walks + hit_by_pitch) / obp_denominator
            + total_bases / at_bats
        )
    return runs, hits, ops


def _record(history: Sequence[Mapping[str, Any]]) -> Tuple[int, int]:
    wins = 0
    losses = 0
    for row in history:
        runs = int(row["runs_scored"])
        opponent_runs = int(row["opponent_runs"])
        if runs > opponent_runs:
            wins += 1
        elif runs < opponent_runs:
            losses += 1
        else:
            raise IngestionError(
                f"tied regular-season result game_id={row['game_id']} "
                f"team_id={row['team_id']}"
            )
    return wins, losses


def _build_context(
    games: Sequence[Mapping[str, Any]],
    team_logs: Sequence[Mapping[str, Any]],
    pitcher_logs: Sequence[Mapping[str, Any]],
    probables: Sequence[Mapping[str, Any]],
) -> Tuple[
    Dict[int, Dict[str, Any]],
    Dict[int, List[Dict[str, Any]]],
    Dict[int, List[Dict[str, Any]]],
    Dict[Tuple[int, int], Dict[str, Any]],
    Dict[int, List[Tuple[date, int]]],
]:
    games_by_id: Dict[int, Dict[str, Any]] = {}
    for raw_game in games:
        game_id = _required_int(raw_game, "game_id", "games_raw")
        context = f"games_raw[{game_id}]"
        game = dict(raw_game)
        game["game_id"] = game_id
        game["game_date"] = _required_date(game, "game_date", context)
        game["home_team_id"] = _required_int(game, "home_team_id", context)
        game["away_team_id"] = _required_int(game, "away_team_id", context)
        game["season"] = _required_int(game, "season", context)
        if game["home_team_id"] == game["away_team_id"]:
            raise IngestionError(f"same home and away team for game_id={game_id}")
        games_by_id[game_id] = game

    logs_by_game: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for raw_log in team_logs:
        game_id = _required_int(raw_log, "game_id", "team_game_logs")
        if game_id not in games_by_id:
            continue
        context = f"team_game_logs[{game_id}]"
        log = dict(raw_log)
        for key in (
            "team_id",
            "opponent_id",
            "runs_scored",
            "hits",
            "walks",
            "hit_by_pitch",
            "sacrifice_flies",
            "at_bats",
            "total_bases",
        ):
            log[key] = _required_nonnegative_int(log, key, context)
        logs_by_game[game_id].append(log)

    team_history: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    incomplete_by_team: Dict[int, List[Tuple[date, int]]] = defaultdict(list)
    for game_id, game in games_by_id.items():
        if not _is_final_game(game):
            continue
        home_id = int(game["home_team_id"])
        away_id = int(game["away_team_id"])
        game_logs = logs_by_game.get(game_id, [])
        by_team = {int(log["team_id"]): log for log in game_logs}
        if len(game_logs) != 2 or set(by_team) != {home_id, away_id}:
            incomplete_by_team[home_id].append((game["game_date"], game_id))
            incomplete_by_team[away_id].append((game["game_date"], game_id))
            continue
        for team_id, opponent_id in ((home_id, away_id), (away_id, home_id)):
            log = by_team[team_id]
            opponent_log = by_team[opponent_id]
            if int(log["opponent_id"]) != opponent_id:
                raise IngestionError(
                    f"opponent mismatch game_id={game_id} team_id={team_id}"
                )
            entry = dict(log)
            entry["game_date"] = game["game_date"]
            entry["opponent_runs"] = int(opponent_log["runs_scored"])
            scheduled = game.get("scheduled_time_utc")
            entry["sort_time"] = (
                _required_datetime(game, "scheduled_time_utc", f"games_raw[{game_id}]")
                if scheduled is not None
                else datetime.min.replace(tzinfo=timezone.utc)
            )
            team_history[team_id].append(entry)

    for history in team_history.values():
        history.sort(
            key=lambda row: (row["game_date"], row["sort_time"], row["game_id"])
        )

    pitcher_history: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for raw_log in pitcher_logs:
        game_id = _required_int(raw_log, "game_id", "pitcher_game_logs")
        game = games_by_id.get(game_id)
        if game is None:
            continue
        context = f"pitcher_game_logs[{game_id}]"
        pitcher_id = _required_int(raw_log, "pitcher_id", context)
        entry = {
            "game_id": game_id,
            "game_date": game["game_date"],
            "pitcher_id": pitcher_id,
            "outs_recorded": _required_nonnegative_int(
                raw_log, "outs_recorded", context
            ),
            "earned_runs_allowed": _required_nonnegative_int(
                raw_log, "earned_runs_allowed", context
            ),
        }
        pitcher_history[pitcher_id].append(entry)
    for history in pitcher_history.values():
        history.sort(key=lambda row: (row["game_date"], row["game_id"]))

    probable_by_key: Dict[Tuple[int, int], Dict[str, Any]] = {}
    for raw_probable in probables:
        game_id = _required_int(raw_probable, "game_id", "probable_pitchers")
        team_id = _required_int(raw_probable, "team_id", "probable_pitchers")
        if game_id not in games_by_id:
            continue
        probable = dict(raw_probable)
        probable["pitcher_id"] = _required_int(
            probable, "pitcher_id", f"probable_pitchers[{game_id},{team_id}]"
        )
        probable_by_key[(game_id, team_id)] = probable

    return (
        games_by_id,
        team_history,
        pitcher_history,
        probable_by_key,
        incomplete_by_team,
    )


def _prior_team_history(
    team_id: int,
    target_date: date,
    team_history: Mapping[int, Sequence[Dict[str, Any]]],
    incomplete_by_team: Mapping[int, Sequence[Tuple[date, int]]],
) -> List[Dict[str, Any]]:
    missing = [
        game_id
        for game_date, game_id in incomplete_by_team.get(team_id, ())
        if game_date < target_date
    ]
    if missing:
        raise IngestionError(
            f"team_id={team_id} has final prior games missing complete "
            f"team logs: {missing}"
        )
    return [
        row
        for row in team_history.get(team_id, ())
        if row["game_date"] < target_date
    ]


def _pitcher_era(
    pitcher_id: int,
    target_date: date,
    pitcher_history: Mapping[int, Sequence[Mapping[str, Any]]],
) -> Optional[float]:
    appearances = [
        row
        for row in pitcher_history.get(pitcher_id, ())
        if row["game_date"] < target_date
    ]
    outs = sum(int(row["outs_recorded"]) for row in appearances)
    if outs == 0:
        return None
    earned_runs = sum(int(row["earned_runs_allowed"]) for row in appearances)
    return earned_runs * 27 / outs


def _team_feature_values(
    team_id: int,
    target_date: date,
    team_history: Mapping[int, Sequence[Dict[str, Any]]],
    incomplete_by_team: Mapping[int, Sequence[Tuple[date, int]]],
) -> Dict[str, Any]:
    history = _prior_team_history(
        team_id, target_date, team_history, incomplete_by_team
    )
    last_5 = _rolling_values(history, 5)
    last_10 = _rolling_values(history, 10)
    wins, losses = _record(history)
    return {
        "runs_avg_last_5": last_5[0],
        "hits_avg_last_5": last_5[1],
        "ops_last_5": last_5[2],
        "runs_avg_last_10": last_10[0],
        "hits_avg_last_10": last_10[1],
        "ops_last_10": last_10[2],
        "wins": wins,
        "losses": losses,
    }


def build_game_feature_rows(
    game: Mapping[str, Any],
    *,
    team_history: Mapping[int, Sequence[Dict[str, Any]]],
    pitcher_history: Mapping[int, Sequence[Mapping[str, Any]]],
    probable_by_key: Mapping[Tuple[int, int], Mapping[str, Any]],
    incomplete_by_team: Mapping[int, Sequence[Tuple[date, int]]],
    mode: str,
    computed_at: datetime,
) -> Optional[List[Dict[str, Any]]]:
    if mode not in MODES:
        raise IngestionError(f"unknown feature mode {mode!r}")
    if computed_at.tzinfo is None:
        raise IngestionError("computed_at must be timezone-aware")
    game_id = _required_int(game, "game_id", "games_raw")
    context = f"games_raw[{game_id}]"
    target_date = _required_date(game, "game_date", context)
    scheduled_start = _required_datetime(game, "scheduled_time_utc", context)
    normalized_computed_at = computed_at.astimezone(timezone.utc)
    if mode == MODE_LIVE and normalized_computed_at >= scheduled_start:
        return None
    cutoff = scheduled_start if mode == MODE_HISTORICAL else normalized_computed_at
    home_id = _required_int(game, "home_team_id", context)
    away_id = _required_int(game, "away_team_id", context)
    season = _required_int(game, "season", context)

    values_by_team = {
        team_id: _team_feature_values(
            team_id, target_date, team_history, incomplete_by_team
        )
        for team_id in (home_id, away_id)
    }
    rows: List[Dict[str, Any]] = []
    for team_id, opponent_id, is_home in (
        (home_id, away_id, True),
        (away_id, home_id, False),
    ):
        team_values = values_by_team[team_id]
        opponent_values = values_by_team[opponent_id]
        opposing_probable = probable_by_key.get((game_id, opponent_id))
        pitcher_id: Optional[int] = None
        pitcher_hand: Optional[str] = None
        pitcher_era: Optional[float] = None
        if opposing_probable is not None:
            pitcher_id = _required_int(
                opposing_probable,
                "pitcher_id",
                f"probable_pitchers[{game_id},{opponent_id}]",
            )
            raw_hand = opposing_probable.get("pitch_hand")
            pitcher_hand = str(raw_hand) if raw_hand is not None else None
            if pitcher_hand not in {None, "R", "L", "S"}:
                raise IngestionError(
                    f"invalid probable pitcher hand game_id={game_id} "
                    f"team_id={opponent_id} hand={pitcher_hand!r}"
                )
            pitcher_era = _pitcher_era(pitcher_id, target_date, pitcher_history)

        row = {
            "game_id": game_id,
            "team_id": team_id,
            "opponent_team_id": opponent_id,
            "season": season,
            "scheduled_start_time_at_cutoff": _iso_utc(scheduled_start),
            "is_home": is_home,
            "feature_cutoff_at": _iso_utc(cutoff),
            "computed_at": _iso_utc(normalized_computed_at),
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "runs_avg_last_5": team_values["runs_avg_last_5"],
            "hits_avg_last_5": team_values["hits_avg_last_5"],
            "ops_last_5": team_values["ops_last_5"],
            "runs_avg_last_10": team_values["runs_avg_last_10"],
            "hits_avg_last_10": team_values["hits_avg_last_10"],
            "ops_last_10": team_values["ops_last_10"],
            "opposing_probable_pitcher_id": pitcher_id,
            "opposing_pitcher_season_era": pitcher_era,
            "opposing_pitcher_hand": pitcher_hand,
            "team_wins_before_game": team_values["wins"],
            "team_losses_before_game": team_values["losses"],
            "opponent_wins_before_game": opponent_values["wins"],
            "opponent_losses_before_game": opponent_values["losses"],
        }
        rows.append(row)
    return rows


def build_feature_rows(
    games: Sequence[Mapping[str, Any]],
    team_logs: Sequence[Mapping[str, Any]],
    pitcher_logs: Sequence[Mapping[str, Any]],
    probables: Sequence[Mapping[str, Any]],
    *,
    season: int,
    game_type: str,
    target_dates: Optional[Sequence[date]],
    mode: str,
    computed_at: datetime,
) -> FeatureBuildResult:
    (
        games_by_id,
        team_history,
        pitcher_history,
        probable_by_key,
        incomplete_by_team,
    ) = _build_context(games, team_logs, pitcher_logs, probables)
    selected_dates = set(target_dates) if target_dates is not None else None
    targets = [
        game
        for game in games_by_id.values()
        if int(game["season"]) == season
        and str(game.get("game_type")) == game_type
        and (selected_dates is None or game["game_date"] in selected_dates)
    ]
    targets.sort(
        key=lambda game: (
            game["game_date"],
            str(game.get("scheduled_time_utc") or ""),
            game["game_id"],
        )
    )
    rows_by_game: Dict[int, List[Dict[str, Any]]] = {}
    skipped = 0
    failed = 0
    for game in targets:
        game_id = int(game["game_id"])
        try:
            rows = build_game_feature_rows(
                game,
                team_history=team_history,
                pitcher_history=pitcher_history,
                probable_by_key=probable_by_key,
                incomplete_by_team=incomplete_by_team,
                mode=mode,
                computed_at=computed_at,
            )
            if rows is None:
                skipped += 1
                LOGGER.info(
                    "game_id=%s action=skip reason=already_started mode=%s",
                    game_id,
                    mode,
                )
                continue
            rows_by_game[game_id] = rows
        except Exception as exc:
            failed += 1
            LOGGER.error(
                "game_id=%s action=feature-transform-fail error=%s", game_id, exc
            )
    return FeatureBuildResult(
        rows_by_game=rows_by_game,
        games_found=len(targets),
        games_skipped_started=skipped,
        games_failed=failed,
    )


def upsert_game_features(
    client: Any, rows: Sequence[Mapping[str, Any]]
) -> int:
    if len(rows) != 2:
        raise IngestionError("feature writes require exactly two team rows per game")
    game_ids = {int(row["game_id"]) for row in rows}
    if len(game_ids) != 1:
        raise IngestionError("feature write rows must belong to one game")
    client.table("pregame_team_features").upsert(
        [dict(row) for row in rows],
        on_conflict="game_id,team_id",
        default_to_null=True,
    ).execute()
    return len(rows)


def ingest_features(
    client: Any,
    *,
    season: int,
    game_type: str,
    target_dates: Optional[Sequence[date]],
    mode: str,
    dry_run: bool,
    computed_at: Optional[datetime] = None,
) -> Dict[str, int]:
    effective_computed_at = computed_at or _utc_now()
    games, team_logs, pitcher_logs, probables = load_feature_source_rows(
        client, season, game_type
    )
    build = build_feature_rows(
        games,
        team_logs,
        pitcher_logs,
        probables,
        season=season,
        game_type=game_type,
        target_dates=target_dates,
        mode=mode,
        computed_at=effective_computed_at,
    )
    rows_ready = sum(len(rows) for rows in build.rows_by_game.values())
    rows_upserted = 0
    write_failures = 0
    if not dry_run:
        for game_id, rows in build.rows_by_game.items():
            try:
                rows_upserted += upsert_game_features(client, rows)
            except Exception as exc:
                write_failures += 1
                LOGGER.error(
                    "game_id=%s table=pregame_team_features action=upsert-fail error=%s",
                    game_id,
                    exc,
                )
    return {
        "games_found": build.games_found,
        "games_skipped_started": build.games_skipped_started,
        "games_failed": build.games_failed + write_failures,
        "rows_ready": rows_ready,
        "rows_upserted": rows_upserted,
    }


def ingest_date(
    client: Any,
    target_date: date,
    game_type: str,
    dry_run: bool,
    *,
    mode: str = MODE_LIVE,
    computed_at: Optional[datetime] = None,
) -> Dict[str, int]:
    return ingest_features(
        client,
        season=target_date.year,
        game_type=game_type,
        target_dates=(target_date,),
        mode=mode,
        dry_run=dry_run,
        computed_at=computed_at,
    )


def resolve_target_dates(args: argparse.Namespace) -> Optional[List[date]]:
    if args.season is not None:
        if args.today or args.date is not None or args.start_date or args.end_date:
            raise IngestionError(
                "--season cannot be combined with --today, --date, or a date range"
            )
        return None
    if args.today:
        if args.date is not None or args.start_date or args.end_date:
            raise IngestionError("--today cannot be combined with explicit dates")
        return [resolve_today(args.timezone)]
    return build_date_range(args.date, args.start_date, args.end_date)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Populate pregame_team_features from Supabase raw tables."
    )
    parser.add_argument("--today", action="store_true")
    parser.add_argument("--date", type=parse_iso_date)
    parser.add_argument("--start-date", type=parse_iso_date)
    parser.add_argument("--end-date", type=parse_iso_date)
    parser.add_argument("--season", type=int)
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--game-type", default="R")
    parser.add_argument("--mode", choices=MODES, default=MODE_LIVE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument(
        "--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO"
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        target_dates = resolve_target_dates(args)
        season = args.season if args.season is not None else target_dates[0].year
        if season < 1876:
            raise IngestionError("--season must be a valid MLB season")
        if target_dates and any(target.year != season for target in target_dates):
            raise IngestionError("date ranges cannot cross seasons")
        if args.season is not None and args.mode != MODE_HISTORICAL:
            raise IngestionError("--season requires --mode historical")
        client = create_supabase_client(args.env_file)
        LOGGER.info(
            "start season=%s target=%s mode=%s game_type=%s dry_run=%s",
            season,
            "all" if target_dates is None else f"{target_dates[0]}..{target_dates[-1]}",
            args.mode,
            args.game_type,
            args.dry_run,
        )
        summary = ingest_features(
            client,
            season=season,
            game_type=args.game_type,
            target_dates=target_dates,
            mode=args.mode,
            dry_run=args.dry_run,
        )
    except (IngestionError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 1
    except Exception as exc:
        LOGGER.error("feature ingestion failed: %s", exc)
        LOGGER.debug("unexpected feature ingestion failure", exc_info=True)
        return 1

    LOGGER.info(
        "complete games_found=%s games_skipped_started=%s games_failed=%s "
        "rows_ready=%s rows_upserted=%s dry_run=%s",
        summary["games_found"],
        summary["games_skipped_started"],
        summary["games_failed"],
        summary["rows_ready"],
        summary["rows_upserted"],
        args.dry_run,
    )
    return 1 if summary["games_failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
