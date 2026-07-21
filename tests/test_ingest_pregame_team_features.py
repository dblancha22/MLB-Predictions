import argparse
import unittest
from datetime import date, datetime, timezone

from scripts.ingest_pregame_team_features import (
    GAME_COLUMNS,
    MODE_HISTORICAL,
    MODE_LIVE,
    PITCHER_LOG_COLUMNS,
    PROBABLE_COLUMNS,
    TEAM_LOG_COLUMNS,
    IngestionError,
    build_feature_rows,
    ingest_features,
    load_feature_source_rows,
    paginated_select,
    resolve_target_dates,
    upsert_game_features,
)


def game(
    game_id,
    game_date,
    home,
    away,
    *,
    scheduled="2026-04-01T20:00:00+00:00",
    status="Final",
    scores=True,
):
    return {
        "game_id": game_id,
        "game_date": game_date,
        "home_team_id": home,
        "away_team_id": away,
        "home_score": 5 if scores else None,
        "away_score": 3 if scores else None,
        "status": status,
        "scheduled_time_utc": scheduled,
        "game_type": "R",
        "season": 2026,
    }


def team_logs(game_id, home, away, *, home_runs=5, away_runs=3, offset=0):
    common = {
        "walks": 2 + offset,
        "hit_by_pitch": 1,
        "sacrifice_flies": 1,
        "at_bats": 30,
    }
    return [
        {
            "game_id": game_id,
            "team_id": home,
            "opponent_id": away,
            "runs_scored": home_runs,
            "hits": 8 + offset,
            "total_bases": 12 + offset,
            **common,
        },
        {
            "game_id": game_id,
            "team_id": away,
            "opponent_id": home,
            "runs_scored": away_runs,
            "hits": 6 + offset,
            "total_bases": 9 + offset,
            **common,
        },
    ]


COMPUTED = datetime(2026, 7, 18, 20, 0, tzinfo=timezone.utc)


