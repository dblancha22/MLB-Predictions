import unittest
from datetime import date
from unittest.mock import Mock, patch

from scripts.ingest_probable_pitchers import (
    IngestionError,
    build_date_range,
    extract_pitch_hand,
    fetch_person,
    fetch_schedule,
    ingest_date,
    pregame_games,
    sync_probable_pitchers,
    transform_assignment_slots,
)


UPDATED_AT = "2026-07-14T12:00:00+00:00"


def sample_game(
    game_id=824766,
    abstract_state="Preview",
    home_probable=True,
    away_probable=True,
):
    home = {"team": {"id": 111}}
    away = {"team": {"id": 139}}
    if home_probable:
        home["probablePitcher"] = {
            "id": 605483,
            "fullName": "Chris Sale",
            "link": "/api/v1/people/605483",
        }
    if away_probable:
        away["probablePitcher"] = {
            "id": 643377,
            "fullName": "Griffin Jax",
            "link": "/api/v1/people/643377",
        }
    return {
        "gamePk": game_id,
        "status": {
            "abstractGameState": abstract_state,
            "codedGameState": "S" if abstract_state == "Preview" else "I",
            "detailedState": "Scheduled" if abstract_state == "Preview" else "In Progress",
        },
        "teams": {"home": home, "away": away},
    }


def person_payload(pitcher_id, code="R"):
    person = {"id": pitcher_id, "fullName": "Pitcher"}
    if code is not None:
        person["pitchHand"] = {"code": code, "description": "Right"}
    return {"people": [person]}


