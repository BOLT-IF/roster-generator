"""Caching regression tests (Bucket A fixes H-02, M-09).

Covers cache-namespace versioning on the memory backend, app-level cache
freshness, and unseeded generate freshness. Each class maps to one fix PR
and must fail before that fix lands (run the class on the parent branch to
see it red).

Run from backend/:

    venv/bin/python -m unittest test_regressions_caching -v
"""

import unittest

import regression_support  # noqa: F401  (env setup before app import)
from regression_support import app

from fastapi.testclient import TestClient  # noqa: E402


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