class FeatureCalculationTests(unittest.TestCase):
    def test_complete_rows_preserve_contract_and_team_order(self):
        prior = game(1, "2026-04-01", 10, 20)
        target = game(
            2,
            "2026-04-02",
            10,
            20,
            scheduled="2026-04-02T20:00:00+00:00",
            status="Scheduled",
            scores=False,
        )
        pitcher_logs = [
            {
                "game_id": 1,
                "pitcher_id": 88,
                "outs_recorded": 9,
                "earned_runs_allowed": 1,
            },
            {
                "game_id": 1,
                "pitcher_id": 99,
                "outs_recorded": 18,
                "earned_runs_allowed": 2,
            },
        ]
        probables = [
            {
                "game_id": 2,
                "team_id": 10,
                "pitcher_id": 88,
                "pitch_hand": "R",
                "capture_type": "pregame",
                "updated_at": "2026-04-02T18:00:00+00:00",
            },
            {
                "game_id": 2,
                "team_id": 20,
                "pitcher_id": 99,
                "pitch_hand": "L",
                "capture_type": "pregame",
                "updated_at": "2026-04-02T18:00:00+00:00",
            },
        ]

        result = build_feature_rows(
            [prior, target],
            team_logs(1, 10, 20),
            pitcher_logs,
            probables,
            season=2026,
            game_type="R",
            target_dates=(date(2026, 4, 2),),
            mode=MODE_HISTORICAL,
            computed_at=COMPUTED,
        )

        home_ops = (8 + 2 + 1) / (30 + 2 + 1 + 1) + 12 / 30
        away_ops = (6 + 2 + 1) / (30 + 2 + 1 + 1) + 9 / 30
        self.assertEqual(
            result.rows_by_game[2],
            [
                {
                    "game_id": 2,
                    "team_id": 10,
                    "opponent_team_id": 20,
                    "season": 2026,
                    "scheduled_start_time_at_cutoff": "2026-04-02T20:00:00+00:00",
                    "is_home": True,
                    "feature_cutoff_at": "2026-04-02T20:00:00+00:00",
                    "computed_at": COMPUTED.isoformat(),
                    "feature_schema_version": 1,
                    "runs_avg_last_5": 5.0,
                    "hits_avg_last_5": 8.0,
                    "ops_last_5": home_ops,
                    "runs_avg_last_10": 5.0,
                    "hits_avg_last_10": 8.0,
                    "ops_last_10": home_ops,
                    "opposing_probable_pitcher_id": 99,
                    "opposing_pitcher_season_era": 3.0,
                    "opposing_pitcher_hand": "L",
                    "team_wins_before_game": 1,
                    "team_losses_before_game": 0,
                    "opponent_wins_before_game": 0,
                    "opponent_losses_before_game": 1,
                },
                {
                    "game_id": 2,
                    "team_id": 20,
                    "opponent_team_id": 10,
                    "season": 2026,
                    "scheduled_start_time_at_cutoff": "2026-04-02T20:00:00+00:00",
                    "is_home": False,
                    "feature_cutoff_at": "2026-04-02T20:00:00+00:00",
                    "computed_at": COMPUTED.isoformat(),
                    "feature_schema_version": 1,
                    "runs_avg_last_5": 3.0,
                    "hits_avg_last_5": 6.0,
                    "ops_last_5": away_ops,
                    "runs_avg_last_10": 3.0,
                    "hits_avg_last_10": 6.0,
                    "ops_last_10": away_ops,
                    "opposing_probable_pitcher_id": 88,
                    "opposing_pitcher_season_era": 3.0,
                    "opposing_pitcher_hand": "R",
                    "team_wins_before_game": 0,
                    "team_losses_before_game": 1,
                    "opponent_wins_before_game": 1,
                    "opponent_losses_before_game": 0,
                },
            ],
        )

    def test_first_game_has_null_rolling_values_and_zero_record(self):
        target = game(
            1,
            "2026-04-01",
            10,
            20,
            status="Scheduled",
            scores=False,
        )
        result = build_feature_rows(
            [target],
            [],
            [],
            [],
            season=2026,
            game_type="R",
            target_dates=(date(2026, 4, 1),),
            mode=MODE_HISTORICAL,
            computed_at=COMPUTED,
        )
        home = result.rows_by_game[1][0]
        self.assertIsNone(home["runs_avg_last_5"])
        self.assertIsNone(home["ops_last_10"])
        self.assertEqual(home["team_wins_before_game"], 0)
        self.assertEqual(home["team_losses_before_game"], 0)

    def test_rolling_ops_aggregates_window_inputs(self):
        first = game(1, "2026-04-01", 10, 20)
        second = game(
            2,
            "2026-04-02",
            10,
            30,
            scheduled="2026-04-02T20:00:00+00:00",
        )
        target = game(
            3,
            "2026-04-03",
            10,
            20,
            scheduled="2026-04-03T20:00:00+00:00",
            status="Scheduled",
            scores=False,
        )
        logs = team_logs(1, 10, 20) + team_logs(2, 10, 30, offset=2)
        result = build_feature_rows(
            [first, second, target],
            logs,
            [],
            [],
            season=2026,
            game_type="R",
            target_dates=(date(2026, 4, 3),),
            mode=MODE_HISTORICAL,
            computed_at=COMPUTED,
        )
        home = result.rows_by_game[3][0]
        expected_ops = (18 + 6 + 2) / (60 + 6 + 2 + 2) + 26 / 60
        self.assertEqual(home["runs_avg_last_5"], 5.0)
        self.assertEqual(home["hits_avg_last_5"], 9.0)
        self.assertAlmostEqual(home["ops_last_5"], expected_ops)
        self.assertEqual(home["team_wins_before_game"], 2)
        self.assertEqual(home["team_losses_before_game"], 0)

    def test_same_day_game_is_excluded_from_doubleheader_features(self):
        prior_day = game(1, "2026-04-01", 10, 20)
        game_one = game(
            2,
            "2026-04-02",
            10,
            30,
            scheduled="2026-04-02T17:00:00+00:00",
        )
        game_two = game(
            3,
            "2026-04-02",
            10,
            30,
            scheduled="2026-04-02T23:00:00+00:00",
            status="Scheduled",
            scores=False,
        )
        logs = team_logs(1, 10, 20) + team_logs(
            2, 10, 30, home_runs=12, away_runs=1
        )
        result = build_feature_rows(
            [prior_day, game_one, game_two],
            logs,
            [],
            [],
            season=2026,
            game_type="R",
            target_dates=(date(2026, 4, 2),),
            mode=MODE_HISTORICAL,
            computed_at=COMPUTED,
        )
        game_two_home = result.rows_by_game[3][0]
        self.assertEqual(game_two_home["runs_avg_last_5"], 5.0)
        self.assertEqual(game_two_home["team_wins_before_game"], 1)

    def test_recovered_probable_is_used_with_entering_era(self):
        prior = game(1, "2026-04-01", 10, 20)
        target = game(
            2,
            "2026-04-02",
            10,
            20,
            scheduled="2026-04-02T20:00:00+00:00",
            status="Scheduled",
            scores=False,
        )
        pitcher_logs = [
            {
                "game_id": 1,
                "pitcher_id": 99,
                "outs_recorded": 18,
                "earned_runs_allowed": 2,
            }
        ]
        probables = [
            {
                "game_id": 2,
                "team_id": 20,
                "pitcher_id": 99,
                "pitch_hand": "L",
                "capture_type": "postgame_recovery",
                "updated_at": "2026-07-01T00:00:00+00:00",
            }
        ]
        result = build_feature_rows(
            [prior, target],
            team_logs(1, 10, 20),
            pitcher_logs,
            probables,
            season=2026,
            game_type="R",
            target_dates=(date(2026, 4, 2),),
            mode=MODE_HISTORICAL,
            computed_at=COMPUTED,
        )
        home = result.rows_by_game[2][0]
        self.assertEqual(home["opposing_probable_pitcher_id"], 99)
        self.assertEqual(home["opposing_pitcher_hand"], "L")
        self.assertEqual(home["opposing_pitcher_season_era"], 3.0)

    def test_live_mode_skips_started_game_but_historical_mode_builds_it(self):
        target = game(
            1,
            "2026-04-01",
            10,
            20,
            scheduled="2026-04-01T20:00:00+00:00",
            status="Final",
        )
        live = build_feature_rows(
            [target],
            team_logs(1, 10, 20),
            [],
            [],
            season=2026,
            game_type="R",
            target_dates=(date(2026, 4, 1),),
            mode=MODE_LIVE,
            computed_at=COMPUTED,
        )
        historical = build_feature_rows(
            [target],
            team_logs(1, 10, 20),
            [],
            [],
            season=2026,
            game_type="R",
            target_dates=(date(2026, 4, 1),),
            mode=MODE_HISTORICAL,
            computed_at=COMPUTED,
        )
        self.assertEqual(live.games_skipped_started, 1)
        self.assertNotIn(1, live.rows_by_game)
        self.assertEqual(
            historical.rows_by_game[1][0]["feature_cutoff_at"],
            "2026-04-01T20:00:00+00:00",
        )
        self.assertEqual(
            historical.rows_by_game[1][0]["computed_at"],
            COMPUTED.isoformat(),
        )

    def test_live_mode_uses_actual_computation_cutoff_before_start(self):
        target = game(
            1,
            "2026-07-18",
            10,
            20,
            scheduled="2026-07-18T22:00:00+00:00",
            status="Scheduled",
            scores=False,
        )
        result = build_feature_rows(
            [target],
            [],
            [],
            [],
            season=2026,
            game_type="R",
            target_dates=(date(2026, 7, 18),),
            mode=MODE_LIVE,
            computed_at=COMPUTED,
        )
        row = result.rows_by_game[1][0]
        self.assertEqual(row["feature_cutoff_at"], COMPUTED.isoformat())
        self.assertEqual(
            row["scheduled_start_time_at_cutoff"],
            "2026-07-18T22:00:00+00:00",
        )

    def test_missing_prior_final_logs_fails_target_game(self):
        prior = game(1, "2026-04-01", 10, 20)
        target = game(
            2,
            "2026-04-02",
            10,
            30,
            scheduled="2026-04-02T20:00:00+00:00",
            status="Scheduled",
            scores=False,
        )
        result = build_feature_rows(
            [prior, target],
            [],
            [],
            [],
            season=2026,
            game_type="R",
            target_dates=(date(2026, 4, 2),),
            mode=MODE_HISTORICAL,
            computed_at=COMPUTED,
        )
        self.assertEqual(result.games_failed, 1)
        self.assertEqual(result.rows_by_game, {})


