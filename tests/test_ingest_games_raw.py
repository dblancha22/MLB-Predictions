import unittest
from datetime import date
from unittest.mock import patch

from scripts.ingest_games_raw import (
    IngestionError,
    build_date_range,
    extract_dependencies,
    effective_game_timestamp,
    flatten_schedule,
    fetch_venue,
    ingest_date,
    insert_missing_rows,
    insert_missing_enriched_venues,
    normalize_supabase_url,
    should_skip_cross_date_postponement,
    transform_game,
    transform_enriched_venue,
    upsert_games,
    utc_timestamptz,
)


INGESTED_AT = "2026-07-14T12:00:00+00:00"


def sample_game(
    *,
    game_id=824252,
    detailed_state="Final",
    status_code="F",
    abstract_state="Final",
    include_scores=True,
    venue=True,
):
    home = {
        "team": {
            "id": 116,
            "name": "Detroit Tigers",
            "teamName": "Tigers",
            "franchiseName": "Detroit",
            "abbreviation": "DET",
            "teamCode": "det",
            "fileCode": "det",
            "locationName": "Detroit",
            "league": {"id": 103},
            "division": {"id": 201},
            "sport": {"id": 1},
            "firstYearOfPlay": "1901",
            "active": True,
            "venue": {"id": 2394},
        }
    }
    away = {
        "team": {
            "id": 141,
            "name": "Toronto Blue Jays",
            "teamName": "Blue Jays",
            "franchiseName": "Toronto",
            "abbreviation": "TOR",
            "teamCode": "tor",
            "fileCode": "tor",
            "locationName": "Toronto",
            "league": {"id": 103},
            "division": {"id": 201},
            "sport": {"id": 1},
            "firstYearOfPlay": "1977",
            "active": True,
            "venue": {"id": 14},
        }
    }
    if include_scores:
        home["score"] = 5
        away["score"] = 3

    game = {
        "gamePk": game_id,
        "gameDate": "2026-07-10T22:40:00Z",
        "officialDate": "2026-07-10",
        "gameType": "R",
        "season": "2026",
        "dayNight": "night",
        "doubleHeader": "N",
        "gameNumber": 1,
        "seriesGameNumber": 2,
        "gamesInSeries": 3,
        "status": {
            "abstractGameState": abstract_state,
            "detailedState": detailed_state,
            "statusCode": status_code,
        },
        "teams": {"home": home, "away": away},
    }
    if venue:
        game["venue"] = {"id": 2394, "name": "Comerica Park"}
    return game


