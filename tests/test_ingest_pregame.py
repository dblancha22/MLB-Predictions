import argparse
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from scripts.ingest_pregame import ALL_STEPS, parse_steps, resolve_dates, run_pregame
from scripts.ingestion.common import IngestionError
from scripts.ingestion.mlb import MLBStatsClient


def args(**overrides):
    values = {
        "today": False,
        "date": None,
        "start_date": None,
        "end_date": None,
        "timezone": "America/Los_Angeles",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class PregameDateResolutionTests(unittest.TestCase):
    def test_step_parser_deduplicates_and_rejects_unknown_steps(self):
        self.assertEqual(
            parse_steps("games,probable-pitchers,games"),
            ALL_STEPS,
        )
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_steps("team-features")

    def test_today_uses_configured_timezone(self):
        now = datetime(2026, 7, 19, 1, 0, tzinfo=timezone.utc)
        with patch(
            "scripts.ingest_pregame.resolve_today", return_value=now.date()
        ) as resolve:
            self.assertEqual(
                resolve_dates(args(today=True, timezone="America/Los_Angeles")),
                [now.date()],
            )
        resolve.assert_called_once_with("America/Los_Angeles")

    def test_today_cannot_be_combined_with_explicit_date(self):
        with self.assertRaises(IngestionError):
            resolve_dates(args(today=True, date=date(2026, 7, 18)))


class PregameOrchestrationTests(unittest.TestCase):
    def test_stages_share_one_combined_schedule_payload(self):
        target = date(2026, 7, 18)
        schedule = {
            "dates": [{"date": target.isoformat(), "games": [{"gamePk": 1}]}]
        }
        seen_payloads = []

        def games_stage(*_args, **kwargs):
            seen_payloads.append(kwargs["schedule_payload"])
            self.assertIsNotNone(kwargs["venue_fetcher"])
            return {"games_upserted": 1}

        def probable_stage(*_args, **kwargs):
            seen_payloads.append(kwargs["schedule_payload"])
            self.assertIsNotNone(kwargs["person_fetcher"])
            return {
                "rows_upserted": 2,
                "rows_deleted": 0,
                "games_failed": 0,
                "people_failed": 0,
            }

        mlb = MLBStatsClient()
        with patch(
            "scripts.ingestion.mlb.request_json", return_value=schedule
        ) as request, patch(
            "scripts.ingest_pregame.games_ingestion.ingest_date",
            side_effect=games_stage,
        ), patch(
            "scripts.ingest_pregame.probable_ingestion.ingest_date",
            side_effect=probable_stage,
        ):
            totals = run_pregame(
                (target,),
                supabase_client=None,
                mlb_client=mlb,
                game_type="R",
                dry_run=True,
                timeout=30.0,
                retries=2,
                steps=ALL_STEPS,
            )

        self.assertEqual(request.call_count, 1)
        self.assertEqual(
            request.call_args.args[1]["hydrate"],
            "probablePitcher,venue,team",
        )
        self.assertIs(seen_payloads[0], seen_payloads[1])
        self.assertEqual(totals["games_upserted"], 1)
        self.assertEqual(totals["probable_rows_upserted"], 2)
        self.assertEqual(totals["dates_failed"], 0)
        self.assertEqual(totals["mlb_requests"], 1)

    def test_games_failure_skips_probable_stage_for_date(self):
        target = date(2026, 7, 18)
        schedule = {"dates": [{"date": target.isoformat(), "games": []}]}
        mlb = MLBStatsClient()
        with patch(
            "scripts.ingestion.mlb.request_json", return_value=schedule
        ), patch(
            "scripts.ingest_pregame.games_ingestion.ingest_date",
            side_effect=RuntimeError("games write failed"),
        ), patch(
            "scripts.ingest_pregame.probable_ingestion.ingest_date"
        ) as probable_stage:
            totals = run_pregame(
                (target,),
                supabase_client=None,
                mlb_client=mlb,
                game_type="R",
                dry_run=True,
                timeout=30.0,
                retries=2,
            )
        probable_stage.assert_not_called()
        self.assertEqual(totals["dates_failed"], 1)

    def test_probable_only_recovery_does_not_run_games_stage(self):
        target = date(2026, 7, 18)
        schedule = {"dates": [{"date": target.isoformat(), "games": []}]}
        mlb = MLBStatsClient()
        with patch(
            "scripts.ingestion.mlb.request_json", return_value=schedule
        ), patch(
            "scripts.ingest_pregame.games_ingestion.ingest_date"
        ) as games_stage, patch(
            "scripts.ingest_pregame.probable_ingestion.ingest_date",
            return_value={
                "rows_upserted": 0,
                "rows_deleted": 0,
                "games_failed": 0,
                "people_failed": 0,
            },
        ) as probable_stage:
            totals = run_pregame(
                (target,),
                supabase_client=None,
                mlb_client=mlb,
                game_type="R",
                dry_run=True,
                timeout=30.0,
                retries=2,
                steps=("probable-pitchers",),
            )
        games_stage.assert_not_called()
        probable_stage.assert_called_once()
        self.assertEqual(totals["dates_failed"], 0)

    def test_probable_metadata_failure_marks_run_incomplete(self):
        target = date(2026, 7, 18)
        schedule = {"dates": [{"date": target.isoformat(), "games": []}]}
        mlb = MLBStatsClient()
        with patch(
            "scripts.ingestion.mlb.request_json", return_value=schedule
        ), patch(
            "scripts.ingest_pregame.games_ingestion.ingest_date",
            return_value={"games_upserted": 0},
        ), patch(
            "scripts.ingest_pregame.probable_ingestion.ingest_date",
            return_value={
                "rows_upserted": 1,
                "rows_deleted": 0,
                "games_failed": 0,
                "people_failed": 1,
            },
        ):
            totals = run_pregame(
                (target,),
                supabase_client=None,
                mlb_client=mlb,
                game_type="R",
                dry_run=True,
                timeout=30.0,
                retries=2,
            )
        self.assertEqual(totals["people_failed"], 1)
        self.assertEqual(totals["dates_failed"], 1)


if __name__ == "__main__":
    unittest.main()
