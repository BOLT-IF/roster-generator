"""C-2 PR2 acceptance tests: friendlies through sessions (AC-F4, D3, D7).

League+knockout sessions with derived rounds must start, friendlies must
survive normalization and never count toward standings, seeding or player
stats, and an unscored friendly must never block ending its round.
"""

import os
import unittest
import uuid

import regression_support  # noqa: F401  (env setup before app import)

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402


def _lk_generate(client, tag, seed=1):
    players = [f"{tag}-{i}" for i in range(1, 13)]
    pairs = [[players[i], players[i + 1]] for i in range(0, 12, 2)]
    payload = {
        "players": players,
        "fixed_pairs": pairs,
        "num_courts": 2,
        "court_numbers": ["1", "2"],
        "rounds": 30,  # stale on purpose: derived is 8 (AC-R3)
        "limits": {},
        "pair_games": 5,
        "pair_start_round": 1,
        "max_consecutive_rest": 1,
        "draw_type": "league_knockout",
        "league_meetings": 1,
        "seed": seed,
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
        "num_courts": 2,
        "court_numbers": ["1", "2"],
        "rounds": 30,  # stale request value; derived must win
        "pair_games": 5,
        "pair_start_round": 1,
        "max_consecutive_rest": 1,
        "league_meetings": 1,
        "draw_type": "league_knockout",
        "seed": 1,
    }


class FriendlySessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_lk_session_starts_with_derived_rounds_and_keeps_friendly(self):
        payload, roster = _lk_generate(self.client, "FK1")
        self.assertEqual(len(roster["rounds"]), 8)
        friendly_rounds = [
            r for r in roster["rounds"] if any(c["friendly"] for c in r["courts"])
        ]
        self.assertEqual(len(friendly_rounds), 1)

        response = self.client.post(
            "/api/sessions",
            json=_session_payload(payload, roster, "C-2 friendly session"),
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        # Derived rounds survive session start despite the stale request value.
        self.assertEqual(len(body["roster"]["rounds"]), 8)
        # The friendly flag survives into the stored session roster.
        stored_friendly = [
            c["friendly"]
            for r in body["roster"]["rounds"]
            for c in r["courts"]
            if c["friendly"]
        ]
        self.assertEqual(len(stored_friendly), 1)

    def test_revalidate_keeps_friendly_flag_and_derived_rounds(self):
        payload, roster = _lk_generate(self.client, "FK2")
        revalidate = {
            "roster": roster,
            "players": payload["players"],
            "fixed_pairs": payload["fixed_pairs"],
            "num_courts": 2,
            "court_numbers": ["1", "2"],
            "rounds": 30,  # stale; the derived 8 must be accepted
            "limits": {},
            "pair_games": 5,
            "pair_start_round": 1,
            "max_consecutive_rest": 1,
            "draw_type": "league_knockout",
            "league_meetings": 1,
            "seed": 1,
        }
        response = self.client.post("/api/rosters/revalidate", json=revalidate)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(body["rounds"]), 8)
        friendly = [c for r in body["rounds"] for c in r["courts"] if c["friendly"]]
        self.assertEqual(len(friendly), 1)

    def test_stats_exclude_friendly_scores(self):
        tag = f"FK3{uuid.uuid4().hex[:4]}"
        payload, roster = _lk_generate(self.client, tag)
        session = self.client.post(
            "/api/sessions",
            json=_session_payload(payload, roster, f"C-2 stats session {tag}"),
        ).json()

        def action(path, body):
            response = self.client.post(
                f"/api/sessions/{session['session_id']}/{path}",
                params={"edit_token": session["edit_token"]},
                json=body,
            )
            assert response.status_code == 200, f"{path}: {response.text}"

        # League: score every round; the friendly court gets a 21-0 blowout
        # so any leakage into stats is loud.
        for round_index in range(8):
            action("start-round", {"stage": "league", "round_index": round_index})
            round_data = session["roster"]["rounds"][round_index]
            for court_index, court in enumerate(round_data["courts"]):
                values = (21, 0) if court["friendly"] else (21, 15)
                action("score", {"stage": "league", "round_index": round_index, "court_index": court_index, "team_key": "teamA", "value": values[0]})
                action("score", {"stage": "league", "round_index": round_index, "court_index": court_index, "team_key": "teamB", "value": values[1]})
            action("end-round", {"stage": "league", "round_index": round_index})

        # Knockout: semifinals then final.
        for knockout_index, court_count in ((0, 2), (1, 1)):
            action("start-round", {"stage": "knockout", "round_index": knockout_index})
            for court_index in range(court_count):
                action("score", {"stage": "knockout", "round_index": knockout_index, "court_index": court_index, "team_key": "teamA", "value": 21})
                action("score", {"stage": "knockout", "round_index": knockout_index, "court_index": court_index, "team_key": "teamB", "value": 15})
            action("end-round", {"stage": "knockout", "round_index": knockout_index})

        stats = self.client.get("/api/stats/players").json()
        by_name = {entry["player_name"]: entry for entry in stats}
        # League-only counts: every pair plays exactly 5 league games in a
        # Play Once league (8 rounds, 15 matches, 1 friendly). The friendly
        # blowout (21-0) must not appear anywhere.
        for player in payload["players"]:
            entry = by_name.get(player)
            self.assertIsNotNone(entry, f"no stats for {player}")
            self.assertEqual(
                entry["league_matches_played"], 5,
                f"{player} league matches must exclude the friendly",
            )
            self.assertNotEqual(entry["league_point_difference"], 21)


if __name__ == "__main__":
    unittest.main()
