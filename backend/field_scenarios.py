"""Field-scenario verification for the C-1 PR1+PR2 engine.

Runs Ashok's six most-used configurations through the real /api/generate
endpoint and reports completeness, fairness spreads, warnings, violations,
seed variety and generation time.
"""

import sys
import time
import uuid
from collections import Counter
from itertools import combinations

sys.path.insert(0, ".")

import os

os.environ.setdefault("PLAYWRIGHT_TEST_MODE", "1")
os.environ["DATABASE_URL"] = f"sqlite:////tmp/roster-field-verify-{uuid.uuid4().hex[:6]}.db"
os.environ["ADMIN_RECOVERY_TOKEN"] = "thisismytoken"
os.environ["CACHE_ENABLED"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402

client = TestClient(app)
client.__enter__()

TAG = uuid.uuid4().hex[:6]


def gen(players, courts, rounds, pairs, pair_games, draw_type="round_robin",
        pair_start_round=1, seed=1, limits=None, max_rest=1):
    payload = {
        "players": players,
        "fixed_pairs": [list(p) for p in pairs],
        "num_courts": courts,
        "court_numbers": [str(i + 1) for i in range(courts)],
        "rounds": rounds,
        "limits": limits or {},
        "pair_games": pair_games,
        "pair_start_round": pair_start_round,
        "max_consecutive_rest": max_rest,
        "draw_type": draw_type,
        "seed": seed,
    }
    start = time.monotonic()
    response = client.post("/api/generate", json=payload)
    return response, time.monotonic() - start


def pair_pairs(pairs):
    pairset = {frozenset(p) for p in pairs}
    def key(a, b):
        x, y = tuple(sorted(a)), tuple(sorted(b))
        return (x, y) if x <= y else (y, x)
    return pairset, key


def analyze(body, players, pairs):
    rounds = body["rounds"]
    issues = []
    # completeness: every player exactly once per round (rest or court)
    for r in rounds:
        on = [p for c in r["courts"] for p in list(c["team_a"]) + list(c["team_b"])]
        if sorted(on + r["resting"]) != sorted(players):
            issues.append(f"round {r['round']} incomplete")
    # consecutive violations (real constraint breaches)
    consecutive = [v for v in body["violations"] if "consecutive" in v]
    # pair-vs-pair matchups
    pairset, key = pair_pairs(pairs)
    mu = Counter()
    pure = 0
    for r in rounds:
        for c in r["courts"]:
            ta, tb = frozenset(c["team_a"]), frozenset(c["team_b"])
            if ta in pairset and tb in pairset:
                mu[key(c["team_a"], c["team_b"])] += 1
                pure += 1
    mvals = [mu.get(key(frozenset(a), frozenset(b)), 0) for a, b in combinations(pairs, 2)] if pairs else []
    fairness = body.get("fairness") or {}
    return {
        "issues": issues,
        "consecutive": consecutive,
        "pure_courts": pure,
        "matchup_spread": (max(mvals) - min(mvals)) if mvals else None,
        "rest_spread": fairness.get("rest_spread"),
        "corest_spread": fairness.get("corest_spread"),
        "fair_matchup": fairness.get("matchup_spread"),
        "warnings": [w.split(":")[0] for w in body["warnings"]],
    }


def run_scenario(label, players_n, courts, rounds, pairs_n, pair_games,
                 draw_type="round_robin", seeds=range(1, 6), max_rest=1):
    print(f"\n=== {label} ({players_n}p/{courts}c/{rounds}r, {pairs_n} pairs, "
          f"pair_games={pair_games}, {draw_type}) ===")
    all_ok = True
    round1_sets = set()
    total_time = 0.0
    warn_counter = Counter()
    spreads = Counter()
    for seed in seeds:
        players = [f"{TAG}F{seed}-{i}" for i in range(1, players_n + 1)]
        pairs = [(players[i], players[i + 1]) for i in range(0, 2 * pairs_n, 2)]
        response, elapsed = gen(players, courts, rounds, pairs, pair_games,
                                draw_type=draw_type, seed=seed, max_rest=max_rest)
        total_time += elapsed
        if response.status_code != 200:
            print(f"  seed {seed}: HTTP {response.status_code}: {response.text[:140]}")
            all_ok = False
            continue
        body = response.json()
        stats = analyze(body, players, pairs)
        round1_sets.add(tuple(sorted(body["rounds"][0]["resting"])))
        warn_counter.update(stats["warnings"])
        spreads[(stats["rest_spread"], stats["corest_spread"], stats["fair_matchup"])] += 1
        flag = ""
        if stats["issues"] or stats["consecutive"]:
            flag = f"  <-- PROBLEMS: {stats['issues'][:2]} {stats['consecutive'][:2]}"
            all_ok = False
        if seed == list(seeds)[0]:
            print(f"  seed {seed}: pure pair-vs-pair courts {stats['pure_courts']}/{rounds * courts}, "
                  f"spreads rest/corest/matchup = {stats['rest_spread']}/{stats['corest_spread']}/{stats['fair_matchup']}, "
                  f"warnings {stats['warnings'] or 'none'}, {elapsed * 1000:.0f}ms{flag}")
        elif flag:
            print(f"  seed {seed}: PROBLEMS {stats['issues'][:2]} {stats['consecutive'][:2]}")
    n = len(list(seeds))
    print(f"  summary over {n} seeds: spreads(rest,corest,matchup) seen {dict(spreads)}, "
          f"warnings {dict(warn_counter) or 'none'}, round-1 rest sets {len(round1_sets)} distinct, "
          f"avg {total_time / max(n, 1) * 1000:.0f}ms, complete={all_ok}")


# 1. 13-15 players, 3 courts, 3 pairs, pair_games 4 / all random
for n in (13, 14, 15):
    run_scenario(f"1.1 3 pairs", n, 3, 10, 3, 4)
for n in (13, 14, 15):
    run_scenario(f"1.2 all random", n, 3, 10, 0, 1)

# 2. 16-20 players, 4 courts, 4 pairs pair_games 5 / all random
for n in (16, 18, 20):
    run_scenario("2.1 4 pairs", n, 4, 10, 4, 5)
for n in (16, 18, 20):
    run_scenario("2.2 all random", n, 4, 10, 0, 1)

# 3. 5 pairs league+knockout on 2 courts (10 rounds = 2 meetings, pair_games 8)
run_scenario("3 L+K 5 pairs", 10, 2, 10, 5, 8, draw_type="league_knockout")

# 4. 6 pairs league+knockout on 2 courts (known C-2 gap: expect clean 422)
players = [f"{TAG}X-{i}" for i in range(1, 13)]
pairs6 = [(players[i], players[i + 1]) for i in range(0, 12, 2)]
response, elapsed = gen(players, 2, 10, pairs6, 8, draw_type="league_knockout", seed=1)
print(f"\n=== 4 L+K 6 pairs/2 courts ===\n  HTTP {response.status_code} ({elapsed*1000:.0f}ms): {response.text[:180]}")

# 5. 5 pairs round robin on 2 courts
run_scenario("5 RR 5 pairs", 10, 2, 10, 5, 4)
run_scenario("5b RR 5 pairs 13r", 10, 2, 13, 5, 5)

# 6. 6 pairs round robin on 2 courts (Organiser shape)
run_scenario("6 RR 6 pairs", 12, 2, 13, 6, 8, seeds=range(1, 21))

client.__exit__(None, None, None)
print("\ndone")
