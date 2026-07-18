import unittest
from datetime import date
from unittest.mock import patch

from scripts.ingest_postgame import ALL_STEPS, run_postgame
from scripts.ingestion.mlb import MLBStatsClient


class PostgameOrchestrationTests(unittest.TestCase):
    def test_range_uses_one_schedule_and_one_boxscore_per_unique_game(self):
        dates = (date(2026, 6, 16), date(2026, 6, 17))
        schedule = {
            "dates": [
                {"date": dates[0].isoformat(), "games": [{"gamePk": 824912}]},
                {"date": dates[1].isoformat(), "games": [{"gamePk": 824912}]},
            ]
        }

        def source(url, _params, _timeout, _retries, *_logger):
            return schedule if url.endswith("/schedule") else {"teams": {}}

        def games_stage(*_args, **_kwargs):
            return {"games_upserted": 1}

        def team_stage(*_args, **kwargs):
            kwargs["boxscore_fetcher"](824912, 30.0, 2)
            return {"rows_upserted": 2, "games_failed": 0}

        def pitcher_stage(*_args, **kwargs):
            kwargs["boxscore_fetcher"](824912, 30.0, 2)
            return {
                "rows_upserted": 4,
                "games_failed": 0,
                "games_marked_processed": 0,
            }

        mlb = MLBStatsClient()
        with patch("scripts.ingestion.mlb.request_json", side_effect=source) as request, patch(
            "scripts.ingest_postgame.games_ingestion.ingest_date",
            side_effect=games_stage,
        ), patch(
            "scripts.ingest_postgame.team_ingestion.ingest_date",
            side_effect=team_stage,
        ), patch(
            "scripts.ingest_postgame.pitcher_ingestion.ingest_date",
            side_effect=pitcher_stage,
        ):
            totals = run_postgame(
                dates,
                supabase_client=None,
                mlb_client=mlb,
                game_type="R",
                dry_run=True,
                timeout=30.0,
                retries=2,
                steps=ALL_STEPS,
                schedule_chunk_days=7,
            )

        self.assertEqual(request.call_count, 2)
        self.assertEqual(totals["mlb_requests"], 2)
        self.assertEqual(totals["mlb_cache_hits"], 3)
        self.assertEqual(totals["dates_failed"], 0)

    def test_games_stage_failure_skips_dependent_stages_for_that_date(self):
        target = date(2026, 7, 10)
        schedule = {"dates": [{"date": target.isoformat(), "games": []}]}
        mlb = MLBStatsClient()
        with patch(
            "scripts.ingestion.mlb.request_json", return_value=schedule
        ), patch(
            "scripts.ingest_postgame.games_ingestion.ingest_date",
            side_effect=RuntimeError("games write failed"),
        ), patch(
            "scripts.ingest_postgame.team_ingestion.ingest_date"
        ) as team_stage, patch(
            "scripts.ingest_postgame.pitcher_ingestion.ingest_date"
        ) as pitcher_stage:
            totals = run_postgame(
                (target,),
                supabase_client=None,
                mlb_client=mlb,
                game_type="R",
                dry_run=True,
                timeout=30.0,
                retries=2,
            )
        team_stage.assert_not_called()
        pitcher_stage.assert_not_called()
        self.assertEqual(totals["dates_failed"], 1)


if __name__ == "__main__":
    unittest.main()