class GameTransformTests(unittest.TestCase):
    def test_final_game_maps_expected_fields_and_scores(self):
        row = transform_game(sample_game(), INGESTED_AT)
        self.assertEqual(row["game_id"], 824252)
        self.assertEqual(row["game_date"], "2026-07-10")
        self.assertEqual(row["scheduled_time_utc"], "2026-07-10T22:40:00+00:00")
        self.assertEqual(row["doubleheader_code"], "N")
        self.assertEqual(row["game_number"], 1)
        self.assertEqual(row["series_game_number"], 2)
        self.assertEqual(row["games_in_series"], 3)
        self.assertEqual(row["status"], "Final")
        self.assertEqual(row["home_score"], 5)
        self.assertEqual(row["away_score"], 3)
        self.assertNotIn("pitcher_logs_processed", row)

    def test_postponed_uses_detailed_status_and_omits_scores(self):
        game = sample_game(detailed_state="Postponed", status_code="DI")
        game["officialDate"] = "2026-07-11"
        row = transform_game(game, INGESTED_AT, date(2026, 7, 10))
        self.assertEqual(row["status"], "Postponed")
        self.assertEqual(row["game_date"], "2026-07-10")
        self.assertNotIn("home_score", row)
        self.assertNotIn("away_score", row)

    def test_cross_date_postponement_is_skipped(self):
        game = sample_game(detailed_state="Postponed", status_code="DI")
        game["rescheduleGameDate"] = "2026-07-11"
        game["rescheduleDate"] = "2026-07-11T16:05:00Z"
        self.assertTrue(
            should_skip_cross_date_postponement(game, date(2026, 7, 10))
        )

    def test_same_day_postponement_uses_replacement_time(self):
        game = sample_game(detailed_state="Postponed", status_code="DI")
        game["rescheduleGameDate"] = "2026-07-10"
        game["rescheduleDate"] = "2026-07-11T00:40:00Z"
        schedule_date = date(2026, 7, 10)
        self.assertFalse(
            should_skip_cross_date_postponement(game, schedule_date)
        )
        self.assertEqual(
            effective_game_timestamp(game, schedule_date),
            "2026-07-11T00:40:00Z",
        )
        row = transform_game(game, INGESTED_AT, schedule_date)
        self.assertEqual(row["game_date"], "2026-07-10")
        self.assertEqual(row["scheduled_time_utc"], "2026-07-11T00:40:00+00:00")

    def test_postponement_without_new_date_is_retained(self):
        game = sample_game(detailed_state="Postponed", status_code="DI")
        schedule_date = date(2026, 7, 10)
        self.assertFalse(
            should_skip_cross_date_postponement(game, schedule_date)
        )
        self.assertEqual(
            effective_game_timestamp(game, schedule_date), game["gameDate"]
        )

    def test_resumed_occurrence_preserves_original_date_time_and_metadata(self):
        game = sample_game()
        game["gameDate"] = "2026-07-11T18:00:00Z"
        game["officialDate"] = "2026-07-10"
        game["resumedFrom"] = "2026-07-10T22:40:00Z"
        game["resumedFromDate"] = "2026-07-10"
        game["seriesGameNumber"] = 2
        game["gamesInSeries"] = 2

        row = transform_game(game, INGESTED_AT, date(2026, 7, 11))

        self.assertEqual(row["game_date"], "2026-07-10")
        self.assertEqual(row["scheduled_time_utc"], "2026-07-10T22:40:00+00:00")
        self.assertNotIn("doubleheader_code", row)
        self.assertNotIn("game_number", row)
        self.assertNotIn("series_game_number", row)
        self.assertNotIn("games_in_series", row)
        self.assertTrue(row["_resumed_occurrence"])

    def test_scheduled_game_omits_scores(self):
        row = transform_game(
            sample_game(
                detailed_state="Scheduled",
                status_code="S",
                abstract_state="Preview",
                include_scores=False,
            ),
            INGESTED_AT,
        )
        self.assertEqual(row["status"], "Scheduled")
        self.assertNotIn("home_score", row)

    def test_missing_venue_is_allowed(self):
        row = transform_game(sample_game(venue=False), INGESTED_AT)
        self.assertIsNone(row["venue_id"])

    def test_dependency_rows_are_deduplicated(self):
        games = [sample_game(), sample_game(game_id=824253)]
        teams, venues = extract_dependencies(games, INGESTED_AT)
        self.assertEqual({row["team_id"] for row in teams}, {116, 141})
        self.assertEqual(
            {row["venue_id"] for row in venues},
            {14, 2394},
        )

    def test_flatten_schedule_handles_no_game_date(self):
        self.assertEqual(flatten_schedule({"dates": []}), [])

    def test_utc_timestamp_normalizes_offsets(self):
        self.assertEqual(
            utc_timestamptz("2026-07-10T18:40:00-04:00"),
            "2026-07-10T22:40:00+00:00",
        )

    def test_optional_series_metadata_is_nullable(self):
        game = sample_game()
        for field in (
            "doubleHeader",
            "gameNumber",
            "seriesGameNumber",
            "gamesInSeries",
        ):
            game.pop(field)
        row = transform_game(game, INGESTED_AT)
        self.assertIsNone(row["doubleheader_code"])
        self.assertIsNone(row["game_number"])
        self.assertIsNone(row["series_game_number"])
        self.assertIsNone(row["games_in_series"])

    def test_enriched_venue_maps_available_location_fields(self):
        row = transform_enriched_venue(
            {
                "id": 31,
                "name": "PNC Park",
                "location": {
                    "city": "Pittsburgh",
                    "state": "Pennsylvania",
                    "stateAbbrev": "PA",
                    "country": "USA",
                    "defaultCoordinates": {
                        "latitude": 40.446904,
                        "longitude": -80.005753,
                    },
                    "elevation": 780,
                    "azimuthAngle": 116.0,
                },
            }
        )
        self.assertEqual(
            row,
            {
                "venue_id": 31,
                "name": "PNC Park",
                "city": "Pittsburgh",
                "state": "PA",
                "country": "USA",
                "latitude": 40.446904,
                "longitude": -80.005753,
                "altitude_ft": 780.0,
                "field_orientation_degrees": 116.0,
            },
        )

    def test_enriched_venue_allows_missing_optional_location_fields(self):
        row = transform_enriched_venue({"id": 999, "name": "Test Park"})
        self.assertEqual(row["venue_id"], 999)
        self.assertIsNone(row["city"])
        self.assertIsNone(row["latitude"])
        self.assertIsNone(row["field_orientation_degrees"])


