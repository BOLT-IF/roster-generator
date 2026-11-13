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


def _team_key(a, b):
    """Order-independent key for a matchup of two teams."""
    x, y = tuple(sorted(a)), tuple(sorted(b))
    return (x, y) if x <= y else (y, x)


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
        # 10 players in 5 pairs, 2 courts, unreachable together-target: the
        # pair never dissolves, so whoever rests, rests as a whole pair.
        players = [f"U{i}" for i in range(1, 11)]
        pairs = [(players[i], players[i + 1]) for i in range(0, 10, 2)]
        rounds, _, _, _ = generate_roster(
            players, 2, 13, {}, pairs,
            pair_target=20, max_consecutive_rest=1, pair_start_round=1, seed=11,
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


class PairDissolutionTests(unittest.TestCase):
    """C-1 v2: a pair dissolves once it completes its pair_games target.

    After the target the two players are independent for courts AND rests
    ("open to be random"); accidental re-pairing on a court is allowed.
    Before the target (and in pure-pair sessions where the target is never
    reached) the pair stays one rest unit - covered by RestFairnessTests.
    """

    def test_pairs_dissolve_after_target(self):
        # 14 players, 3 courts, 3 pairs targeting 4 games together: the
        # pairs complete around round 5 and dissolve for the rest of the
        # session.
        players = [f"V{i}" for i in range(1, 15)]
        pairs = [(players[i], players[i + 1]) for i in range(0, 6, 2)]
        for seed in (1, 2, 3):
            with self.subTest(seed=seed):
                rounds, rest_counts, fpc, warnings = generate_roster(
                    players, 3, 13, {}, pairs,
                    pair_target=4, max_consecutive_rest=1, pair_start_round=1, seed=seed,
                )
                for pair, count in fpc.items():
                    self.assertTrue(
                        4 <= count <= 5,
                        f"{pair} played together {count}x (target 4)",
                    )
                # After dissolution, members rest independently: some later
                # round rests exactly one member of a completed pair.
                completed = [p for p in pairs if fpc.get(p, 0) >= 4]
                independent_rests = 0
                for r in rounds:
                    if r["round"] <= 6:
                        continue
                    resting = set(r["resting"])
                    for pair in completed:
                        if len(resting & set(pair)) == 1:
                            independent_rests += 1
                self.assertGreater(
                    independent_rests, 0,
                    "dissolved pair members must be able to rest alone",
                )
                # With pairs dissolved, everyone rotates: rest spread <= 1.
                vals = [rest_counts[p] for p in players]
                self.assertLessEqual(max(vals) - min(vals), 1)


class NoBackToBackRestPriorityTests(unittest.TestCase):
    """C-1 v3 §3 rule 2: no player rests consecutive rounds - highest
    scheduling priority. Zero violations whenever any schedule can avoid
    them (never traded for rest spread, co-rest, or matchup fairness), and
    the arithmetic minimum when unavoidable."""

    @staticmethod
    def _b2b_violations(rounds, max_consecutive_rest):
        violations = validate_roster(rounds, {}, max_consecutive_rest, [], {}, 1, 1)
        return sum(1 for v in violations if "rested" in v and "consecutive" in v)

    def test_zero_back_to_back_when_avoidable(self):
        # The fairness optimizer (spread, co-rest, matchups) runs fully on
        # these configs - none of it may ever cost a back-to-back rest.
        configs = [
            (12, 2, 13, "all"),   # Organiser shape
            (13, 3, 10, "none"),
            (18, 4, 10, "none"),
            (10, 2, 12, "none"),
            (16, 4, 10, "all"),
        ]
        for players_n, courts, rounds_n, mode in configs:
            if players_n - courts * 4 <= 0:
                continue
            with self.subTest(config=f"{players_n}p/{courts}c/{rounds_n}r/{mode}"):
                for seed in (1, 2, 3):
                    players = [f"N{seed}-{i}" for i in range(1, players_n + 1)]
                    pairs = (
                        [(players[i], players[i + 1]) for i in range(0, players_n - 1, 2)]
                        if mode == "all" else []
                    )
                    rounds, _, _, _ = generate_roster(
                        players, courts, rounds_n, {}, pairs,
                        pair_target=13, max_consecutive_rest=1, pair_start_round=1, seed=seed,
                    )
                    self.assertEqual(
                        self._b2b_violations(rounds, 1), 0,
                        "a player rested back-to-back although an avoiding schedule exists",
                    )

    def test_unavoidable_case_hits_arithmetic_floor(self):
        # 9 players, 1 court: 5 must rest but only 4 play, so at least
        # (5 - 4) = 1 rester repeats every round after the first. Over 6
        # rounds the minimum is exactly 5 back-to-back events - the engine
        # must hit that floor, not merely stay near it.
        players = [f"F{i}" for i in range(1, 10)]
        for seed in (1, 2, 3):
            with self.subTest(seed=seed):
                rounds, _, _, _ = generate_roster(
                    players, 1, 6, {}, [],
                    pair_target=1, max_consecutive_rest=1, pair_start_round=1, seed=seed,
                )
                self.assertEqual(self._b2b_violations(rounds, 1), 5)


class MatchupFairnessTests(unittest.TestCase):
    """AC-M1..M4: pair-vs-pair matchup balance (fixed pairs) and partner/
    opponent balance (rotating)."""

    @staticmethod
    def _pair_pair_keys(pairs):
        return [
            _team_key(frozenset(a), frozenset(b))
            for a, b in combinations(pairs, 2)
        ]

    @staticmethod
    def _matchup_counts(rounds, pairs):
        pairset = {frozenset(p) for p in pairs}
        counts = Counter()
        for r in rounds:
            for a, b in r["courts"]:
                ta, tb = frozenset(a), frozenset(b)
                if ta in pairset and tb in pairset:
                    counts[_team_key(ta, tb)] += 1
        return counts

    def test_ac_m1_organiser_matchup_spread_within_one_all_seeds(self):
        keys = self._pair_pair_keys(ORGANISER_PAIRS)
        for seed in range(1, 21):
            with self.subTest(seed=seed):
                rounds, _, _, _ = organiser_roster(seed=seed)
                counts = self._matchup_counts(rounds, ORGANISER_PAIRS)
                vals = [counts.get(k, 0) for k in keys]
                self.assertLessEqual(
                    max(vals) - min(vals),
                    1,
                    f"matchup spread {max(vals) - min(vals)} > 1; dist {sorted(Counter(vals).items())}",
                )

    def test_ac_m2_no_repeat_while_unused_matchup_exists(self):
        # On the Organiser config every matchup must be used before any
        # reaches its second meeting (26 matches over 15 matchups forces
        # 11 repeats, but no matchup may hit 2 while another sits at 0).
        keys = self._pair_pair_keys(ORGANISER_PAIRS)
        for seed in range(1, 21):
            with self.subTest(seed=seed):
                rounds, _, _, _ = organiser_roster(seed=seed)
                counts = self._matchup_counts(rounds, ORGANISER_PAIRS)
                vals = [counts.get(k, 0) for k in keys]
                if min(vals) == 0:
                    self.assertLessEqual(
                        max(vals),
                        1,
                        f"a matchup repeated while another was never used; dist {sorted(Counter(vals).items())}",
                    )

    def test_ac_m2_grid_pair_configs_matchup_spread(self):
        for players_n, courts, rounds_n, mode in GRID:
            if mode != "all" or players_n - courts * 4 <= 0:
                continue
            with self.subTest(config=f"{players_n}p/{courts}c/{rounds_n}r/{mode}"):
                players, courts_, rounds_, pairs, target = grid_config(players_n, courts, rounds_n, mode)
                rounds, _, _, warnings = generate_roster(
                    players, courts_, rounds_, {}, pairs,
                    pair_target=target, max_consecutive_rest=1, pair_start_round=1, seed=5,
                )
                counts = self._matchup_counts(rounds, pairs)
                keys = self._pair_pair_keys(pairs)
                vals = [counts.get(k, 0) for k in keys]
                s = spread(vals)
                self.assertTrue(
                    s <= 1 or has_rule(warnings, "matchup_spread"),
                    f"matchup spread {s} > 1 without a matchup_spread warning",
                )

    def test_ac_m3_rotating_partners_once_before_repeat_and_opponents_even(self):
        for players_n, courts, rounds_n in ((10, 2, 12), (12, 2, 13), (16, 3, 13), (8, 1, 6)):
            with self.subTest(config=f"{players_n}p/{courts}c/{rounds_n}r rotating"):
                players = [f"R{i}" for i in range(1, players_n + 1)]
                if players_n - courts * 4 <= 0:
                    continue
                rounds, _, _, warnings = generate_roster(
                    players, courts, rounds_n, {}, [],
                    pair_target=3, max_consecutive_rest=1, pair_start_round=5, seed=5,
                )
                # Partnerships: no repeat while an unused pairing exists.
                total_pairings = len(list(combinations(players, 2)))
                used, repeats_while_unused = set(), 0
                for r in rounds:
                    for a, b in r["courts"]:
                        for team in (a, b):
                            key = frozenset(team)
                            if key in used:
                                if len(used) < total_pairings:
                                    repeats_while_unused += 1
                            else:
                                used.add(key)
                self.assertTrue(
                    repeats_while_unused == 0 or has_rule(warnings, "partner_repeat"),
                    f"{repeats_while_unused} partnership repeats while unused pairings remained",
                )
                # Opponents: spread <= 2, or a matchup_spread warning.
                opp = Counter()
                for r in rounds:
                    for a, b in r["courts"]:
                        for x in a:
                            for y in b:
                                opp[tuple(sorted((x, y)))] += 1
                vals = [opp.get(tuple(sorted(x)), 0) for x in combinations(players, 2)]
                self.assertTrue(
                    spread(vals) <= 2 or has_rule(warnings, "matchup_spread"),
                    f"opponent spread {spread(vals)} > 2 without a matchup_spread warning",
                )

    def test_ac_m4_shorted_matchups_vary_by_seed(self):
        keys = self._pair_pair_keys(ORGANISER_PAIRS)
        shorted_sets = set()
        for seed in range(1, 21):
            rounds, _, _, _ = organiser_roster(seed=seed)
            counts = self._matchup_counts(rounds, ORGANISER_PAIRS)
            shorted_sets.add(frozenset(k for k in keys if counts.get(k, 0) == 1))
        self.assertGreaterEqual(
            len(shorted_sets),
            3,
            f"the shorted matchups must vary with the seed; got {len(shorted_sets)} distinct sets",
        )


class FairnessReportTests(unittest.TestCase):
    """AC-W1: /api/generate exposes a structured fairness report."""

    @classmethod
    def setUpClass(cls):
        import regression_support  # noqa: F401  (env setup before app import)
        from fastapi.testclient import TestClient
        from app import app
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def _generate(self, **overrides):
        payload = {
            "players": ORGANISER_PLAYERS,
            "fixed_pairs": [list(p) for p in ORGANISER_PAIRS],
            "num_courts": 2,
            "court_numbers": ["1", "2"],
            "rounds": 13,
            "limits": {},
            "pair_games": 13,
            "pair_start_round": 1,
            "max_consecutive_rest": 1,
            "seed": 1,
        }
        payload.update(overrides)
        response = self.client.post("/api/generate", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_fairness_object_shape_and_fields(self):
        body = self._generate()
        self.assertIn("fairness", body)
        fairness = body["fairness"]
        for key in ("rest_spread", "corest_spread", "matchup_spread"):
            self.assertIn(key, fairness)
            self.assertIsInstance(fairness[key], int)
        self.assertIn("issues", fairness)
        for issue in fairness["issues"]:
            self.assertIn("rule", issue)
            self.assertIn("summary", issue)
            self.assertIn("affected", issue)
            self.assertIsInstance(issue["affected"], list)

    def test_organiser_matchup_issue_marks_unavoidable(self):
        body = self._generate()
        matchup_issues = [i for i in body["fairness"]["issues"] if i["rule"] == "matchup_spread"]
        self.assertTrue(matchup_issues, "the Organiser config must carry a matchup issue (26 matches, 15 matchups)")
        issue = matchup_issues[0]
        self.assertTrue(issue.get("unavoidable"), "11x2 + 4x1 is arithmetically forced with 13 rounds")
        self.assertTrue(issue["affected"], "the issue must name the shorted matchups")
        # Backward compatibility: every issue also appears in warnings.
        for issue in body["fairness"]["issues"]:
            self.assertTrue(
                any(w.startswith(issue["rule"]) for w in body["warnings"]),
                f"warnings must still carry the {issue['rule']} string",
            )

    def test_rotating_report_is_well_formed_and_warns_honestly(self):
        # AC-M3's targets (opponent spread ≤2, partner-once) are not always
        # achievable per-run for rotating schedules; the spec requires the
        # report to say exactly what slipped. A clean run must have no
        # issues; an unclean run must carry well-formed issues from the
        # known rules, mirrored in warnings.
        body = self._generate(
            players=[f"C{i}" for i in range(1, 11)],
            fixed_pairs=[],
            pair_games=1,
            rounds=12,
        )
        fairness = body["fairness"]
        known_rules = {"rest_spread", "corest_spread", "rest_unit_split",
                       "matchup_spread", "partner_repeat"}
        for issue in fairness["issues"]:
            self.assertIn(issue["rule"], known_rules)
            self.assertIn("summary", issue)
            self.assertIn("affected", issue)
            self.assertIsInstance(issue["affected"], list)
            self.assertTrue(issue["affected"])
            # Backward compatibility: every issue also appears in warnings.
            self.assertTrue(
                any(w.startswith(issue["rule"]) for w in body["warnings"]),
                f"warnings must carry the {issue['rule']} string",
            )
        # A run that meets every target must report no issues at all.
        if not fairness["issues"]:
            self.assertLessEqual(fairness["rest_spread"], 1)
            self.assertLessEqual(fairness["corest_spread"], 1)
            self.assertLessEqual(fairness["matchup_spread"], 2)


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
