#!/usr/bin/env python3
"""Synchronize pregame MLB probable-pitcher assignments into Supabase."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen


MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
MLB_PERSON_URL = "https://statsapi.mlb.com/api/v1/people/{pitcher_id}"
EXPECTED_SUPABASE_PROJECT_REF = "soakgdpuvtxadjextekg"
DEFAULT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
PREGAME_ABSTRACT_STATE = "Preview"

LOGGER = logging.getLogger("ingest_probable_pitchers")
AssignmentKey = Tuple[int, int]


class IngestionError(RuntimeError):
    """Raised when source data or configuration cannot be safely ingested."""


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE entries without overwriting process variables."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def normalize_supabase_url(value: str) -> str:
    parsed = urlparse(value.strip().rstrip("/"))
    if parsed.scheme != "https" or not parsed.hostname:
        raise IngestionError("SUPABASE_URL must be a valid HTTPS project URL")
    normalized_path = parsed.path.rstrip("/")
    if normalized_path not in {"", "/rest/v1"}:
        raise IngestionError(
            "SUPABASE_URL must be the project base URL or end with /rest/v1"
        )
    return urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))


def parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid date {value!r}; expected YYYY-MM-DD"
        ) from exc


def build_date_range(
    single_date: Optional[date], start_date: Optional[date], end_date: Optional[date]
) -> List[date]:
    if single_date is not None:
        if start_date is not None or end_date is not None:
            raise IngestionError("--date cannot be combined with a date range")
        return [single_date]
    if start_date is None or end_date is None:
        raise IngestionError("provide --date or both --start-date and --end-date")
    if start_date > end_date:
        raise IngestionError("--start-date must be on or before --end-date")
    return [
        start_date + timedelta(days=offset)
        for offset in range((end_date - start_date).days + 1)
    ]


def _request_json(
    url: str, params: Mapping[str, Any], timeout: float, retries: int
) -> Dict[str, Any]:
    request_url = f"{url}?{urlencode(params)}" if params else url
    request = Request(
        request_url,
        headers={"Accept": "application/json", "User-Agent": "MLB-Predictions-ingestion/1.0"},
    )
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                if not 200 <= response.status < 300:
                    raise IngestionError(
                        f"MLB Stats API returned HTTP {response.status} for {request_url}"
                    )
                payload = json.load(response)
                if not isinstance(payload, dict):
                    raise IngestionError("MLB Stats API response was not a JSON object")
                return payload
        except HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code < 600
            if not retryable or attempt >= retries:
                raise IngestionError(
                    f"MLB Stats API returned HTTP {exc.code} for {request_url}"
                ) from exc
        except (URLError, TimeoutError) as exc:
            if attempt >= retries:
                raise IngestionError(
                    f"MLB Stats API request failed for {request_url}: {exc}"
                ) from exc
        delay = 2**attempt
        LOGGER.warning("MLB request failed; retrying in %s second(s)", delay)
        time.sleep(delay)
    raise AssertionError("retry loop exited unexpectedly")


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


def create_supabase_client(env_file: Path):
    load_env_file(env_file)
    raw_url = os.getenv("SUPABASE_URL", "").strip()
    secret_key = (
        os.getenv("SUPABASE_SECRET_KEY", "").strip()
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    )
    if not raw_url:
        raise IngestionError("SUPABASE_URL is not set")
    if not secret_key:
        raise IngestionError(
            "SUPABASE_SECRET_KEY or SUPABASE_SERVICE_ROLE_KEY is not set"
        )
    supabase_url = normalize_supabase_url(raw_url)
    project_ref = (urlparse(supabase_url).hostname or "").split(".", 1)[0]
    if project_ref != EXPECTED_SUPABASE_PROJECT_REF:
        raise IngestionError(
            "SUPABASE_URL does not point to the expected BagBrainOfficial project "
            f"({EXPECTED_SUPABASE_PROJECT_REF})"
        )
    try:
        from supabase import create_client
    except ImportError as exc:
        raise IngestionError(
            "supabase-py is not installed; run: python -m pip install -r requirements-ingestion.txt"
        ) from exc
    return create_client(supabase_url, secret_key)


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
) -> Dict[str, int]:
    schedule_games = flatten_schedule(
        fetch_schedule(target_date, game_type, timeout, retries)
    )
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
    hands: Dict[int, Optional[str]] = {}
    for pitcher_id in sorted({int(row["pitcher_id"]) for row in rows}):
        try:
            hands[pitcher_id] = extract_pitch_hand(
                fetch_person(pitcher_id, timeout, retries), pitcher_id
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
        if args.retries < 0:
            raise IngestionError("--retries cannot be negative")
        if args.timeout <= 0:
            raise IngestionError("--timeout must be positive")
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
