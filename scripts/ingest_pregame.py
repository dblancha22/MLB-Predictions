#!/usr/bin/env python3
"""Populate same-day pregame MLB schedule and probable-pitcher raw tables."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

try:
    from scripts import ingest_games_raw as games_ingestion
    from scripts import ingest_pregame_team_features as feature_ingestion
    from scripts import ingest_probable_pitchers as probable_ingestion
    from scripts.ingestion.common import (
        DEFAULT_ENV_FILE,
        DEFAULT_TIMEZONE,
        IngestionError,
        build_date_range,
        create_supabase_client,
        parse_iso_date,
        resolve_today,
        validate_runtime_options,
    )
    from scripts.ingestion.mlb import MLBStatsClient, schedule_payloads_by_date
except ModuleNotFoundError:  # Support direct `python scripts/...` execution.
    import ingest_games_raw as games_ingestion  # type: ignore[no-redef]
    import ingest_pregame_team_features as feature_ingestion  # type: ignore[no-redef]
    import ingest_probable_pitchers as probable_ingestion  # type: ignore[no-redef]
    from ingestion.common import (  # type: ignore[no-redef]
        DEFAULT_ENV_FILE,
        DEFAULT_TIMEZONE,
        IngestionError,
        build_date_range,
        create_supabase_client,
        parse_iso_date,
        resolve_today,
        validate_runtime_options,
    )
    from ingestion.mlb import (  # type: ignore[no-redef]
        MLBStatsClient,
        schedule_payloads_by_date,
    )


LOGGER = logging.getLogger("ingest_pregame")
ALL_STEPS = ("games", "probable-pitchers", "team-features")
PREGAME_SCHEDULE_HYDRATION = "probablePitcher,venue,team"


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
    if args.today:
        if (
            args.date is not None
            or args.start_date is not None
            or args.end_date is not None
        ):
            raise IngestionError("--today cannot be combined with --date or a date range")
        return [resolve_today(args.timezone)]
    return build_date_range(args.date, args.start_date, args.end_date)


def run_pregame(
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
    """Run ordered pregame stages from one shared hydrated schedule payload."""
    if not dates:
        raise IngestionError("at least one date is required")
    if schedule_chunk_days <= 0:
        raise IngestionError("--schedule-chunk-days must be positive")

    selected = set(steps)
    totals = {
        "dates": len(dates),
        "dates_failed": 0,
        "games_upserted": 0,
        "probable_rows_upserted": 0,
        "probable_rows_deleted": 0,
        "probable_games_failed": 0,
        "people_failed": 0,
        "feature_games_skipped_started": 0,
        "feature_games_failed": 0,
        "feature_rows_ready": 0,
        "feature_rows_upserted": 0,
    }
    failed_dates: Set[date] = set()

    for chunk in chunked_dates(dates, schedule_chunk_days):
        try:
            schedule = mlb_client.fetch_schedule_range(
                chunk[0],
                chunk[-1],
                game_type,
                hydrate=PREGAME_SCHEDULE_HYDRATION,
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
            dependency_failed = False
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
                    dependency_failed = True
                    LOGGER.error(
                        "date=%s stage=games action=fail error=%s", target_date, exc
                    )
                    continue

            if "probable-pitchers" in selected:
                try:
                    summary = probable_ingestion.ingest_date(
                        supabase_client,
                        target_date,
                        game_type,
                        dry_run,
                        timeout,
                        retries,
                        schedule_payload=payload,
                        person_fetcher=mlb_client.fetch_person,
                    )
                    totals["probable_rows_upserted"] += summary["rows_upserted"]
                    totals["probable_rows_deleted"] += summary["rows_deleted"]
                    totals["probable_games_failed"] += summary["games_failed"]
                    totals["people_failed"] += summary["people_failed"]
                    if summary["games_failed"] or summary["people_failed"]:
                        failed_dates.add(target_date)
                        dependency_failed = True
                except Exception as exc:
                    failed_dates.add(target_date)
                    dependency_failed = True
                    LOGGER.error(
                        "date=%s stage=probable-pitchers action=fail error=%s",
                        target_date,
                        exc,
                    )

            if "team-features" in selected:
                if dependency_failed:
                    LOGGER.warning(
                        "date=%s stage=team-features action=skip "
                        "reason=pregame-dependency-failed",
                        target_date,
                    )
                    continue
                try:
                    summary = feature_ingestion.ingest_date(
                        supabase_client,
                        target_date,
                        game_type,
                        dry_run,
                        mode=feature_ingestion.MODE_LIVE,
                    )
                    totals["feature_games_skipped_started"] += summary[
                        "games_skipped_started"
                    ]
                    totals["feature_games_failed"] += summary["games_failed"]
                    totals["feature_rows_ready"] += summary["rows_ready"]
                    totals["feature_rows_upserted"] += summary["rows_upserted"]
                    if summary["games_failed"]:
                        failed_dates.add(target_date)
                except Exception as exc:
                    failed_dates.add(target_date)
                    totals["feature_games_failed"] += 1
                    LOGGER.error(
                        "date=%s stage=team-features action=fail error=%s",
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
            "Populate same-day games_raw and probable_pitchers from one shared "
            "MLB schedule run, then build pregame_team_features from Supabase."
        )
    )
    parser.add_argument("--today", action="store_true")
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
        client = (
            create_supabase_client(args.env_file)
            if not args.dry_run or "team-features" in args.steps
            else None
        )
        mlb_client = MLBStatsClient(args.timeout, args.retries)
        LOGGER.info(
            "start dates=%s..%s timezone=%s steps=%s dry_run=%s",
            dates[0],
            dates[-1],
            args.timezone,
            ",".join(args.steps),
            args.dry_run,
        )
        totals = run_pregame(
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
        LOGGER.error("pregame ingestion failed: %s", exc)
        LOGGER.debug("unexpected ingestion failure", exc_info=True)
        return 1

    LOGGER.info(
        "complete dates=%s dates_failed=%s games_upserted=%s "
        "probable_rows_upserted=%s probable_rows_deleted=%s "
        "probable_games_failed=%s people_failed=%s mlb_requests=%s "
        "feature_games_skipped_started=%s feature_games_failed=%s "
        "feature_rows_ready=%s feature_rows_upserted=%s mlb_cache_hits=%s dry_run=%s",
        totals["dates"],
        totals["dates_failed"],
        totals["games_upserted"],
        totals["probable_rows_upserted"],
        totals["probable_rows_deleted"],
        totals["probable_games_failed"],
        totals["people_failed"],
        totals["mlb_requests"],
        totals["feature_games_skipped_started"],
        totals["feature_games_failed"],
        totals["feature_rows_ready"],
        totals["feature_rows_upserted"],
        totals["mlb_cache_hits"],
        args.dry_run,
    )
    return 1 if totals["dates_failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