class TransformTests(unittest.TestCase):
    def test_pregame_filter_is_strict_and_deduplicates_game_id(self):
        first = sample_game()
        duplicate = sample_game()
        live = sample_game(game_id=2, abstract_state="Live")
        self.assertEqual(pregame_games([first, live, duplicate]), [duplicate])

    def test_two_announced_pitchers_map_to_two_rows(self):
        rows, missing = transform_assignment_slots(sample_game(), UPDATED_AT)
        self.assertEqual(len(rows), 2)
        self.assertEqual(missing, set())
        self.assertEqual(
            rows[0],
            {
                "game_id": 824766,
                "team_id": 111,
                "pitcher_id": 605483,
                "pitch_hand": None,
                "full_name": "Chris Sale",
                "updated_at": UPDATED_AT,
            },
        )

    def test_missing_probable_becomes_clear_key_not_null_row(self):
        rows, missing = transform_assignment_slots(
            sample_game(home_probable=False), UPDATED_AT
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(missing, {(824766, 111)})
        self.assertEqual(rows[0]["team_id"], 139)

    def test_both_missing_probables_produce_two_clear_keys(self):
        rows, missing = transform_assignment_slots(
            sample_game(home_probable=False, away_probable=False), UPDATED_AT
        )
        self.assertEqual(rows, [])
        self.assertEqual(missing, {(824766, 111), (824766, 139)})

    def test_malformed_probable_rejects_game_instead_of_clearing(self):
        game = sample_game()
        game["teams"]["home"]["probablePitcher"] = "unknown"
        with self.assertRaises(IngestionError):
            transform_assignment_slots(game, UPDATED_AT)

    def test_pitch_hand_uses_matching_person_code(self):
        self.assertEqual(extract_pitch_hand(person_payload(643377), 643377), "R")

    def test_missing_pitch_hand_is_allowed(self):
        self.assertIsNone(extract_pitch_hand(person_payload(643377, None), 643377))

    def test_wrong_person_id_is_rejected(self):
        with self.assertRaises(IngestionError):
            extract_pitch_hand(person_payload(1), 643377)


class DateRangeTests(unittest.TestCase):
    def test_single_date(self):
        target = date(2026, 7, 17)
        self.assertEqual(build_date_range(target, None, None), [target])

    def test_inclusive_range(self):
        self.assertEqual(
            build_date_range(None, date(2026, 7, 17), date(2026, 7, 18)),
            [date(2026, 7, 17), date(2026, 7, 18)],
        )

    def test_reversed_range_fails(self):
        with self.assertRaises(IngestionError):
            build_date_range(None, date(2026, 7, 18), date(2026, 7, 17))


class FakeResponse:
    def __init__(self, data=None):
        self.data = data


class FakeQuery:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self.operation = None
        self.filters = []

    def select(self, columns):
        self.operation = "select"
        self.client.calls.append(("select", self.table, columns))
        return self

    def in_(self, column, values):
        self.client.calls.append(("in", self.table, column, values))
        return self

    def upsert(self, rows, **kwargs):
        self.operation = "upsert"
        self.client.calls.append(("upsert", self.table, rows, kwargs))
        return self

    def delete(self):
        self.operation = "delete"
        self.client.calls.append(("delete", self.table))
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        self.client.calls.append(("eq", self.table, column, value))
        return self

    def execute(self):
        if self.operation == "select" and self.table == "teams":
            return FakeResponse(self.client.teams)
        if self.operation == "select" and self.table == "probable_pitchers":
            return FakeResponse(self.client.existing_probables)
        if self.operation == "delete":
            self.client.deleted.append(tuple(self.filters))
        return FakeResponse([])


class FakeClient:
    def __init__(self, teams=None, existing_probables=None):
        self.teams = teams or []
        self.existing_probables = existing_probables or []
        self.calls = []
        self.deleted = []

    def table(self, name):
        return FakeQuery(self, name)


class WriteTests(unittest.TestCase):
    def test_sync_upserts_announced_and_deletes_existing_missing_slot(self):
        rows, missing = transform_assignment_slots(
            sample_game(home_probable=False), UPDATED_AT
        )
        client = FakeClient(
            existing_probables=[
                {"game_id": 824766, "team_id": 111},
                {"game_id": 824766, "team_id": 139},
            ]
        )
        self.assertEqual(sync_probable_pitchers(client, rows, missing), (1, 1))
        upsert = next(call for call in client.calls if call[0] == "upsert")
        self.assertEqual(upsert[1], "probable_pitchers")
        self.assertEqual(
            upsert[3],
            {"on_conflict": "game_id,team_id", "default_to_null": False},
        )
        self.assertEqual(
            client.deleted,
            [(('game_id', 824766), ('team_id', 111))],
        )

    def test_sync_does_not_issue_delete_when_missing_slot_has_no_row(self):
        rows, missing = transform_assignment_slots(
            sample_game(home_probable=False), UPDATED_AT
        )
        client = FakeClient(existing_probables=[])
        self.assertEqual(sync_probable_pitchers(client, rows, missing), (1, 0))
        self.assertFalse(any(call[0] == "delete" for call in client.calls))

    def test_ingest_deletes_absent_assignment_from_valid_pregame_response(self):
        game = sample_game(home_probable=False, away_probable=False)
        client = FakeClient(
            teams=[{"team_id": 111}, {"team_id": 139}],
            existing_probables=[{"game_id": 824766, "team_id": 111}],
        )
        with patch(
            "scripts.ingest_probable_pitchers.fetch_schedule",
            return_value={"dates": [{"games": [game]}]},
        ):
            summary = ingest_date(
                client, date(2026, 7, 17), "R", False, 30.0, 2
            )
        self.assertEqual(summary["assignments_missing"], 2)
        self.assertEqual(summary["rows_deleted"], 1)

    def test_non_pregame_game_does_not_clear_existing_assignment(self):
        live = sample_game(abstract_state="Live", home_probable=False)
        client = FakeClient(existing_probables=[{"game_id": 824766, "team_id": 111}])
        with patch(
            "scripts.ingest_probable_pitchers.fetch_schedule",
            return_value={"dates": [{"games": [live]}]},
        ):
            summary = ingest_date(
                client, date(2026, 7, 17), "R", False, 30.0, 2
            )
        self.assertEqual(summary["pregame_games_found"], 0)
        self.assertFalse(any(call[0] == "delete" for call in client.calls))

    def test_people_failure_writes_current_assignment_with_null_hand(self):
        game = sample_game(away_probable=False)
        client = FakeClient(
            teams=[{"team_id": 111}, {"team_id": 139}],
            existing_probables=[],
        )
        with patch(
            "scripts.ingest_probable_pitchers.fetch_schedule",
            return_value={"dates": [{"games": [game]}]},
        ), patch(
            "scripts.ingest_probable_pitchers.fetch_person",
            side_effect=IngestionError("people unavailable"),
        ):
            summary = ingest_date(
                client, date(2026, 7, 17), "R", False, 30.0, 2
            )
        self.assertEqual(summary["people_failed"], 1)
        upsert = next(call for call in client.calls if call[0] == "upsert")
        self.assertIsNone(upsert[2][0]["pitch_hand"])

    def test_malformed_game_never_deletes_assignments(self):
        game = sample_game()
        game["teams"]["home"]["probablePitcher"] = "unknown"
        client = FakeClient(existing_probables=[{"game_id": 824766, "team_id": 111}])
        with patch(
            "scripts.ingest_probable_pitchers.fetch_schedule",
            return_value={"dates": [{"games": [game]}]},
        ):
            summary = ingest_date(
                client, date(2026, 7, 17), "R", False, 30.0, 2
            )
        self.assertEqual(summary["games_failed"], 1)
        self.assertFalse(any(call[0] == "delete" for call in client.calls))

    def test_no_game_date_succeeds(self):
        with patch(
            "scripts.ingest_probable_pitchers.fetch_schedule",
            return_value={"dates": []},
        ):
            summary = ingest_date(
                None, date(2026, 7, 14), "R", True, 30.0, 2
            )
        self.assertEqual(summary["games_found"], 0)
        self.assertEqual(summary["games_failed"], 0)

    def test_injected_schedule_and_person_fetcher_avoid_standalone_requests(self):
        game = sample_game(away_probable=False)
        payload = {"dates": [{"games": [game]}]}
        person_fetcher = Mock(return_value=person_payload(605483, "L"))
        with patch("scripts.ingest_probable_pitchers.fetch_schedule") as schedule:
            summary = ingest_date(
                None,
                date(2026, 7, 17),
                "R",
                True,
                30.0,
                2,
                schedule_payload=payload,
                person_fetcher=person_fetcher,
            )
        schedule.assert_not_called()
        person_fetcher.assert_called_once_with(605483, 30.0, 2)
        self.assertEqual(summary["assignments_found"], 1)
        self.assertEqual(summary["people_failed"], 0)


class EndpointTests(unittest.TestCase):
    def test_schedule_uses_probable_pitcher_hydration(self):
        with patch(
            "scripts.ingest_probable_pitchers._request_json", return_value={}
        ) as request_mock:
            fetch_schedule(date(2026, 7, 17), timeout=12.0, retries=1)
        request_mock.assert_called_once_with(
            "https://statsapi.mlb.com/api/v1/schedule",
            {
                "sportId": 1,
                "gameType": "R",
                "date": "2026-07-17",
                "hydrate": "probablePitcher,team",
            },
            12.0,
            1,
        )

    def test_person_uses_documented_endpoint(self):
        with patch(
            "scripts.ingest_probable_pitchers._request_json", return_value={}
        ) as request_mock:
            fetch_person(643377, timeout=12.0, retries=1)
        request_mock.assert_called_once_with(
            "https://statsapi.mlb.com/api/v1/people/643377", {}, 12.0, 1
        )


if __name__ == "__main__":
    unittest.main()
