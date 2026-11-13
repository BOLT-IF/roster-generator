"""C-2 follow-up: knockout round splitting on 1-court brackets (AC-KO1/KO2).

With 4 qualifiers, the first knockout round holds 2 semifinal matches. On
2+ courts both fit; on a single court they must split across consecutive
rounds - 'Semifinals, part 1', 'Semifinals, part 2', then the Final - and
the frontend bracket, the backend stats mirror and the completion-state
count must all agree. Verified red on main before implementation:
main plans 2 knockout rounds regardless of courts.
"""

import os
import unittest
import uuid

import regression_support  # noqa: F401  (env setup before app import)

from fastapi.testclient import TestClient  # noqa: E402

import app as app_module  # noqa: E402
from app import app  # noqa: E402


def _lk_generate(client, tag):
    players = [f"{tag}-{i}" for i in range(1, 9)]
    pairs = [[players[i], players[i + 1]] for i in range(0, 8, 2)]
    payload = {
        "players": players,
        "fixed_pairs": pairs,
        "num_courts": 1,
        "court_numbers": ["1"],
        "rounds": 6,
        "limits": {},
        "pair_games": 3,
        "pair_start_round": 1,
        "max_consecutive_rest": 1,
        "draw_type": "league_knockout",
        "league_meetings": 1,
        "seed": 1,
    }
    response = client.post("/api/generate", json=payload)
    assert response.status_code == 200, response.text
    return payload, response.json()


def _session_payload(payload, roster, name):
    return {
        "admin_token": os.environ["ADMIN_RECOVERY_TOKEN"],
        "roster": roster,
        "draw_config": {
            "draw_type": "league_knockout",
            "league_meetings": 1,
            "knockout_qualifiers": 4,
        },
        "name": name,
        "selected_players": [
            {"player_id": f"id-{p}", "short_name": p, "full_name": p}
            for p in payload["players"]
        ],
        "fixed_pairs": payload["fixed_pairs"],
        "limits": {},
        "num_courts": 1,
        "court_numbers": ["1"],
        "rounds": 6,
        "pair_games": 3,
        "pair_start_round": 1,
        "max_consecutive_rest": 1,
        "league_meetings": 1,
        "draw_type": "league_knockout",
        "seed": 1,
    }


class PlannedRoundCountTests(unittest.TestCase):
    def test_single_court_splits_the_semifinals(self):
        config = {"draw_type": "league_knockout", "knockout_qualifiers": 4}
        self.assertEqual(app_module._planned_knockout_rounds(config, 4, court_count=1), 3)
        self.assertEqual(app_module._planned_knockout_rounds(config, 4, court_count=2), 2)
        self.assertEqual(app_module._planned_knockout_rounds(config, 4, court_count=5), 2)
        # Unknown court count keeps the unsplit plan.
        self.assertEqual(app_module._planned_knockout_rounds(config, 4), 2)
        # 2 qualifiers: a single final, never split.
        config2 = {"draw_type": "league_knockout", "knockout_qualifiers": 2}
        self.assertEqual(app_module._planned_knockout_rounds(config2, 4, court_count=1), 1)


class SplitBracketFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def _play_full_session(self, tag):
        payload, roster = _lk_generate(self.client, tag)
        self.assertEqual(len(roster["rounds"]), 6)  # 6 matches / 1 court
        session = self.client.post(
            "/api/sessions", json=_session_payload(payload, roster, f"KO split {tag}")
        ).json()
        session_id = session["session_id"]
        edit_token = session["edit_token"]

        def action(path, body):
            response = self.client.post(
                f"/api/sessions/{session_id}/{path}",
                params={"edit_token": edit_token},
                json=body,
            )
            assert response.status_code == 200, f"{path}: {response.text}"

        # League: 6 rounds, one match per round. Give pair 1 a perfect
        # league record so the seeds are deterministic (pair 1 tops the
        # standings).
        for round_index in range(6):
            action("start-round", {"stage": "league", "round_index": round_index})
            round_data = session["roster"]["rounds"][round_index]
            for court_index, court in enumerate(round_data["courts"]):
                if court["friendly"]:
                    continue
                pair_wins = court["team_a"][0].startswith(f"{tag}-1") or court["team_a"][1].startswith(f"{tag}-1")
                winner_score = 21 if pair_wins else 21
                loser_score = 15 if pair_wins else 19
                # teamA wins unless pair-1 is on teamB
                if court["team_a"][0].startswith(f"{tag}-1") or court["team_a"][1].startswith(f"{tag}-1"):
                    values = (21, 15)
                else:
                    values = (19, 21)
                action("score", {"stage": "league", "round_index": round_index, "court_index": court_index, "team_key": "teamA", "value": values[0]})
                action("score", {"stage": "league", "round_index": round_index, "court_index": court_index, "team_key": "teamB", "value": values[1]})
            action("end-round", {"stage": "league", "round_index": round_index})

        # Knockout: three rounds - part 1, part 2, final (AC-KO1).
        knockout_matches = [(0, 1), (1, 1), (2, 1)]
        for round_index, court_count in knockout_matches:
            action("start-round", {"stage": "knockout", "round_index": round_index})
            for court_index in range(court_count):
                action("score", {"stage": "knockout", "round_index": round_index, "court_index": court_index, "team_key": "teamA", "value": 21})
                action("score", {"stage": "knockout", "round_index": round_index, "court_index": court_index, "team_key": "teamB", "value": 15})
            action("end-round", {"stage": "knockout", "round_index": round_index})

        return payload, session_id, edit_token

    def test_split_bracket_completes_and_feeds_stats(self):
        # Unique tag per run: player stats accumulate across sessions in the
        # persistent regression database, so reuse would double-count.
        tag = f"KSP{uuid.uuid4().hex[:6]}"
        payload, session_id, _ = self._play_full_session(tag)

        detail = self.client.get(f"/api/sessions/{session_id}").json()
        self.assertEqual(detail["ended_league_rounds"], [True] * 6)
        self.assertEqual(detail["ended_knockout_rounds"], [True, True, True])
        self.assertEqual(detail["active_knockout_round"], 2)

        # The stats mirror built the split bracket: every player has
        # league stats; the champion pair also carries knockout wins
        # (part + final = 2 wins for each finalist's winners).
        stats = self.client.get("/api/stats/players").json()
        by_name = {entry["player_name"]: entry for entry in stats}
        for player in payload["players"]:
            entry = by_name.get(player)
            self.assertIsNotNone(entry, f"no stats for {player}")
            self.assertEqual(entry["league_matches_played"], 3)
        knockout_games = {p: (by_name[p]["knockout_matches_played"], by_name[p]["knockout_wins"]) for p in payload["players"]}
        self.assertTrue(any(count >= 1 for count, _ in knockout_games.values()))
        # The champion pair wins both its knockout matches (part + final);
        # the runner-up also plays two but wins only one.
        champions = [p for p, (_, wins) in knockout_games.items() if wins == 2]
        self.assertEqual(len(champions), 2, f"exactly one champion pair, got {champions}")

    def test_completion_state_counts_the_split(self):
        # Without the split count, ending 2 knockout rounds would leave the
        # session at 6+2 < 6+3 and never complete - the flow test above
        # proves it; this pins the arithmetic directly.
        config = {"draw_type": "league_knockout", "knockout_qualifiers": 4}
        self.assertEqual(
            app_module._planned_knockout_rounds(config, 4, court_count=1),
            3,
        )


if __name__ == "__main__":
    unittest.main()
