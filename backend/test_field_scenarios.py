"""Field-scenario acceptance tests: the group's six most-used configurations.

Distinct from test_fairness.py (which maps the signed-off C-1 spec ACs):
this module maps REAL FIELD USAGE, supplied by Ashok on 2026-11-13:

    1. 13-15 players on 3 courts - 3 pairs (4 games together) / all random
    2. 16-20 players on 4 courts - 4 pairs (5 games together) / all random
    3. 5 pairs league+knockout on 2 courts
    4. 6 pairs league+knockout on 2 courts (C-2 gap: clean 422 until then)
    5. 5 pairs round robin on 2 courts
    6. 6 pairs round robin on 2 courts (the Organiser config)

Assertions are on PROPERTIES (completeness, pair-together counts, fairness
spread bounds, pinned warning rules, seed variety, time budget) - never on
exact rosters - so engine improvements pass while regressions fail loudly.
Expectations that encode known limits (the 13p rest warning, the C-2 422)
are marked with comments; they flip deliberately when the capability lands.

Run from backend/:

    venv/bin/python -m unittest test_field_scenarios -v
"""

import time
import unittest
from collections import Counter
from itertools import combinations

import regression_support  # noqa: F401  (env setup before app import)

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402

TIME_BUDGET_S = 5.0
ROTATING_WARNING_RULES = {"matchup_spread", "partner_repeat"}
CLIENT = None


def _generate(tag, players_n, courts, rounds, pairs_n, pair_games,
              draw_type="round_robin", seed=1):
    players = [f"{tag}-{i}" for i in range(1, players_n + 1)]
    pairs = [[players[i], players[i + 1]] for i in range(0, 2 * pairs_n, 2)]
    payload = {
        "players": players,
        "fixed_pairs": pairs,
        "num_courts": courts,
        "court_numbers": [str(i + 1) for i in range(courts)],
        "rounds": rounds,
        "limits": {},
        "pair_games": pair_games,
        "pair_start_round": 1,
        "max_consecutive_rest": 1,
        "draw_type": draw_type,
        "seed": seed,
    }
    start = time.monotonic()
    response = CLIENT.post("/api/generate", json=payload)
    elapsed = time.monotonic() - start
    return players, [tuple(sorted(p)) for p in pairs], response, elapsed


def _assert_complete(test, body, players):
    for r in body["rounds"]:
        on_courts = [p for c in r["courts"] for p in list(c["team_a"]) + list(c["team_b"])]
        test.assertEqual(
            sorted(on_courts + r["resting"]),
            sorted(players),
            f"round {r['round']} does not account for every player exactly once",
        )


def _assert_pair_counts(test, body, pair_games, slack=1):
    counts = body["fixed_pair_counts"]
    test.assertTrue(counts)
    for pair, count in counts.items():
        test.assertTrue(
            pair_games <= count <= pair_games + slack,
            f"{pair} played together {count}x (target {pair_games})",
        )


def _assert_no_consecutive_violations(test, body):
    consecutive = [v for v in body["violations"] if "consecutive" in v]
    test.assertEqual(consecutive, [], f"consecutive limit violations: {consecutive}")


def _warning_rules(body):
    return {w.split(":")[0] for w in body["warnings"]}


def _pure_pair_courts(body, pairs):
    pairset = {frozenset(p) for p in pairs}
    pure = 0
    for r in body["rounds"]:
        for c in r["courts"]:
            if frozenset(c["team_a"]) in pairset and frozenset(c["team_b"]) in pairset:
                pure += 1
    return pure


class _FieldScenarioTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global CLIENT
        cls.client = TestClient(app)
        cls.client.__enter__()
        CLIENT = cls.client

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)


