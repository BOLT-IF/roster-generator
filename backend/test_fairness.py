"""C-1 scheduling fairness acceptance tests (spec: C-1-REQUIREMENTS.md v1).

Written red-first against the pre-C-1 engine: AC-R2 (seed-dependent
round-1 resters) and AC-F3 (co-rest spread) fail on it. Every test maps to
a numbered acceptance criterion in the spec.

Run from backend/:

    venv/bin/python -m unittest test_fairness -v
"""

import random
import time
import unittest
from collections import Counter
from itertools import combinations

from roster_engine import generate_roster, validate_roster

ORGANISER_PLAYERS = [f"P{i}" for i in range(1, 13)]
ORGANISER_PAIRS = [(ORGANISER_PLAYERS[i], ORGANISER_PLAYERS[i + 1]) for i in range(0, 12, 2)]


def organiser_roster(seed=1):
    """The Organiser.pdf configuration: 12 players, 6 fixed pairs, 2 courts, 13 rounds."""
    return generate_roster(
        ORGANISER_PLAYERS,
        num_courts=2,
        num_rounds=13,
        consecutive_limits={},
        fixed_pairs=ORGANISER_PAIRS,
        pair_target=13,
        max_consecutive_rest=1,
        pair_start_round=1,
        seed=seed,
    )


# (players, courts, rounds, pairs_mode) — subset of the AC-PERF-1 grid
GRID = [
    (8, 1, 6, "none"),
    (8, 1, 6, "all"),
    (9, 1, 6, "mixed"),
    (10, 2, 13, "none"),
    (10, 2, 13, "all"),
    (12, 2, 13, "all"),
    (12, 2, 13, "half"),
    (16, 3, 13, "all"),
    (20, 4, 20, "all"),
    (24, 5, 20, "all"),
]


