"""Deploy-status endpoint: compares the running build against main.

GET /api/deploy-info tells the planner at a glance whether the latest
code is deployed: the deployed SHA (Render's RENDER_GIT_COMMIT at deploy
time), the latest main SHA from the public GitHub API, and a verdict.

Tests are hermetic: the GitHub helper is patched, never hit for real.
"""

import os
import unittest

import regression_support  # noqa: F401  (env setup before app import)

from fastapi.testclient import TestClient  # noqa: E402

import app as app_module  # noqa: E402
from app import app  # noqa: E402


class DeployInfoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        self._github = app_module._github_json
        os.environ["APP_GIT_SHA"] = "d3adb33f0000000000000000000000000000000"

    def tearDown(self):
        app_module._github_json = self._github
        os.environ.pop("APP_GIT_SHA", None)
        os.environ.pop("RENDER_GIT_COMMIT", None)

    def _get(self):
        response = self.client.get("/api/deploy-info")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_deployed_sha_reported_and_unknown_when_github_unreachable(self):
        app_module._github_json = lambda path: None
        body = self._get()
        self.assertEqual(body["deployed_sha"], "d3adb33f0000000000000000000000000000000")
        self.assertIsNone(body["latest_main_sha"])
        self.assertEqual(body["status"], "unknown")

    def test_up_to_date_when_deployed_matches_main(self):
        app_module._github_json = lambda path: {
            "sha": "d3adb33f0000000000000000000000000000000",
            "commit": {"committer": {"date": "2026-11-13T08:00:00Z"}},
        }
        body = self._get()
        self.assertEqual(body["status"], "up_to_date")
        self.assertEqual(body["latest_main_sha"], "d3adb33f0000000000000000000000000000000")
        self.assertEqual(body["ahead_by"], 0)

    def test_behind_reports_latest_sha_and_ahead_count(self):
        def github(path):
            if path.endswith("/commits/main"):
                return {
                    "sha": "f00dcafe00000000000000000000000000000000",
                    "commit": {"committer": {"date": "2026-11-13T09:00:00Z"}},
                }
            if "/compare/" in path:
                return {"ahead_by": 2}
            return None

        app_module._github_json = github
        body = self._get()
        self.assertEqual(body["status"], "behind")
        self.assertEqual(body["deployed_sha"], "d3adb33f0000000000000000000000000000000")
        self.assertEqual(body["latest_main_sha"], "f00dcafe00000000000000000000000000000000")
        self.assertEqual(body["ahead_by"], 2)
        self.assertEqual(body["latest_main_at"], "2026-11-13T09:00:00Z")

    def test_local_dev_without_sha_is_unknown(self):
        os.environ.pop("APP_GIT_SHA", None)
        os.environ.pop("RENDER_GIT_COMMIT", None)
        app_module._github_json = lambda path: None
        body = self._get()
        self.assertIsNone(body["deployed_sha"])
        self.assertEqual(body["status"], "unknown")

    def test_render_commit_takes_precedence(self):
        os.environ["RENDER_GIT_COMMIT"] = "cafe123400000000000000000000000000000000"
        app_module._github_json = lambda path: {
            "sha": "cafe123400000000000000000000000000000000",
            "commit": {"committer": {"date": "2026-11-13T10:00:00Z"}},
        }
        body = self._get()
        self.assertEqual(body["status"], "up_to_date")
        self.assertEqual(body["deployed_sha"], "cafe123400000000000000000000000000000000")


if __name__ == "__main__":
    unittest.main()