class DateRangeTests(unittest.TestCase):
    def test_single_date(self):
        target = date(2026, 7, 10)
        self.assertEqual(build_date_range(target, None, None), [target])

    def test_inclusive_date_range(self):
        self.assertEqual(
            build_date_range(None, date(2026, 7, 10), date(2026, 7, 12)),
            [date(2026, 7, 10), date(2026, 7, 11), date(2026, 7, 12)],
        )

    def test_reversed_range_fails(self):
        with self.assertRaises(IngestionError):
            build_date_range(None, date(2026, 7, 12), date(2026, 7, 10))


class ConfigurationTests(unittest.TestCase):
    def test_supabase_base_url_is_unchanged(self):
        self.assertEqual(
            normalize_supabase_url("https://example.supabase.co"),
            "https://example.supabase.co",
        )

    def test_legacy_rest_url_is_normalized(self):
        self.assertEqual(
            normalize_supabase_url("https://example.supabase.co/rest/v1/"),
            "https://example.supabase.co",
        )

    def test_unknown_supabase_path_is_rejected(self):
        with self.assertRaises(IngestionError):
            normalize_supabase_url("https://example.supabase.co/other")


class FakeResponse:
    def __init__(self, data=None):
        self.data = data


class FakeQuery:
    def __init__(self, client, table):
        self.client = client
        self.table = table

    def select(self, column):
        self.client.calls.append(("select", self.table, column))
        return self

    def in_(self, column, values):
        self.client.calls.append(("in", self.table, column, values))
        return self

    def insert(self, rows):
        self.client.calls.append(("insert", self.table, rows))
        return self

    def upsert(self, rows, **kwargs):
        self.client.calls.append(("upsert", self.table, rows, kwargs))
        return self

    def execute(self):
        if self.client.next_select_data is not None:
            data = self.client.next_select_data
            self.client.next_select_data = None
            return FakeResponse(data)
        return FakeResponse([])


class FakeClient:
    def __init__(self, existing=None):
        self.calls = []
        self.next_select_data = existing

    def table(self, name):
        return FakeQuery(self, name)


