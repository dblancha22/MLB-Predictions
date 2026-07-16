#!/usr/bin/env python3
"""Ingest final MLB team batting totals into Supabase team_game_logs.

This writer is intentionally standalone. Shared ingestion utilities can be
extracted after both this script and ingest_games_raw.py are stable.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen


MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
MLB_BOXSCORE_URL = "https://statsapi.mlb.com/api/v1/game/{game_id}/boxscore"
EXPECTED_SUPABASE_PROJECT_REF = "soakgdpuvtxadjextekg"
DEFAULT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
FINAL_STATUS_CODE = "F"
FINAL_CODED_GAME_STATE = "F"

LOGGER = logging.getLogger("ingest_team_game_logs")


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
    "runs_scored": "runs",
    "hits": "hits",
    "home_runs": "homeRuns",
    "strikeouts": "strikeOuts",
    "walks": "baseOnBalls",
    "plate_appearances": "plateAppearances",
    "at_bats": "atBats",
    "total_bases": "totalBases",
    "left_on_base": "leftOnBase",
    "grounded_into_double_play": "groundIntoDoublePlay",
    "doubles": "doubles",
    "triples": "triples",
}


def transform_team_game_rows(
    schedule_game: Mapping[str, Any], boxscore: Mapping[str, Any]
) -> List[Dict[str, int]]:
    game_id = _required_int(schedule_game, "gamePk", "game")
    context = f"game[{game_id}]"
    schedule_team_ids = {
        side: int(
            _nested_required(schedule_game, ("teams", side, "team", "id"), context)
        )
        for side in ("home", "away")
    }
    rows: List[Dict[str, int]] = []
    for side, opponent_side in (("home", "away"), ("away", "home")):
        side_context = f"{context}.boxscore.teams.{side}"
        boxscore_team_id = int(
            _nested_required(boxscore, ("teams", side, "team", "id"), context)
        )
        if boxscore_team_id != schedule_team_ids[side]:
            raise IngestionError(
                f"team mismatch for {context} side={side}: schedule="
                f"{schedule_team_ids[side]} boxscore={boxscore_team_id}"
            )
        batting = _nested_required(
            boxscore, ("teams", side, "teamStats", "batting"), context
        )
        if not isinstance(batting, Mapping):
            raise IngestionError(f"invalid MLB batting object {side_context}")
        row: Dict[str, int] = {
            "game_id": game_id,
            "team_id": boxscore_team_id,
            "opponent_id": schedule_team_ids[opponent_side],
        }
        for column, source_field in STAT_COLUMNS.items():
            row[column] = _required_int(batting, source_field, side_context)
        rows.append(row)
    return rows


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


def validate_dependencies(
    client: Any, rows: Sequence[Mapping[str, int]]
) -> Tuple[List[Dict[str, int]], List[int]]:
    """Return rows whose game/team references exist and invalid game IDs."""
    if not rows:
        return [], []
    game_ids = sorted({row["game_id"] for row in rows})
    team_ids = sorted(
        {row["team_id"] for row in rows} | {row["opponent_id"] for row in rows}
    )
    games_response = (
        client.table("games_raw")
        .select("game_id")
        .in_("game_id", game_ids)
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
    invalid_games = sorted(
        {
            row["game_id"]
            for row in rows
            if row["game_id"] not in existing_games
            or row["team_id"] not in existing_teams
            or row["opponent_id"] not in existing_teams
        }
    )
    invalid_set = set(invalid_games)
    return [dict(row) for row in rows if row["game_id"] not in invalid_set], invalid_games


def upsert_team_game_logs(client: Any, rows: Sequence[Mapping[str, int]]) -> int:
    if not rows:
        return 0
    client.table("team_game_logs").upsert(
        [dict(row) for row in rows],
        on_conflict="game_id,team_id",
        default_to_null=False,
    ).execute()
    return len(rows)


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
    eligible_games = final_games(schedule_games)
    summary = {
        "games_found": len(schedule_games),
        "final_games_found": len(eligible_games),
        "non_final_skipped": len(schedule_games) - len(eligible_games),
        "games_failed": 0,
        "rows_ready": 0,
        "rows_upserted": 0,
    }
    rows: List[Dict[str, int]] = []
    for game in eligible_games:
        game_id = _required_int(game, "gamePk", "game")
        try:
            boxscore = fetch_boxscore(game_id, timeout, retries)
            rows.extend(transform_team_game_rows(game, boxscore))
        except Exception as exc:
            summary["games_failed"] += 1
            LOGGER.error(
                "date=%s game=%s source=MLB-boxscore action=skip error=%s",
                target_date,
                game_id,
                exc,
            )

    summary["rows_ready"] = len(rows)
    if dry_run or not rows:
        return summary

    valid_rows, invalid_games = validate_dependencies(client, rows)
    for game_id in invalid_games:
        LOGGER.error(
            "date=%s game=%s table=team_game_logs action=skip "
            "error=missing games_raw or teams dependency",
            target_date,
            game_id,
        )
    summary["games_failed"] += len(invalid_games)
    summary["rows_ready"] = len(valid_rows)
    summary["rows_upserted"] = upsert_team_game_logs(client, valid_rows)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Populate team_game_logs from final MLB boxscores."
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

    totals = {
        "games_found": 0,
        "final_games_found": 0,
        "non_final_skipped": 0,
        "games_failed": 0,
        "rows_ready": 0,
        "rows_upserted": 0,
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
            "games_failed=%s rows_ready=%s rows_upserted=%s dry_run=%s",
            target_date,
            summary["games_found"],
            summary["final_games_found"],
            summary["non_final_skipped"],
            summary["games_failed"],
            summary["rows_ready"],
            summary["rows_upserted"],
            args.dry_run,
        )
        for key in summary:
            totals[key] += summary[key]

    LOGGER.info(
        "complete dates=%s games_found=%s final_games_found=%s games_failed=%s "
        "dates_failed=%s rows_ready=%s rows_upserted=%s dry_run=%s",
        len(dates),
        totals["games_found"],
        totals["final_games_found"],
        totals["games_failed"],
        totals["dates_failed"],
        totals["rows_ready"],
        totals["rows_upserted"],
        args.dry_run,
    )
    return 1 if totals["games_failed"] or totals["dates_failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
