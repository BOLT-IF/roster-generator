# CI Speed Survey

**Date:** 2026-11-13 · **Goal:** cut the ~15-minute PR pipeline without losing any test coverage or accuracy. **Baseline measured from run 43452428196 (green, PR #48) and run 43438800453 (step-level API data).**

## Where the time actually goes

| Job | Duration | Breakdown |
|---|---|---|
| backend-tests | 1m23s | setup 16s + tests 67s (already cut from ~135s to 37-72s by the C-2 tier-budget fix) |
| e2e-tests | **15m00s** | setup **89s** (browsers 65s, backend venv 13s, npm 5s) + **Playwright suite 14m46s** |
| **Total (jobs run in parallel)** | **~15 min** | e2e is the entire problem |

The suite itself is 14m46s because:

1. **`workers: 1`** (playwright.config.js) - every test runs strictly one at a time. This is deliberate and correct: all tests share one uvicorn backend and one SQLite database, so parallel workers inside one runner would race on shared state.
2. **204 test executions** - ~68 specs x 3 device projects (desktop / iPhone 13 / Pixel 7). The 3-project matrix is real coverage (viewport-specific bugs have been caught by it); dropping any project loses coverage.
3. **CI runners are ~6x slower per test than a local machine** (2 vCPU, throttled): the same suite is 2.2 minutes locally.

So caching helps only the 89s of setup; the lever that matters is **parallelism across runners**.

## The proposal (implemented in this PR)

**Shard the e2e suite across 4 parallel jobs** (`npx playwright test --shard=N/4` in a matrix). Each shard is a separate runner with its own backend, its own database, its own browsers - the exact isolation semantics the suite has today, just 4x fewer tests per runner. Sharding splits at the file level, so tests that share a spec file stay together.

Coverage check: the union of shards 1-4 is exactly the full suite - every test, every device project, every assertion, unchanged. A shard failing fails the PR.

Expected wall time: setup ~60s (with browser caching) + ~222s of tests per shard (51 tests x 4.35s) = **~5 minutes**, down from ~15.

Plus two cheap setup wins:
- **Cache Playwright browsers** (~/.cache/ms-playwright keyed on package-lock): 65s -> ~10s per job.
- The backend venv step (13s) stays as-is (pip download cache already active); not worth extra complexity.

## Options considered and rejected

- **`workers: 2`+ in one runner** - tests share one backend/DB; parallel workers race on shared state (player names collide, sqlite write contention). Would require re-architecting test isolation for maybe 1.7x, with real flake risk. Sharding gets 4x for free.
- **Fewer device projects** - that IS coverage loss; the viewport matrix has caught real bugs. Rejected per the goal.
- **Path-filtered runs** (skip e2e when only backend files change) - loses coverage on those PRs and builds false confidence. Rejected.
- **Bigger runners (4/8-core)** - paid even on public repos. Sharding on free standard runners is free.
- **`retries: 1` on CI** - would mask the exact flakiness we just eliminated at the root (deterministic seeding); a red run should mean red. Not added; can be a later decision.

## One admin step (one-time)

Branch protection requires checks by exact name. The matrix produces `e2e-tests (1)` .. `e2e-tests (4)` instead of `e2e-tests`, so the required-status-check list must be updated once. This PR's workflow does not touch protection; update via Settings -> Branches -> main -> required checks (or let the bot do it via API).

## Result summary

| Metric | Before | After (expected) |
|---|---|---|
| PR pipeline wall time | ~15 min | ~5 min |
| e2e test executions per PR | 204 | 204 (unchanged) |
| Backend suite | 125 tests | 125 tests (unchanged) |
| Coverage / assertions | - | unchanged by construction |
