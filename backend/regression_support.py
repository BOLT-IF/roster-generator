"""Shared support for the per-area API regression test modules.

The regression suite is split by area so each module stays small and new
tests append to their own file instead of piling onto one tail (which
caused recurring merge conflicts):

    test_regressions_scoring.py     score writes and score bounds
    test_regressions_caching.py     cache versioning and freshness
    test_regressions_sessions.py    session/round lifecycle guards
    test_regressions_knockout.py    knockout guards, ties, qualifiers
    test_regressions_engine.py      roster engine invariants
    test_regressions_players.py     player registry behavior
    test_regressions_validation.py  request validation

Run one area from backend/:

    venv/bin/python -m unittest test_regressions_scoring -v

or the whole suite:

    venv/bin/python -m unittest discover -v

The test database is configured BEFORE importing the app package because
the app reads environment variables at import time. Importing this module
performs that setup, so every regression module imports it first (before
anything else that touches the app package).
"""

import os

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
