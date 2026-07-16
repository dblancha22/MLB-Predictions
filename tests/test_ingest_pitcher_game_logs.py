import unittest
from datetime import date
from unittest.mock import patch

from scripts.ingest_pitcher_game_logs import (
    IngestionError,
    build_date_range,
    fetch_boxscore,
    final_games,
    ingest_date,
    mark_pitcher_logs_processed,
    transform_pitcher_game_rows,
    upsert_pitcher_game_logs,
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


def pitching_stats(**overrides):
    stats = {
        "gamesPitched": 1,
        "gamesStarted": 0,
        "outs": 18,
        "strikeOuts": 6,
        "baseOnBalls": 3,
        "homeRuns": 1,
        "hits": 2,
        "runs": 2,
        "earnedRuns": 2,
        "pitchesThrown": 86,
        "battersFaced": 24,
        "flyOuts": 3,
        "groundOuts": 5,
    }
    stats.update(overrides)
    return stats


def player(pitcher_id, **stats):
    return {
        "person": {"id": pitcher_id, "fullName": f"Pitcher {pitcher_id}"},
        "stats": {"pitching": pitching_stats(**stats)},
    }


def sample_boxscore(home_id=116, away_id=143):
    return {
        "teams": {
            "home": {
                "team": {"id": home_id},
                "pitchers": [656427, 621097],
                "players": {
                    "ID656427": player(656427, gamesStarted=1),
                    "ID621097": player(
                        621097,
                        outs=2,
                        strikeOuts=0,
                        baseOnBalls=0,
                        homeRuns=0,
                        hits=1,
                        runs=0,
                        earnedRuns=0,
                        pitchesThrown=16,
                        battersFaced=4,
                        flyOuts=1,
                        groundOuts=2,
                    ),
                },
            },
            "away": {
                "team": {"id": away_id},
                "pitchers": [605400, 641835],
                "players": {
                    "ID605400": player(
                        605400,
                        gamesStarted=1,
                        outs=15,
                        strikeOuts=8,
                        baseOnBalls=2,
                        hits=3,
                        pitchesThrown=84,
                        battersFaced=20,
                        groundOuts=3,
                    ),
                    "ID641835": player(
                        641835,
                        outs=3,
                        strikeOuts=1,
                        baseOnBalls=2,
                        homeRuns=0,
                        runs=5,
                        earnedRuns=4,
                        pitchesThrown=36,
                        battersFaced=8,
                        flyOuts=2,
                        groundOuts=1,
                    ),
                },
            },
        }
    }


class TransformTests(unittest.TestCase):
    def test_final_filter_uses_coded_state_and_deduplicates_game_id(self):
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

    def test_maps_every_appearance_and_marks_mlb_starter(self):
        rows = transform_pitcher_game_rows(
            sample_schedule_game(), sample_boxscore()
        )
        self.assertEqual(len(rows), 4)
        home_starter, home_reliever, away_starter, away_reliever = rows
        self.assertEqual(home_starter["game_id"], 824252)
        self.assertEqual(home_starter["pitcher_id"], 656427)
        self.assertEqual(home_starter["team_id"], 116)
        self.assertTrue(home_starter["is_starter"])
        self.assertEqual(home_starter["outs_recorded"], 18)
        self.assertEqual(home_starter["pitches_thrown"], 86)
        self.assertFalse(home_reliever["is_starter"])
        self.assertEqual(home_reliever["outs_recorded"], 2)
        self.assertEqual(away_starter["team_id"], 143)
        self.assertTrue(away_starter["is_starter"])
        self.assertFalse(away_reliever["is_starter"])
        self.assertEqual(away_reliever["earned_runs_allowed"], 4)

    def test_zero_values_are_preserved(self):
        rows = transform_pitcher_game_rows(
            sample_schedule_game(), sample_boxscore()
        )
        home_reliever = rows[1]
        self.assertEqual(home_reliever["strikeouts"], 0)
        self.assertEqual(home_reliever["walks"], 0)
        self.assertEqual(home_reliever["home_runs_allowed"], 0)

    def test_listed_nonappearance_is_skipped_and_actual_starter_is_marked(self):
        boxscore = sample_boxscore()
        boxscore["teams"]["away"]["pitchers"].insert(0, 607536)
        boxscore["teams"]["away"]["players"]["ID607536"] = player(
            607536,
            gamesPitched=0,
            gamesStarted=0,
            outs=0,
            strikeOuts=0,
            baseOnBalls=0,
            homeRuns=0,
            hits=0,
            runs=0,
            earnedRuns=0,
            pitchesThrown=0,
            battersFaced=0,
            flyOuts=0,
            groundOuts=0,
        )
        del boxscore["teams"]["away"]["players"]["ID607536"]["stats"][
            "pitching"
        ]["pitchesThrown"]
        rows = transform_pitcher_game_rows(sample_schedule_game(), boxscore)
        self.assertNotIn(607536, {row["pitcher_id"] for row in rows})
        away_starters = [
            row
            for row in rows
            if row["team_id"] == 143 and row["is_starter"]
        ]
        self.assertEqual([row["pitcher_id"] for row in away_starters], [605400])

    def test_missing_outs_rejects_whole_game_transform(self):
        boxscore = sample_boxscore()
        del boxscore["teams"]["home"]["players"]["ID621097"]["stats"][
            "pitching"
        ]["outs"]
        with self.assertRaises(IngestionError):
            transform_pitcher_game_rows(sample_schedule_game(), boxscore)

    def test_schedule_and_boxscore_team_mismatch_rejects_game(self):
        with self.assertRaises(IngestionError):
            transform_pitcher_game_rows(
                sample_schedule_game(), sample_boxscore(home_id=999)
            )

    def test_pitcher_list_and_player_id_mismatch_rejects_game(self):
        boxscore = sample_boxscore()
        boxscore["teams"]["home"]["players"]["ID656427"]["person"]["id"] = 1
        with self.assertRaises(IngestionError):
            transform_pitcher_game_rows(sample_schedule_game(), boxscore)


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
        self.operation = None
        self.eq_value = None

    def select(self, columns):
        self.operation = "select"
        self.client.calls.append(("select", self.table, columns))
        return self

    def eq(self, column, value):
        self.eq_value = value
        self.client.calls.append(("eq", self.table, column, value))
        return self

    def in_(self, column, values):
        self.client.calls.append(("in", self.table, column, values))
        return self

    def upsert(self, rows, **kwargs):
        self.operation = "upsert"
        self.client.calls.append(("upsert", self.table, rows, kwargs))
        return self

    def update(self, values):
        self.operation = "update"
        self.client.calls.append(("update", self.table, values))
        return self

    def execute(self):
        if self.table == "games_raw" and self.operation == "update":
            self.client.marker_attempts += 1
            if self.client.marker_attempts <= self.client.marker_failures:
                raise RuntimeError("temporary marker failure")
            if self.client.marker_returns_no_rows:
                return FakeResponse([])
            return FakeResponse([{"game_id": self.eq_value}])
        if self.table == "games_raw":
            return FakeResponse(
                [row for row in self.client.games if row["game_id"] == self.eq_value]
            )
        if self.table == "teams":
            return FakeResponse(self.client.teams)
        return FakeResponse([])


class FakeClient:
    def __init__(
        self,
        games=None,
        teams=None,
        marker_failures=0,
        marker_returns_no_rows=False,
    ):
        self.games = games or []
        self.teams = teams or []
        self.marker_failures = marker_failures
        self.marker_returns_no_rows = marker_returns_no_rows
        self.marker_attempts = 0
        self.calls = []

    def table(self, name):
        return FakeQuery(self, name)


class WriteTests(unittest.TestCase):
    def setUp(self):
        self.rows = transform_pitcher_game_rows(
            sample_schedule_game(), sample_boxscore()
        )

    def test_dependency_validation_accepts_game_and_both_teams(self):
        client = FakeClient(
            games=[{"game_id": 824252}],
            teams=[{"team_id": 116}, {"team_id": 143}],
        )
        validate_dependencies(client, self.rows)

    def test_dependency_validation_rejects_missing_team(self):
        client = FakeClient(
            games=[{"game_id": 824252}], teams=[{"team_id": 116}]
        )
        with self.assertRaises(IngestionError):
            validate_dependencies(client, self.rows)

    def test_upsert_uses_composite_primary_key(self):
        client = FakeClient()
        self.assertEqual(upsert_pitcher_game_logs(client, self.rows), 4)
        upsert = next(call for call in client.calls if call[0] == "upsert")
        self.assertEqual(upsert[1], "pitcher_game_logs")
        self.assertEqual(
            upsert[3],
            {"on_conflict": "game_id,pitcher_id", "default_to_null": False},
        )

    def test_marker_retries_before_succeeding(self):
        client = FakeClient(marker_failures=2)
        with patch("scripts.ingest_pitcher_game_logs.time.sleep") as sleep:
            mark_pitcher_logs_processed(client, 824252, retries=2)
        self.assertEqual(client.marker_attempts, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])

    def test_marker_retry_exhaustion_raises(self):
        client = FakeClient(marker_failures=3)
        with patch("scripts.ingest_pitcher_game_logs.time.sleep"):
            with self.assertRaises(IngestionError):
                mark_pitcher_logs_processed(client, 824252, retries=2)
        self.assertEqual(client.marker_attempts, 3)

    def test_marker_no_matching_row_is_retried_and_fails(self):
        client = FakeClient(marker_returns_no_rows=True)
        with patch("scripts.ingest_pitcher_game_logs.time.sleep"):
            with self.assertRaises(IngestionError):
                mark_pitcher_logs_processed(client, 824252, retries=1)
        self.assertEqual(client.marker_attempts, 2)

    def test_rows_are_upserted_before_marker_update(self):
        client = FakeClient(
            games=[{"game_id": 824252}],
            teams=[{"team_id": 116}, {"team_id": 143}],
        )
        schedule = {"dates": [{"games": [sample_schedule_game()]}]}
        with patch(
            "scripts.ingest_pitcher_game_logs.fetch_schedule", return_value=schedule
        ), patch(
            "scripts.ingest_pitcher_game_logs.fetch_boxscore",
            return_value=sample_boxscore(),
        ):
            summary = ingest_date(
                client, date(2026, 7, 10), "R", False, 30.0, 2
            )
        action_calls = [call[0] for call in client.calls]
        self.assertLess(action_calls.index("upsert"), action_calls.index("update"))
        self.assertEqual(summary["rows_upserted"], 4)
        self.assertEqual(summary["games_marked_processed"], 1)
        self.assertEqual(summary["games_failed"], 0)

    def test_marker_failure_preserves_written_count_and_fails_game(self):
        client = FakeClient(
            games=[{"game_id": 824252}],
            teams=[{"team_id": 116}, {"team_id": 143}],
            marker_failures=3,
        )
        schedule = {"dates": [{"games": [sample_schedule_game()]}]}
        with patch(
            "scripts.ingest_pitcher_game_logs.fetch_schedule", return_value=schedule
        ), patch(
            "scripts.ingest_pitcher_game_logs.fetch_boxscore",
            return_value=sample_boxscore(),
        ), patch("scripts.ingest_pitcher_game_logs.time.sleep"):
            summary = ingest_date(
                client, date(2026, 7, 10), "R", False, 30.0, 2
            )
        self.assertEqual(summary["rows_upserted"], 4)
        self.assertEqual(summary["games_marked_processed"], 0)
        self.assertEqual(summary["games_failed"], 1)

    def test_one_boxscore_failure_does_not_block_other_games(self):
        failed = sample_schedule_game(game_id=1)
        good = sample_schedule_game(game_id=2)
        schedule = {"dates": [{"games": [failed, good]}]}

        def boxscore_side_effect(game_id, timeout, retries):
            if game_id == 1:
                raise IngestionError("boxscore unavailable")
            return sample_boxscore()

        with patch(
            "scripts.ingest_pitcher_game_logs.fetch_schedule", return_value=schedule
        ), patch(
            "scripts.ingest_pitcher_game_logs.fetch_boxscore",
            side_effect=boxscore_side_effect,
        ):
            summary = ingest_date(
                None, date(2026, 7, 10), "R", True, 30.0, 2
            )
        self.assertEqual(summary["games_failed"], 1)
        self.assertEqual(summary["rows_ready"], 4)

    def test_no_game_date_succeeds(self):
        with patch(
            "scripts.ingest_pitcher_game_logs.fetch_schedule",
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
            "scripts.ingest_pitcher_game_logs._request_json", return_value={}
        ) as request_mock:
            fetch_boxscore(824252, timeout=12.0, retries=1)
        request_mock.assert_called_once_with(
            "https://statsapi.mlb.com/api/v1/game/824252/boxscore", {}, 12.0, 1
        )


if __name__ == "__main__":
    unittest.main()
