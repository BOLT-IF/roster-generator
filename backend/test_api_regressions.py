"""API regression tests accompanying the Bucket A fix stack.

Run from backend/:

    venv/bin/python -m unittest test_api_regressions -v

Each test class maps to one fix PR and must fail before that fix lands
(run the class on the parent branch to see it red). The test database is
configured BEFORE importing the app package because the app reads
environment variables at import time.
"""

import os
import unittest

os.environ.setdefault("PLAYWRIGHT_TEST_MODE", "1")
os.environ["DATABASE_URL"] = "sqlite:////tmp/roster-api-regressions.db"
os.environ["ADMIN_RECOVERY_TOKEN"] = "thisismytoken"
os.environ["CACHE_ENABLED"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402


def generate_roster(client, **overrides):
    payload = {
        "players": ["A", "B", "C", "D"],
        "fixed_pairs": [],
        "num_courts": 1,
        "court_numbers": ["1"],
        "rounds": 1,
        "limits": {},
        "pair_games": 1,
        "pair_start_round": 1,
        "max_consecutive_rest": 1,
        "seed": 1,
    }
    payload.update(overrides)
    response = client.post("/api/generate", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def create_round_robin_session(client, name="Regression Session", roster=None):
    if roster is None:
        roster = generate_roster(client)
    response = client.post(
        "/api/sessions",
        json={
            "name": name,
            "roster": roster,
            "draw_config": {
                "draw_type": "round_robin",
                "league_meetings": 1,
                "knockout_qualifiers": 4,
            },
            "selected_players": [],
            "fixed_pairs": [],
            "limits": {},
            "pair_games": 1,
            "pair_start_round": 1,
            "max_consecutive_rest": 1,
            "admin_token": "thisismytoken",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def post_action(client, session, path, body):
    return client.post(
        f"/api/sessions/{session['session_id']}/{path}",
        params={"edit_token": session["edit_token"]},
        json=body,
    )


def get_session(client, session):
    return client.get(
        f"/api/sessions/{session['session_id']}",
        params={"edit_token": session["edit_token"]},
    )


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


class MemoryCacheVersionTests(unittest.TestCase):
    """H-02: namespace bumps must change the cache key on the memory backend.

    Previously incr() wrote to a private dict that get() never read, so every
    bump was a no-op and stale entries were served until their TTL expired.
    """

    def test_bump_changes_cache_key_and_is_stable_between_bumps(self):
        from cache import CacheManager, MemoryCacheBackend

        manager = CacheManager()
        manager._enabled = True
        manager._backend = MemoryCacheBackend()

        key_before = manager.build_key("players", "all")
        manager.bump("players")
        key_after_first_bump = manager.build_key("players", "all")
        self.assertNotEqual(key_before, key_after_first_bump)

        manager.bump("players")
        key_after_second_bump = manager.build_key("players", "all")
        self.assertNotEqual(key_after_second_bump, key_after_first_bump)

    def test_bumped_namespace_stops_serving_cached_entries(self):
        from cache import CacheManager, MemoryCacheBackend

        manager = CacheManager()
        manager._enabled = True
        manager._backend = MemoryCacheBackend()

        manager.set_json(manager.build_key("players", "all"), ["stale"], ttl_seconds=300)
        self.assertEqual(manager.get_json(manager.build_key("players", "all")), ["stale"])

        manager.bump("players")
        self.assertIsNone(manager.get_json(manager.build_key("players", "all")))


class MemoryCacheFreshnessTests(unittest.TestCase):
    """H-02 (app level): with the memory cache active, a newly created player
    must be visible to the very next GET instead of waiting out the TTL."""

    def test_created_player_is_visible_immediately_with_memory_cache(self):
        import uuid

        from cache import MemoryCacheBackend

        import app as app_module

        probe_name = f"Cache Freshness Probe {uuid.uuid4().hex[:8]}"
        original_enabled = app_module.cache._enabled
        original_backend = app_module.cache._backend

        client = TestClient(app)
        client.__enter__()
        app_module.cache._enabled = True
        app_module.cache._backend = MemoryCacheBackend()
        try:
            # Warm the players cache with a first read.
            first = client.get("/api/players")
            self.assertEqual(first.status_code, 200, first.text)

            created = client.post("/api/players", json={"full_name": probe_name, "short_name": probe_name})
            self.assertEqual(created.status_code, 201, created.text)

            listed = client.get("/api/players")
            self.assertEqual(listed.status_code, 200, listed.text)
            names = [player["full_name"] for player in listed.json()]
            self.assertIn(probe_name, names)
        finally:
            app_module.cache._enabled = original_enabled
            app_module.cache._backend = original_backend
            client.__exit__(None, None, None)


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


class UnseededGenerateFreshnessTests(unittest.TestCase):
    """M-09: unseeded /api/generate must not return the identical cached roster.

    The endpoint cached responses by request fingerprint for a full hour, so
    two identical unseeded requests (the planner's Regenerate button) returned
    byte-identical rosters while the UI promised 'leave empty for random'.
    """

    def test_unseeded_generations_differ_and_seeded_stay_deterministic(self):
        import app as app_module
        from cache import MemoryCacheBackend

        original_enabled = app_module.cache._enabled
        original_backend = app_module.cache._backend

        client = TestClient(app)
        client.__enter__()
        app_module.cache._enabled = True
        app_module.cache._backend = MemoryCacheBackend()
        try:
            base = {
                "players": ["A", "B", "C", "D", "E", "F", "G", "H"],
                "fixed_pairs": [],
                "num_courts": 2,
                "court_numbers": ["1", "2"],
                "rounds": 3,
                "limits": {},
                "pair_games": 1,
                "pair_start_round": 5,
                "max_consecutive_rest": 1,
            }

            first = client.post("/api/generate", json=base)
            second = client.post("/api/generate", json=base)
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(second.status_code, 200, second.text)
            self.assertNotEqual(first.json(), second.json())

            seeded_one = client.post("/api/generate", json={**base, "seed": 1})
            seeded_two = client.post("/api/generate", json={**base, "seed": 1})
            self.assertEqual(seeded_one.status_code, 200, seeded_one.text)
            self.assertEqual(seeded_one.json(), seeded_two.json())
        finally:
            app_module.cache._enabled = original_enabled
            app_module.cache._backend = original_backend
            client.__exit__(None, None, None)


if __name__ == "__main__":
    unittest.main()