def grid_config(players_n, courts, rounds, mode):
    players = [f"G{i}" for i in range(1, players_n + 1)]
    if mode == "none":
        pairs = []
    elif mode == "all":
        pairs = [(players[i], players[i + 1]) for i in range(0, players_n - 1, 2)]
    else:  # half (rounded down, remainder unpaired)
        pairs = [(players[i], players[i + 1]) for i in range(0, (players_n // 2) - 1, 2)]
    pair_target = max(1, (4 * courts * rounds) // len(pairs)) if pairs else 3
    return players, courts, rounds, pairs, pair_target


def units_for(players, pairs):
    """Rest units for an all-session-active pair config (pair_start_round=1)."""
    units = [tuple(pair) for pair in pairs]
    paired = {p for pair in pairs for p in pair}
    units.extend((p,) for p in players if p not in paired)
    return units


def corest_spread(rounds, units):
    """Co-rest count spread over ALL unit pairs (unused pairs count 0)."""
    counts, unit_sets = corest_counts(rounds, units)
    n = len(unit_sets)
    values = [counts.get((i, j), 0) for i in range(n) for j in range(i + 1, n)]
    return spread(values)


def corest_counts(rounds, units):
    """Co-rest count for every pair of units (both fully resting in a round)."""
    counts = Counter()
    unit_sets = [frozenset(u) for u in units]
    for r in rounds:
        resting = set(r["resting"])
        for a, b in combinations(range(len(unit_sets)), 2):
            if unit_sets[a] <= resting and unit_sets[b] <= resting:
                counts[(a, b)] += 1
    return counts, unit_sets


def spread(values):
    vals = list(values)
    if not vals:
        return 0
    return max(vals) - min(vals)


def has_rule(warnings, rule):
    return any(w.startswith(rule) for w in warnings)


class FairnessDeterminismTests(unittest.TestCase):
    """AC-R1..R4: seeded, random-feeling, order-independent rest selection."""

    def test_ac_r1_same_seed_gives_identical_output(self):
        first = organiser_roster(seed=7)
        second = organiser_roster(seed=7)
        self.assertEqual(first, second)

    def test_ac_r2_round1_resters_depend_on_seed(self):
        round1_sets = {
            tuple(sorted(organiser_roster(seed=s)[0][0]["resting"]))
            for s in range(1, 21)
        }
        self.assertGreaterEqual(
            len(round1_sets),
            3,
            f"round-1 resters must vary with the seed; got {len(round1_sets)} distinct sets",
        )

    def test_ac_r3_player_order_does_not_change_fairness_metrics(self):
        base_players = list(ORGANISER_PLAYERS)
        shuffled = list(base_players)
        random.Random(123).shuffle(shuffled)
        pairs_shuffled = [
            (shuffled[base_players.index(a)], shuffled[base_players.index(b)])
            for a, b in ORGANISER_PAIRS
        ]

        runs = []
        for players, pairs in ((base_players, ORGANISER_PAIRS), (shuffled, pairs_shuffled)):
            rounds, rest_counts, _, _ = generate_roster(
                players, 2, 13, {}, pairs,
                pair_target=13, max_consecutive_rest=1, pair_start_round=1, seed=9,
            )
            units = units_for(players, pairs)
            runs.append((
                spread(rest_counts[p] for p in players),
                corest_spread(rounds, units),
            ))

        self.assertEqual(runs[0], runs[1], "fairness metrics must not depend on input player order")

    def test_ac_r4_null_seed_generations_differ(self):
        first = organiser_roster(seed=None)
        second = organiser_roster(seed=None)
        self.assertNotEqual(first[0], second[0])


class RestFairnessTests(unittest.TestCase):
    """AC-F1, AC-F2: rest-count spread and rest-as-unit."""

    def test_ac_f1_rest_count_spread_within_one_across_grid(self):
        for players_n, courts, rounds, mode in GRID:
            with self.subTest(config=f"{players_n}p/{courts}c/{rounds}r/{mode}"):
                players, courts_, rounds_, pairs, target = grid_config(players_n, courts, rounds, mode)
                _, rest_counts, _, warnings = generate_roster(
                    players, courts_, rounds_, {}, pairs,
                    pair_target=target, max_consecutive_rest=1, pair_start_round=1, seed=5,
                )
                s = spread(rest_counts[p] for p in players)
                self.assertTrue(
                    s <= 1 or has_rule(warnings, "rest_spread"),
                    f"rest-count spread {s} > 1 without a rest_spread warning",
                )

    def test_ac_f2_active_pairs_rest_as_a_unit(self):
        # 10 players in 5 pairs, 2 courts: whoever rests, rests as a whole pair.
        players = [f"U{i}" for i in range(1, 11)]
        pairs = [(players[i], players[i + 1]) for i in range(0, 10, 2)]
        rounds, _, _, _ = generate_roster(
            players, 2, 13, {}, pairs,
            pair_target=10, max_consecutive_rest=1, pair_start_round=1, seed=11,
        )
        pair_sets = {frozenset(p) for p in pairs}
        for r in rounds:
            resting = set(r["resting"])
            for pair in pair_sets:
                overlap = resting & pair
                self.assertTrue(
                    overlap in (frozenset(), pair),
                    f"round {r['round']}: pair {sorted(pair)} partially resting ({sorted(overlap)})",
                )

    def test_ac_f2_forced_split_emits_warning_and_keeps_completeness(self):
        # Three players in three different pairs are limited to 1 consecutive
        # game. Round 1 rests one pair; whichever limited players played must
        # rest in round 2 — that is two players from two different pairs for
        # only 2 rest slots, so no whole-pair rest set exists: the pairs must
        # split, and each split must be named with its round.
        players = [f"S{i}" for i in range(1, 11)]
        pairs = [(players[i], players[i + 1]) for i in range(0, 10, 2)]
        partner_of = {"S5": "S6", "S7": "S8", "S9": "S10"}
        limits = {"S5": 1, "S7": 1, "S9": 1}

        # Round 1 must rest a pair containing a limited player, otherwise the
        # third limited player's limit cannot hold with only 2 rest slots.
        for seed in range(1, 40):
            rounds, _, _, warnings = generate_roster(
                players, 2, 13, limits, pairs,
                pair_target=10, max_consecutive_rest=1, pair_start_round=1, seed=seed,
            )
            if set(rounds[0]["resting"]) & {"S5", "S7", "S9"}:
                break
        else:
            self.fail("no seed rested a limited player's pair in round 1")

        round2 = set(rounds[1]["resting"])
        forced = round2 & set(partner_of)
        self.assertTrue(forced, "sanity: limited players must rest in round 2")

        split_warnings = [w for w in warnings if w.startswith("rest_unit_split")]
        self.assertTrue(split_warnings, "forced split must be reported")
        joined = " ".join(split_warnings)
        self.assertIn("round 2", joined)
        for p in sorted(forced):
            self.assertIn(f"{p} & {partner_of[p]}", joined)

        violations = validate_roster(rounds, limits, 1, pairs, {}, 10, 1)
        consecutive = [v for v in violations if "consecutive" in v]
        self.assertEqual(consecutive, [], "limits must still hold after the split")


class CorestFairnessTests(unittest.TestCase):
    """AC-F3, AC-F4: co-rest spread and no back-to-back rest sets."""

    def test_ac_f3_organiser_golden_corest_spread_within_one(self):
        rounds, _, _, _ = organiser_roster(seed=1)
        units = units_for(ORGANISER_PLAYERS, ORGANISER_PAIRS)

        s = corest_spread(rounds, units)
        self.assertLessEqual(s, 1, f"co-rest spread {s} > 1 on the Organiser config")

        rest_groups = {tuple(sorted(r["resting"])) for r in rounds}
        self.assertGreaterEqual(
            len(rest_groups),
            13,
            f"13 rounds should use 13 distinct rest groupings; got {len(rest_groups)}",
        )

    def test_ac_f3_corest_spread_across_grid(self):
        for players_n, courts, rounds_n, mode in GRID:
            with self.subTest(config=f"{players_n}p/{courts}c/{rounds_n}r/{mode}"):
                players, courts_, rounds_, pairs, target = grid_config(players_n, courts, rounds_n, mode)
                if players_n - courts_ * 4 <= 0:
                    continue  # no rest slots in this config
                rounds, _, _, warnings = generate_roster(
                    players, courts_, rounds_, {}, pairs,
                    pair_target=target, max_consecutive_rest=1, pair_start_round=1, seed=5,
                )
                units = units_for(players, pairs)
                s = corest_spread(rounds, units)
                self.assertTrue(
                    s <= 1 or has_rule(warnings, "corest_spread"),
                    f"co-rest spread {s} > 1 without a corest_spread warning",
                )

    def test_ac_f4_no_back_to_back_identical_rest_sets(self):
        for players_n, courts, rounds_n, mode in GRID:
            with self.subTest(config=f"{players_n}p/{courts}c/{rounds_n}r/{mode}"):
                players, courts_, rounds_, pairs, target = grid_config(players_n, courts, rounds_n, mode)
                if players_n - courts_ * 4 <= 0:
                    continue
                rounds, _, _, _ = generate_roster(
                    players, courts_, rounds_, {}, pairs,
                    pair_target=target, max_consecutive_rest=1, pair_start_round=1, seed=3,
                )
                previous = None
                for r in rounds:
                    current = frozenset(r["resting"])
                    if previous is not None and current:
                        self.assertNotEqual(
                            current,
                            previous,
                            f"rounds {r['round'] - 1} and {r['round']} rest the identical set",
                        )
                    previous = current


class LimitPrecedenceTests(unittest.TestCase):
    """AC-L1, AC-L2: organizer limits beat fairness; slips produce warnings."""

    def test_ac_l1_limits_hold_across_grid(self):
        for players_n, courts, rounds_n, mode in GRID:
            with self.subTest(config=f"{players_n}p/{courts}c/{rounds_n}r/{mode}"):
                players, courts_, rounds_, pairs, target = grid_config(players_n, courts, rounds_n, mode)
                if players_n - courts_ * 4 <= 0:
                    continue
                # A limit of ceil(N/R) consecutive games is comfortably
                # satisfiable (rest capacity R*rounds/N >= rounds/(L+1)) while
                # still binding, so any breach is the scheduler's fault.
                num_resting = players_n - courts_ * 4
                limit = max(1, -(-players_n // num_resting))
                limits = {p: limit for p in players}
                # max_consecutive_rest must also be arithmetically possible:
                # resting share R/N <= m/(m+1)  =>  m >= ceil(R / (N - R)).
                max_rest = max(1, -(-num_resting // (players_n - num_resting)))
                rounds, _, _, _ = generate_roster(
                    players, courts_, rounds_, limits, pairs,
                    pair_target=target, max_consecutive_rest=max_rest, pair_start_round=1, seed=5,
                )
                violations = validate_roster(rounds, limits, max_rest, pairs, {}, target, 1)
                consecutive = [v for v in violations if "consecutive" in v]
                self.assertEqual(
                    consecutive,
                    [],
                    f"consecutive-game limits broken: {consecutive}",
                )

    def test_ac_l2_limit_forced_rest_spread_warns_with_names(self):
        # A player limited to 1 consecutive game must rest every other round,
        # far more than anyone else: the slip must be named in a warning.
        players = [f"L{i}" for i in range(1, 11)]
        pairs = [(players[i], players[i + 1]) for i in range(0, 10, 2)]
        limits = {"L1": 1}
        rounds, rest_counts, _, warnings = generate_roster(
            players, 2, 13, limits, pairs,
            pair_target=10, max_consecutive_rest=1, pair_start_round=1, seed=4,
        )
        s = spread(rest_counts[p] for p in players)
        self.assertGreater(s, 1, "sanity: the limit should force an uneven rest load here")
        rest_spread_warnings = [w for w in warnings if w.startswith("rest_spread")]
        self.assertTrue(rest_spread_warnings, "rest_spread warning missing")
        self.assertIn("L1", " ".join(rest_spread_warnings))


class FairnessPerformanceTests(unittest.TestCase):
    """AC-PERF-1 (smoke): the largest grid config stays far inside the budget."""

    def test_large_config_generates_within_budget(self):
        players = [f"B{i}" for i in range(1, 25)]
        pairs = [(players[i], players[i + 1]) for i in range(0, 24, 2)]
        start = time.monotonic()
        rounds, rest_counts, _, _ = generate_roster(
            players, 5, 20, {}, pairs,
            pair_target=8, max_consecutive_rest=1, pair_start_round=1, seed=2,
        )
        elapsed = time.monotonic() - start
        self.assertEqual(len(rounds), 20)
        self.assertLess(elapsed, 10, f"generation took {elapsed:.1f}s; budget is 10s")


if __name__ == "__main__":
    unittest.main()
