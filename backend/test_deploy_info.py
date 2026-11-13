"""Deploy-status endpoint: compares the running build against main.

GET /api/deploy-info tells the planner at a glance whether the latest
code is deployed: the deployed SHA, the latest main SHA from the public
GitHub API, and a verdict.

The deployed SHA comes from a source ladder: the host's runtime env
(RENDER_GIT_COMMIT), an APP_GIT_SHA override, a build-baked
backend/deploy_sha.txt, or the local git checkout. All network and
process lookups are patched in tests - nothing here hits GitHub for real.
"""

import os
import tempfile
import unittest

import regression_support  # noqa: F401  (env setup before app import)

from fastapi.testclient import TestClient  # noqa: E402

import app as app_module  # noqa: E402
from app import app  # noqa: E402

FULL_SHA = "d3adb33f0000000000000000000000000000000"
MAIN_SHA = "f00dcafe00000000000000000000000000000000"


class DeployedShaSourceTests(unittest.TestCase):
    """Priority: RENDER_GIT_COMMIT > APP_GIT_SHA > baked file > git checkout."""

    def setUp(self):
        self._git = app_module._git_head_sha
        self._file = app_module._DEPLOY_SHA_FILE
        app_module._git_head_sha = lambda: None
        app_module._DEPLOY_SHA_FILE = "/nonexistent-deploy-sha.txt"
        os.environ.pop("RENDER_GIT_COMMIT", None)
        os.environ.pop("APP_GIT_SHA", None)

    def tearDown(self):
        app_module._git_head_sha = self._git
        app_module._DEPLOY_SHA_FILE = self._file
        os.environ.pop("RENDER_GIT_COMMIT", None)
        os.environ.pop("APP_GIT_SHA", None)

    def test_render_env_wins_over_everything(self):
        os.environ["RENDER_GIT_COMMIT"] = FULL_SHA
        os.environ["APP_GIT_SHA"] = MAIN_SHA
        self.assertEqual(app_module._deployed_git_sha(), FULL_SHA)

    def test_app_git_sha_overrides_file_and_git(self):
        os.environ["APP_GIT_SHA"] = FULL_SHA
        app_module._git_head_sha = lambda: MAIN_SHA
        self.assertEqual(app_module._deployed_git_sha(), FULL_SHA)

    def test_build_baked_file_used_when_env_missing(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
            fh.write(FULL_SHA)
            app_module._DEPLOY_SHA_FILE = fh.name
        try:
            self.assertEqual(app_module._deployed_git_sha(), FULL_SHA)
        finally:
            os.unlink(fh.name)

    def test_git_checkout_last_resort(self):
        app_module._git_head_sha = lambda: FULL_SHA
        self.assertEqual(app_module._deployed_git_sha(), FULL_SHA)

    def test_none_when_no_source_exists(self):
        self.assertIsNone(app_module._deployed_git_sha())


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
        self._sha = app_module._deployed_git_sha
        app_module._deployed_git_sha = lambda: FULL_SHA

    def tearDown(self):
        app_module._github_json = self._github
        app_module._deployed_git_sha = self._sha
        os.environ.pop("APP_GIT_SHA", None)
        os.environ.pop("RENDER_GIT_COMMIT", None)

    def _get(self):
        response = self.client.get("/api/deploy-info")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_deployed_sha_reported_and_unknown_when_github_unreachable(self):
        app_module._github_json = lambda path: None
        body = self._get()
        self.assertEqual(body["deployed_sha"], FULL_SHA)
        self.assertIsNone(body["latest_main_sha"])
        self.assertEqual(body["status"], "unknown")

    def test_up_to_date_when_deployed_matches_main(self):
        app_module._github_json = lambda path: {
            "sha": FULL_SHA,
            "commit": {"committer": {"date": "2026-11-13T08:00:00Z"}},
        }
        body = self._get()
        self.assertEqual(body["status"], "up_to_date")
        self.assertEqual(body["latest_main_sha"], FULL_SHA)
        self.assertEqual(body["ahead_by"], 0)

    def test_behind_reports_latest_sha_and_ahead_count(self):
        def github(path):
            if path.endswith("/commits/main"):
                return {
                    "sha": MAIN_SHA,
                    "commit": {"committer": {"date": "2026-11-13T09:00:00Z"}},
                }
            if "/compare/" in path:
                return {"ahead_by": 2}
            return None

        app_module._github_json = github
        body = self._get()
        self.assertEqual(body["status"], "behind")
        self.assertEqual(body["deployed_sha"], FULL_SHA)
        self.assertEqual(body["latest_main_sha"], MAIN_SHA)
        self.assertEqual(body["ahead_by"], 2)
        self.assertEqual(body["latest_main_at"], "2026-11-13T09:00:00Z")

    def test_no_sha_anywhere_is_unknown(self):
        app_module._deployed_git_sha = lambda: None
        app_module._github_json = lambda path: None
        body = self._get()
        self.assertIsNone(body["deployed_sha"])
        self.assertEqual(body["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
