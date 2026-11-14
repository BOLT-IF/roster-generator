"""Session lifecycle regression tests (Bucket A fixes M-08a, M-07, M-06, L-07a.2).

Covers stats updates on reopen, round start/end guards, edit-round (re-open)
guards, and completed_at stability. Each class maps to one fix PR and must
fail before that fix lands (run the class on the parent branch to see it
red).

Run from backend/:

    venv/bin/python -m unittest test_regressions_sessions -v
"""

import unittest

import regression_support  # noqa: F401  (env setup before app import)
from regression_support import (
    create_round_robin_session,
    generate_roster,
    get_session,
    post_action,
)

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402


class ReopenedSessionStatsTests(unittest.TestCase):
    """M-08a: reopening a completed session must update the leaderboard.

    The session factory runs with autoflush=False; without an explicit flush
    between deleting a session's analytics rows and rebuilding the summary,
    the rebuild re-counted the rows it was about to delete and the stale
    totals (including championships) survived the reopen.
    """

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_reopening_completed_session_updates_leaderboard(self):
        import uuid

        tag = uuid.uuid4().hex[:8]
        players = [f"Ropen {tag} {i}" for i in range(4)]
        roster = generate_roster(self.client, players=players)
        session = create_round_robin_session(self.client, name=f"M08a Reopen {tag}", roster=roster)

        post_action(self.client, session, "start-round", {"stage": "league", "round_index": 0})
        post_action(
            self.client,
            session,
            "score",
            {"stage": "league", "round_index": 0, "court_index": 0, "team_key": "teamA", "value": 21},
        )
        post_action(
            self.client,
            session,
            "score",
            {"stage": "league", "round_index": 0, "court_index": 0, "team_key": "teamB", "value": 15},
        )
        ended = post_action(self.client, session, "end-round", {"stage": "league", "round_index": 0})
        self.assertEqual(ended.status_code, 200, ended.text)

        stats = self.client.get("/api/stats/players").json()
        before = {row["player_name"] for row in stats}
        self.assertTrue(set(players).issubset(before), f"players missing after completion: {set(players) - before}")

        reopened = post_action(self.client, session, "edit-round", {"stage": "league", "round_index": 0})
        self.assertEqual(reopened.status_code, 200, reopened.text)

        stats_after = self.client.get("/api/stats/players").json()
        after = {row["player_name"] for row in stats_after}
        self.assertFalse(
            set(players).intersection(after),
            f"reopened session still contributes to the leaderboard: {set(players).intersection(after)}",
        )


