"""C-2 acceptance tests: league + knockout on fewer courts.

Covers C-2-REQUIREMENTS v1 AC-K1..K8 (feasibility, coverage, fairness,
rematch), AC-F1..F3 (friendlies), AC-R3 (derived rounds) and AC-P1
(performance). The whole module was verified red on pre-C-2 main: the
field case (6 pairs / 2 courts) 422'd with "requires exactly 3 court(s)"
and none of these endpoints accepted the configs below.
"""

import time
import unittest
import uuid
from collections import Counter
from itertools import combinations

import regression_support  # noqa: F401  (env setup before app import)

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402

CLIENT = None


def _generate(players_n, courts, pairs_n, *, meetings=1, rounds=None, pair_games=None, seed=1):
    players = [f"L{players_n}-{i}" for i in range(1, players_n + 1)]
    pairs = [[players[i], players[i + 1]] for i in range(0, 2 * pairs_n, 2)]
    payload = {
        "players": players,
        "fixed_pairs": pairs,
        "num_courts": courts,
        "court_numbers": [str(i + 1) for i in range(courts)],
        "rounds": rounds if rounds is not None else 30,  # stale on purpose (AC-R3)
        "limits": {},
        "pair_games": pair_games if pair_games is not None else (pairs_n - 1) * meetings,
        "pair_start_round": 1,
        "max_consecutive_rest": 1,
        "draw_type": "league_knockout",
        "league_meetings": meetings,
        "seed": seed,
    }
    start = time.monotonic()
    response = CLIENT.post("/api/generate", json=payload)
    return players, [tuple(sorted(p)) for p in pairs], response, time.monotonic() - start


def _pair_sets(pairs):
    return {frozenset(p) for p in pairs}


def _league_counts(body, pairs):
    """League pair-vs-pair meeting counts, friendlies excluded (AC-F4)."""
    ps = _pair_sets(pairs)

    def key(a, b):
        x, y = tuple(sorted(a)), tuple(sorted(b))
        return (x, y) if x <= y else (y, x)

    counts = Counter()
    friendlies = 0
    for r in body["rounds"]:
        for court in r["courts"]:
            if court.get("friendly"):
                friendlies += 1
                continue
            ta, tb = frozenset(court["team_a"]), frozenset(court["team_b"])
            if ta in ps and tb in ps:
                counts[key(court["team_a"], court["team_b"])] += 1
    values = [counts.get(key(frozenset(a), frozenset(b)), 0) for a, b in combinations(pairs, 2)]
    return counts, values, friendlies


def _b2b_extensions(body):
    resting = {}
    for r in body["rounds"]:
        for p in r["resting"]:
            resting.setdefault(p, set()).add(r["round"])
    events = 0
    for rounds_in in resting.values():
        run = 0
        for round_num in range(1, len(body["rounds"]) + 1):
            if round_num in rounds_in:
                run += 1
                if run > 1:
                    events += 1
            else:
                run = 0
    return events


def _adjacent_rematches(body, pairs):
    ps = _pair_sets(pairs)

    def key(a, b):
        x, y = tuple(sorted(a)), tuple(sorted(b))
        return (x, y) if x <= y else (y, x)

    adjacent = 0
    previous = set()
    for r in body["rounds"]:
        current = {
            key(c["team_a"], c["team_b"])
            for c in r["courts"]
            if not c.get("friendly")
            and frozenset(c["team_a"]) in ps and frozenset(c["team_b"]) in ps
        }
        adjacent += len(current & previous)
        previous = current
    return adjacent


class _LeagueTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global CLIENT
        cls.client = TestClient(app)
        cls.client.__enter__()
        CLIENT = cls.client

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)


