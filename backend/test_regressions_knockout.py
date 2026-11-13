"""Knockout regression tests (Bucket A fixes M-04, H-09, H-04, M-10a).

Covers knockout start guards, tied knockout rounds, legacy qualifier
normalization, and final-standings tie-break alignment with the UI. Each
class maps to one fix PR and must fail before that fix lands (run the
class on the parent branch to see it red).

Run from backend/:

    venv/bin/python -m unittest test_regressions_knockout -v
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


class KnockoutStartGuardsTests(unittest.TestCase):
    """M-04: knockout rounds cannot start before the league is finished.

    With no draw-type or league-completion check, a knockout round could be
    started on a plain round_robin session (phantom knockout rounds could
    then 'complete' it with zero league play) or on a league_knockout
    session mid-league, pre-entering scores that later bind to whatever
    pairs qualify.
    """

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def _create_lk_session(self, name):
        roster = generate_roster(
            self.client,
            players=["A", "B", "C", "D", "E", "F", "G", "H"],
            fixed_pairs=[["A", "B"], ["C", "D"], ["E", "F"], ["G", "H"]],
            num_courts=2,
            court_numbers=["1", "2"],
            rounds=3,
            pair_games=1,
        )
        return create_round_robin_session(
            self.client,
            name=name,
            roster=roster,
            draw_config={"draw_type": "league_knockout", "league_meetings": 1, "knockout_qualifiers": 4},
            fixed_pairs=[["A", "B"], ["C", "D"], ["E", "F"], ["G", "H"]],
            pair_games=1,
        )

    def test_round_robin_session_rejects_knockout_start(self):
        session = create_round_robin_session(self.client, name="M04 Round Robin KO")
        response = post_action(
            self.client, session, "start-round", {"stage": "knockout", "round_index": 0}
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("league + knockout", response.json()["detail"].lower())

    def test_lk_session_rejects_knockout_before_league_completes(self):
        session = self._create_lk_session("M04 Early KO")
        response = post_action(
            self.client, session, "start-round", {"stage": "knockout", "round_index": 0}
        )
        self.assertEqual(response.status_code, 409, response.text)

        post_action(self.client, session, "start-round", {"stage": "league", "round_index": 0})
        response = post_action(
            self.client, session, "start-round", {"stage": "knockout", "round_index": 0}
        )
        self.assertEqual(response.status_code, 409, response.text)

    def test_lk_session_allows_knockout_after_league_completes(self):
        session = self._create_lk_session("M04 On Time KO")
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
            ended = post_action(
                self.client, session, "end-round", {"stage": "league", "round_index": round_index}
            )
            self.assertEqual(ended.status_code, 200, ended.text)

        response = post_action(
            self.client, session, "start-round", {"stage": "knockout", "round_index": 0}
        )
        self.assertEqual(response.status_code, 200, response.text)


class KnockoutTieTests(unittest.TestCase):
    """H-09: a knockout round containing a tied match cannot be ended.

    Ending a tied semifinal or final left the session permanently stuck:
    'complete' on the screen, never in history, champion forever TBD.
    """

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def _complete_league(self, name):
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
            ended = post_action(
                self.client, session, "end-round", {"stage": "league", "round_index": round_index}
            )
            assert ended.status_code == 200, ended.text
        return session

    def test_tied_knockout_round_cannot_be_ended(self):
        session = self._complete_league("H09 Tie")
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
                {"stage": "knockout", "round_index": 0, "court_index": court, "team_key": "teamB", "value": 21},
            )

        response = post_action(self.client, session, "end-round", {"stage": "knockout", "round_index": 0})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("tie", response.json()["detail"].lower())

        detail = get_session(self.client, session).json()
        self.assertFalse(detail["ended_knockout_rounds"][0], "round must not be marked ended after tie rejection")

    def test_decisive_knockout_round_still_ends(self):
        session = self._complete_league("H09 Decisive")
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
        response = post_action(self.client, session, "end-round", {"stage": "knockout", "round_index": 0})
        self.assertEqual(response.status_code, 200, response.text)

    def test_tied_league_round_can_still_be_ended(self):
        session = create_round_robin_session(self.client, name="H09 League Draw RR")
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
            {"stage": "league", "round_index": 0, "court_index": 0, "team_key": "teamB", "value": 21},
        )
        response = post_action(self.client, session, "end-round", {"stage": "league", "round_index": 0})
        self.assertEqual(response.status_code, 200, response.text)


class QualifierNormalizationTests(unittest.TestCase):
    """H-04: legacy sessions with odd knockout_qualifiers must not crash.

    Sessions created before request validation could hold
    knockout_qualifiers=3 (or 5+). Completing their knockout hit seeds[3]
    with a 3-entry list: an IndexError 500 on every end-round attempt, and
    the planned-rounds count disagreed with the built bracket.
    """

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def _create_lk_session(self, name):
        roster = generate_roster(
            self.client,
            players=["A", "B", "C", "D", "E", "F", "G", "H"],
            fixed_pairs=[["A", "B"], ["C", "D"], ["E", "F"], ["G", "H"]],
            num_courts=2,
            court_numbers=["1", "2"],
            rounds=3,
            pair_games=1,
        )
        return create_round_robin_session(
            self.client,
            name=name,
            roster=roster,
            draw_config={"draw_type": "league_knockout", "league_meetings": 1, "knockout_qualifiers": 4},
            fixed_pairs=[["A", "B"], ["C", "D"], ["E", "F"], ["G", "H"]],
            pair_games=1,
        )

    def _corrupt_to_legacy_qualifiers(self, session_id, qualifiers):
        import copy

        import app as app_module

        with app_module.get_db_session() as db:
            record = db.scalar(
                app_module.select(app_module.SharedSessionRecord).where(
                    app_module.SharedSessionRecord.session_id == session_id
                )
            )
            data = copy.deepcopy(record.data)
            data["draw_config"]["knockout_qualifiers"] = qualifiers
            record.data = data

    def _complete_league(self, session):
        for round_index in range(3):
            post_action(
                self.client, session, "start-round", {"stage": "league", "round_index": round_index}
            )
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

    def test_legacy_three_qualifiers_completes_without_500(self):
        session = self._create_lk_session("H04 Legacy Three")
        self._corrupt_to_legacy_qualifiers(session["session_id"], 3)
        self._complete_league(session)

        started = post_action(
            self.client, session, "start-round", {"stage": "knockout", "round_index": 0}
        )
        self.assertEqual(started.status_code, 200, started.text)
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
        ended = post_action(
            self.client, session, "end-round", {"stage": "knockout", "round_index": 0}
        )
        self.assertEqual(ended.status_code, 200, f"previously IndexError 500: {ended.text}")

        detail = get_session(self.client, session).json()
        self.assertTrue(detail["ended_knockout_rounds"][0])

    def test_legacy_five_qualifiers_completes_without_500(self):
        session = self._create_lk_session("H04 Legacy Five")
        self._corrupt_to_legacy_qualifiers(session["session_id"], 5)
        self._complete_league(session)

        started = post_action(
            self.client, session, "start-round", {"stage": "knockout", "round_index": 0}
        )
        self.assertEqual(started.status_code, 200, started.text)
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
        ended = post_action(
            self.client, session, "end-round", {"stage": "knockout", "round_index": 0}
        )
        self.assertEqual(ended.status_code, 200, ended.text)


class TieBreakAlignmentTests(unittest.TestCase):
    """M-10a: the final standings tie-break must match the UI's.

    The server broke full ties with raw Python string comparison (uppercase
    first: 'Beta' before 'alpha'), while the UI used localeCompare - so the
    server could seed different semifinalists than the scorers saw ranked
    on screen. Both sides now break ties case-insensitively.
    """

    def test_final_tiebreak_is_case_insensitive(self):
        from app import _rank_stats_entries

        entries = [
            ("Beta & One", {"points": 10, "point_difference": 5, "wins": 3}),
            ("alpha & Two", {"points": 10, "point_difference": 5, "wins": 3}),
            ("Gamma & Three", {"points": 12, "point_difference": 5, "wins": 4}),
        ]
        ranked = [name for name, _ in _rank_stats_entries(entries)]
        self.assertEqual(ranked[0], "Gamma & Three", "higher points must rank first")
        self.assertEqual(
            ranked[1:],
            ["alpha & Two", "Beta & One"],
            "case-insensitive order expected: raw string order puts 'Beta & One' first",
        )


if __name__ == "__main__":
    unittest.main()