class FakeResponse:
    def __init__(self, data=None):
        self.data = data


class FakeQuery:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self.start = 0
        self.end = 999

    def select(self, columns):
        self.client.calls.append(("select", self.table, columns))
        return self

    def eq(self, column, value):
        self.client.calls.append(("eq", self.table, column, value))
        return self

    def order(self, column):
        self.client.calls.append(("order", self.table, column))
        return self

    def range(self, start, end):
        self.start = start
        self.end = end
        self.client.calls.append(("range", self.table, start, end))
        return self

    def upsert(self, rows, **kwargs):
        self.client.calls.append(("upsert", self.table, rows, kwargs))
        return self

    def execute(self):
        rows = self.client.data.get(self.table, [])
        return FakeResponse(rows[self.start : self.end + 1])


class FakeClient:
    def __init__(self, data=None):
        self.data = data or {}
        self.calls = []

    def table(self, name):
        return FakeQuery(self, name)


class SupabaseBehaviorTests(unittest.TestCase):
    def test_source_reads_preserve_columns_filters_and_ordering(self):
        target = game(
            1,
            "2026-04-01",
            10,
            20,
            status="Scheduled",
            scores=False,
        )
        client = FakeClient(
            {
                "games_raw": [target],
                "team_game_logs": [],
                "pitcher_game_logs": [],
                "probable_pitchers": [],
            }
        )

        load_feature_source_rows(client, 2026, "R")

        self.assertEqual(
            [call for call in client.calls if call[0] == "select"],
            [
                ("select", "games_raw", GAME_COLUMNS),
                ("select", "team_game_logs", TEAM_LOG_COLUMNS),
                ("select", "pitcher_game_logs", PITCHER_LOG_COLUMNS),
                ("select", "probable_pitchers", PROBABLE_COLUMNS),
            ],
        )
        self.assertEqual(
            [call for call in client.calls if call[0] == "eq"],
            [
                ("eq", "games_raw", "season", 2026),
                ("eq", "games_raw", "game_type", "R"),
            ],
        )
        self.assertEqual(
            [call for call in client.calls if call[0] == "order"],
            [
                ("order", "games_raw", "game_id"),
                ("order", "team_game_logs", "game_id"),
                ("order", "team_game_logs", "team_id"),
                ("order", "pitcher_game_logs", "game_id"),
                ("order", "pitcher_game_logs", "pitcher_id"),
                ("order", "probable_pitchers", "game_id"),
                ("order", "probable_pitchers", "team_id"),
            ],
        )

    def test_dry_run_preserves_summary_and_performs_no_upsert(self):
        target = game(
            1,
            "2026-04-01",
            10,
            20,
            status="Scheduled",
            scores=False,
        )
        client = FakeClient(
            {
                "games_raw": [target],
                "team_game_logs": [],
                "pitcher_game_logs": [],
                "probable_pitchers": [],
            }
        )

        summary = ingest_features(
            client,
            season=2026,
            game_type="R",
            target_dates=(date(2026, 4, 1),),
            mode=MODE_HISTORICAL,
            dry_run=True,
            computed_at=COMPUTED,
        )

        self.assertEqual(
            summary,
            {
                "games_found": 1,
                "games_skipped_started": 0,
                "games_failed": 0,
                "rows_ready": 2,
                "rows_upserted": 0,
            },
        )
        self.assertFalse(any(call[0] == "upsert" for call in client.calls))

    def test_paginated_select_reads_every_page(self):
        client = FakeClient({"source": [{"id": value} for value in range(5)]})
        rows = paginated_select(
            client, "source", "id", order_by=("id",), page_size=2
        )
        self.assertEqual([row["id"] for row in rows], list(range(5)))
        ranges = [call for call in client.calls if call[0] == "range"]
        self.assertEqual(
            ranges,
            [
                ("range", "source", 0, 1),
                ("range", "source", 2, 3),
                ("range", "source", 4, 5),
            ],
        )
        self.assertEqual(
            len([call for call in client.calls if call == ("order", "source", "id")]),
            3,
        )

    def test_upsert_writes_exactly_one_game_pair_and_nulls_stale_values(self):
        client = FakeClient()
        rows = [{"game_id": 1, "team_id": 10}, {"game_id": 1, "team_id": 20}]
        self.assertEqual(upsert_game_features(client, rows), 2)
        upsert = next(call for call in client.calls if call[0] == "upsert")
        self.assertEqual(upsert[1], "pregame_team_features")
        self.assertEqual(
            upsert[3],
            {"on_conflict": "game_id,team_id", "default_to_null": True},
        )

    def test_upsert_rejects_partial_game(self):
        with self.assertRaises(IngestionError):
            upsert_game_features(FakeClient(), [{"game_id": 1, "team_id": 10}])


class TargetResolutionTests(unittest.TestCase):
    def test_season_selects_all_dates(self):
        args = argparse.Namespace(
            season=2026,
            today=False,
            date=None,
            start_date=None,
            end_date=None,
            timezone="America/Los_Angeles",
        )
        self.assertIsNone(resolve_target_dates(args))


if __name__ == "__main__":
    unittest.main()
