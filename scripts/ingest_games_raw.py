#!/usr/bin/env python3
"""Ingest MLB schedule rows into Supabase raw tables.

The script inserts missing team and venue identities before upserting games_raw.
It intentionally does not update existing team or venue rows.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timezone
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
MLB_VENUE_URL = "https://statsapi.mlb.com/api/v1/venues/{venue_id}"
FINAL_STATUS_CODE = "F"

LOGGER = logging.getLogger("ingest_games_raw")


def _request_json(
    url: str, params: Mapping[str, Any], timeout: float, retries: int
) -> Dict[str, Any]:
    return request_json(url, params, timeout, retries, LOGGER)


def fetch_schedule(
    game_date: date,
    game_type: str = "R",
    timeout: float = 30.0,
    retries: int = 2,
) -> Dict[str, Any]:
    return _request_json(
        MLB_SCHEDULE_URL,
        {
            "sportId": 1,
            "gameType": game_type,
            "date": game_date.isoformat(),
            "hydrate": "venue,team",
        },
        timeout,
        retries,
    )


def fetch_venue(
    venue_id: int, timeout: float = 30.0, retries: int = 2
) -> Mapping[str, Any]:
    payload = _request_json(
        MLB_VENUE_URL.format(venue_id=venue_id),
        {"hydrate": "location"},
        timeout,
        retries,
    )
    venues = payload.get("venues")
    if not isinstance(venues, list) or not venues:
        raise IngestionError(
            f"MLB venue endpoint returned no venue for venue_id={venue_id}"
        )
    venue = venues[0]
    if not isinstance(venue, Mapping):
        raise IngestionError(
            f"MLB venue endpoint returned an invalid venue for venue_id={venue_id}"
        )
    returned_id = int(_required(venue, "id", f"venue[{venue_id}]"))
    if returned_id != venue_id:
        raise IngestionError(
            f"MLB venue endpoint returned venue_id={returned_id} for requested venue_id={venue_id}"
        )
    return venue


def flatten_schedule(payload: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    games: List[Mapping[str, Any]] = []
    for date_entry in payload.get("dates", []):
        entry_games = date_entry.get("games", []) if isinstance(date_entry, Mapping) else []
        games.extend(game for game in entry_games if isinstance(game, Mapping))
    return games


def _required(mapping: Mapping[str, Any], key: str, context: str) -> Any:
    value = mapping.get(key)
    if value is None:
        raise IngestionError(f"missing required MLB field {context}.{key}")
    return value


def _nested_required(mapping: Mapping[str, Any], path: Sequence[str], context: str) -> Any:
    current: Any = mapping
    traversed: List[str] = []
    for key in path:
        traversed.append(key)
        if not isinstance(current, Mapping) or current.get(key) is None:
            joined = ".".join(traversed)
            raise IngestionError(f"missing required MLB field {context}.{joined}")
        current = current[key]
    return current


def utc_timestamptz(value: str) -> str:
    """Convert an MLB ISO-8601 timestamp to explicit UTC ISO text."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IngestionError(f"invalid MLB gameDate timestamp {value!r}") from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc).replace(microsecond=0)
    return parsed.isoformat()


def _status_details(game: Mapping[str, Any], context: str) -> Mapping[str, Any]:
    status = game.get("status") or {}
    if not isinstance(status, Mapping):
        raise IngestionError(f"invalid MLB field {context}.status")
    return status


def _reschedule_game_date(
    game: Mapping[str, Any], context: str
) -> Optional[date]:
    value = game.get("rescheduleGameDate")
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise IngestionError(
            f"invalid MLB field {context}.rescheduleGameDate={value!r}"
        ) from exc


def should_skip_cross_date_postponement(
    game: Mapping[str, Any], schedule_date: date
) -> bool:
    """Skip only postponed games explicitly moved to another local game date."""
    game_id = game.get("gamePk", "unknown")
    context = f"game[{game_id}]"
    status = _status_details(game, context)
    if status.get("detailedState") != "Postponed":
        return False
    reschedule_game_date = _reschedule_game_date(game, context)
    return (
        reschedule_game_date is not None
        and reschedule_game_date != schedule_date
    )


