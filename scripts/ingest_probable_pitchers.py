#!/usr/bin/env python3
"""Synchronize pregame MLB probable-pitcher assignments into Supabase."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

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
MLB_PERSON_URL = "https://statsapi.mlb.com/api/v1/people/{pitcher_id}"
PREGAME_ABSTRACT_STATE = "Preview"

LOGGER = logging.getLogger("ingest_probable_pitchers")
AssignmentKey = Tuple[int, int]


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
        {
            "sportId": 1,
            "gameType": game_type,
            "date": target_date.isoformat(),
            "hydrate": "probablePitcher,team",
        },
        timeout,
        retries,
    )


def fetch_person(
    pitcher_id: int, timeout: float = 30.0, retries: int = 2
) -> Dict[str, Any]:
    return _request_json(
        MLB_PERSON_URL.format(pitcher_id=pitcher_id), {}, timeout, retries
    )


def flatten_schedule(payload: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    games: List[Mapping[str, Any]] = []
    for date_entry in payload.get("dates", []):
        entry_games = date_entry.get("games", []) if isinstance(date_entry, Mapping) else []
        games.extend(game for game in entry_games if isinstance(game, Mapping))
    return games


def _required_int(mapping: Mapping[str, Any], key: str, context: str) -> int:
    value = mapping.get(key)
    if value is None or isinstance(value, bool):
        raise IngestionError(f"missing required MLB field {context}.{key}")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise IngestionError(
            f"invalid integer MLB field {context}.{key}={value!r}"
        ) from exc


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


def pregame_games(games: Iterable[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    """Return one valid pregame occurrence per canonical MLB gamePk."""
    by_id: Dict[int, Mapping[str, Any]] = {}
    for game in games:
        status = game.get("status")
        if not isinstance(status, Mapping):
            continue
        if status.get("abstractGameState") != PREGAME_ABSTRACT_STATE:
            continue
        game_id = _required_int(game, "gamePk", "game")
        by_id[game_id] = game
    return list(by_id.values())


def transform_assignment_slots(
    game: Mapping[str, Any], updated_at: str
) -> Tuple[List[Dict[str, Any]], Set[AssignmentKey]]:
    """Map announced assignments and identify slots MLB currently leaves empty."""
    game_id = _required_int(game, "gamePk", "game")
    context = f"game[{game_id}]"
    rows: List[Dict[str, Any]] = []
    missing: Set[AssignmentKey] = set()
    for side in ("home", "away"):
        side_data = _nested_required(game, ("teams", side), context)
        if not isinstance(side_data, Mapping):
            raise IngestionError(f"invalid MLB field {context}.teams.{side}")
        team = side_data.get("team")
        if not isinstance(team, Mapping):
            raise IngestionError(f"missing required MLB field {context}.teams.{side}.team")
        team_id = _required_int(team, "id", f"{context}.teams.{side}.team")
        probable = side_data.get("probablePitcher")
        if probable is None:
            missing.add((game_id, team_id))
            continue
        if not isinstance(probable, Mapping):
            raise IngestionError(
                f"invalid MLB field {context}.teams.{side}.probablePitcher"
            )
        pitcher_id = _required_int(
            probable, "id", f"{context}.teams.{side}.probablePitcher"
        )
        full_name = probable.get("fullName")
        rows.append(
            {
                "game_id": game_id,
                "team_id": team_id,
                "pitcher_id": pitcher_id,
                "pitch_hand": None,
                "full_name": str(full_name) if full_name is not None else None,
                "updated_at": updated_at,
            }
        )
    return rows, missing


def extract_pitch_hand(payload: Mapping[str, Any], pitcher_id: int) -> Optional[str]:
    people = payload.get("people")
    if not isinstance(people, list):
        raise IngestionError(
            f"MLB people endpoint returned no people list for pitcher_id={pitcher_id}"
        )
    person = next(
        (
            candidate
            for candidate in people
            if isinstance(candidate, Mapping) and candidate.get("id") == pitcher_id
        ),
        None,
    )
    if person is None:
        raise IngestionError(
            f"MLB people endpoint returned no matching person for pitcher_id={pitcher_id}"
        )
    pitch_hand = person.get("pitchHand")
    if pitch_hand is None:
        return None
    if not isinstance(pitch_hand, Mapping):
        raise IngestionError(f"invalid MLB pitchHand for pitcher_id={pitcher_id}")
    code = pitch_hand.get("code")
    return str(code) if code is not None else None


def validate_team_dependencies(client: Any, team_ids: Iterable[int]) -> None:
    expected = sorted(set(team_ids))
    if not expected:
        return
    response = (
        client.table("teams").select("team_id").in_("team_id", expected).execute()
    )
    existing = {row["team_id"] for row in (response.data or [])}
    missing = sorted(set(expected) - existing)
    if missing:
        raise IngestionError(f"missing teams dependency for team_id(s)={missing}")


def sync_probable_pitchers(
    client: Any,
    rows: Sequence[Mapping[str, Any]],
    missing_assignments: Set[AssignmentKey],
) -> Tuple[int, int]:
    """Upsert announced assignments and delete currently empty pregame slots."""
    game_ids = sorted(
        {int(row["game_id"]) for row in rows}
        | {game_id for game_id, _ in missing_assignments}
    )
    existing_keys: Set[AssignmentKey] = set()
    if game_ids:
        response = (
            client.table("probable_pitchers")
            .select("game_id,team_id")
            .in_("game_id", game_ids)
            .execute()
        )
        existing_keys = {
            (int(row["game_id"]), int(row["team_id"]))
            for row in (response.data or [])
        }

    prepared = [dict(row) for row in rows]
    if prepared:
        client.table("probable_pitchers").upsert(
            prepared,
            on_conflict="game_id,team_id",
            default_to_null=False,
        ).execute()

    to_delete = sorted(existing_keys & missing_assignments)
    for game_id, team_id in to_delete:
        (
            client.table("probable_pitchers")
            .delete()
            .eq("game_id", game_id)
            .eq("team_id", team_id)
            .execute()
        )
    return len(prepared), len(to_delete)


def ingest_date(
    client: Any,
    target_date: date,
    game_type: str,
    dry_run: bool,
    timeout: float,
    retries: int,
    schedule_payload: Optional[Mapping[str, Any]] = None,
    person_fetcher: Optional[Any] = None,
) -> Dict[str, int]:
    payload = (
        fetch_schedule(target_date, game_type, timeout, retries)
        if schedule_payload is None
        else schedule_payload
    )
    schedule_games = flatten_schedule(payload)
    eligible_games = pregame_games(schedule_games)
    summary = {
        "games_found": len(schedule_games),
        "pregame_games_found": len(eligible_games),
        "non_pregame_skipped": len(schedule_games) - len(eligible_games),
        "games_failed": 0,
        "assignments_found": 0,
        "assignments_missing": 0,
        "people_failed": 0,
        "rows_upserted": 0,
        "rows_deleted": 0,
    }
    updated_at = datetime.now(timezone.utc).isoformat()
    rows: List[Dict[str, Any]] = []
    missing_assignments: Set[AssignmentKey] = set()
    for game in eligible_games:
        game_id = game.get("gamePk")
        try:
            game_rows, game_missing = transform_assignment_slots(game, updated_at)
            rows.extend(game_rows)
            missing_assignments.update(game_missing)
        except Exception as exc:
            summary["games_failed"] += 1
            LOGGER.error(
                "date=%s game=%s source=MLB-schedule action=skip error=%s",
                target_date,
                game_id,
                exc,
            )

    summary["assignments_found"] = len(rows)
    summary["assignments_missing"] = len(missing_assignments)
    get_person = fetch_person if person_fetcher is None else person_fetcher
    hands: Dict[int, Optional[str]] = {}
    for pitcher_id in sorted({int(row["pitcher_id"]) for row in rows}):
        try:
            hands[pitcher_id] = extract_pitch_hand(
                get_person(pitcher_id, timeout, retries), pitcher_id
            )
        except Exception as exc:
            summary["people_failed"] += 1
            hands[pitcher_id] = None
            LOGGER.error(
                "date=%s pitcher=%s source=MLB-people action=use-null-hand error=%s",
                target_date,
                pitcher_id,
                exc,
            )
    for row in rows:
        row["pitch_hand"] = hands[int(row["pitcher_id"])]

    if dry_run or (not rows and not missing_assignments):
        return summary

    team_ids = {int(row["team_id"]) for row in rows} | {
        team_id for _, team_id in missing_assignments
    }
    validate_team_dependencies(client, team_ids)
    upserted, deleted = sync_probable_pitchers(client, rows, missing_assignments)
    summary["rows_upserted"] = upserted
    summary["rows_deleted"] = deleted
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Synchronize pregame probable_pitchers from the MLB Stats API."
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

    total_games_failed = 0
    total_people_failed = 0
    dates_failed = 0
    total_upserted = 0
    total_deleted = 0
    for target_date in dates:
        try:
            summary = ingest_date(
                client, target_date, args.game_type, args.dry_run, args.timeout, args.retries
            )
        except Exception as exc:
            dates_failed += 1
            LOGGER.error("date=%s action=fail error=%s", target_date, exc)
            LOGGER.debug("date ingestion failure", exc_info=True)
            continue
        total_games_failed += summary["games_failed"]
        total_people_failed += summary["people_failed"]
        total_upserted += summary["rows_upserted"]
        total_deleted += summary["rows_deleted"]
        LOGGER.info(
            "date=%s games_found=%s pregame_games_found=%s non_pregame_skipped=%s "
            "games_failed=%s assignments_found=%s assignments_missing=%s "
            "people_failed=%s rows_upserted=%s rows_deleted=%s dry_run=%s",
            target_date,
            summary["games_found"],
            summary["pregame_games_found"],
            summary["non_pregame_skipped"],
            summary["games_failed"],
            summary["assignments_found"],
            summary["assignments_missing"],
            summary["people_failed"],
            summary["rows_upserted"],
            summary["rows_deleted"],
            args.dry_run,
        )

    LOGGER.info(
        "complete dates=%s games_failed=%s people_failed=%s dates_failed=%s "
        "rows_upserted=%s rows_deleted=%s dry_run=%s",
        len(dates),
        total_games_failed,
        total_people_failed,
        dates_failed,
        total_upserted,
        total_deleted,
        args.dry_run,
    )
    return 1 if total_games_failed or total_people_failed or dates_failed else 0


if __name__ == "__main__":
    sys.exit(main())
