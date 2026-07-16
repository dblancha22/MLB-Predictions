import unittest
from datetime import date
from unittest.mock import patch

from scripts.ingest_team_game_logs import (
    IngestionError,
    build_date_range,
    fetch_boxscore,
    final_games,
    ingest_date,
    transform_team_game_rows,
    upsert_team_game_logs,
    validate_dependencies,
)


def sample_schedule_game(
    game_id=824252, status_code="F", coded_game_state="F"
):
    return {
        "gamePk": game_id,
        "status": {
            "statusCode": status_code,
            "codedGameState": coded_game_state,
            "detailedState": "Final",
        },
        "teams": {
            "home": {"team": {"id": 116}},
            "away": {"team": {"id": 143}},
        },
    }


def batting_stats(**overrides):
    stats = {
        "runs": 10,
        "hits": 8,
        "homeRuns": 3,
        "strikeOuts": 9,
        "baseOnBalls": 5,
        "plateAppearances": 38,
        "atBats": 32,
        "totalBases": 20,
        "leftOnBase": 7,
        "groundIntoDoublePlay": 0,
        "doubles": 1,
        "triples": 1,
    }
    stats.update(overrides)
    return stats


def sample_boxscore(home_id=116, away_id=143):
    return {
        "teams": {
            "home": {
                "team": {"id": home_id},
                "teamStats": {"batting": batting_stats()},
            },
            "away": {
                "team": {"id": away_id},
                "teamStats": {
                    "batting": batting_stats(
                        runs=2,
                        hits=4,
                        homeRuns=1,
                        strikeOuts=7,
                        baseOnBalls=3,
                        plateAppearances=36,
                        atBats=32,
                        totalBases=7,
                        leftOnBase=15,
                        doubles=0,
                        triples=0,
                    )
                },
            },
        }
    }


class TransformTests(unittest.TestCase):
    def test_final_filter_uses_mlb_status_code_and_deduplicates_game_id(self):
        final = sample_schedule_game()
        duplicate = sample_schedule_game()
        scheduled = sample_schedule_game(
            game_id=2, status_code="S", coded_game_state="S"
        )
        self.assertEqual(final_games([final, duplicate, scheduled]), [duplicate])

    def test_completed_early_is_postgame_safe_final(self):
        completed_early = sample_schedule_game(
            game_id=824295, status_code="FR", coded_game_state="F"
        )
        completed_early["status"]["detailedState"] = "Completed Early"
        self.assertEqual(final_games([completed_early]), [completed_early])

    def test_maps_two_team_rows_with_opponents(self):
        rows = transform_team_game_rows(sample_schedule_game(), sample_boxscore())
        self.assertEqual(len(rows), 2)
        home, away = rows
        self.assertEqual(home["game_id"], 824252)
        self.assertEqual(home["team_id"], 116)
        self.assertEqual(home["opponent_id"], 143)
        self.assertEqual(home["runs_scored"], 10)
        self.assertEqual(home["home_runs"], 3)
        self.assertEqual(home["walks"], 5)
        self.assertEqual(home["grounded_into_double_play"], 0)
        self.assertEqual(away["team_id"], 143)
        self.assertEqual(away["opponent_id"], 116)
        self.assertEqual(away["runs_scored"], 2)
        self.assertEqual(away["left_on_base"], 15)

    def test_missing_required_batting_value_rejects_game(self):
        boxscore = sample_boxscore()
        del boxscore["teams"]["home"]["teamStats"]["batting"]["hits"]
        with self.assertRaises(IngestionError):
            transform_team_game_rows(sample_schedule_game(), boxscore)

    def test_schedule_and_boxscore_team_mismatch_rejects_game(self):
        with self.assertRaises(IngestionError):
            transform_team_game_rows(
                sample_schedule_game(), sample_boxscore(home_id=999)
            )


class DateRangeTests(unittest.TestCase):
    def test_single_date(self):
        target = date(2026, 7, 10)
        self.assertEqual(build_date_range(target, None, None), [target])

    def test_inclusive_range(self):
        self.assertEqual(
            build_date_range(None, date(2026, 7, 10), date(2026, 7, 11)),
            [date(2026, 7, 10), date(2026, 7, 11)],
        )


class FakeResponse:
    def __init__(self, data=None):
        self.data = data


class FakeQuery:
    def __init__(self, client, table):
        self.client = client
        self.table = table

    def select(self, columns):
        self.client.calls.append(("select", self.table, columns))
        return self

    def in_(self, column, values):
        self.client.calls.append(("in", self.table, column, values))
        return self

    def upsert(self, rows, **kwargs):
        self.client.calls.append(("upsert", self.table, rows, kwargs))
        return self

    def execute(self):
        if self.table == "games_raw":
            return FakeResponse(self.client.games)
        if self.table == "teams":
            return FakeResponse(self.client.teams)
        return FakeResponse([])


class FakeClient:
    def __init__(self, games=None, teams=None):
        self.games = games or []
        self.teams = teams or []
        self.calls = []

    def table(self, name):
        return FakeQuery(self, name)


class WriteTests(unittest.TestCase):
    def test_dependency_validation_filters_whole_invalid_game(self):
        rows = transform_team_game_rows(sample_schedule_game(), sample_boxscore())
        client = FakeClient(
            games=[{"game_id": 824252}], teams=[{"team_id": 116}]
        )
        valid, invalid = validate_dependencies(client, rows)
        self.assertEqual(valid, [])
        self.assertEqual(invalid, [824252])

    def test_upsert_uses_composite_primary_key(self):
        rows = transform_team_game_rows(sample_schedule_game(), sample_boxscore())
        client = FakeClient()
        self.assertEqual(upsert_team_game_logs(client, rows), 2)
        upsert = next(call for call in client.calls if call[0] == "upsert")
        self.assertEqual(upsert[1], "team_game_logs")
        self.assertEqual(
            upsert[3],
            {"on_conflict": "game_id,team_id", "default_to_null": False},
        )

    def test_one_boxscore_failure_does_not_block_other_games(self):
        failed = sample_schedule_game(game_id=1)
        good = sample_schedule_game(game_id=2)
        schedule = {"dates": [{"games": [failed, good]}]}

        def boxscore_side_effect(game_id, timeout, retries):
            if game_id == 1:
                raise IngestionError("boxscore unavailable")
            return sample_boxscore()

        with patch(
            "scripts.ingest_team_game_logs.fetch_schedule", return_value=schedule
        ), patch(
            "scripts.ingest_team_game_logs.fetch_boxscore",
            side_effect=boxscore_side_effect,
        ):
            summary = ingest_date(
                None, date(2026, 7, 10), "R", True, 30.0, 2
            )
        self.assertEqual(summary["games_failed"], 1)
        self.assertEqual(summary["rows_ready"], 2)

    def test_no_game_date_succeeds(self):
        with patch(
            "scripts.ingest_team_game_logs.fetch_schedule",
            return_value={"dates": []},
        ):
            summary = ingest_date(
                None, date(2026, 7, 13), "R", True, 30.0, 2
            )
        self.assertEqual(summary["games_found"], 0)
        self.assertEqual(summary["games_failed"], 0)
        self.assertEqual(summary["rows_ready"], 0)

    def test_fetch_boxscore_calls_documented_endpoint(self):
        with patch(
            "scripts.ingest_team_game_logs._request_json", return_value={}
        ) as request_mock:
            fetch_boxscore(824252, timeout=12.0, retries=1)
        request_mock.assert_called_once_with(
            "https://statsapi.mlb.com/api/v1/game/824252/boxscore", {}, 12.0, 1
        )


if __name__ == "__main__":
    unittest.main()