def effective_game_timestamp(game: Mapping[str, Any], schedule_date: date) -> str:
    """Return the original scheduled instant for a game's canonical row."""
    game_id = game.get("gamePk", "unknown")
    context = f"game[{game_id}]"
    if game.get("resumedFrom"):
        return str(game["resumedFrom"])
    status = _status_details(game, context)
    reschedule_game_date = _reschedule_game_date(game, context)
    if (
        status.get("detailedState") == "Postponed"
        and reschedule_game_date == schedule_date
        and game.get("rescheduleDate")
    ):
        return str(game["rescheduleDate"])
    return str(_required(game, "gameDate", context))


def transform_game(
    game: Mapping[str, Any], ingested_at: str, schedule_date: Optional[date] = None
) -> Dict[str, Any]:
    game_id = int(_required(game, "gamePk", "game"))
    context = f"game[{game_id}]"
    game_date_value = (
        str(game.get("resumedFromDate") or schedule_date.isoformat())
        if schedule_date is not None
        else game.get("officialDate")
    )
    if game_date_value is None:
        game_date_value = utc_timestamptz(
            str(_required(game, "gameDate", context))
        )[:10]

    status = _status_details(game, context)
    detailed_status = status.get("detailedState") or status.get("abstractGameState")
    if detailed_status is None:
        raise IngestionError(f"missing required MLB field {context}.status.detailedState")

    row: Dict[str, Any] = {
        "game_id": game_id,
        "game_date": str(game_date_value),
        "home_team_id": int(
            _nested_required(game, ("teams", "home", "team", "id"), context)
        ),
        "away_team_id": int(
            _nested_required(game, ("teams", "away", "team", "id"), context)
        ),
        "venue_id": (
            game.get("venue", {}).get("id")
            if isinstance(game.get("venue"), Mapping)
            else None
        ),
        "status": str(detailed_status),
        "scheduled_time_utc": utc_timestamptz(
            effective_game_timestamp(game, schedule_date)
            if schedule_date is not None
            else str(_required(game, "gameDate", context))
        ),
        "game_type": str(_required(game, "gameType", context)),
        "season": int(_required(game, "season", context)),
        "day_night": game.get("dayNight"),
        "updated_at": ingested_at,
    }

    # A resumed-game occurrence repeats the original gamePk on the resume date,
    # but MLB can report that date's series context instead of the original
    # game's context. Omit these keys so an upsert preserves the original row.
    if not game.get("resumedFrom"):
        row.update(
            {
                "doubleheader_code": game.get("doubleHeader"),
                "game_number": _optional_int(game.get("gameNumber")),
                "series_game_number": _optional_int(game.get("seriesGameNumber")),
                "games_in_series": _optional_int(game.get("gamesInSeries")),
            }
        )
    else:
        row["_resumed_occurrence"] = True

    # Only a completed final (status code F) is postgame-safe for score storage.
    home = _nested_required(game, ("teams", "home"), context)
    away = _nested_required(game, ("teams", "away"), context)
    if status.get("statusCode") == FINAL_STATUS_CODE:
        if isinstance(home, Mapping) and isinstance(away, Mapping):
            if home.get("score") is not None and away.get("score") is not None:
                row["home_score"] = int(home["score"])
                row["away_score"] = int(away["score"])
            else:
                LOGGER.warning(
                    "game=%s statusCode=F but one or both final scores are missing", game_id
                )

    return row


def _optional_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    return int(value)


def transform_team(team: Mapping[str, Any], ingested_at: str) -> Dict[str, Any]:
    team_id = int(_required(team, "id", "team"))
    league = team.get("league") if isinstance(team.get("league"), Mapping) else {}
    division = team.get("division") if isinstance(team.get("division"), Mapping) else {}
    sport = team.get("sport") if isinstance(team.get("sport"), Mapping) else {}
    venue = team.get("venue") if isinstance(team.get("venue"), Mapping) else {}
    return {
        "team_id": team_id,
        "name": team.get("name"),
        "team_name": team.get("teamName"),
        "franchise_name": team.get("franchiseName"),
        "abbreviation": team.get("abbreviation"),
        "team_code": team.get("teamCode"),
        "file_code": team.get("fileCode"),
        "location_name": team.get("locationName"),
        "league_id": _optional_int(league.get("id")),
        "division_id": _optional_int(division.get("id")),
        "sport_id": _optional_int(sport.get("id")) or 1,
        "first_year_of_play": _optional_int(team.get("firstYearOfPlay")),
        "active": team.get("active"),
        "venue_id": _optional_int(venue.get("id")),
        "updated_at": ingested_at,
    }


