"""Player registry regression tests (Bucket A fixes M-01, M-17, L-08, L-05, L-07a, L-07a.3).

Covers rename/restore conflicts with soft-deleted players, normalized-name
backfill, seed gating of the default directory, player id entropy, and NFC
name folding. Each class maps to one fix PR and must fail before that fix
lands (run the class on the parent branch to see it red).

Run from backend/:

    venv/bin/python -m unittest test_regressions_players -v
"""

import unittest

import regression_support  # noqa: F401  (env setup before app import)

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402


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
    """L-05: the 22-name default directory seeds only when explicitly enabled.

    Every empty database was auto-seeded with 22 hardcoded personal names,
    on any deployment. Seeding is gated by ROSTER_SEED_PLAYERS and defaults
    OFF for clean deployments; setting it to '1' re-enables the 22-name
    convenience directory for the group's local setup.
    """

    def _count_players_on_fresh_db(self, flag):
        import os
        import subprocess
        import sys

        db_path = f"/tmp/roster-seed-{flag or 'unset'}-{os.getpid()}.db"
        seed_line = (
            f"os.environ['ROSTER_SEED_PLAYERS'] = '{flag}'" if flag is not None else "pass"
        )
        script = "\n".join([
            "import os",
            "os.environ['PLAYWRIGHT_TEST_MODE'] = '1'",
            f"os.environ['DATABASE_URL'] = 'sqlite:///{db_path}'",
            "os.environ['CACHE_ENABLED'] = 'false'",
            seed_line,
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
        default = self._count_players_on_fresh_db(None)
        self.assertEqual(
            default,
            0,
            "default (ROSTER_SEED_PLAYERS unset) must seed nothing on an empty database",
        )

        enabled = self._count_players_on_fresh_db("1")
        self.assertEqual(
            enabled,
            22,
            "ROSTER_SEED_PLAYERS=1 must seed the 22-name directory",
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


class NfcNameNormalizationTests(unittest.TestCase):
    """L-07a.3: composed and decomposed name forms are the same player.

    Without NFC folding, 'José' stored as NFC and a second 'José' typed in
    NFD (e + combining accent) created two different players.
    """

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_decomposed_form_conflicts_with_composed_form(self):
        import unicodedata
        import uuid

        tag = uuid.uuid4().hex[:8]
        composed = unicodedata.normalize("NFC", f"José {tag}")
        decomposed = unicodedata.normalize("NFD", f"José {tag}")
        self.assertNotEqual(composed, decomposed, "sanity: the two forms must differ as raw strings")

        first = self.client.post(
            "/api/players", json={"full_name": composed, "short_name": f"JZa{tag}"}
        )
        self.assertEqual(first.status_code, 201, first.text)

        duplicate = self.client.post(
            "/api/players", json={"full_name": decomposed, "short_name": f"JZb{tag}"}
        )
        self.assertEqual(
            duplicate.status_code,
            409,
            f"decomposed form of the same name must conflict, got {duplicate.status_code}: {duplicate.text}",
        )


if __name__ == "__main__":
    unittest.main()
