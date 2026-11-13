"""Scoring regression tests (Bucket A fixes H-03, M-11).

Covers score-write behavior: batched updates on fresh courts and the
bounds on accepted score values. Each class maps to one fix PR and must
fail before that fix lands (run the class on the parent branch to see it
red).

Run from backend/:

    venv/bin/python -m unittest test_regressions_scoring -v
"""

import unittest

import regression_support  # noqa: F401  (env setup before app import)
from regression_support import (
    create_round_robin_session,
    get_session,
    post_action,
)

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402


class BatchScoreFreshCourtTests(unittest.TestCase):
    """H-03: a batch containing both teams of a court with no stored row.

    Before the fix, the second update in the batch could not see the first
    update's unflushed insert, so it inserted a duplicate primary key and the
    whole batch failed with 500 and no scores stored.
    """

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_batch_with_both_teams_on_fresh_court_stores_both_scores(self):
        session = create_round_robin_session(self.client, name="H03 Batch Fresh Court")
        started = post_action(
            self.client, session, "start-round", {"stage": "league", "round_index": 0}
        )
        self.assertEqual(started.status_code, 200, started.text)

        batch = post_action(
            self.client,
            session,
            "scores/batch",
            {
                "stage": "league",
                "round_index": 0,
                "updates": [
                    {
                        "stage": "league",
                        "round_index": 0,
                        "court_index": 0,
                        "team_key": "teamA",
                        "value": 21,
                    },
                    {
                        "stage": "league",
                        "round_index": 0,
                        "court_index": 0,
                        "team_key": "teamB",
                        "value": 15,
                    },
                ],
            },
        )
        self.assertEqual(batch.status_code, 200, batch.text)

        detail = get_session(self.client, session)
        self.assertEqual(detail.status_code, 200)
        scores = detail.json()["league_scores_by_round"][0][0]
        self.assertEqual(scores, {"teamA": 21, "teamB": 15})

    def test_single_write_then_batch_still_works(self):
        session = create_round_robin_session(self.client, name="H03 Single Then Batch")
        post_action(
            self.client, session, "start-round", {"stage": "league", "round_index": 0}
        )
        first = post_action(
            self.client,
            session,
            "score",
            {
                "stage": "league",
                "round_index": 0,
                "court_index": 0,
                "team_key": "teamA",
                "value": 21,
            },
        )
        self.assertEqual(first.status_code, 200, first.text)

        batch = post_action(
            self.client,
            session,
            "scores/batch",
            {
                "stage": "league",
                "round_index": 0,
                "updates": [
                    {
                        "stage": "league",
                        "round_index": 0,
                        "court_index": 0,
                        "team_key": "teamA",
                        "value": 21,
                    },
                    {
                        "stage": "league",
                        "round_index": 0,
                        "court_index": 0,
                        "team_key": "teamB",
                        "value": 15,
                    },
                ],
            },
        )
        self.assertEqual(batch.status_code, 200, batch.text)
        scores = get_session(self.client, session).json()["league_scores_by_round"][0][0]
        self.assertEqual(scores, {"teamA": 21, "teamB": 15})

    def test_round_can_be_ended_after_fresh_court_batch(self):
        session = create_round_robin_session(self.client, name="H03 Batch Then End")
        post_action(
            self.client, session, "start-round", {"stage": "league", "round_index": 0}
        )
        batch = post_action(
            self.client,
            session,
            "scores/batch",
            {
                "stage": "league",
                "round_index": 0,
                "updates": [
                    {
                        "stage": "league",
                        "round_index": 0,
                        "court_index": 0,
                        "team_key": "teamA",
                        "value": 21,
                    },
                    {
                        "stage": "league",
                        "round_index": 0,
                        "court_index": 0,
                        "team_key": "teamB",
                        "value": 15,
                    },
                ],
            },
        )
        self.assertEqual(batch.status_code, 200, batch.text)
        ended = post_action(
            self.client, session, "end-round", {"stage": "league", "round_index": 0}
        )
        self.assertEqual(ended.status_code, 200, ended.text)
        self.assertTrue(ended.json()["ended_league_rounds"][0])


class ScoreBoundsTests(unittest.TestCase):
    """M-11: score values must be bounded integers.

    Negative, oversized, and overflow values were accepted (or 500'd on
    int overflow); the UI silently clamped negatives to 0 so the screen and
    the server disagreed on what was stored.
    """

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def _score(self, session, value):
        return post_action(
            self.client,
            session,
            "score",
            {"stage": "league", "round_index": 0, "court_index": 0, "team_key": "teamA", "value": value},
        )

    def test_negative_score_rejected(self):
        session = create_round_robin_session(self.client, name="M11 Negative")
        post_action(self.client, session, "start-round", {"stage": "league", "round_index": 0})
        response = self._score(session, -5)
        self.assertEqual(response.status_code, 422, response.text)

    def test_overflow_score_rejected(self):
        session = create_round_robin_session(self.client, name="M11 Overflow")
        post_action(self.client, session, "start-round", {"stage": "league", "round_index": 0})
        response = self._score(session, 10**20)
        self.assertEqual(response.status_code, 422, response.text)

    def test_score_above_cap_rejected(self):
        session = create_round_robin_session(self.client, name="M11 Above Cap")
        post_action(self.client, session, "start-round", {"stage": "league", "round_index": 0})
        response = self._score(session, 100)
        self.assertEqual(response.status_code, 422, response.text)

    def test_boundary_scores_accepted(self):
        session = create_round_robin_session(self.client, name="M11 Boundaries")
        post_action(self.client, session, "start-round", {"stage": "league", "round_index": 0})
        for value in (0, 99):
            response = self._score(session, value)
            self.assertEqual(response.status_code, 200, f"value {value}: {response.text}")

    def test_clearing_a_score_still_allowed(self):
        session = create_round_robin_session(self.client, name="M11 Clear")
        post_action(self.client, session, "start-round", {"stage": "league", "round_index": 0})
        self.assertEqual(self._score(session, 21).status_code, 200)
        response = self._score(session, None)
        self.assertEqual(response.status_code, 200, response.text)
        scores = get_session(self.client, session).json()["league_scores_by_round"][0][0]
        self.assertEqual(scores["teamA"], "")

    def test_batch_rejects_out_of_range_value(self):
        session = create_round_robin_session(self.client, name="M11 Batch")
        post_action(self.client, session, "start-round", {"stage": "league", "round_index": 0})
        batch = post_action(
            self.client,
            session,
            "scores/batch",
            {
                "stage": "league",
                "round_index": 0,
                "updates": [
                    {"stage": "league", "round_index": 0, "court_index": 0, "team_key": "teamA", "value": 150},
                ],
            },
        )
        self.assertEqual(batch.status_code, 422, batch.text)


if __name__ == "__main__":
    unittest.main()
