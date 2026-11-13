"""Badminton doubles roster generation engine (library, no CLI)."""

import random
from collections import Counter
from itertools import combinations


class RosterError(Exception):
    """Raised when roster generation fails due to invalid input."""


def _normalize_pair(pair):
    return tuple(sorted(pair))


def _team_label(team):
    return " & ".join(team)


def _co_key(unit_a, unit_b):
    """Order-independent dict key for a pair of rest units."""
    a, b = sorted((tuple(sorted(unit_a)), tuple(sorted(unit_b))))
    return (a, b)


def _rest_units(players, fixed_pairs, pairs_active, pair_counts=None, pair_target=None):
    """Rest units for the round.

    Once fixed pairs are active, a pair is ONE unit only while it is still
    under its together-target (pair_games). When the pair completes its
    target games it dissolves: the two players go back to being independent
    for courts AND rests (C-1 requirements v2 - "open to be random" after
    the target; accidental re-pairing on a court is allowed). Before
    activation every player is an independent unit.
    """
    if not pairs_active:
        return [[p] for p in players]
    counts = pair_counts or {}
    units = []
    paired = set()
    for pair in fixed_pairs:
        if pair_target is None or counts.get(pair, 0) < pair_target:
            units.append(list(pair))
            paired.update(pair)
    units.extend([p] for p in players if p not in paired)
    return units


def _units_signature(units):
    """Hashable signature of a unit structure, for phase-break detection."""
    return frozenset(frozenset(u) for u in units)


class _SearchBudgetExceeded(Exception):
    """Internal: the rest-schedule search blew its application budget."""