class LeagueFeasibilityTests(_LeagueTest):
    """AC-K1, AC-K2, AC-K3, AC-R3, AC-E1."""

    def test_field_case_six_pairs_two_courts_play_once(self):
        players, pairs, response, _ = _generate(12, 2, 6, meetings=1, seed=1)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(body["rounds"]), 8)  # ceil(15 / 2)
        counts, values, friendlies = _league_counts(body, pairs)
        self.assertEqual(sorted(values), [1] * 15)  # every matchup exactly once
        self.assertEqual(friendlies, 1)  # the spare slot (AC-F1)
        self.assertEqual(_b2b_extensions(body), 0)  # AC-K4
        self.assertEqual(_adjacent_rematches(body, pairs), 0)
        # Forced consecutive rests are never blocking violations (D10).
        self.assertFalse([v for v in body["violations"] if ": rested " in v])

    def test_field_case_six_pairs_two_courts_play_twice(self):
        players, pairs, response, _ = _generate(12, 2, 6, meetings=2, seed=1)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(body["rounds"]), 15)  # 30 matches / 2 courts
        _, values, friendlies = _league_counts(body, pairs)
        self.assertEqual(sorted(values), [2] * 15)
        self.assertEqual(friendlies, 0)
        self.assertEqual(_b2b_extensions(body), 0)
        self.assertEqual(_adjacent_rematches(body, pairs), 0)  # AC-K8 (D6)
        # Play Twice duplicates are expected: exactly one per matchup,
        # filtered as allowed by the frontend.
        duplicates = [v for v in body["violations"] if v.startswith("Duplicate knockout matchup")]
        self.assertEqual(len(duplicates), 15)

    def test_coverage_exact_across_setups(self):
        # AC-K2 (1 court allowed, D9), AC-K3, AC-E1 (setups that already
        # worked move to the planner too).
        setups = [
            (10, 2, 5, 1), (10, 2, 5, 2),
            (14, 2, 7, 1),
            (16, 3, 8, 1), (16, 4, 8, 1),
            (12, 1, 6, 1),
            (8, 1, 4, 1), (8, 2, 4, 1),
            (12, 3, 6, 1),
        ]
        for players_n, courts, pairs_n, meetings in setups:
            with self.subTest(config=f"{pairs_n} pairs/{courts}c x{meetings}"):
                players, pairs, response, _ = _generate(
                    players_n, courts, pairs_n, meetings=meetings, seed=2
                )
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                total = pairs_n * (pairs_n - 1) // 2 * meetings
                expected_rounds = -(-total // courts)
                self.assertEqual(len(body["rounds"]), expected_rounds)
                _, values, _ = _league_counts(body, pairs)
                self.assertEqual(sorted(values), [meetings] * (pairs_n * (pairs_n - 1) // 2))

    def test_more_courts_than_matches_rejected(self):
        players, pairs, response, _ = _generate(12, 4, 6, meetings=1, seed=1)
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("at most 3 court(s)", response.json()["detail"])

    def test_stale_rounds_value_is_derived_not_rejected(self):
        # AC-R3: the server derives rounds from pairs/courts/meetings.
        for stale in (3, 30, 50):
            with self.subTest(rounds=stale):
                _, _, response, _ = _generate(12, 2, 6, meetings=1, rounds=stale, seed=1)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(len(response.json()["rounds"]), 8)


class LeagueFairnessTests(_LeagueTest):
    """AC-K4, AC-K5, AC-K6, AC-K7, AC-K8."""

    def test_zero_back_to_back_when_avoidable(self):
        setups = [
            (12, 2, 6, 1), (12, 2, 6, 2),
            (10, 2, 5, 1), (10, 2, 5, 2),
            (16, 3, 8, 1), (16, 4, 8, 1),
            (8, 2, 4, 1), (12, 3, 6, 1),
        ]
        for players_n, courts, pairs_n, meetings in setups:
            for seed in (1, 2, 3):
                with self.subTest(config=f"{pairs_n}p/{courts}c x{meetings}", seed=seed):
                    _, _, response, _ = _generate(
                        players_n, courts, pairs_n, meetings=meetings, seed=seed
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(_b2b_extensions(response.json()), 0)

    def test_forced_back_to_back_reported_not_blocking(self):
        # 4 pairs / 1 court: 2 play, 2 pairs rest every round - consecutive
        # rests are arithmetically unavoidable (pinned bound from measured
        # minimum + slack; the exhaustive-search minimum is 2 round overlaps).
        players, pairs, response, _ = _generate(8, 1, 4, meetings=1, seed=1)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertFalse([v for v in body["violations"] if ": rested " in v])
        self.assertLessEqual(_b2b_extensions(body), 8)
        issue = [i for i in body["fairness"]["issues"] if i["rule"] == "rest_consecutive"]
        self.assertTrue(issue, "forced back-to-back rests must be a fairness issue")
        self.assertTrue(issue[0]["affected"])
        # 6 pairs / 1 court: rest share 4/6 > 1/2 - unavoidability is
        # arithmetic, so the issue is marked unavoidable.
        players, pairs, response, _ = _generate(12, 1, 6, meetings=1, seed=1)
        body = response.json()
        issue = [i for i in body["fairness"]["issues"] if i["rule"] == "rest_consecutive"]
        self.assertTrue(issue)
        self.assertTrue(issue[0]["unavoidable"])
        self.assertLessEqual(_b2b_extensions(body), 70)

    def test_rest_count_spread_within_one(self):
        # AC-K6: pairs rest within one of each other where arithmetic allows.
        for players_n, courts, pairs_n, meetings in ((12, 2, 6, 1), (10, 2, 5, 2), (16, 3, 8, 1)):
            with self.subTest(config=f"{pairs_n}p/{courts}c x{meetings}"):
                _, _, response, _ = _generate(players_n, courts, pairs_n, meetings=meetings, seed=1)
                body = response.json()
                rests = list(body["rest_counts"].values())
                self.assertLessEqual(max(rests) - min(rests), 1)

    def test_seed_variety_and_determinism(self):
        # AC-K7: round-1 resting pairs vary by seed; same seed is identical.
        round1 = set()
        for seed in (1, 2, 3, 4, 5):
            _, _, response, _ = _generate(12, 2, 6, meetings=1, seed=seed)
            round1.add(tuple(sorted(response.json()["rounds"][0]["resting"])))
        self.assertGreaterEqual(len(round1), 2, "round-1 resters must vary by seed")

        _, _, first, _ = _generate(12, 2, 6, meetings=1, seed=42)
        _, _, second, _ = _generate(12, 2, 6, meetings=1, seed=42)
        self.assertEqual(first.json()["rounds"], second.json()["rounds"])

    def test_play_twice_rematches_never_consecutive(self):
        for players_n, courts, pairs_n in ((12, 2, 6), (10, 2, 5)):
            for seed in (1, 2):
                with self.subTest(config=f"{pairs_n}p/{courts}c", seed=seed):
                    _, pairs, response, _ = _generate(
                        players_n, courts, pairs_n, meetings=2, seed=seed
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(_adjacent_rematches(response.json(), pairs), 0)


class FriendlyTests(_LeagueTest):
    """AC-F1, AC-F2, AC-F3 (API flag; UI labels land in PR3)."""

    def test_friendly_fills_only_the_spare_slot(self):
        players, pairs, response, _ = _generate(12, 2, 6, meetings=1, seed=1)
        body = response.json()
        friendly_rounds = [
            r for r in body["rounds"]
            if any(c.get("friendly") for c in r["courts"])
        ]
        self.assertEqual(len(friendly_rounds), 1)
        friendly_round = friendly_rounds[0]
        flagged = [c for c in friendly_round["courts"] if c.get("friendly")]
        self.assertEqual(len(flagged), 1)
        # The friendly sits alongside exactly one league match (the spare
        # slot), and its players are on court, not resting.
        league = [c for c in friendly_round["courts"] if not c.get("friendly")]
        self.assertEqual(len(league), 1)
        on_court = {
            p for c in friendly_round["courts"]
            for p in list(c["team_a"]) + list(c["team_b"])
        }
        for p in on_court:
            self.assertNotIn(p, friendly_round["resting"])
        # 6 pairs - 2 league - 2 friendly = 2 resting.
        self.assertEqual(len(friendly_round["resting"]), 4)

    def test_friendly_goes_to_most_rested_pairs(self):
        # AC-F2/D4: the friendly pair-teams are the pairs with the most
        # league rests so far (then fewest games; seeded tie-break).
        players, pairs, response, _ = _generate(12, 2, 6, meetings=1, seed=1)
        body = response.json()
        pair_of = {p: pair for pair in pairs for p in pair}
        league_rests = Counter()
        friendly_round_index = None
        for index, r in enumerate(body["rounds"]):
            if any(c.get("friendly") for c in r["courts"]):
                friendly_round_index = index
                break
            for p in r["resting"]:
                league_rests[pair_of[p]] += 1
        self.assertIsNotNone(friendly_round_index)
        friendly_pairs = {
            frozenset(c["team_a"]) if c.get("friendly") else frozenset(c["team_b"])
            for c in body["rounds"][friendly_round_index]["courts"] if c.get("friendly")
        }
        # Recompute: pairs idle from league play that round.
        playing = set()
        for c in body["rounds"][friendly_round_index]["courts"]:
            if not c.get("friendly"):
                playing.update(c["team_a"] + c["team_b"])
        idle = [pair for pair in pairs if not any(p in playing for p in pair)]
        max_rests = max(league_rests[pair] for pair in idle)
        for team in friendly_pairs:
            pair = tuple(sorted(team))
            self.assertEqual(
                league_rests[pair], max_rests,
                "friendly must go to the most-rested idle pairs",
            )

    def test_friendly_flag_roundtrip_shape(self):
        players, pairs, response, _ = _generate(14, 2, 7, meetings=1, seed=3)
        body = response.json()
        flagged = sum(1 for r in body["rounds"] for c in r["courts"] if c.get("friendly"))
        self.assertEqual(flagged, 1)  # 21 matches / 2 courts = 11 rounds, 1 spare


class LeaguePerformanceTests(_LeagueTest):
    """AC-P1: worst configuration stays under the 10s budget."""

    def test_worst_config_under_budget(self):
        _, _, response, elapsed = _generate(16, 2, 8, meetings=1, seed=1)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertLess(elapsed, 10.0, f"generation took {elapsed:.1f}s")


if __name__ == "__main__":
    unittest.main()
