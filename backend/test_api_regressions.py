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


def create_round_robin_session(
    client,
    name="Regression Session",
    roster=None,
    draw_config=None,
    fixed_pairs=None,
    pair_games=None,
):
    if roster is None:
        roster = generate_roster(client)
    response = client.post(
        "/api/sessions",
        json={
            "name": name,
            "roster": roster,
            "draw_config": draw_config
            or {
                "draw_type": "round_robin",
                "league_meetings": 1,
                "knockout_qualifiers": 4,
            },
            "selected_players": [],
            "fixed_pairs": fixed_pairs or [],
            "limits": {},
            "pair_games": pair_games or 1,
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


class RenameSoftDeletedConflictTests(unittest.TestCase):
    """M-01: renaming onto a soft-deleted player's name must return 409.

    The rename conflict check ignored soft-deleted players, passed the app
    layer, and then hit the DB UNIQUE constraint on the normalized names:
    a raw 500 (IntegrityError) instead of a conflict response.
    """

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_rename_onto_soft_deleted_name_returns_409_not_500(self):
        import uuid

        tag = uuid.uuid4().hex[:8]
        ghost_full = f"Ghost One {tag}"
        ghost_short = f"GO{tag}"
        live_full = f"Live One {tag}"
        live_short = f"LO{tag}"

        ghost = self.client.post("/api/players", json={"full_name": ghost_full, "short_name": ghost_short})
        self.assertEqual(ghost.status_code, 201, ghost.text)
        ghost_id = ghost.json()["player_id"]

        deleted = self.client.post(
            f"/api/players/{ghost_id}/delete",
            json={"admin_token": "thisismytoken", "delete_history": False},
        )
        self.assertEqual(deleted.status_code, 204, deleted.text)

        live = self.client.post("/api/players", json={"full_name": live_full, "short_name": live_short})
        self.assertEqual(live.status_code, 201, live.text)
        live_id = live.json()["player_id"]

        renamed = self.client.patch(
            f"/api/players/{live_id}",
            json={"full_name": ghost_full, "short_name": ghost_short},
        )
        self.assertEqual(renamed.status_code, 409, renamed.text)

        unchanged = self.client.get("/api/players")
        names = {player["full_name"] for player in unchanged.json()}
        self.assertIn(live_full, names)
        self.assertNotIn(ghost_full, names)


class ExactPairRestoreTests(unittest.TestCase):
    """M-17: creating a player must not hijack a soft-deleted player's identity.

    The restore-on-create path matched soft-deleted players by ANY name
    (including old aliases), so a brand-new person whose short name equalled
    a deleted player's old alias silently became that player: same player_id,
    inherited aliases, and history linkage.
    """

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def _deleted_player_with_alias(self, tag):
        original_full = f"Restore Exact {tag}"
        original_short = f"REX{tag}"
        created = self.client.post("/api/players", json={"full_name": original_full, "short_name": original_short})
        self.assertEqual(created.status_code, 201, created.text)
        player_id = created.json()["player_id"]

        renamed = self.client.patch(
            f"/api/players/{player_id}",
            json={"full_name": f"Renamed Exact {tag}", "short_name": f"RNX{tag}"},
        )
        self.assertEqual(renamed.status_code, 200, renamed.text)

        deleted = self.client.post(
            f"/api/players/{player_id}/delete",
            json={"admin_token": "thisismytoken", "delete_history": False},
        )
        self.assertEqual(deleted.status_code, 204, deleted.text)
        return player_id, original_full, original_short

    def test_alias_only_match_does_not_hijack_identity(self):
        import uuid

        tag = uuid.uuid4().hex[:8]
        player_id, original_full, original_short = self._deleted_player_with_alias(tag)

        other = self.client.post(
            "/api/players",
            json={"full_name": f"Different Person {tag}", "short_name": original_short},
        )
        self.assertEqual(
            other.status_code,
            409,
            f"alias-held short name must conflict explicitly, got {other.status_code}: {other.text}",
        )

    def test_recreate_by_current_full_name_with_fresh_short_restores(self):
        import uuid

        tag = uuid.uuid4().hex[:8]
        full_name = f"Plain Deleted {tag}"
        created = self.client.post("/api/players", json={"full_name": full_name, "short_name": f"PD{tag}"})
        self.assertEqual(created.status_code, 201, created.text)
        player_id = created.json()["player_id"]

        deleted = self.client.post(
            f"/api/players/{player_id}/delete",
            json={"admin_token": "thisismytoken", "delete_history": False},
        )
        self.assertEqual(deleted.status_code, 204, deleted.text)

        restored = self.client.post(
            "/api/players",
            json={"full_name": full_name, "short_name": f"FRESH{tag}"},
        )
        self.assertEqual(restored.status_code, 201, restored.text)
        self.assertEqual(restored.json()["player_id"], player_id)
        self.assertEqual(restored.json()["short_name"], f"FRESH{tag}")
        self.assertIn(f"PD{tag}", restored.json()["aliases"])

    def test_exact_current_pair_still_restores(self):
        import uuid

        tag = uuid.uuid4().hex[:8]
        player_id, _, _ = self._deleted_player_with_alias(tag)

        restored = self.client.post(
            "/api/players",
            json={"full_name": f"Renamed Exact {tag}", "short_name": f"RNX{tag}"},
        )
        self.assertEqual(restored.status_code, 201, restored.text)
        self.assertEqual(restored.json()["player_id"], player_id)
        self.assertIsNotNone(restored.json().get("aliases"))

    def test_same_full_name_with_different_short_conflicts(self):
        import uuid

        tag = uuid.uuid4().hex[:8]
        _, original_full, _ = self._deleted_player_with_alias(tag)

        other = self.client.post(
            "/api/players",
            json={"full_name": original_full, "short_name": f"NEW{tag}"},
        )
        self.assertEqual(
            other.status_code,
            409,
            f"full name held by a deleted player must conflict explicitly, got {other.status_code}: {other.text}",
        )


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


class LegacyNameBackfillTests(unittest.TestCase):
    """L-08: legacy players rows get their normalized names backfilled.

    The schema migration added normalized_* columns with DEFAULT '' and no
    backfill, so pre-feature rows kept empty normalized names: the DB UNIQUE
    constraints never fired, and creating 'Legacy Larry' twice succeeded.
    """

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_backfill_restores_conflict_detection_for_legacy_rows(self):
        import uuid

        import app as app_module

        tag = uuid.uuid4().hex[:8]
        full_name = f"Legacy Larry {tag}"
        short_name = f"LL{tag}"
        created = self.client.post("/api/players", json={"full_name": full_name, "short_name": short_name})
        self.assertEqual(created.status_code, 201, created.text)
        player_id = created.json()["player_id"]

        # Simulate a pre-migration row: normalized columns empty.
        with app_module.get_db_session() as db:
            row = db.get(app_module.PlayerRecord, player_id)
            row.normalized_full_name = ""
            row.normalized_short_name = ""

        # The next boot backfills normalized names for legacy rows.
        with app_module.get_db_session() as db:
            app_module._backfill_player_normalized_names(db)

        with app_module.get_db_session() as db:
            row = db.get(app_module.PlayerRecord, player_id)
            self.assertEqual(row.normalized_full_name, full_name.lower())
            self.assertEqual(row.normalized_short_name, short_name.lower())

        duplicate = self.client.post("/api/players", json={"full_name": full_name, "short_name": short_name})
        self.assertEqual(
            duplicate.status_code,
            409,
            f"legacy row must conflict again after backfill, got {duplicate.status_code}: {duplicate.text}",
        )


class SeedGatingTests(unittest.TestCase):
    """L-05: the 22-name default directory seeds only when enabled.

    Every empty database was auto-seeded with 22 hardcoded personal names,
    on any deployment. Seeding is now gated by ROSTER_SEED_PLAYERS (default
    enabled, preserving the group's local convenience; '0' gives clean
    deployments).
    """

    def _count_players_on_fresh_db(self, flag):
        import os
        import subprocess
        import sys

        db_path = f"/tmp/roster-seed-{flag}-{os.getpid()}.db"
        script = "\n".join([
            "import os",
            "os.environ['PLAYWRIGHT_TEST_MODE'] = '1'",
            f"os.environ['DATABASE_URL'] = 'sqlite:///{db_path}'",
            "os.environ['CACHE_ENABLED'] = 'false'",
            f"os.environ['ROSTER_SEED_PLAYERS'] = '{flag}'",
            "from database import init_db, get_db_session",
            "init_db()",
            "import app as a",
            "with get_db_session() as db:",
            "    a._ensure_player_registry(db)",
            "    print(len(db.scalars(a.select(a.PlayerRecord)).all()))",
        ])
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return int(result.stdout.strip().splitlines()[-1])

    def test_default_directory_seeding_is_env_gated(self):
        disabled = self._count_players_on_fresh_db("0")
        self.assertEqual(disabled, 0, "ROSTER_SEED_PLAYERS=0 must seed nothing on an empty database")

        enabled = self._count_players_on_fresh_db("1")
        self.assertEqual(
            enabled,
            22,
            "default ROSTER_SEED_PLAYERS must keep seeding the 22-name directory",
        )


class PlayerIdEntropyTests(unittest.TestCase):
    """L-07a: player ids get 64-bit entropy and regenerate on collision.

    Ids were plr_ + 32 bits — enumerable at internet scale, and a collision
    would fail the insert with a raw IntegrityError.
    """

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_player_ids_have_64_bit_entropy(self):
        import re

        from app import _generate_player_id

        ids = {_generate_player_id() for _ in range(1000)}
        self.assertEqual(len(ids), 1000)
        for player_id in ids:
            self.assertTrue(re.fullmatch(r"plr_[0-9a-f]{16}", player_id), f"bad id shape: {player_id}")

    def test_create_regenerates_on_id_collision(self):
        import uuid
        from unittest.mock import patch

        import app as app_module

        tag = uuid.uuid4().hex[:8]
        first = self.client.post(
            "/api/players", json={"full_name": f"Entropy One {tag}", "short_name": f"EO{tag}"}
        )
        self.assertEqual(first.status_code, 201, first.text)
        taken_id = first.json()["player_id"]
        fresh_id = f"plr_{tag[:16]}"

        with patch.object(app_module, "_generate_player_id", side_effect=[taken_id, fresh_id]):
            second = self.client.post(
                "/api/players",
                json={"full_name": f"Entropy Two {tag}", "short_name": f"ET{tag}"},
            )

        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(
            second.json()["player_id"],
            fresh_id,
            "collision with an existing id must regenerate instead of failing",
        )


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


if __name__ == "__main__":
    unittest.main()