def _plan_schedule(players, num_rounds, num_courts, num_resting, consecutive_limits,
                   fixed_pairs, pair_start_round, max_consecutive_rest, rng,
                   pair_target=3, application_budget=40000, candidate_cap=300):
    """Plan the whole session's rest schedule and (for pure fixed-pair
    rounds) the court pairings, with backtracking search.

    Tries the strictest fairness rules first and relaxes in tiers, following
    the C-1 precedence (limits > max-consecutive-rest > rest-count spread >
    co-rest variety > matchup balance > no back-to-back). Organizer limits
    (consecutive-game limits) are honored in every tier; everything else
    drops one tier at a time. Returns a list of (resting_set, courts)
    tuples per round — courts is a list of (pair, pair) matchups for pure
    fixed-pair rounds, else None (the caller assigns courts greedily) —
    or None when no tier succeeded within its budget, in which case the
    caller falls back entirely to the greedy per-round selection.
    """
    def units_for_round(rnd, pair_counts):
        # Units depend on the pair-together counts at that round: a pair
        # that has completed its pair_games target is dissolved into two
        # singles. The planner only counts pairings from rounds it planned
        # itself, so counts can lag the greedy assigner's by a round - an
        # acceptable approximation that errs on keeping pairs fused longer.
        return _rest_units(
            players, fixed_pairs, rnd + 1 >= pair_start_round,
            pair_counts=pair_counts, pair_target=pair_target,
        )

    no_limit = num_rounds + 1
    all_players = frozenset(players)
    n_pairs = len(fixed_pairs)
    pair_pool = n_pairs * (n_pairs - 1) // 2

    # --- arithmetic feasibility pre-checks (skip tiers that cannot work) ---
    def mcr_feasible():
        # A player resting at most m consecutive rounds must play at least
        # one round in between, so the resting share is at most m/(m+1).
        if num_resting <= 0:
            return True
        return num_resting * (max_consecutive_rest + 1) <= len(players) * max_consecutive_rest

    def co_feasible():
        if num_resting <= 0:
            return True
        # Fewest rest units a round can use (largest units first); every
        # pair of co-resting units consumes one co-rest slot. Checked with
        # the initial (all pairs fused) structure - the loosest case.
        for rnd in range(num_rounds):
            units = units_for_round(rnd, {})
            largest = max(len(u) for u in units) if units else 1
            k_min = -(-num_resting // largest)
            if units and k_min >= 2:
                min_events = num_rounds * (k_min * (k_min - 1) // 2)
                available = len(units) * (len(units) - 1) // 2
                if min_events > available:
                    return False
        return True

    def matchup_feasible():
        # Matchup planning needs at least two active fixed pairs.
        return n_pairs >= 2 and pair_start_round <= num_rounds

    mcr_ok = mcr_feasible()
    matchup_ok = matchup_feasible()

    def tier(co_mode, b2b=True, spread=True, matchup=False):
        flags = {"co": co_mode, "b2b": b2b, "spread": spread, "matchup": matchup}
        if mcr_ok:
            flags["mcr"] = True
        return flags

    # Relaxation ladder, strictest first: matchup balance (priority 6)
    # relaxes before co-rest variety (5), which relaxes before the
    # no-back-to-back rule; rest-count spread outlasts both.
    tiers = []
    if co_feasible():
        if matchup_ok:
            tiers.append(tier("cap1", matchup=True))
        tiers.append(tier("cap1"))
    if matchup_ok:
        tiers.append(tier("spread", matchup=True))
    tiers.append(tier("spread"))
    if matchup_ok:
        tiers.append(tier(None, matchup=True))
    tiers.append(tier(None))
    tiers.append(tier(None, b2b=False))
    if mcr_ok:
        tiers.append({"mcr": True})

    def resting_candidates(rnd, units, must_rest, cannot_rest, enforce_mcr, co, rest_counts):
        """Resting sets for this round, exact size, best-first ordering."""
        order = list(units)
        rng.shuffle(order)

        # Enumerate on the smaller side (resting or playing) to bound the
        # combinations; the other side is the complement of whole units.
        if num_resting <= len(players) - num_resting:
            target = num_resting
            direct = True
        else:
            target = len(players) - num_resting
            direct = False

        subsets = []

        def rec(index, chosen, size):
            if size == target:
                subsets.append(list(chosen))
                return
            if index >= len(order):
                return
            unit = order[index]
            if size + len(unit) <= target:
                rec(index + 1, chosen + [unit], size + len(unit))
            rec(index + 1, chosen, size)

        rec(0, [], 0)

        scored = []
        for subset in subsets:
            members = frozenset(p for u in subset for p in u)
            resting = members if direct else all_players - members
            if not must_rest <= resting:
                continue
            blocked = cannot_rest & resting
            if enforce_mcr and blocked:
                continue
            full = [frozenset(u) for u in units if set(u) <= resting]
            co_max = max(
                [co.get(_co_key(a, b), 0) for a, b in combinations(full, 2)]
                or [0]
            )
            count_sum = sum(rest_counts[p] for p in resting)
            scored.append(((len(blocked), count_sum, co_max, rng.random()), resting))
        scored.sort(key=lambda item: item[0])
        return [resting for _, resting in scored[:candidate_cap]]

    def court_arrangements(resting, pair_counts):
        """All ways to split the playing fixed pairs into courts, or None
        when the round is not a pure fixed-pair round: singles or split
        pairs playing, or a playing pair already at its pair_games target
        (it must split, so the greedy assigner handles the round). Each
        arrangement is a tuple of (pair, pair)."""
        playing = all_players - resting
        playing_pairs = [p for p in fixed_pairs if p[0] in playing and p[1] in playing]
        needed = 2 * num_courts
        if (
            len(playing) != 2 * needed
            or len(playing_pairs) != needed
            or any(pair_counts.get(p, 0) >= pair_target for p in playing_pairs)
        ):
            return None
        partitions = []

        def part(remaining, acc):
            if not remaining:
                partitions.append(tuple(acc))
                return
            first = remaining[0]
            for i in range(1, len(remaining)):
                part(remaining[1:i] + remaining[i + 1:], acc + [(first, remaining[i])])

        part(playing_pairs, [])
        return partitions

    def dfs(rnd, rest_counts, consec_play, consec_rest, co, co_done,
            matchup, pair_counts, prev_resting, prev_units, flags, budget):
        if rnd == num_rounds:
            if flags.get("co") == "spread":
                for phase_units, phase_co in co_done + ((prev_units, co),):
                    n = len(phase_units)
                    if n < 2:
                        continue
                    unit_sets = [frozenset(u) for u in phase_units]
                    values = [
                        phase_co.get(_co_key(unit_sets[i], unit_sets[j]), 0)
                        for i in range(n)
                        for j in range(i + 1, n)
                    ]
                    if max(values) - min(values) > 1:
                        return None
            if flags.get("matchup") and pair_pool:
                values = [
                    matchup.get(_co_key(frozenset(a), frozenset(b)), 0)
                    for a, b in combinations(fixed_pairs, 2)
                ]
                if max(values) - min(values) > 1:
                    return None
            return []
        round_num = rnd + 1
        must_rest = {p for p in players if consec_play[p] >= consecutive_limits.get(p, no_limit)}
        cannot_rest = {p for p in players if consec_rest[p] >= max_consecutive_rest} - must_rest

        # Units for this round (pairs fuse on activation and dissolve when
        # they complete their together-target). A change in the unit
        # structure starts a fresh co-rest phase: co-rest between merged
        # pair units or dissolved singles is only comparable within one
        # structure. The completed phase is kept for the final check.
        units = units_for_round(rnd, pair_counts)
        if prev_units is not None and _units_signature(units) != _units_signature(prev_units):
            phase_co = {}
            phase_done = co_done + ((prev_units, co),)
        else:
            phase_co = co
            phase_done = co_done

        for resting in resting_candidates(rnd, units, must_rest, cannot_rest, flags.get("mcr"), phase_co, rest_counts):
            budget[0] -= 1
            if budget[0] < 0:
                raise _SearchBudgetExceeded()
            if flags.get("b2b") and resting and prev_resting is not None and resting == prev_resting:
                continue

            new_counts = dict(rest_counts)
            for p in resting:
                new_counts[p] += 1
            if flags.get("spread"):
                values = new_counts.values()
                if max(values) - min(values) > 1:
                    continue

            new_co = dict(phase_co)
            full = [frozenset(u) for u in units if set(u) <= resting]
            ok = True
            co_mode = flags.get("co")
            for a, b in combinations(full, 2):
                key = _co_key(a, b)
                value = new_co.get(key, 0) + 1
                if co_mode == "cap1" and value > 1:
                    ok = False
                    break
                new_co[key] = value
            if not ok:
                continue
            if co_mode == "spread":
                unit_count = len(units)
                unit_pair_count = unit_count * (unit_count - 1) // 2
                if unit_pair_count and new_co:
                    events = sum(new_co.values())
                    allowed_max = events // unit_pair_count + 1
                    if max(new_co.values()) > allowed_max:
                        continue

            new_cp = dict(consec_play)
            new_cr = dict(consec_rest)
            for p in players:
                if p in resting:
                    new_cp[p] = 0
                    new_cr[p] += 1
                else:
                    new_cp[p] += 1
                    new_cr[p] = 0

            # Court pairings: only pure fixed-pair rounds in active phases
            # can be planned; everything else falls to the greedy assigner.
            if flags.get("matchup") and round_num >= pair_start_round:
                arrangements = court_arrangements(resting, pair_counts)
            else:
                arrangements = None
            if arrangements is None:
                branches = [(None, matchup)]
            else:
                def arrangement_cost(arr):
                    return sum(
                        (matchup.get(_co_key(a, b), 0) + 1) ** 2 for a, b in arr
                    )
                arrangements = sorted(
                    arrangements, key=lambda arr: (arrangement_cost(arr), rng.random())
                )
                branches = [
                    (arr, matchup)
                    for arr in arrangements
                ]

            for arrangement, _ in branches:
                budget[0] -= 1
                if budget[0] < 0:
                    raise _SearchBudgetExceeded()
                new_matchup = dict(matchup)
                new_pair_counts = dict(pair_counts)
                ok = True
                if arrangement:
                    for a, b in arrangement:
                        key = _co_key(a, b)
                        new_matchup[key] = new_matchup.get(key, 0) + 1
                        new_pair_counts[a] = new_pair_counts.get(a, 0) + 1
                        new_pair_counts[b] = new_pair_counts.get(b, 0) + 1
                    if pair_pool and new_matchup:
                        total = sum(new_matchup.values())
                        allowed_max = total // pair_pool + 1
                        if max(new_matchup.values()) > allowed_max:
                            ok = False
                elif round_num >= pair_start_round:
                    # Courts go to the greedy assigner this round: it forces
                    # every under-target pair with both members playing onto
                    # one team, so approximate the together-increment now -
                    # this keeps dissolution timing (and therefore the unit
                    # structure of later rounds) aligned with reality.
                    playing = all_players - resting
                    for pair in fixed_pairs:
                        if (pair[0] in playing and pair[1] in playing
                                and new_pair_counts.get(pair, 0) < pair_target):
                            new_pair_counts[pair] = new_pair_counts.get(pair, 0) + 1
                if not ok:
                    continue

                tail = dfs(
                    rnd + 1, new_counts, new_cp, new_cr, new_co, phase_done,
                    new_matchup, new_pair_counts, resting, units, flags, budget,
                )
                if tail is not None:
                    return [(resting, arrangement)] + tail
        return None

    for flags in tiers:
        budget = [application_budget]
        try:
            plan = dfs(
                0,
                {p: 0 for p in players},
                {p: 0 for p in players},
                {p: 0 for p in players},
                {},
                (),
                {},
                {p: 0 for p in fixed_pairs},
                None,
                None,
                flags,
                budget,
            )
        except _SearchBudgetExceeded:
            plan = None
        if plan is not None:
            return plan
    return None


def _select_resting_set(players, num_resting, must_rest, cannot_rest,
                        rest_counts, consec_play, co_rest, last_resting,
                        units, pair_map, rng, attempts=300):
    """Pick this round's resting set.

    Precedence (C-1-REQUIREMENTS.md §3): organizer limits first (must_rest
    honored, cannot_rest avoided), then whole pair units, then rest-count
    balance, then co-rest variety, then no repeat of last round's rest set.
    All ties are broken by the seeded RNG, so round-1 resters depend on the
    seed rather than on input order (M-28). `units` and `pair_map` reflect
    the target-aware unit structure (pairs dissolved after completing
    pair_games are independent).

    Returns the set of resting players.
    """
    if num_resting <= 0:
        return set()

    pair_map = pair_map or {}

    def full_resting_units(resting):
        return [frozenset(u) for u in units if set(u) <= resting]

    def build_attempt():
        resting = set(must_rest)
        budget = num_resting - len(resting)

        # Limits first: complete forced players to whole pair units while
        # the budget allows (rest-as-unit outranks count balance).
        for p in sorted(resting):
            partner = pair_map.get(p)
            if partner and partner not in resting and budget >= 1:
                resting.add(partner)
                budget -= 1

        for allow_blocked in (False, True):
            candidates = [
                u for u in units
                if not (set(u) & resting)
                and (allow_blocked or not any(p in cannot_rest for p in u))
            ]
            while budget > 0 and candidates:
                resting_full = full_resting_units(resting)

                def pick_key(unit):
                    co = max(
                        [co_rest.get(_co_key(unit, rf), 0) for rf in resting_full]
                        or [0]
                    )
                    return (sum(rest_counts[p] for p in unit), co, rng.random())

                best_index = min(range(len(candidates)), key=lambda i: pick_key(candidates[i]))
                unit = candidates.pop(best_index)
                if len(unit) <= budget:
                    resting.update(unit)
                    budget -= len(unit)

            if budget <= 0:
                break

        # Leftover budget that no whole unit fits: split the best unit.
        # (Only reachable in mixed/odd configurations; the split is
        # reported as a rest_unit_split warning afterwards.)
        if budget > 0:
            candidates = [u for u in units if not (set(u) & resting)]
            if candidates:
                best = min(
                    candidates,
                    key=lambda u: (
                        any(p in cannot_rest for p in u),
                        sum(rest_counts[p] for p in u),
                        rng.random(),
                    ),
                )
                members = list(best)
                rng.shuffle(members)
                resting.update(members[:budget])

        # Overflow (more forced players than rest slots): drop the least
        # urgent players — non-forced first, then lowest consecutive play.
        while len(resting) > num_resting:
            droppable = [p for p in resting if p not in must_rest]
            if not droppable:
                droppable = sorted(resting)
            drop = min(droppable, key=lambda p: (consec_play[p], rng.random()))
            resting.discard(drop)

        # Safety net: the round requires exactly num_resting resters; a
        # shortfall would silently drop players in the court builder
        # (H-05). Completeness outranks every preference above.
        while len(resting) < num_resting:
            fillable = [p for p in players if p not in resting]
            if not fillable:
                break
            resting.add(min(fillable, key=lambda p: (rest_counts[p], rng.random())))

        return resting

    def score(resting):
        s = 0
        s += 10000 * sum(1 for p in must_rest if p not in resting)
        s += 1000 * sum(1 for p in resting if p in cannot_rest)
        s += 100 * sum(rest_counts[p] for p in resting)
        full = full_resting_units(resting)
        cos = [co_rest.get(_co_key(a, b), 0) for a, b in combinations(full, 2)]
        if cos:
            s += 10 * max(cos) + sum(cos)
        if last_resting is not None and frozenset(resting) == last_resting:
            s += 500
        return s

    best_set, best_score = None, None
    for _ in range(attempts):
        candidate = build_attempt()
        candidate_score = score(candidate)
        if best_score is None or candidate_score < best_score:
            best_set, best_score = candidate, candidate_score
    return best_set


def _fairness_issues(rounds, players, fixed_pairs, pair_start_round, pair_target=None):
    """Derive structured C-1 fairness issues purely from the roster.

    Rules (C-1-REQUIREMENTS.md §5): rest_spread, rest_unit_split,
    corest_spread, matchup_spread (with an unavoidable flag when the
    unevenness is arithmetically forced), and partner_repeat for rotating
    mode. Each issue is {rule, summary, affected, unavoidable}.

    pair_target enables the v2 unit semantics: a pair that has completed
    its together-target is dissolved, so its members resting separately is
    normal (not a split) and co-rest phases break at dissolution.
    """
    issues = []

    rest_counts = Counter()
    for r in rounds:
        for p in r["resting"]:
            rest_counts[p] += 1
    counts = [rest_counts.get(p, 0) for p in players]
    rest_spread = (max(counts) - min(counts)) if counts else 0
    if rest_spread > 1:
        high = [p for p in players if rest_counts.get(p, 0) == max(counts)]
        low = [p for p in players if rest_counts.get(p, 0) == min(counts)]
        issues.append({
            "rule": "rest_spread",
            "summary": f"{', '.join(high)} rest {max(counts)}× while {', '.join(low)} rest {min(counts)}×",
            "affected": high,
            "unavoidable": False,
        })

    # Reconstruct the unit structure round by round: together-counts grow
    # from the courts, and a pair dissolves once its count reaches the
    # target (same order the engine used when it picked the units).
    together_counts = {pair: 0 for pair in fixed_pairs}
    phases = []
    current = None
    prev_sig = None
    for r in rounds:
        active = r["round"] >= pair_start_round
        resting = set(r["resting"])
        units = _rest_units(players, fixed_pairs, active, together_counts, pair_target)
        sig = _units_signature(units)
        if current is None or sig != prev_sig:
            current = {"units": units, "co": Counter()}
            phases.append(current)
        prev_sig = sig

        # A split is only a split while the pair is still a unit (under
        # target); dissolved members resting separately is the v2 semantics.
        unit_pairs = {frozenset(u) for u in units if len(u) == 2}
        if active:
            for pair in fixed_pairs:
                if frozenset(pair) not in unit_pairs:
                    continue
                overlap = resting & set(pair)
                if overlap and len(overlap) < len(pair):
                    issues.append({
                        "rule": "rest_unit_split",
                        "summary": f"{pair[0]} & {pair[1]} split in round {r['round']}",
                        "affected": [f"{pair[0]} & {pair[1]}"],
                        "unavoidable": False,
                    })
        full = [frozenset(u) for u in units if set(u) <= resting]
        for a, b in combinations(full, 2):
            current["co"][_co_key(a, b)] += 1

        for a, b in r["courts"]:
            for pair in fixed_pairs:
                if (pair[0] in a and pair[1] in a) or (pair[0] in b and pair[1] in b):
                    together_counts[pair] += 1

    corest_spread = 0
    for phase in phases:
        unit_pairs = list(combinations(phase["units"], 2))
        if not unit_pairs:
            continue
        values = [
            phase["co"].get(_co_key(frozenset(a), frozenset(b)), 0)
            for a, b in unit_pairs
        ]
        corest_spread = max(corest_spread, max(values) - min(values))
        if max(values) - min(values) > 1:
            hottest = [
                f"{' & '.join(k[0])} + {' & '.join(k[1])}"
                for k, v in phase["co"].items()
                if v == max(values)
            ][:3]
            issues.append({
                "rule": "corest_spread",
                "summary": f"{'; '.join(hottest)} rest together {max(values)}× while some units never rest together",
                "affected": hottest,
                "unavoidable": False,
            })

    matchup_spread = 0
    if fixed_pairs:
        # Fixed-pair mode: pair-vs-pair meetings (AC-M1/M2/M4).
        pair_sets = {frozenset(p) for p in fixed_pairs}
        matchup_counts = Counter()
        for r in rounds:
            if r["round"] < pair_start_round:
                continue
            for a, b in r["courts"]:
                ta, tb = frozenset(a), frozenset(b)
                if ta in pair_sets and tb in pair_sets:
                    matchup_counts[_co_key(a, b)] += 1
        keys = [_co_key(frozenset(a), frozenset(b)) for a, b in combinations(fixed_pairs, 2)]
        values = [matchup_counts.get(k, 0) for k in keys]
        matchup_spread = (max(values) - min(values)) if values else 0
        if matchup_spread >= 1:
            total_matches = sum(matchup_counts.values())
            unavoidable = total_matches > len(keys)
            shorted = [k for k in keys if matchup_counts.get(k, 0) == min(values)]
            labels = [f"{' & '.join(k[0])} vs {' & '.join(k[1])}" for k in shorted]
            summary = (
                f"{len(shorted)} matchup(s) meet {min(values)}× while others meet {max(values)}×"
            )
            if unavoidable:
                summary += f" (unavoidable with {len(rounds)} rounds)"
            issues.append({
                "rule": "matchup_spread",
                "summary": summary,
                "affected": labels,
                "unavoidable": unavoidable,
            })
    else:
        # Rotating mode: opponent balance (target spread ≤2) and partner
        # usage (every pairing once before any repeat) — AC-M3.
        opponent_counts = Counter()
        partnership_used = set()
        partnership_repeats = Counter()
        for r in rounds:
            for a, b in r["courts"]:
                for x in a:
                    for y in b:
                        opponent_counts[tuple(sorted((x, y)))] += 1
                for team in (a, b):
                    key = tuple(sorted(team))
                    if key in partnership_used:
                        partnership_repeats[key] += 1
                    else:
                        partnership_used.add(key)
        player_pairs = [tuple(sorted(x)) for x in combinations(players, 2)]
        values = [opponent_counts.get(k, 0) for k in player_pairs]
        matchup_spread = (max(values) - min(values)) if values else 0
        if matchup_spread > 2:
            hottest = [k for k in player_pairs if opponent_counts.get(k, 0) == max(values)][:3]
            issues.append({
                "rule": "matchup_spread",
                "summary": f"opponents meet between {min(values)}× and {max(values)}× (target spread ≤2)",
                "affected": [f"{k[0]} vs {k[1]}" for k in hottest],
                "unavoidable": False,
            })
        if partnership_repeats and len(partnership_used) < len(player_pairs):
            repeated = list(partnership_repeats)[:3]
            never = [k for k in player_pairs if k not in partnership_used][:3]
            issues.append({
                "rule": "partner_repeat",
                "summary": (
                    f"{sum(partnership_repeats.values())} partnership repeat(s) "
                    f"while {len(player_pairs) - len(partnership_used)} pairing(s) never used"
                ),
                "affected": [f"{' & '.join(k)}" for k in repeated] + [f"never: {' & '.join(k)}" for k in never],
                "unavoidable": False,
            })

    return issues, rest_spread, corest_spread, matchup_spread


def fairness_report(rounds, players, fixed_pairs, pair_start_round, pair_target=None):
    """C-1 AC-W1: the structured fairness report for a generated roster."""
    issues, rest_spread, corest_spread, matchup_spread = _fairness_issues(
        rounds, players, fixed_pairs, pair_start_round, pair_target
    )
    return {
        "rest_spread": rest_spread,
        "corest_spread": corest_spread,
        "matchup_spread": matchup_spread,
        "issues": issues,
    }


def _fairness_warnings(rounds, players, fixed_pairs, pair_start_round, pair_target=None):
    """Fairness warnings as plain strings (rule-prefixed), one per issue.

    Kept for backward compatibility: the API appends these to `warnings`
    while the structured report rides in `fairness`.
    """
    issues, _, _, _ = _fairness_issues(rounds, players, fixed_pairs, pair_start_round, pair_target)
    return [f"{issue['rule']}: {issue['summary']}" for issue in issues]


def _score_assignment(courts, partner_history, opponent_history, fixed_pairs,
                      fixed_pair_counts, pair_target, pairs_active,
                      matchup_history):
    score = 0
    pair_sets = {frozenset(p) for p in fixed_pairs} if pairs_active else set()
    for team_a, team_b in courts:
        score += partner_history.get(tuple(sorted(team_a)), 0) * _PARTNER_WEIGHT
        score += partner_history.get(tuple(sorted(team_b)), 0) * _PARTNER_WEIGHT
        for pa in team_a:
            for pb in team_b:
                count = opponent_history.get(tuple(sorted([pa, pb])), 0)
                score += _OPPONENT_WEIGHT * count * count
        if pairs_active:
            ta, tb = frozenset(team_a), frozenset(team_b)
            if ta in pair_sets and tb in pair_sets:
                # C-1 AC-M1/M2: convex in the meeting count — a linear
                # penalty cannot distinguish arrangements whose count SUMS
                # are equal, so spread would not improve. Quadratic cost
                # makes balanced arrangements strictly cheaper.
                count = matchup_history.get(_co_key(team_a, team_b), 0)
                score += _MATCHUP_WEIGHT * count * count

    for pair in fixed_pairs:
        playing_members = set()
        together = False
        for team_a, team_b in courts:
            for member in pair:
                if member in team_a or member in team_b:
                    playing_members.add(member)
            if pair[0] in team_a and pair[1] in team_a:
                together = True
            if pair[0] in team_b and pair[1] in team_b:
                together = True

        if pairs_active:
            if fixed_pair_counts.get(pair, 0) >= pair_target:
                continue
            if len(playing_members) == 2 and not together:
                score += _PAIR_SPLIT_WEIGHT
        else:
            if together:
                score += 200

    return score


# Balance weights for the court-assignment search (C-1 AC-M1..M3).
# Matchup and opponent costs are CONVEX (count squared): linear penalties
# are blind to arrangements with equal count sums, which is exactly the
# matchup-spread failure mode. The pair-split weight dominates repeat
# matchups so pair-vs-pair courts always win over mixed teams, and the
# partner weight dominates opponent savings so rotating mode uses every
# partnership once before any repeat (in pure fixed-pair rounds the
# partner term is arrangement-invariant, so the large weight is harmless).
_PARTNER_WEIGHT = 40
_OPPONENT_WEIGHT = 2
_MATCHUP_WEIGHT = 30
_PAIR_SPLIT_WEIGHT = 300


def _enumerate_pairings(items):
    """All ways to split items into unordered pairs (105 for 8 items)."""
    results = []

    def rec(remaining, acc):
        if not remaining:
            results.append(tuple(acc))
            return
        first = remaining[0]
        for i in range(1, len(remaining)):
            rec(remaining[1:i] + remaining[i + 1:], acc + [(first, remaining[i])])

    rec(list(items), [])
    return results


def _best_rotating_assignment(playing, num_courts, partner_history,
                              opponent_history, fixed_pairs,
                              fixed_pair_counts, pair_target, rng):
    """Exhaustive court assignment for rotating rounds (no active pairs).

    Systematically enumerates every team partition and court grouping for
    small playing sets (up to 8 players / 2 courts) instead of sampling
    random attempts: the joint partner/opponent objectives need the full
    arrangement space, which random restarts miss (AC-M3). The enumeration
    order is rng-shuffled first so ties stay seed-dependent.
    """
    team_partitions = _enumerate_pairings(sorted(playing))
    rng.shuffle(team_partitions)
    groupings = _enumerate_pairings(range(2 * num_courts))

    best, best_score = None, float("inf")
    for partition in team_partitions:
        teams = [tuple(sorted(team)) for team in partition]
        for grouping in groupings:
            courts = tuple(
                (teams[a], teams[b]) for a, b in grouping
            )
            s = _score_assignment(
                courts, partner_history, opponent_history,
                fixed_pairs, fixed_pair_counts, pair_target,
                False, {},
            )
            if s < best_score:
                best_score = s
                best = [c for c in courts]
    return best


def _best_court_assignment(playing, num_courts, partner_history, opponent_history,
                           fixed_pairs, fixed_pair_counts, pair_target,
                           pairs_active, attempts=500, rng=None, matchup_history=None):
    shuffler = rng if rng is not None else random
    playing_set = set(playing)
    if not pairs_active and len(playing) <= 8 and len(playing) == 4 * num_courts:
        exhaustive = _best_rotating_assignment(
            playing, num_courts, partner_history, opponent_history,
            fixed_pairs, fixed_pair_counts, pair_target, shuffler,
        )
        if exhaustive is not None:
            return exhaustive
    if pairs_active:
        active_pairs = [
            p for p in fixed_pairs
            if p[0] in playing_set and p[1] in playing_set and fixed_pair_counts.get(p, 0) < pair_target
        ]
    else:
        active_pairs = []

    best, best_score = None, float("inf")
    for _ in range(attempts):
        pool = list(playing)
        courts = []

        shuffler.shuffle(active_pairs)
        placed = set()
        court_slots = list(range(num_courts))
        shuffler.shuffle(court_slots)
        slot_idx = 0
        pair_assignments = {}
        for pair in active_pairs:
            if pair[0] in placed or pair[1] in placed or slot_idx >= len(court_slots):
                continue
            c = court_slots[slot_idx]
            pair_assignments[c] = list(pair)
            placed.update(pair)
            slot_idx += 1

        remaining = [p for p in pool if p not in placed]
        shuffler.shuffle(remaining)

        ri = 0
        for c in range(num_courts):
            if c in pair_assignments:
                team_a = pair_assignments[c]
                team_b = [remaining[ri], remaining[ri + 1]]
                ri += 2
            else:
                team_a = [remaining[ri], remaining[ri + 1]]
                team_b = [remaining[ri + 2], remaining[ri + 3]]
                ri += 4
            courts.append((tuple(sorted(team_a)), tuple(sorted(team_b))))

        s = _score_assignment(courts, partner_history, opponent_history,
                              fixed_pairs, fixed_pair_counts, pair_target,
                              pairs_active, matchup_history or {})
        if s < best_score:
            best_score = s
            best = [c for c in courts]

    return best


def validate_roster(rounds, consecutive_limits, max_consecutive_rest,
                    fixed_pairs, fixed_pair_counts, pair_target, pair_start_round):
    """Return a list of human-readable constraint violation strings."""
    players = set()
    for r in rounds:
        for ta, tb in r["courts"]:
            players.update(ta)
            players.update(tb)
        players.update(r["resting"])

    violations = []
    for p in sorted(players):
        cp = 0
        cr = 0
        for r in rounds:
            playing = any(p in ta or p in tb for ta, tb in r["courts"])
            if playing:
                cp += 1
                cr = 0
                limit = consecutive_limits.get(p, len(rounds) + 1)
                if cp > limit:
                    violations.append(
                        f"{p}: played {cp} consecutive (limit {limit}) at round {r['round']}"
                    )
            else:
                cr += 1
                cp = 0
                if cr > max_consecutive_rest:
                    violations.append(
                        f"{p}: rested {cr} consecutive (limit {max_consecutive_rest}) at round {r['round']}"
                    )

    for pair in fixed_pairs:
        count = fixed_pair_counts.get(pair, 0)
        if count < pair_target:
            violations.append(
                f"{pair[0]} & {pair[1]}: played {count} games together (target {pair_target})"
            )

    for r in rounds:
        if r["round"] < pair_start_round:
            for team_a, team_b in r["courts"]:
                for pair in fixed_pairs:
                    if (pair[0] in team_a and pair[1] in team_a) or \
                       (pair[0] in team_b and pair[1] in team_b):
                        violations.append(
                            f"{pair[0]} & {pair[1]}: played together in round {r['round']} "
                            f"(before pair-start-round {pair_start_round})"
                        )

    return violations


def generate_roster(players, num_courts, num_rounds, consecutive_limits,
                    fixed_pairs, pair_target=3, max_consecutive_rest=1,
                    pair_start_round=5, seed=None):
    """Generate a roster and return (rounds, rest_counts, fixed_pair_counts).

    Raises RosterError on invalid input.
    """
    # A dedicated RNG instance keeps seeded generation deterministic
    # without reseeding the process-global random module (which corrupted
    # concurrent seeded requests and every other random consumer).
    rng = random.Random(seed)

    num_playing = num_courts * 4
    num_resting = len(players) - num_playing

    if num_resting < 0:
        raise RosterError(
            f"Need at least {num_playing} players for {num_courts} court(s), "
            f"but only {len(players)} provided."
        )

    warnings = []
    if num_resting == 0 and consecutive_limits:
        warnings.append(
            "No rest slots available (players == courts*4). "
            "Consecutive game limits cannot be enforced."
        )

    rest_counts = {p: 0 for p in players}
    consec_play = {p: 0 for p in players}
    consec_rest = {p: 0 for p in players}
    partner_history = {}
    opponent_history = {}
    matchup_history = {}
    fixed_pair_counts = {p: 0 for p in fixed_pairs}
    rounds = []

    # C-1: plan the whole-session schedule first (rest sets +, for pure
    # fixed-pair rounds, court pairings) via tiered backtracking; fall back
    # to the greedy per-round selection when planning fails. All randomness
    # flows through the seeded rng, so the plan is reproducible per seed
    # and varies across seeds.
    schedule = _plan_schedule(
        players, num_rounds, num_courts, num_resting, consecutive_limits,
        fixed_pairs, pair_start_round, max_consecutive_rest, rng,
        pair_target=pair_target,
    )

    # Co-rest bookkeeping for the greedy fallback: how often each pair of
    # rest units rested together. Reset whenever the unit structure changes
    # (pairs activating, or a pair dissolving after completing its
    # together-target).
    co_rest = {}
    last_resting = None
    prev_units_sig = None

    for rnd in range(num_rounds):
        round_num = rnd + 1
        pairs_active = bool(fixed_pairs) and round_num >= pair_start_round

        # Target-aware units: a pair that completed its pair_games target
        # is dissolved into two independent players (C-1 v2 semantics).
        units = _rest_units(
            players, fixed_pairs, pairs_active,
            pair_counts=fixed_pair_counts, pair_target=pair_target,
        )
        units_sig = _units_signature(units)
        if units_sig != prev_units_sig:
            co_rest = {}
        prev_units_sig = units_sig

        active_pair_map = {}
        for a, b in fixed_pairs:
            if fixed_pair_counts.get((a, b), 0) < pair_target:
                active_pair_map[a] = b
                active_pair_map[b] = a

        if schedule is not None:
            resting = set(schedule[rnd][0])
            planned_courts = schedule[rnd][1]
        else:
            no_limit = num_rounds + 1
            must_rest = {p for p in players if consec_play[p] >= consecutive_limits.get(p, no_limit)}
            cannot_rest = {p for p in players if consec_rest[p] >= max_consecutive_rest} - must_rest

            resting = _select_resting_set(
                players, num_resting, must_rest, cannot_rest,
                rest_counts, consec_play, co_rest, last_resting,
                units, active_pair_map, rng,
            )
            planned_courts = None
        last_resting = frozenset(resting)

        fully_resting = [frozenset(u) for u in units if set(u) <= resting]
        for unit_a, unit_b in combinations(fully_resting, 2):
            key = _co_key(unit_a, unit_b)
            co_rest[key] = co_rest.get(key, 0) + 1

        playing = [p for p in players if p not in resting]

        if planned_courts is not None:
            courts = [
                (tuple(sorted(team_a)), tuple(sorted(team_b)))
                for team_a, team_b in planned_courts
            ]
        else:
            courts = _best_court_assignment(
                playing, num_courts, partner_history, opponent_history,
                fixed_pairs, fixed_pair_counts, pair_target,
                pairs_active, rng=rng, matchup_history=matchup_history,
            )

        # Structural safety net: every player must appear exactly once per
        # round - on a court or resting. A future engine change that breaks
        # this invariant must fail loudly, not silently drop or duplicate
        # players.
        on_courts = [p for team_a, team_b in courts for p in list(team_a) + list(team_b)]
        if (
            len(on_courts) != num_courts * 4
            or len(set(on_courts)) != len(on_courts)
            or set(on_courts) & set(resting)
            or set(on_courts) | set(resting) != set(players)
        ):
            raise RosterError(
                f"Internal scheduling error: round {round_num} does not account "
                "for every player exactly once. Please report this configuration."
            )

        for p in resting:
            rest_counts[p] += 1
            consec_rest[p] += 1
            consec_play[p] = 0
        for p in playing:
            consec_play[p] += 1
            consec_rest[p] = 0

        fixed_pair_set = {frozenset(p) for p in fixed_pairs}
        for team_a, team_b in courts:
            ta, tb = frozenset(team_a), frozenset(team_b)
            if pairs_active and ta in fixed_pair_set and tb in fixed_pair_set:
                key = _co_key(team_a, team_b)
                matchup_history[key] = matchup_history.get(key, 0) + 1
            partner_history[team_a] = partner_history.get(team_a, 0) + 1
            partner_history[team_b] = partner_history.get(team_b, 0) + 1
            for pa in team_a:
                for pb in team_b:
                    key = tuple(sorted([pa, pb]))
                    opponent_history[key] = opponent_history.get(key, 0) + 1
            for pair in fixed_pairs:
                if (pair[0] in team_a and pair[1] in team_a) or \
                   (pair[0] in team_b and pair[1] in team_b):
                    fixed_pair_counts[pair] += 1

        rounds.append({"round": round_num, "courts": courts, "resting": sorted(resting)})

    warnings.extend(_fairness_warnings(rounds, players, fixed_pairs, pair_start_round, pair_target))
    return rounds, rest_counts, fixed_pair_counts, warnings


def generate_fixed_pair_knockout_roster(players, fixed_pairs, num_courts, num_rounds, pair_target):
    """Generate a strict round-robin league schedule for fixed-pair knockout sessions."""
    normalized_players = sorted(players)
    normalized_pairs = [_normalize_pair(pair) for pair in fixed_pairs]

    if not normalized_pairs:
        raise RosterError("League + knockout scheduling requires at least one fixed pair.")

    pair_players = sorted(player for pair in normalized_pairs for player in pair)
    if len(pair_players) != len(set(pair_players)):
        raise RosterError("Each player may appear in at most one fixed pair for league + knockout scheduling.")
    if pair_players != normalized_players:
        raise RosterError("League + knockout scheduling requires every selected player to belong to exactly one fixed pair.")

    team_count = len(normalized_pairs)
    if team_count < 2:
        raise RosterError("Need at least 2 fixed pairs for league + knockout scheduling.")

    teams_with_bye = list(normalized_pairs)
    if team_count % 2 == 1:
        teams_with_bye.append(None)

    base_rounds = len(teams_with_bye) - 1
    matches_per_round = team_count // 2

    if num_courts != matches_per_round:
        raise RosterError(
            f"League + knockout scheduling requires exactly {matches_per_round} court(s) for {team_count} fixed pair(s), "
            f"but {num_courts} provided."
        )
    if num_rounds % base_rounds != 0:
        raise RosterError(
            f"League + knockout scheduling requires rounds to be a multiple of {base_rounds} for {team_count} fixed pair(s), "
            f"but {num_rounds} provided."
        )

    meetings = num_rounds // base_rounds
    expected_pair_target = (team_count - 1) * meetings
    if pair_target != expected_pair_target:
        raise RosterError(
            f"League + knockout scheduling requires pair_games={expected_pair_target} for {team_count} fixed pair(s) "
            f"across {meetings} meeting(s), but {pair_target} provided."
        )

    cycle_rounds = []
    rotation = list(teams_with_bye)
    for _ in range(base_rounds):
        matches = []
        resting_team = None
        for index in range(len(rotation) // 2):
            first_team = rotation[index]
            second_team = rotation[-(index + 1)]
            if first_team is None:
                resting_team = second_team
                continue
            if second_team is None:
                resting_team = first_team
                continue
            matches.append((first_team, second_team))

        cycle_rounds.append({
            "matches": matches,
            "resting_team": resting_team,
        })

        anchor = rotation[0]
        rotated = [rotation[-1], *rotation[1:-1]]
        rotation = [anchor, *rotated]

    rounds = []
    rest_counts = {player: 0 for player in normalized_players}
    fixed_pair_counts = {pair: expected_pair_target for pair in normalized_pairs}

    round_number = 1
    for meeting_index in range(meetings):
        for cycle_round in cycle_rounds:
            courts = []
            for first_team, second_team in cycle_round["matches"]:
                if meeting_index % 2 == 0:
                    courts.append((first_team, second_team))
                else:
                    courts.append((second_team, first_team))

            resting = []
            if cycle_round["resting_team"] is not None:
                resting = list(cycle_round["resting_team"])
                for player in resting:
                    rest_counts[player] += 1

            rounds.append({
                "round": round_number,
                "courts": courts,
                "resting": sorted(resting),
            })
            round_number += 1

    return rounds, rest_counts, fixed_pair_counts, []


def find_duplicate_fixed_pair_matchups(rounds, fixed_pairs):
    """Return duplicate matchup violations for normalized fixed-pair league rounds."""
    normalized_pairs = {_normalize_pair(pair) for pair in fixed_pairs}
    if not normalized_pairs:
        return []

    seen_matchups = {}
    violations = []
    for round_data in rounds:
        for team_a, team_b in round_data.get("courts", []):
            normalized_team_a = _normalize_pair(team_a)
            normalized_team_b = _normalize_pair(team_b)
            if normalized_team_a not in normalized_pairs or normalized_team_b not in normalized_pairs:
                continue

            matchup_key = tuple(sorted((normalized_team_a, normalized_team_b)))
            previous_round = seen_matchups.get(matchup_key)
            if previous_round is not None:
                violations.append(
                    f"Duplicate knockout matchup: {_team_label(matchup_key[0])} vs {_team_label(matchup_key[1])} "
                    f"(rounds {previous_round} and {round_data['round']})"
                )
            else:
                seen_matchups[matchup_key] = round_data["round"]

    return violations
