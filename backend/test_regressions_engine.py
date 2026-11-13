"""Roster engine regression tests (Bucket A fixes L-02, H-05).

Covers RNG isolation for seeded generation and per-round player
completeness invariants. These test the engine module directly, without
the HTTP app. Each class maps to one fix PR and must fail before that fix
lands (run the class on the parent branch to see it red).

Run from backend/:

    venv/bin/python -m unittest test_regressions_engine -v
"""

import unittest


class SeededRngIsolationTests(unittest.TestCase):
    """L-02: seeded generation must not reseed the process-global RNG.

    generate_roster called random.seed(seed) on the global module, so
    concurrent seeded requests interleaved each other's draws (only 5 of 12
    concurrent same-seed runs matched the serial result) and every other
    random consumer in the process got silently reseeded.
    """

    def test_seeded_generation_does_not_reseed_the_global_rng(self):
        import random as random_module

        from roster_engine import generate_roster

        players = [f"P{i}" for i in range(8)]
        common = dict(
            num_courts=2,
            num_rounds=2,
            consecutive_limits={},
            fixed_pairs=[],
        )

        generate_roster(players, seed=1, **common)
        first_draw = random_module.random()
        generate_roster(players, seed=1, **common)
        second_draw = random_module.random()
        self.assertNotEqual(
            first_draw,
            second_draw,
            "global RNG was reseeded by seeded generation: both draws identical",
        )

    def test_same_seed_still_produces_identical_rosters(self):
        from roster_engine import generate_roster

        players = [f"P{i}" for i in range(8)]
        common = dict(
            num_courts=2,
            num_rounds=2,
            consecutive_limits={},
            fixed_pairs=[],
            seed=42,
        )

        first_rounds, _, _, _ = generate_roster(players, **common)
        second_rounds, _, _, _ = generate_roster(players, **common)
        self.assertEqual(first_rounds, second_rounds)


class EngineCompletenessTests(unittest.TestCase):
    """H-05: every player is playing or resting exactly once per round.

    With 9 players on 1 court, the rest selector could return fewer than the
    required 5 resters (cannot_rest thinned the candidates); the surplus
    'playing' players then vanished in the court builder - neither on a
    court nor resting - while rest_counts still claimed perfectly balanced
    rest. Field-observed with seed 42: rounds 2, 4 and 6 each lost a player.
    """

    def test_every_player_accounted_for_exactly_once_per_round(self):
        from roster_engine import generate_roster

        players = [f"P{i}" for i in range(9)]
        rounds, rest_counts, _, _ = generate_roster(
            players,
            num_courts=1,
            num_rounds=6,
            consecutive_limits={},
            fixed_pairs=[],
            max_consecutive_rest=1,
            seed=42,
        )

        for round_data in rounds:
            on_courts = [
                player
                for team_a, team_b in round_data["courts"]
                for player in list(team_a) + list(team_b)
            ]
            accounted = on_courts + round_data["resting"]
            self.assertEqual(
                sorted(accounted),
                sorted(players),
                f"round {round_data['round']} dropped or duplicated a player",
            )
            self.assertEqual(len(on_courts), 4, f"round {round_data['round']} must field exactly 4 players on 1 court")

        self.assertEqual(sum(rest_counts.values()), 6 * 5, "rest slots must total rounds * resting-per-round")

    def test_completeness_across_other_odd_shapes(self):
        from roster_engine import generate_roster

        for player_count, courts, num_rounds in ((7, 1, 5), (10, 2, 6), (13, 3, 7), (6, 1, 4)):
            players = [f"P{i}" for i in range(player_count)]
            rounds, _, _, _ = generate_roster(
                players,
                num_courts=courts,
                num_rounds=num_rounds,
                consecutive_limits={},
                fixed_pairs=[],
                max_consecutive_rest=1,
                seed=7,
            )
            for round_data in rounds:
                on_courts = [
                    player
                    for team_a, team_b in round_data["courts"]
                    for player in list(team_a) + list(team_b)
                ]
                accounted = on_courts + round_data["resting"]
                self.assertEqual(
                    sorted(accounted),
                    sorted(players),
                    f"{player_count}p/{courts}c round {round_data['round']} dropped or duplicated a player",
                )
                self.assertEqual(len(on_courts), courts * 4)


if __name__ == "__main__":
    unittest.main()
