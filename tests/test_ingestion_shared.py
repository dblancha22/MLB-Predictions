import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from scripts.ingestion.common import IngestionError, resolve_today, resolve_yesterday
from scripts.ingestion.mlb import MLBStatsClient, schedule_payloads_by_date


class DateResolutionTests(unittest.TestCase):
    def test_today_uses_configured_timezone(self):
        now = datetime(2026, 7, 19, 1, 0, tzinfo=timezone.utc)
        self.assertEqual(
            resolve_today("America/Los_Angeles", now).isoformat(),
            "2026-07-18",
        )

    def test_yesterday_uses_configured_timezone_without_changing_source_dates(self):
        now = datetime(2026, 7, 16, 1, 0, tzinfo=timezone.utc)
        self.assertEqual(
            resolve_yesterday("America/Los_Angeles", now).isoformat(),
            "2026-07-14",
        )

    def test_unknown_timezone_is_rejected(self):
        with self.assertRaises(IngestionError):
            resolve_yesterday("Not/A-Timezone")


class MLBClientCacheTests(unittest.TestCase):
    def test_successful_boxscore_is_requested_once_per_run(self):
        client = MLBStatsClient()
        with patch(
            "scripts.ingestion.mlb.request_json", return_value={"teams": {}}
        ) as request:
            first = client.fetch_boxscore(824252)
            second = client.fetch_boxscore(824252)
        self.assertIs(first, second)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(client.requests_made, 1)
        self.assertEqual(client.cache_hits, 1)

    def test_exhausted_failure_is_not_requested_again_in_same_run(self):
        client = MLBStatsClient()
        with patch(
            "scripts.ingestion.mlb.request_json",
            side_effect=IngestionError("boxscore unavailable"),
        ) as request:
            for _ in range(2):
                with self.assertRaises(IngestionError):
                    client.fetch_boxscore(824252)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(client.requests_made, 1)
        self.assertEqual(client.cache_hits, 1)

    def test_range_schedule_keeps_each_source_date_separate(self):
        first = datetime(2026, 7, 10).date()
        second = datetime(2026, 7, 11).date()
        payload = {
            "dates": [
                {"date": first.isoformat(), "games": [{"gamePk": 1}]},
                {"date": second.isoformat(), "games": [{"gamePk": 2}]},
            ]
        }
        split = schedule_payloads_by_date(payload, (first, second))
        self.assertEqual(split[first]["dates"][0]["games"][0]["gamePk"], 1)
        self.assertEqual(split[second]["dates"][0]["games"][0]["gamePk"], 2)

    def test_schedule_hydration_is_part_of_the_request_contract(self):
        client = MLBStatsClient()
        with patch(
            "scripts.ingestion.mlb.request_json", return_value={"dates": []}
        ) as request:
            client.fetch_schedule_range(
                datetime(2026, 7, 18).date(),
                datetime(2026, 7, 18).date(),
                hydrate="probablePitcher,venue,team",
            )
        self.assertEqual(
            request.call_args.args[1]["hydrate"],
            "probablePitcher,venue,team",
        )


if __name__ == "__main__":
    unittest.main()