class DatabaseWriteTests(unittest.TestCase):
    def test_dimension_insert_only_writes_missing_rows(self):
        client = FakeClient(existing=[{"team_id": 116}])
        inserted = insert_missing_rows(
            client,
            "teams",
            "team_id",
            [{"team_id": 116}, {"team_id": 141}],
        )
        self.assertEqual(inserted, 1)
        inserts = [call for call in client.calls if call[0] == "insert"]
        self.assertEqual(inserts, [("insert", "teams", [{"team_id": 141}])])

    def test_games_are_batched_by_score_presence(self):
        client = FakeClient()
        rows = [
            {"game_id": 1, "status": "Scheduled"},
            {"game_id": 2, "status": "Final", "home_score": 5, "away_score": 3},
        ]
        self.assertEqual(upsert_games(client, rows), 2)
        upserts = [call for call in client.calls if call[0] == "upsert"]
        self.assertEqual(len(upserts), 2)
        self.assertNotIn("home_score", upserts[0][2][0])
        self.assertEqual(upserts[1][2][0]["home_score"], 5)
        for call in upserts:
            self.assertEqual(
                call[3], {"on_conflict": "game_id", "default_to_null": False}
            )

    def test_resumed_game_explicitly_preserves_existing_schedule_metadata(self):
        client = FakeClient(
            existing=[
                {
                    "game_id": 824912,
                    "day_night": "night",
                    "doubleheader_code": "N",
                    "game_number": 1,
                    "series_game_number": 1,
                    "games_in_series": 3,
                }
            ]
        )
        row = {
            "game_id": 824912,
            "status": "Final",
            "home_score": 2,
            "away_score": 7,
            "_resumed_occurrence": True,
        }

        self.assertEqual(upsert_games(client, [row]), 1)

        upsert = next(call for call in client.calls if call[0] == "upsert")
        written = upsert[2][0]
        self.assertNotIn("_resumed_occurrence", written)
        self.assertEqual(written["doubleheader_code"], "N")
        self.assertEqual(written["game_number"], 1)
        self.assertEqual(written["series_game_number"], 1)
        self.assertEqual(written["games_in_series"], 3)

    def test_existing_venue_does_not_trigger_mlb_lookup(self):
        client = FakeClient(existing=[{"venue_id": 31}])
        with patch("scripts.ingest_games_raw.fetch_venue") as fetch_mock:
            inserted = insert_missing_enriched_venues(
                client,
                [{"venue_id": 31, "name": "PNC Park"}],
                30.0,
                2,
            )
        self.assertEqual(inserted, 0)
        fetch_mock.assert_not_called()
        self.assertFalse(any(call[0] == "insert" for call in client.calls))

    def test_missing_venue_is_enriched_and_inserted(self):
        client = FakeClient(existing=[])
        source_venue = {
            "id": 31,
            "name": "PNC Park",
            "location": {
                "city": "Pittsburgh",
                "stateAbbrev": "PA",
                "country": "USA",
                "defaultCoordinates": {
                    "latitude": 40.446904,
                    "longitude": -80.005753,
                },
                "elevation": 780,
                "azimuthAngle": 116,
            },
        }
        with patch(
            "scripts.ingest_games_raw.fetch_venue", return_value=source_venue
        ) as fetch_mock:
            inserted = insert_missing_enriched_venues(
                client,
                [{"venue_id": 31, "name": "PNC Park"}],
                20.0,
                1,
            )
        self.assertEqual(inserted, 1)
        fetch_mock.assert_called_once_with(31, 20.0, 1)
        inserts = [call for call in client.calls if call[0] == "insert"]
        self.assertEqual(inserts[0][1], "venues")
        self.assertEqual(inserts[0][2][0]["city"], "Pittsburgh")

    def test_fetch_venue_validates_requested_id(self):
        with patch(
            "scripts.ingest_games_raw._request_json",
            return_value={"venues": [{"id": 32, "name": "Wrong Park"}]},
        ):
            with self.assertRaises(IngestionError):
                fetch_venue(31)

    def test_fetch_venue_calls_documented_endpoint(self):
        source_venue = {"id": 31, "name": "PNC Park"}
        with patch(
            "scripts.ingest_games_raw._request_json",
            return_value={"venues": [source_venue]},
        ) as request_mock:
            venue = fetch_venue(31, timeout=12.0, retries=1)
        self.assertEqual(venue, source_venue)
        request_mock.assert_called_once_with(
            "https://statsapi.mlb.com/api/v1/venues/31",
            {"hydrate": "location"},
            12.0,
            1,
        )

    def test_ingest_summary_counts_cross_date_skip(self):
        kept = sample_game(game_id=1)
        skipped = sample_game(
            game_id=2, detailed_state="Postponed", status_code="DI"
        )
        skipped["rescheduleGameDate"] = "2026-07-11"
        skipped["rescheduleDate"] = "2026-07-11T16:05:00Z"
        payload = {"dates": [{"games": [kept, skipped]}]}
        with patch("scripts.ingest_games_raw.fetch_schedule", return_value=payload):
            summary = ingest_date(
                None,
                date(2026, 7, 10),
                "R",
                True,
                30.0,
                2,
            )
        self.assertEqual(summary["games_found"], 2)
        self.assertEqual(summary["games_skipped"], 1)
        self.assertEqual(summary["games_upserted"], 0)


if __name__ == "__main__":
    unittest.main()