class PairsOnThreeCourtsTests(_FieldScenarioTest):
    """Scenario 1.1: 13-15 players, 3 courts, 3 pairs, 4 games together."""

    def test_scenario_1_1(self):
        for players_n in (13, 14, 15):
            with self.subTest(players=players_n):
                round1_sets = set()
                for seed in (1, 2, 3):
                    players, pairs, response, elapsed = _generate(
                        f"S11-{players_n}", players_n, 3, 10, 3, 4, seed=seed
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertLess(elapsed, TIME_BUDGET_S)
                    body = response.json()
                    _assert_complete(self, body, players)
                    _assert_no_consecutive_violations(self, body)
                    _assert_pair_counts(self, body, 4)
                    fairness = body["fairness"]
                    self.assertLessEqual(fairness["rest_spread"], 2)
                    self.assertLessEqual(fairness["corest_spread"], 1)
                    self.assertLessEqual(fairness["matchup_spread"], 1)
                    rules = _warning_rules(body)
                    # v2 pair semantics: pairs dissolve after completing
                    # their together-target, so even the 13-player shape
                    # (one rest slot) rotates everyone once the 3 pairs
                    # finish their 4 games - all warning-free.
                    self.assertEqual(rules, set())
                    round1_sets.add(tuple(sorted(body["rounds"][0]["resting"])))
                self.assertGreaterEqual(len(round1_sets), 2, "round-1 resters must vary by seed")


class RandomOnThreeCourtsTests(_FieldScenarioTest):
    """Scenario 1.2: 13-15 players, 3 courts, all random."""

    def test_scenario_1_2(self):
        for players_n in (13, 14, 15):
            with self.subTest(players=players_n):
                round1_sets = set()
                for seed in (1, 2, 3):
                    players, _, response, elapsed = _generate(
                        f"S12-{players_n}", players_n, 3, 10, 0, 1, seed=seed
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertLess(elapsed, TIME_BUDGET_S)
                    body = response.json()
                    _assert_complete(self, body, players)
                    _assert_no_consecutive_violations(self, body)
                    fairness = body["fairness"]
                    self.assertLessEqual(fairness["rest_spread"], 1)
                    self.assertLessEqual(fairness["corest_spread"], 1)
                    # Rotating sessions at this size can exceed the opponent
                    # target; that must be reported, never silent (the
                    # session-level rotating design is C-2's engine).
                    self.assertLessEqual(fairness["matchup_spread"], 4)
                    self.assertTrue(_warning_rules(body) <= ROTATING_WARNING_RULES)
                    round1_sets.add(tuple(sorted(body["rounds"][0]["resting"])))
                self.assertGreaterEqual(len(round1_sets), 2)


class PairsOnFourCourtsTests(_FieldScenarioTest):
    """Scenario 2.1: 16-20 players, 4 courts, 4 pairs, 5 games together."""

    def test_scenario_2_1(self):
        for players_n in (16, 18, 20):
            with self.subTest(players=players_n):
                round1_sets = set()
                for seed in (1, 2, 3):
                    players, pairs, response, elapsed = _generate(
                        f"S21-{players_n}", players_n, 4, 10, 4, 5, seed=seed
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertLess(elapsed, TIME_BUDGET_S)
                    body = response.json()
                    _assert_complete(self, body, players)
                    _assert_no_consecutive_violations(self, body)
                    _assert_pair_counts(self, body, 5)
                    fairness = body["fairness"]
                    self.assertLessEqual(fairness["rest_spread"], 1)
                    self.assertLessEqual(fairness["corest_spread"], 1)
                    self.assertLessEqual(fairness["matchup_spread"], 1)
                    self.assertEqual(_warning_rules(body), set(),
                                     "the group's main pair sessions must be warning-free")
                    round1_sets.add(tuple(sorted(body["rounds"][0]["resting"])))
                if players_n > 16:  # 16p has no rest slots at all
                    self.assertGreaterEqual(len(round1_sets), 2)


class RandomOnFourCourtsTests(_FieldScenarioTest):
    """Scenario 2.2: 16-20 players, 4 courts, all random."""

    def test_scenario_2_2(self):
        for players_n in (16, 18, 20):
            with self.subTest(players=players_n):
                for seed in (1, 2, 3):
                    players, _, response, elapsed = _generate(
                        f"S22-{players_n}", players_n, 4, 10, 0, 1, seed=seed
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertLess(elapsed, TIME_BUDGET_S)
                    body = response.json()
                    _assert_complete(self, body, players)
                    _assert_no_consecutive_violations(self, body)
                    fairness = body["fairness"]
                    self.assertLessEqual(fairness["rest_spread"], 1)
                    self.assertLessEqual(fairness["corest_spread"], 1)
                    self.assertLessEqual(fairness["matchup_spread"], 4)
                    self.assertTrue(_warning_rules(body) <= ROTATING_WARNING_RULES)


class LeagueKnockoutFieldTests(_FieldScenarioTest):
    """Scenarios 3 and 4: league+knockout with 5 and 6 pairs on 2 courts."""

    def test_scenario_3_five_pairs_league_knockout(self):
        players, pairs, response, elapsed = _generate(
            "S3", 10, 2, 10, 5, 8, draw_type="league_knockout", seed=1
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertLess(elapsed, TIME_BUDGET_S)
        body = response.json()
        _assert_complete(self, body, players)
        _assert_no_consecutive_violations(self, body)
        # Every league match is pair-vs-pair, each pair meets every other
        # pair exactly twice (10 rounds = 2 meetings of the 5-team cycle).
        self.assertEqual(_pure_pair_courts(body, pairs), 20)
        for pair, count in body["fixed_pair_counts"].items():
            self.assertEqual(count, 8, f"{pair} should meet each pair twice (4 opponents x 2)")
        fairness = body["fairness"]
        self.assertEqual(
            (fairness["rest_spread"], fairness["corest_spread"], fairness["matchup_spread"]),
            (0, 0, 0),
        )
        self.assertEqual(_warning_rules(body), set())

    def test_scenario_4_six_pairs_league_knockout_rejects_cleanly(self):
        # C-2 capability gap: 6 pairs need 3 courts in the strict cycle
        # scheduler. Until C-2 stretches cycle rounds, the API must reject
        # with a clean 422 and an actionable message - never a 500. When
        # C-2 lands, replace this with a success-path test.
        players, _, response, elapsed = _generate(
            "S4", 12, 2, 10, 6, 8, draw_type="league_knockout", seed=1
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("requires exactly 3 court(s)", response.json()["detail"])
        self.assertLess(elapsed, 1.0)


class RoundRobinPairsFieldTests(_FieldScenarioTest):
    """Scenarios 5 and 6: pure-pair round robins on 2 courts."""

    def test_scenario_5_five_pairs_round_robin(self):
        round1_sets = set()
        for seed in (1, 2, 3, 4, 5):
            players, pairs, response, elapsed = _generate(
                "S5", 10, 2, 10, 5, 4, seed=seed
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertLess(elapsed, TIME_BUDGET_S)
            body = response.json()
            _assert_complete(self, body, players)
            _assert_no_consecutive_violations(self, body)
            _assert_pair_counts(self, body, 4)
            fairness = body["fairness"]
            self.assertLessEqual(fairness["rest_spread"], 1)
            self.assertLessEqual(fairness["corest_spread"], 1)
            self.assertLessEqual(fairness["matchup_spread"], 1)
            self.assertEqual(_warning_rules(body), set())
            round1_sets.add(tuple(sorted(body["rounds"][0]["resting"])))
        self.assertGreaterEqual(len(round1_sets), 3)

    def test_scenario_5b_five_pairs_thirteen_rounds(self):
        players, pairs, response, elapsed = _generate("S5b", 10, 2, 13, 5, 5, seed=1)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertLess(elapsed, TIME_BUDGET_S)
        body = response.json()
        _assert_complete(self, body, players)
        _assert_pair_counts(self, body, 5)
        fairness = body["fairness"]
        # 26 matches over 10 possible pair matchups: unevenness is
        # arithmetically forced and must be reported as unavoidable.
        self.assertLessEqual(fairness["matchup_spread"], 1)
        matchup_issues = [i for i in fairness["issues"] if i["rule"] == "matchup_spread"]
        self.assertTrue(matchup_issues)
        self.assertTrue(matchup_issues[0]["unavoidable"])

    def test_scenario_6_six_pairs_round_robin_all_seeds(self):
        round1_sets = set()
        for seed in range(1, 21):
            players, pairs, response, elapsed = _generate(
                "S6", 12, 2, 13, 6, 8, seed=seed
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertLess(elapsed, TIME_BUDGET_S)
            body = response.json()
            _assert_complete(self, body, players)
            _assert_no_consecutive_violations(self, body)
            _assert_pair_counts(self, body, 8)
            # 12 of 13 rounds are pure pair-vs-pair; once every pair has
            # its 8 together-games the final round goes mixed by design
            # (pair_games respected). At least 10 rounds must stay pure.
            self.assertGreaterEqual(_pure_pair_courts(body, pairs), 20)
            fairness = body["fairness"]
            self.assertLessEqual(fairness["rest_spread"], 1)
            self.assertLessEqual(fairness["corest_spread"], 1)
            self.assertLessEqual(fairness["matchup_spread"], 1)
            self.assertEqual(_warning_rules(body), {"matchup_spread"})
            round1_sets.add(tuple(sorted(body["rounds"][0]["resting"])))
        self.assertGreaterEqual(len(round1_sets), 3, "round-1 resters must vary by seed")


if __name__ == "__main__":
    unittest.main()