class RoundLifecycleTests(unittest.TestCase):
    """M-07: score writes require started rounds; only the active round ends.

    _validate_score_target checked 'ended' but not 'started', so scores
    could be pre-entered for rounds nobody had begun. end_round accepted any
    round index up to the active one, so after re-opening an earlier round it
    could be ended again out of order, leaving later rounds ended around a
    temporally inconsistent earlier one.
    """

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def _create_two_round_session(self, name):
        roster = generate_roster(
            self.client,
            players=["A", "B", "C", "D", "E", "F", "G", "H"],
            num_courts=2,
            court_numbers=["1", "2"],
            rounds=2,
        )
        return create_round_robin_session(self.client, name=name, roster=roster)

    def test_score_rejected_for_unstarted_round(self):
        session = self._create_two_round_session("M07 Unstarted Score")
        post_action(self.client, session, "start-round", {"stage": "league", "round_index": 0})
        response = post_action(
            self.client,
            session,
            "score",
            {"stage": "league", "round_index": 1, "court_index": 0, "team_key": "teamA", "value": 21},
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("started", response.json()["detail"].lower())

    def test_batch_rejected_for_unstarted_round(self):
        session = self._create_two_round_session("M07 Unstarted Batch")
        post_action(self.client, session, "start-round", {"stage": "league", "round_index": 0})
        batch = post_action(
            self.client,
            session,
            "scores/batch",
            {
                "stage": "league",
                "round_index": 1,
                "updates": [
                    {"stage": "league", "round_index": 1, "court_index": 0, "team_key": "teamA", "value": 21},
                ],
            },
        )
        self.assertEqual(batch.status_code, 409, batch.text)

    def test_only_the_active_round_can_be_ended(self):
        session = self._create_two_round_session("M07 Out Of Order End")
        post_action(self.client, session, "start-round", {"stage": "league", "round_index": 0})
        post_action(
            self.client,
            session,
            "score",
            {"stage": "league", "round_index": 0, "court_index": 0, "team_key": "teamA", "value": 21},
        )
        post_action(
            self.client,
            session,
            "score",
            {"stage": "league", "round_index": 0, "court_index": 0, "team_key": "teamB", "value": 15},
        )
        post_action(
            self.client,
            session,
            "score",
            {"stage": "league", "round_index": 0, "court_index": 1, "team_key": "teamA", "value": 21},
        )
        post_action(
            self.client,
            session,
            "score",
            {"stage": "league", "round_index": 0, "court_index": 1, "team_key": "teamB", "value": 15},
        )
        post_action(self.client, session, "end-round", {"stage": "league", "round_index": 0})
        post_action(self.client, session, "start-round", {"stage": "league", "round_index": 1})

        # Re-open round 0 (still allowed at this point in the stack) and try
        # to end it while round 1 is the active round.
        reopened = post_action(self.client, session, "edit-round", {"stage": "league", "round_index": 0})
        self.assertEqual(reopened.status_code, 200, reopened.text)
        response = post_action(self.client, session, "end-round", {"stage": "league", "round_index": 0})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("active", response.json()["detail"].lower())

    def test_scoring_and_ending_the_active_round_still_work(self):
        session = self._create_two_round_session("M07 Happy Path")
        post_action(self.client, session, "start-round", {"stage": "league", "round_index": 0})
        for court in range(2):
            post_action(
                self.client,
                session,
                "score",
                {"stage": "league", "round_index": 0, "court_index": court, "team_key": "teamA", "value": 21},
            )
            post_action(
                self.client,
                session,
                "score",
                {"stage": "league", "round_index": 0, "court_index": court, "team_key": "teamB", "value": 15},
            )
        ended = post_action(self.client, session, "end-round", {"stage": "league", "round_index": 0})
        self.assertEqual(ended.status_code, 200, ended.text)


class EditRoundGuardsTests(unittest.TestCase):
    """M-06: only the last ended league round re-opens; knockout wipes need confirm.

    Any ended league round could be re-opened, including earlier ones while
    later rounds stayed ended around it, and every re-open silently deleted
    all knockout rounds and scores with no confirmation.
    """

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def _complete_round_robin(self, name, rounds=2):
        roster = generate_roster(
            self.client,
            players=["A", "B", "C", "D", "E", "F", "G", "H"],
            num_courts=2,
            court_numbers=["1", "2"],
            rounds=rounds,
        )
        session = create_round_robin_session(self.client, name=name, roster=roster)
        for round_index in range(rounds):
            post_action(self.client, session, "start-round", {"stage": "league", "round_index": round_index})
            for court in range(2):
                post_action(
                    self.client,
                    session,
                    "score",
                    {"stage": "league", "round_index": round_index, "court_index": court, "team_key": "teamA", "value": 21},
                )
                post_action(
                    self.client,
                    session,
                    "score",
                    {"stage": "league", "round_index": round_index, "court_index": court, "team_key": "teamB", "value": 15},
                )
            ended = post_action(
                self.client, session, "end-round", {"stage": "league", "round_index": round_index}
            )
            assert ended.status_code == 200, ended.text
        return session

    def _complete_lk_with_semifinals(self, name):
        roster = generate_roster(
            self.client,
            players=["A", "B", "C", "D", "E", "F", "G", "H"],
            fixed_pairs=[["A", "B"], ["C", "D"], ["E", "F"], ["G", "H"]],
            num_courts=2,
            court_numbers=["1", "2"],
            rounds=3,
            pair_games=1,
        )
        session = create_round_robin_session(
            self.client,
            name=name,
            roster=roster,
            draw_config={"draw_type": "league_knockout", "league_meetings": 1, "knockout_qualifiers": 4},
            fixed_pairs=[["A", "B"], ["C", "D"], ["E", "F"], ["G", "H"]],
            pair_games=1,
        )
        for round_index in range(3):
            post_action(self.client, session, "start-round", {"stage": "league", "round_index": round_index})
            for court in range(2):
                post_action(
                    self.client,
                    session,
                    "score",
                    {"stage": "league", "round_index": round_index, "court_index": court, "team_key": "teamA", "value": 21},
                )
                post_action(
                    self.client,
                    session,
                    "score",
                    {"stage": "league", "round_index": round_index, "court_index": court, "team_key": "teamB", "value": 15},
                )
            post_action(self.client, session, "end-round", {"stage": "league", "round_index": round_index})
        post_action(self.client, session, "start-round", {"stage": "knockout", "round_index": 0})
        for court in range(2):
            post_action(
                self.client,
                session,
                "score",
                {"stage": "knockout", "round_index": 0, "court_index": court, "team_key": "teamA", "value": 21},
            )
            post_action(
                self.client,
                session,
                "score",
                {"stage": "knockout", "round_index": 0, "court_index": court, "team_key": "teamB", "value": 15},
            )
        ended = post_action(self.client, session, "end-round", {"stage": "knockout", "round_index": 0})
        assert ended.status_code == 200, ended.text
        return session

    def test_only_the_last_ended_league_round_can_be_reopened(self):
        session = self._complete_round_robin("M06 Non Last Reopen")

        early = post_action(self.client, session, "edit-round", {"stage": "league", "round_index": 0})
        self.assertEqual(early.status_code, 409, early.text)
        self.assertIn("most recently", early.json()["detail"].lower())

        last = post_action(self.client, session, "edit-round", {"stage": "league", "round_index": 1})
        self.assertEqual(last.status_code, 200, last.text)

    def test_reopen_with_knockout_data_requires_confirm(self):
        session = self._complete_lk_with_semifinals("M06 Knockout Wipe")

        without_confirm = post_action(
            self.client, session, "edit-round", {"stage": "league", "round_index": 2}
        )
        self.assertEqual(without_confirm.status_code, 409, without_confirm.text)
        self.assertIn("knockout", without_confirm.json()["detail"].lower())

        detail = get_session(self.client, session).json()
        self.assertTrue(detail["ended_knockout_rounds"][0], "knockout round must survive the rejected edit")

        with_confirm = post_action(
            self.client,
            session,
            "edit-round",
            {"stage": "league", "round_index": 2, "confirm_knockout_wipe": True},
        )
        self.assertEqual(with_confirm.status_code, 200, with_confirm.text)

        detail = get_session(self.client, session).json()
        self.assertEqual(detail["ended_knockout_rounds"], [], "confirmed edit must still wipe knockout data")

    def test_reopen_without_knockout_data_needs_no_confirm(self):
        session = self._complete_round_robin("M06 No Knockout")
        response = post_action(self.client, session, "edit-round", {"stage": "league", "round_index": 1})
        self.assertEqual(response.status_code, 200, response.text)


class CompletedAtPersistenceTests(unittest.TestCase):
    """L-07a.2: a session's completed_at is stamped once and never drifts.

    completed_at was taken from record.updated_at on every stats sync, so
    any later mutation - even a rename - reshuffled history ordering.
    """

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_completed_at_survives_later_mutations(self):
        import time
        import uuid

        tag = uuid.uuid4().hex[:8]
        session = create_round_robin_session(self.client, name=f"Stamp {tag}")
        post_action(self.client, session, "start-round", {"stage": "league", "round_index": 0})
        post_action(
            self.client,
            session,
            "score",
            {"stage": "league", "round_index": 0, "court_index": 0, "team_key": "teamA", "value": 21},
        )
        post_action(
            self.client,
            session,
            "score",
            {"stage": "league", "round_index": 0, "court_index": 0, "team_key": "teamB", "value": 15},
        )
        ended = post_action(self.client, session, "end-round", {"stage": "league", "round_index": 0})
        self.assertEqual(ended.status_code, 200, ended.text)

        def history_entry():
            history = self.client.get("/api/history/sessions")
            self.assertEqual(history.status_code, 200, history.text)
            return next(item for item in history.json() if item["session_id"] == session["session_id"])

        first = history_entry()["completed_at"]

        time.sleep(1.1)
        renamed = self.client.post(
            f"/api/sessions/{session['session_id']}/rename",
            params={"edit_token": session["edit_token"]},
            json={"name": f"Stamp Renamed {tag}"},
        )
        self.assertEqual(renamed.status_code, 200, renamed.text)

        second = history_entry()["completed_at"]
        self.assertEqual(
            first,
            second,
            "completed_at must be stamped once; a rename must not shift it",
        )


class LiveRoundStartGuardTests(unittest.TestCase):
    """Field bug 2026-11-14: a new round could be started while the previous
    one was still live, and the live round could then never be ended ("Only
    the active round can be ended") - the session was stranded forever and
    could never complete. Starting the next round must require the previous
    round to be ended.
    """

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def _session(self, name):
        roster = generate_roster(
            self.client,
            players=["A", "B", "C", "D", "E", "F", "G", "H"],
            num_courts=1,
            rounds=6,
        )
        return create_round_robin_session(self.client, name=name, roster=roster)

    def test_league_round_cannot_start_while_previous_is_live(self):
        session = self._session("Live Guard League")
        post_action(self.client, session, "start-round", {"stage": "league", "round_index": 0})
        # The bug: starting round 1 while round 0 is live stranded round 0.
        blocked = post_action(
            self.client, session, "start-round", {"stage": "league", "round_index": 1}
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertIn("End the current round", blocked.json()["detail"])
        # The live round stays endable: score it and end it.
        for team_key, value in (("teamA", 21), ("teamB", 15)):
            post_action(
                self.client,
                session,
                "score",
                {"stage": "league", "round_index": 0, "court_index": 0, "team_key": team_key, "value": value},
            )
        ended = post_action(self.client, session, "end-round", {"stage": "league", "round_index": 0})
        self.assertEqual(ended.status_code, 200, ended.text)
        # Now the next round may start.
        started = post_action(
            self.client, session, "start-round", {"stage": "league", "round_index": 1}
        )
        self.assertEqual(started.status_code, 200, started.text)

    def test_knockout_round_cannot_start_while_previous_is_live(self):
        roster = generate_roster(
            self.client,
            players=["A", "B", "C", "D", "E", "F", "G", "H"],
            fixed_pairs=[["A", "B"], ["C", "D"], ["E", "F"], ["G", "H"]],
            num_courts=2,
            rounds=3,
            pair_games=1,
        )
        session = create_round_robin_session(
            self.client,
            name="Live Guard Knockout",
            roster=roster,
            draw_config={"draw_type": "league_knockout", "league_meetings": 1, "knockout_qualifiers": 4},
            fixed_pairs=[["A", "B"], ["C", "D"], ["E", "F"], ["G", "H"]],
            pair_games=1,
        )
        for round_index in range(3):
            post_action(self.client, session, "start-round", {"stage": "league", "round_index": round_index})
            for court_index in range(2):
                for team_key, value in (("teamA", 21), ("teamB", 15)):
                    post_action(
                        self.client,
                        session,
                        "score",
                        {"stage": "league", "round_index": round_index, "court_index": court_index, "team_key": team_key, "value": value},
                    )
            post_action(self.client, session, "end-round", {"stage": "league", "round_index": round_index})

        post_action(self.client, session, "start-round", {"stage": "knockout", "round_index": 0})
        blocked = post_action(
            self.client, session, "start-round", {"stage": "knockout", "round_index": 1}
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertIn("End the current round", blocked.json()["detail"])
        # The live semifinal stays endable, then the final may start.
        for court_index in range(2):
            for team_key, value in (("teamA", 21), ("teamB", 15)):
                post_action(
                    self.client,
                    session,
                    "score",
                    {"stage": "knockout", "round_index": 0, "court_index": court_index, "team_key": team_key, "value": value},
                )
        ended = post_action(self.client, session, "end-round", {"stage": "knockout", "round_index": 0})
        self.assertEqual(ended.status_code, 200, ended.text)
        started = post_action(
            self.client, session, "start-round", {"stage": "knockout", "round_index": 1}
        )
        self.assertEqual(started.status_code, 200, started.text)


if __name__ == "__main__":
    unittest.main()
