#!/usr/bin/env python3
"""Populate all previous-day or date-range MLB postgame raw tables."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

try:
    from scripts import ingest_games_raw as games_ingestion
    from scripts import ingest_pitcher_game_logs as pitcher_ingestion
    from scripts import ingest_probable_pitchers as probable_ingestion
    from scripts import ingest_team_game_logs as team_ingestion
    from scripts.ingestion.common import (
        DEFAULT_ENV_FILE,
        DEFAULT_TIMEZONE,
        IngestionError,
        build_date_range,
        create_supabase_client,
        parse_iso_date,
        resolve_yesterday,
        validate_runtime_options,
    )
    from scripts.ingestion.mlb import MLBStatsClient, schedule_payloads_by_date
except ModuleNotFoundError:  # Support direct `python scripts/...` execution.
    import ingest_games_raw as games_ingestion  # type: ignore[no-redef]
    import ingest_pitcher_game_logs as pitcher_ingestion  # type: ignore[no-redef]
    import ingest_probable_pitchers as probable_ingestion  # type: ignore[no-redef]
    import ingest_team_game_logs as team_ingestion  # type: ignore[no-redef]
    from ingestion.common import (  # type: ignore[no-redef]
        DEFAULT_ENV_FILE,
        DEFAULT_TIMEZONE,
        IngestionError,
        build_date_range,
        create_supabase_client,
        parse_iso_date,
        resolve_yesterday,
        validate_runtime_options,
    )
    from ingestion.mlb import (  # type: ignore[no-redef]
        MLBStatsClient,
        schedule_payloads_by_date,
    )


LOGGER = logging.getLogger("ingest_postgame")
ALL_STEPS = ("games", "probable-recovery", "team-logs", "pitcher-logs")
POSTGAME_SCHEDULE_HYDRATION = "probablePitcher,venue,team"


def parse_steps(value: str) -> Tuple[str, ...]:
    steps = tuple(dict.fromkeys(part.strip() for part in value.split(",") if part.strip()))
    invalid = sorted(set(steps) - set(ALL_STEPS))
    if invalid:
        raise argparse.ArgumentTypeError(
            f"invalid step(s) {invalid}; choose from {','.join(ALL_STEPS)}"
        )
    if not steps:
        raise argparse.ArgumentTypeError("at least one ingestion step is required")
    return steps


def chunked_dates(dates: Sequence[date], chunk_size: int) -> Iterable[Tuple[date, ...]]:
    for start in range(0, len(dates), chunk_size):
        yield tuple(dates[start : start + chunk_size])


def resolve_dates(args: argparse.Namespace) -> List[date]:
    if args.yesterday:
        if args.date is not None or args.start_date is not None or args.end_date is not None:
            raise IngestionError(
                "--yesterday cannot be combined with --date or a date range"
            )
        return [resolve_yesterday(args.timezone)]
    return build_date_range(args.date, args.start_date, args.end_date)


def run_postgame(
    dates: Sequence[date],
    *,
    supabase_client: Any,
    mlb_client: MLBStatsClient,
    game_type: str,
    dry_run: bool,
    timeout: float,
    retries: int,
    steps: Sequence[str] = ALL_STEPS,
    schedule_chunk_days: int = 7,
) -> Dict[str, int]:
    """Run ordered postgame stages while sharing schedule and boxscore payloads."""
    if not dates:
        raise IngestionError("at least one date is required")
    if schedule_chunk_days <= 0:
        raise IngestionError("--schedule-chunk-days must be positive")

    selected = set(steps)
    totals = {
        "dates": len(dates),
        "dates_failed": 0,
        "games_upserted": 0,
        "probable_rows_inserted": 0,
        "probable_assignments_found": 0,
        "probable_assignments_existing": 0,
        "probable_assignments_missing": 0,
        "probable_games_failed": 0,
        "probable_people_failed": 0,
        "team_rows_upserted": 0,
        "pitcher_rows_upserted": 0,
        "team_games_failed": 0,
        "pitcher_games_failed": 0,
        "games_marked_processed": 0,
    }
    failed_dates: Set[date] = set()

    for chunk in chunked_dates(dates, schedule_chunk_days):
        try:
            schedule = mlb_client.fetch_schedule_range(
                chunk[0],
                chunk[-1],
                game_type,
                hydrate=POSTGAME_SCHEDULE_HYDRATION,
            )
            schedules = schedule_payloads_by_date(schedule, chunk)
        except Exception as exc:
            failed_dates.update(chunk)
            LOGGER.error(
                "start_date=%s end_date=%s source=MLB-schedule action=fail error=%s",
                chunk[0],
                chunk[-1],
                exc,
            )
            continue

        for target_date in chunk:
            payload = schedules[target_date]
            if "games" in selected:
                try:
                    summary = games_ingestion.ingest_date(
                        supabase_client,
                        target_date,
                        game_type,
                        dry_run,
                        timeout,
                        retries,
                        schedule_payload=payload,
                        venue_fetcher=mlb_client.fetch_venue,
                    )
                    totals["games_upserted"] += summary["games_upserted"]
                except Exception as exc:
                    failed_dates.add(target_date)
                    LOGGER.error(
                        "date=%s stage=games action=fail error=%s", target_date, exc
                    )
                    continue

            if "probable-recovery" in selected:
                try:
                    summary = probable_ingestion.ingest_recovery_date(
                        supabase_client,
                        target_date,
                        game_type,
                        dry_run,
                        timeout,
                        retries,
                        schedule_payload=payload,
                        person_fetcher=mlb_client.fetch_person,
                    )
                    totals["probable_rows_inserted"] += summary["rows_inserted"]
                    totals["probable_assignments_found"] += summary[
                        "assignments_found"
                    ]
                    totals["probable_assignments_existing"] += summary[
                        "assignments_existing"
                    ]
                    totals["probable_assignments_missing"] += summary[
                        "assignments_missing"
                    ]
                    totals["probable_games_failed"] += summary["games_failed"]
                    totals["probable_people_failed"] += summary["people_failed"]
                    if summary["games_failed"] or summary["people_failed"]:
                        failed_dates.add(target_date)
                except Exception as exc:
                    failed_dates.add(target_date)
                    LOGGER.error(
                        "date=%s stage=probable-recovery action=fail error=%s",
                        target_date,
                        exc,
                    )

            if "team-logs" in selected:
                try:
                    summary = team_ingestion.ingest_date(
                        supabase_client,
                        target_date,
                        game_type,
                        dry_run,
                        timeout,
                        retries,
                        schedule_payload=payload,
                        boxscore_fetcher=mlb_client.fetch_boxscore,
                    )
                    totals["team_rows_upserted"] += summary["rows_upserted"]
                    totals["team_games_failed"] += summary["games_failed"]
                    if summary["games_failed"]:
                        failed_dates.add(target_date)
                except Exception as exc:
                    failed_dates.add(target_date)
                    LOGGER.error(
                        "date=%s stage=team-logs action=fail error=%s",
                        target_date,
                        exc,
                    )

            if "pitcher-logs" in selected:
                try:
                    summary = pitcher_ingestion.ingest_date(
                        supabase_client,
                        target_date,
                        game_type,
                        dry_run,
                        timeout,
                        retries,
                        schedule_payload=payload,
                        boxscore_fetcher=mlb_client.fetch_boxscore,
                    )
                    totals["pitcher_rows_upserted"] += summary["rows_upserted"]
                    totals["pitcher_games_failed"] += summary["games_failed"]
                    totals["games_marked_processed"] += summary[
                        "games_marked_processed"
                    ]
                    if summary["games_failed"]:
                        failed_dates.add(target_date)
                except Exception as exc:
                    failed_dates.add(target_date)
                    LOGGER.error(
                        "date=%s stage=pitcher-logs action=fail error=%s",
                        target_date,
                        exc,
                    )

    totals["dates_failed"] = len(failed_dates)
    totals["mlb_requests"] = mlb_client.requests_made
    totals["mlb_cache_hits"] = mlb_client.cache_hits
    return totals


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Populate games_raw, probable_pitchers recovery rows, team_game_logs, "
            "and pitcher_game_logs from one shared MLB schedule/boxscore run."
        )
    )
    parser.add_argument("--yesterday", action="store_true")
    parser.add_argument("--date", type=parse_iso_date)
    parser.add_argument("--start-date", type=parse_iso_date)
    parser.add_argument("--end-date", type=parse_iso_date)
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--game-type", default="R")
    parser.add_argument("--steps", type=parse_steps, default=ALL_STEPS)
    parser.add_argument("--schedule-chunk-days", type=int, default=7)
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
        dates = resolve_dates(args)
        validate_runtime_options(args.timeout, args.retries)
        if args.schedule_chunk_days <= 0:
            raise IngestionError("--schedule-chunk-days must be positive")
        client = None if args.dry_run else create_supabase_client(args.env_file)
        mlb_client = MLBStatsClient(args.timeout, args.retries)
        LOGGER.info(
            "start dates=%s..%s timezone=%s steps=%s dry_run=%s",
            dates[0],
            dates[-1],
            args.timezone,
            ",".join(args.steps),
            args.dry_run,
        )
        totals = run_postgame(
            dates,
            supabase_client=client,
            mlb_client=mlb_client,
            game_type=args.game_type,
            dry_run=args.dry_run,
            timeout=args.timeout,
            retries=args.retries,
            steps=args.steps,
            schedule_chunk_days=args.schedule_chunk_days,
        )
    except (IngestionError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 1
    except Exception as exc:
        LOGGER.error("postgame ingestion failed: %s", exc)
        LOGGER.debug("unexpected ingestion failure", exc_info=True)
        return 1

    LOGGER.info(
        "complete dates=%s dates_failed=%s games_upserted=%s "
        "probable_assignments_found=%s probable_assignments_existing=%s "
        "probable_assignments_missing=%s probable_rows_inserted=%s "
        "probable_games_failed=%s "
        "probable_people_failed=%s "
        "team_rows_upserted=%s pitcher_rows_upserted=%s "
        "games_marked_processed=%s team_games_failed=%s "
        "pitcher_games_failed=%s mlb_requests=%s mlb_cache_hits=%s dry_run=%s",
        totals["dates"],
        totals["dates_failed"],
        totals["games_upserted"],
        totals["probable_assignments_found"],
        totals["probable_assignments_existing"],
        totals["probable_assignments_missing"],
        totals["probable_rows_inserted"],
        totals["probable_games_failed"],
        totals["probable_people_failed"],
        totals["team_rows_upserted"],
        totals["pitcher_rows_upserted"],
        totals["games_marked_processed"],
        totals["team_games_failed"],
        totals["pitcher_games_failed"],
        totals["mlb_requests"],
        totals["mlb_cache_hits"],
        args.dry_run,
    )
    return 1 if totals["dates_failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
