"""Request validation regression tests (Bucket A fixes M-02, M-15, M-16, M-18a, M-22a).

Covers malformed input on /api/generate, /api/sessions, and /api/players:
duplicates, empty/oversized values, and pair-key delimiters in names must
all get clean 422s instead of silent acceptance or raw 500s. This class
maps to the validation fix wave and must fail before that fix lands.

Run from backend/:

    venv/bin/python -m unittest test_regressions_validation -v
"""

import unittest

import regression_support  # noqa: F401  (env setup before app import)
from regression_support import generate_roster

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402


class RequestValidationTests(unittest.TestCase):
    """M-02/M-15/M-16/M-18a/M-22a: malformed input must get clean 422s.

    Before this fix wave, duplicate players were silently accepted (a player
    could appear on both teams of the same match), empty/oversized inputs
    returned raw 500s from unhandled pydantic errors inside handlers, and
    names containing ' & ' or '/' silently corrupted pair keys.
    """

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def _generate_raw(self, **overrides):
        payload = {
            "players": ["A", "B", "C", "D"],
            "fixed_pairs": [],
            "num_courts": 1,
            "court_numbers": ["1"],
            "rounds": 1,
            "limits": {},
            "pair_games": 1,
            "pair_start_round": 5,
            "max_consecutive_rest": 1,
        }
        payload.update(overrides)
        return self.client.post("/api/generate", json=payload)

    def _create_raw(self, roster, **overrides):
        payload = {
            "name": "Validation Wave",
            "roster": roster,
            "draw_config": {"draw_type": "round_robin", "league_meetings": 1, "knockout_qualifiers": 4},
            "selected_players": [],
            "fixed_pairs": [],
            "limits": {},
            "pair_games": 1,
            "pair_start_round": 5,
            "max_consecutive_rest": 1,
            "admin_token": "thisismytoken",
        }
        payload.update(overrides)
        return self.client.post("/api/sessions", json=payload)

    def test_generate_rejects_duplicate_player_names(self):
        response = self._generate_raw(players=["A", "A", "B", "C"])
        self.assertEqual(response.status_code, 422, response.text)

    def test_generate_rejects_empty_string_player(self):
        response = self._generate_raw(players=["A", "", "C", "D"])
        self.assertEqual(response.status_code, 422, response.text)

    def test_generate_rejects_zero_rounds(self):
        response = self._generate_raw(rounds=0)
        self.assertEqual(response.status_code, 422, response.text)

    def test_generate_rejects_oversized_rounds(self):
        response = self._generate_raw(rounds=10000)
        self.assertEqual(response.status_code, 422, response.text)

    def test_generate_rejects_zero_courts(self):
        response = self._generate_raw(num_courts=0)
        self.assertEqual(response.status_code, 422, response.text)

    def test_generate_rejects_pair_delimiter_in_player_name(self):
        response = self._generate_raw(players=["Tom & Jerry", "B", "C", "D"])
        self.assertEqual(response.status_code, 422, response.text)

    def test_session_create_rejects_empty_roster_rounds(self):
        roster = generate_roster(self.client)
        roster["rounds"] = []
        response = self._create_raw(roster)
        self.assertEqual(response.status_code, 422, response.text)

    def test_session_create_rejects_empty_court_numbers(self):
        roster = generate_roster(self.client)
        roster["court_numbers"] = []
        response = self._create_raw(roster)
        self.assertEqual(response.status_code, 422, response.text)

    def test_session_create_rejects_oversized_name(self):
        roster = generate_roster(self.client)
        response = self._create_raw(roster, name="x" * 121)
        self.assertEqual(response.status_code, 422, response.text)

    def test_session_create_rejects_duplicate_player_in_round(self):
        roster = generate_roster(self.client)
        roster["rounds"][0]["courts"][0]["team_a"][1] = roster["rounds"][0]["courts"][0]["team_a"][0]
        response = self._create_raw(roster)
        self.assertIn(response.status_code, (409, 422), response.text)

    def test_session_create_rejects_odd_knockout_qualifiers(self):
        roster = generate_roster(self.client, players=["A", "B", "C", "D", "E", "F", "G", "H"], num_courts=2, court_numbers=["1", "2"], rounds=3)
        draw = {"draw_type": "league_knockout", "league_meetings": 1, "knockout_qualifiers": 3}
        response = self._create_raw(roster, draw_config=draw, fixed_pairs=[["A", "B"], ["C", "D"], ["E", "F"], ["G", "H"]])
        self.assertEqual(response.status_code, 422, response.text)

    def test_session_create_rejects_qualifiers_above_pair_count(self):
        roster = generate_roster(self.client)
        draw = {"draw_type": "league_knockout", "league_meetings": 1, "knockout_qualifiers": 4}
        response = self._create_raw(roster, draw_config=draw, fixed_pairs=[["A", "B"], ["C", "D"]])
        self.assertEqual(response.status_code, 422, response.text)

    def test_session_create_accepts_valid_request(self):
        response = self._create_raw(generate_roster(self.client))
        self.assertEqual(response.status_code, 200, response.text)

    def test_player_create_rejects_lone_surrogate(self):
        # Send the raw JSON escape so the server-side parser materializes the
        # lone surrogate (a well-behaved JSON encoder would refuse it).
        response = self.client.post(
            "/api/players",
            content='{"full_name":"\\ud800","short_name":"S1"}',
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 422, response.text)

    def test_player_create_rejects_pair_delimiters_in_short_name(self):
        import uuid

        tag = uuid.uuid4().hex[:8]
        for short_name in (f"A & B {tag}", f"A/B {tag}"):
            response = self.client.post(
                "/api/players",
                json={"full_name": f"Delimiter Player {tag}", "short_name": short_name},
            )
            self.assertEqual(response.status_code, 422, f"{short_name!r} must be rejected: {response.text}")

    def test_player_create_strips_control_characters(self):
        import uuid

        tag = uuid.uuid4().hex[:8]
        response = self.client.post(
            "/api/players",
            json={"full_name": f"NUL\x00Name {tag}", "short_name": f"NUL\x00{tag}"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertNotIn("\x00", body["full_name"] + body["short_name"])


if __name__ == "__main__":
    unittest.main()