def transform_venue(venue: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "venue_id": int(_required(venue, "id", "venue")),
        "name": venue.get("name"),
    }


def _optional_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    return float(value)


def transform_enriched_venue(venue: Mapping[str, Any]) -> Dict[str, Any]:
    row = transform_venue(venue)
    location = (
        venue.get("location")
        if isinstance(venue.get("location"), Mapping)
        else {}
    )
    coordinates = (
        location.get("defaultCoordinates")
        if isinstance(location.get("defaultCoordinates"), Mapping)
        else {}
    )
    row.update(
        {
            "city": location.get("city"),
            "state": location.get("stateAbbrev") or location.get("state"),
            "country": location.get("country"),
            "latitude": _optional_float(coordinates.get("latitude")),
            "longitude": _optional_float(coordinates.get("longitude")),
            "altitude_ft": _optional_float(location.get("elevation")),
            "field_orientation_degrees": _optional_float(
                location.get("azimuthAngle")
            ),
        }
    )
    return row


def extract_dependencies(
    games: Iterable[Mapping[str, Any]], ingested_at: str
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    teams: Dict[int, Dict[str, Any]] = {}
    venues: Dict[int, Dict[str, Any]] = {}

    for game in games:
        game_id = game.get("gamePk", "unknown")
        for side in ("home", "away"):
            team = _nested_required(game, ("teams", side, "team"), f"game[{game_id}]")
            if not isinstance(team, Mapping):
                raise IngestionError(f"invalid MLB team object for game={game_id} side={side}")
            row = transform_team(team, ingested_at)
            teams[row["team_id"]] = row
            team_venue = team.get("venue")
            if isinstance(team_venue, Mapping) and team_venue.get("id") is not None:
                venue_row = transform_venue(team_venue)
                venues[venue_row["venue_id"]] = venue_row

        venue = game.get("venue")
        if isinstance(venue, Mapping) and venue.get("id") is not None:
            row = transform_venue(venue)
            venues[row["venue_id"]] = row

    return list(teams.values()), list(venues.values())


def insert_missing_rows(
    client: Any, table: str, id_column: str, rows: Sequence[Mapping[str, Any]]
) -> int:
    if not rows:
        return 0
    ids = [row[id_column] for row in rows]
    response = client.table(table).select(id_column).in_(id_column, ids).execute()
    existing = {row[id_column] for row in (response.data or [])}
    missing = [dict(row) for row in rows if row[id_column] not in existing]
    if missing:
        client.table(table).insert(missing).execute()
    return len(missing)


def insert_missing_enriched_venues(
    client: Any,
    venue_rows: Sequence[Mapping[str, Any]],
    timeout: float,
    retries: int,
    venue_fetcher: Optional[Any] = None,
) -> int:
    if not venue_rows:
        return 0
    venue_ids = list(dict.fromkeys(row["venue_id"] for row in venue_rows))
    response = (
        client.table("venues")
        .select("venue_id")
        .in_("venue_id", venue_ids)
        .execute()
    )
    existing_ids = {row["venue_id"] for row in (response.data or [])}
    missing_ids = [venue_id for venue_id in venue_ids if venue_id not in existing_ids]
    if not missing_ids:
        return 0

    fetcher = fetch_venue if venue_fetcher is None else venue_fetcher
    enriched_rows = []
    for venue_id in missing_ids:
        LOGGER.info("venue=%s source=MLB action=enrich", venue_id)
        venue = fetcher(int(venue_id), timeout, retries)
        enriched_rows.append(transform_enriched_venue(venue))

    client.table("venues").insert(enriched_rows).execute()
    return len(enriched_rows)


def upsert_games(client: Any, rows: Sequence[Mapping[str, Any]]) -> int:
    if not rows:
        return 0

    prepared = [dict(row) for row in rows]
    resumed = [row for row in prepared if row.pop("_resumed_occurrence", False)]
    if resumed:
        preserve_columns = (
            "game_id,day_night,doubleheader_code,game_number,"
            "series_game_number,games_in_series"
        )
        resumed_ids = [row["game_id"] for row in resumed]
        response = (
            client.table("games_raw")
            .select(preserve_columns)
            .in_("game_id", resumed_ids)
            .execute()
        )
        existing_by_id = {
            existing["game_id"]: existing for existing in (response.data or [])
        }
        for row in resumed:
            existing = existing_by_id.get(row["game_id"])
            if not existing:
                continue
            for column in (
                "day_night",
                "doubleheader_code",
                "game_number",
                "series_game_number",
                "games_in_series",
            ):
                row[column] = existing.get(column)

    # Keep score columns out of non-final payloads so reruns cannot erase stored finals.
    scored = [row for row in prepared if "home_score" in row and "away_score" in row]
    unscored = [row for row in prepared if "home_score" not in row]
    for batch in (unscored, scored):
        if batch:
            client.table("games_raw").upsert(
                batch, on_conflict="game_id", default_to_null=False
            ).execute()
    return len(rows)


def ingest_date(
    client: Any,
    target_date: date,
    game_type: str,
    dry_run: bool,
    timeout: float,
    retries: int,
    schedule_payload: Optional[Mapping[str, Any]] = None,
    venue_fetcher: Optional[Any] = None,
) -> Dict[str, int]:
    payload = (
        fetch_schedule(target_date, game_type, timeout, retries)
        if schedule_payload is None
        else schedule_payload
    )
    games = flatten_schedule(payload)
    skipped_games = []
    games_to_ingest = []
    for game in games:
        destination = (
            skipped_games
            if should_skip_cross_date_postponement(game, target_date)
            else games_to_ingest
        )
        destination.append(game)
    for game in skipped_games:
        LOGGER.info(
            "date=%s game=%s status=Postponed reschedule_game_date=%s action=skip",
            target_date,
            game.get("gamePk"),
            game.get("rescheduleGameDate"),
        )
    ingested_at = datetime.now(timezone.utc).isoformat()
    teams, venues = extract_dependencies(games_to_ingest, ingested_at)
    game_rows = [
        transform_game(game, ingested_at, target_date) for game in games_to_ingest
    ]

    summary = {
        "games_found": len(games),
        "games_skipped": len(skipped_games),
        "teams_found": len(teams),
        "venues_found": len(venues),
        "teams_inserted": 0,
        "venues_inserted": 0,
        "games_upserted": 0,
    }
    if dry_run or not game_rows:
        return summary

    summary["venues_inserted"] = insert_missing_enriched_venues(
        client, venues, timeout, retries, venue_fetcher
    )
    summary["teams_inserted"] = insert_missing_rows(client, "teams", "team_id", teams)
    summary["games_upserted"] = upsert_games(client, game_rows)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Populate games_raw from the MLB Stats API."
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
        totals = {
            "games_found": 0,
            "games_skipped": 0,
            "teams_inserted": 0,
            "venues_inserted": 0,
            "games_upserted": 0,
        }
        for target_date in dates:
            summary = ingest_date(
                client,
                target_date,
                args.game_type,
                args.dry_run,
                args.timeout,
                args.retries,
            )
            LOGGER.info(
                "date=%s games_found=%s games_skipped=%s teams_found=%s venues_found=%s "
                "teams_inserted=%s venues_inserted=%s games_upserted=%s dry_run=%s",
                target_date,
                summary["games_found"],
                summary["games_skipped"],
                summary["teams_found"],
                summary["venues_found"],
                summary["teams_inserted"],
                summary["venues_inserted"],
                summary["games_upserted"],
                args.dry_run,
            )
            for key in totals:
                totals[key] += summary[key]

        LOGGER.info(
            "complete dates=%s games_found=%s games_skipped=%s "
            "teams_inserted=%s venues_inserted=%s "
            "games_upserted=%s dry_run=%s",
            len(dates),
            totals["games_found"],
            totals["games_skipped"],
            totals["teams_inserted"],
            totals["venues_inserted"],
            totals["games_upserted"],
            args.dry_run,
        )
        return 0
    except (IngestionError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 1
    except Exception as exc:  # Supabase client errors are not part of one stable hierarchy.
        LOGGER.error("ingestion failed: %s", exc)
        LOGGER.debug("unexpected ingestion failure", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
