import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from roster_engine import (
    find_duplicate_fixed_pair_matchups,
    generate_fixed_pair_knockout_roster,
    generate_roster,
)


def matchup_counts(rounds):
    counts = {}
    for round_data in rounds:
        for team_a, team_b in round_data["courts"]:
            key = tuple(sorted((tuple(sorted(team_a)), tuple(sorted(team_b)))))
            counts[key] = counts.get(key, 0) + 1
    return counts


class KnockoutFixedPairTests(unittest.TestCase):
    def test_generates_single_meeting_schedule_for_four_fixed_pairs(self):
        players = ["A", "B", "C", "D", "E", "F", "G", "H"]
        fixed_pairs = [("A", "B"), ("C", "D"), ("E", "F"), ("G", "H")]

        rounds, rest_counts, fixed_pair_counts, warnings, _ = generate_fixed_pair_knockout_roster(
            players=players,
            fixed_pairs=fixed_pairs,
            num_courts=2,
            num_rounds=3,
            pair_target=3,
            league_meetings=1,
        )

        self.assertEqual(len(rounds), 3)
        self.assertEqual(warnings, [])
        self.assertTrue(all(rested == 0 for rested in rest_counts.values()))
        self.assertEqual(set(fixed_pair_counts.values()), {3})
        self.assertTrue(all(count == 1 for count in matchup_counts(rounds).values()))
        self.assertEqual(find_duplicate_fixed_pair_matchups(rounds, fixed_pairs), [])

    def test_generates_odd_team_schedule_without_duplicate_opponents(self):
        players = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
        fixed_pairs = [("A", "B"), ("C", "D"), ("E", "F"), ("G", "H"), ("I", "J")]

        rounds, rest_counts, fixed_pair_counts, warnings, _ = generate_fixed_pair_knockout_roster(
            players=players,
            fixed_pairs=fixed_pairs,
            num_courts=2,
            num_rounds=5,
            pair_target=4,
            league_meetings=1,
        )

        self.assertEqual(len(rounds), 5)
        self.assertEqual(warnings, [])
        self.assertEqual(set(rest_counts.values()), {1})
        self.assertEqual(set(fixed_pair_counts.values()), {4})
        self.assertEqual(len(matchup_counts(rounds)), 10)
        self.assertTrue(all(count == 1 for count in matchup_counts(rounds).values()))
        self.assertEqual(find_duplicate_fixed_pair_matchups(rounds, fixed_pairs), [])

    def test_generates_multiple_meetings_for_fixed_pair_knockout(self):
        players = ["A", "B", "C", "D", "E", "F", "G", "H"]
        fixed_pairs = [("A", "B"), ("C", "D"), ("E", "F"), ("G", "H")]

        rounds, _, fixed_pair_counts, _, _ = generate_fixed_pair_knockout_roster(
            players=players,
            fixed_pairs=fixed_pairs,
            num_courts=2,
            num_rounds=6,
            pair_target=6,
            league_meetings=2,
        )

        self.assertEqual(len(rounds), 6)
        self.assertEqual(set(fixed_pair_counts.values()), {6})
        self.assertTrue(all(count == 2 for count in matchup_counts(rounds).values()))

    def test_duplicate_matchup_validator_flags_repeated_knockout_pairings(self):
        fixed_pairs = [("A", "B"), ("C", "D"), ("E", "F"), ("G", "H")]
        rounds = [
            {"round": 1, "courts": [(("A", "B"), ("C", "D")), (("E", "F"), ("G", "H"))], "resting": []},
            {"round": 2, "courts": [(("A", "B"), ("C", "D")), (("E", "F"), ("G", "H"))], "resting": []},
        ]

        violations = find_duplicate_fixed_pair_matchups(rounds, fixed_pairs)

        self.assertEqual(len(violations), 2)
        self.assertTrue(all(violation.startswith("Duplicate knockout matchup:") for violation in violations))

    def test_plain_round_robin_generator_remains_available(self):
        rounds, _, _, _ = generate_roster(
            players=["A", "B", "C", "D"],
            num_courts=1,
            num_rounds=1,
            consecutive_limits={},
            fixed_pairs=[],
            pair_target=1,
            max_consecutive_rest=1,
            pair_start_round=1,
            seed=1,
        )

        self.assertEqual(len(rounds), 1)


if __name__ == "__main__":
    unittest.main()
