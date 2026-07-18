#!/usr/bin/env python3
"""Ingest final MLB pitcher appearances into Supabase pitcher_game_logs."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:
    from scripts.ingestion.common import (
        DEFAULT_ENV_FILE,
        IngestionError,
        build_date_range,
        create_supabase_client,
        normalize_supabase_url,
        parse_iso_date,
        validate_runtime_options,
    )
    from scripts.ingestion.mlb import request_json
except ModuleNotFoundError:  # Support direct `python scripts/...` execution.
    from ingestion.common import (  # type: ignore[no-redef]
        DEFAULT_ENV_FILE,
        IngestionError,
        build_date_range,
        create_supabase_client,
        normalize_supabase_url,
        parse_iso_date,
        validate_runtime_options,
    )
    from ingestion.mlb import request_json  # type: ignore[no-redef]


MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
MLB_BOXSCORE_URL = "https://statsapi.mlb.com/api/v1/game/{game_id}/boxscore"
FINAL_STATUS_CODE = "F"
FINAL_CODED_GAME_STATE = "F"

LOGGER = logging.getLogger("ingest_pitcher_game_logs")


def _request_json(
    url: str, params: Mapping[str, Any], timeout: float, retries: int
) -> Dict[str, Any]:
    return request_json(url, params, timeout, retries, LOGGER)


def fetch_schedule(
    target_date: date,
    game_type: str = "R",
    timeout: float = 30.0,
    retries: int = 2,
) -> Dict[str, Any]:
    return _request_json(
        MLB_SCHEDULE_URL,
        {"sportId": 1, "gameType": game_type, "date": target_date.isoformat()},
        timeout,
        retries,
    )


def fetch_boxscore(
    game_id: int, timeout: float = 30.0, retries: int = 2
) -> Dict[str, Any]:
    return _request_json(
        MLB_BOXSCORE_URL.format(game_id=game_id), {}, timeout, retries
    )


def flatten_schedule(payload: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    games: List[Mapping[str, Any]] = []
    for date_entry in payload.get("dates", []):
        entry_games = date_entry.get("games", []) if isinstance(date_entry, Mapping) else []
        games.extend(game for game in entry_games if isinstance(game, Mapping))
    return games


def _nested_required(mapping: Mapping[str, Any], path: Sequence[str], context: str) -> Any:
    current: Any = mapping
    traversed: List[str] = []
    for key in path:
        traversed.append(key)
        if not isinstance(current, Mapping) or current.get(key) is None:
            raise IngestionError(
                f"missing required MLB field {context}.{'.'.join(traversed)}"
            )
        current = current[key]
    return current


def _required_int_value(value: Any, context: str) -> int:
    if value is None or isinstance(value, bool):
        raise IngestionError(f"missing required MLB integer {context}")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise IngestionError(f"invalid MLB integer {context}={value!r}") from exc


def _required_int(mapping: Mapping[str, Any], key: str, context: str) -> int:
    return _required_int_value(mapping.get(key), f"{context}.{key}")


def final_games(games: Iterable[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    """Return final games once per canonical MLB gamePk."""
    by_id: Dict[int, Mapping[str, Any]] = {}
    for game in games:
        status = game.get("status")
        if not isinstance(status, Mapping) or not (
            status.get("statusCode") == FINAL_STATUS_CODE
            or status.get("codedGameState") == FINAL_CODED_GAME_STATE
        ):
            continue
        game_id = _required_int(game, "gamePk", "game")
        by_id[game_id] = game
    return list(by_id.values())


STAT_COLUMNS = {
    "outs_recorded": "outs",
    "strikeouts": "strikeOuts",
    "walks": "baseOnBalls",
    "home_runs_allowed": "homeRuns",
    "hits_allowed": "hits",
    "runs_allowed": "runs",
    "earned_runs_allowed": "earnedRuns",
    "pitches_thrown": "pitchesThrown",
    "batters_faced": "battersFaced",
    "fly_outs": "flyOuts",
    "ground_outs": "groundOuts",
}


def transform_pitcher_game_rows(
    schedule_game: Mapping[str, Any], boxscore: Mapping[str, Any]
) -> List[Dict[str, Any]]:
    game_id = _required_int(schedule_game, "gamePk", "game")
    context = f"game[{game_id}]"
    schedule_team_ids = {
        side: _required_int_value(
            _nested_required(schedule_game, ("teams", side, "team", "id"), context),
            f"{context}.teams.{side}.team.id",
        )
        for side in ("home", "away")
    }

    rows: List[Dict[str, Any]] = []
    for side in ("home", "away"):
        side_context = f"{context}.boxscore.teams.{side}"
        boxscore_team_id = _required_int_value(
            _nested_required(boxscore, ("teams", side, "team", "id"), context),
            f"{side_context}.team.id",
        )
        if boxscore_team_id != schedule_team_ids[side]:
            raise IngestionError(
                f"team mismatch for {context} side={side}: schedule="
                f"{schedule_team_ids[side]} boxscore={boxscore_team_id}"
            )

        pitcher_ids = _nested_required(boxscore, ("teams", side, "pitchers"), context)
        players = _nested_required(boxscore, ("teams", side, "players"), context)
        if not isinstance(pitcher_ids, list) or not pitcher_ids:
            raise IngestionError(f"missing pitcher list {side_context}.pitchers")
        if not isinstance(players, Mapping):
            raise IngestionError(f"invalid player map {side_context}.players")

        side_rows: List[Dict[str, Any]] = []
        for index, raw_pitcher_id in enumerate(pitcher_ids):
            pitcher_id = _required_int_value(
                raw_pitcher_id, f"{side_context}.pitchers[{index}]"
            )
            player_key = f"ID{pitcher_id}"
            player = players.get(player_key)
            if not isinstance(player, Mapping):
                raise IngestionError(
                    f"missing required MLB player {side_context}.players.{player_key}"
                )
            person_id = _required_int_value(
                _nested_required(
                    player,
                    ("person", "id"),
                    f"{side_context}.players.{player_key}",
                ),
                f"{side_context}.players.{player_key}.person.id",
            )
            if person_id != pitcher_id:
                raise IngestionError(
                    f"pitcher mismatch for {context} side={side}: list="
                    f"{pitcher_id} player={person_id}"
                )
            pitching = _nested_required(
                player, ("stats", "pitching"), f"{side_context}.players.{player_key}"
            )
            if not isinstance(pitching, Mapping):
                raise IngestionError(
                    f"invalid MLB pitching object {side_context}.players.{player_key}"
                )

            pitching_context = f"{side_context}.players.{player_key}.stats.pitching"
            games_pitched = _required_int(pitching, "gamesPitched", pitching_context)
            if games_pitched == 0:
                continue
            games_started = _required_int(pitching, "gamesStarted", pitching_context)

            row: Dict[str, Any] = {
                "game_id": game_id,
                "pitcher_id": pitcher_id,
                "team_id": boxscore_team_id,
                "is_starter": games_started > 0,
            }
            for column, source_field in STAT_COLUMNS.items():
                row[column] = _required_int(pitching, source_field, pitching_context)
            side_rows.append(row)
        if not side_rows:
            raise IngestionError(f"no pitcher appearances found for {side_context}")
        starter_count = sum(1 for row in side_rows if row["is_starter"])
        if starter_count != 1:
            raise IngestionError(
                f"expected one MLB starter for {side_context}; found {starter_count}"
            )
        rows.extend(side_rows)
    return rows


def validate_dependencies(client: Any, rows: Sequence[Mapping[str, Any]]) -> None:
    """Require the game and both teams referenced by one transformed game."""
    if not rows:
        raise IngestionError("cannot validate an empty pitcher row set")
    game_ids = {int(row["game_id"]) for row in rows}
    if len(game_ids) != 1:
        raise IngestionError("dependency validation requires exactly one game")
    game_id = next(iter(game_ids))
    team_ids = sorted({int(row["team_id"]) for row in rows})

    games_response = (
        client.table("games_raw")
        .select("game_id")
        .eq("game_id", game_id)
        .execute()
    )
    teams_response = (
        client.table("teams")
        .select("team_id")
        .in_("team_id", team_ids)
        .execute()
    )
    existing_games = {row["game_id"] for row in (games_response.data or [])}
    existing_teams = {row["team_id"] for row in (teams_response.data or [])}
    missing_teams = sorted(set(team_ids) - existing_teams)
    if game_id not in existing_games or missing_teams:
        details: List[str] = []
        if game_id not in existing_games:
            details.append(f"missing games_raw game_id={game_id}")
        if missing_teams:
            details.append(f"missing teams={missing_teams}")
        raise IngestionError("; ".join(details))


def upsert_pitcher_game_logs(
    client: Any, rows: Sequence[Mapping[str, Any]]
) -> int:
    if not rows:
        return 0
    client.table("pitcher_game_logs").upsert(
        [dict(row) for row in rows],
        on_conflict="game_id,pitcher_id",
        default_to_null=False,
    ).execute()
    return len(rows)


def mark_pitcher_logs_processed(client: Any, game_id: int, retries: int) -> None:
    """Mark one fully written game, retrying a failed bookkeeping update."""
    for attempt in range(retries + 1):
        try:
            response = (
                client.table("games_raw")
                .update({"pitcher_logs_processed": True})
                .eq("game_id", game_id)
                .execute()
            )
            updated_ids = {
                row.get("game_id")
                for row in (response.data or [])
                if isinstance(row, Mapping)
            }
            if game_id not in updated_ids:
                raise IngestionError(
                    f"games_raw marker update matched no row for game_id={game_id}"
                )
            return
        except Exception as exc:
            if attempt >= retries:
                raise IngestionError(
                    f"failed to mark pitcher logs processed for game_id={game_id} "
                    f"after {retries + 1} attempt(s): {exc}"
                ) from exc
            delay = 2**attempt
            LOGGER.warning(
                "game=%s table=games_raw action=retry-marker attempt=%s "
                "delay_seconds=%s error=%s",
                game_id,
                attempt + 1,
                delay,
                exc,
            )
            time.sleep(delay)


def ingest_date(
    client: Any,
    target_date: date,
    game_type: str,
    dry_run: bool,
    timeout: float,
    retries: int,
    schedule_payload: Optional[Mapping[str, Any]] = None,
    boxscore_fetcher: Optional[Any] = None,
) -> Dict[str, int]:
    payload = (
        fetch_schedule(target_date, game_type, timeout, retries)
        if schedule_payload is None
        else schedule_payload
    )
    schedule_games = flatten_schedule(payload)
    get_boxscore = fetch_boxscore if boxscore_fetcher is None else boxscore_fetcher
    eligible_games = final_games(schedule_games)
    summary = {
        "games_found": len(schedule_games),
        "final_games_found": len(eligible_games),
        "non_final_skipped": len(schedule_games) - len(eligible_games),
        "games_failed": 0,
        "rows_ready": 0,
        "rows_upserted": 0,
        "games_marked_processed": 0,
    }

    for game in eligible_games:
        game_id = _required_int(game, "gamePk", "game")
        try:
            boxscore = get_boxscore(game_id, timeout, retries)
            rows = transform_pitcher_game_rows(game, boxscore)
            summary["rows_ready"] += len(rows)
            if dry_run:
                continue
            validate_dependencies(client, rows)
            summary["rows_upserted"] += upsert_pitcher_game_logs(client, rows)
            mark_pitcher_logs_processed(client, game_id, retries)
            summary["games_marked_processed"] += 1
        except Exception as exc:
            summary["games_failed"] += 1
            LOGGER.error(
                "date=%s game=%s source=MLB-boxscore table=pitcher_game_logs "
                "action=skip error=%s",
                target_date,
                game_id,
                exc,
            )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Populate pitcher_game_logs from final MLB boxscores."
    )
    parser.add_argument("--date", type=parse_iso_date)
    parser.add_argument("--start-date", type=parse_iso_date)
    parser.add_argument("--end-date", type=parse_iso_date)
    parser.add_argument("--game-type", default="R")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=2)
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
        dates = build_date_range(args.date, args.start_date, args.end_date)
        validate_runtime_options(args.timeout, args.retries)
        client = None if args.dry_run else create_supabase_client(args.env_file)
    except (IngestionError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 1

    totals = {
        "games_found": 0,
        "final_games_found": 0,
        "non_final_skipped": 0,
        "games_failed": 0,
        "rows_ready": 0,
        "rows_upserted": 0,
        "games_marked_processed": 0,
        "dates_failed": 0,
    }
    for target_date in dates:
        try:
            summary = ingest_date(
                client, target_date, args.game_type, args.dry_run, args.timeout, args.retries
            )
        except Exception as exc:
            totals["dates_failed"] += 1
            LOGGER.error("date=%s action=fail error=%s", target_date, exc)
            LOGGER.debug("date ingestion failure", exc_info=True)
            continue
        LOGGER.info(
            "date=%s games_found=%s final_games_found=%s non_final_skipped=%s "
            "games_failed=%s rows_ready=%s rows_upserted=%s "
            "games_marked_processed=%s dry_run=%s",
            target_date,
            summary["games_found"],
            summary["final_games_found"],
            summary["non_final_skipped"],
            summary["games_failed"],
            summary["rows_ready"],
            summary["rows_upserted"],
            summary["games_marked_processed"],
            args.dry_run,
        )
        for key in summary:
            totals[key] += summary[key]

    LOGGER.info(
        "complete dates=%s games_found=%s final_games_found=%s games_failed=%s "
        "dates_failed=%s rows_ready=%s rows_upserted=%s "
        "games_marked_processed=%s dry_run=%s",
        len(dates),
        totals["games_found"],
        totals["final_games_found"],
        totals["games_failed"],
        totals["dates_failed"],
        totals["rows_ready"],
        totals["rows_upserted"],
        totals["games_marked_processed"],
        args.dry_run,
    )
    return 1 if totals["games_failed"] or totals["dates_failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
