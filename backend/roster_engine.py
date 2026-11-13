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


def _rest_units(players, fixed_pairs, pairs_active):
    """Rest units for the round: once pairs are active, a fixed pair is one
    unit (both partners rest or neither); unpaired players are single units.
    Before activation every player is an independent unit."""
    if not pairs_active:
        return [[p] for p in players]
    units = []
    paired = set()
    for pair in fixed_pairs:
        units.append(list(pair))
        paired.update(pair)
    units.extend([p] for p in players if p not in paired)
    return units


class _SearchBudgetExceeded(Exception):
    """Internal: the rest-schedule search blew its application budget."""


def _plan_rest_schedule(players, num_rounds, num_resting, consecutive_limits,
                        fixed_pairs, pair_start_round, max_consecutive_rest,
                        rng, application_budget=40000, candidate_cap=300):
    """Plan the whole session's rest schedule with backtracking search.

    Tries the strictest fairness rules first and relaxes in tiers, following
    the C-1 precedence (limits > max-consecutive-rest > rest-count spread >
    co-rest variety / no back-to-back). Organizer limits (consecutive-game
    limits) are honored in every tier; everything else drops one tier at a
    time. Returns a list of frozensets (resting players per round), or None
    when no tier succeeded within its budget — the caller then falls back
    to the greedy per-round selection.
    """
    if num_resting <= 0:
        return [frozenset()] * num_rounds

    units_per_round = [
        _rest_units(players, fixed_pairs, rnd + 1 >= pair_start_round)
        for rnd in range(num_rounds)
    ]
    no_limit = num_rounds + 1
    all_players = frozenset(players)

    # --- arithmetic feasibility pre-checks (skip tiers that cannot work) ---
    def mcr_feasible():
        # A player resting at most m consecutive rounds must play at least
        # one round in between, so the resting share is at most m/(m+1).
        return num_resting * (max_consecutive_rest + 1) <= len(players) * max_consecutive_rest

    def co_feasible():
        # Fewest rest units a round can use (largest units first); every
        # pair of co-resting units consumes one co-rest slot.
        for units in units_per_round:
            largest = max(len(u) for u in units) if units else 1
            k_min = -(-num_resting // largest)
            if units and k_min >= 2:
                min_events = num_rounds * (k_min * (k_min - 1) // 2)
                available = len(units) * (len(units) - 1) // 2
                if min_events > available:
                    return False
        return True

    tiers = []
    # Relaxation ladder, strictest first. Organizer limits (must_rest) are
    # honored in every tier; max-consecutive-rest is kept while arithmetically
    # possible; rest-count spread outlasts co-rest variety, which outlasts the
    # no-back-to-back rule (C-1 precedence §3). The "spread" co mode allows a
    # unit pair to reach floor(events/pairs)+1 during the session but requires
    # the final co-rest spread to be ≤ 1.
    mcr_ok = mcr_feasible()

    def tier(co_mode, b2b=True, spread=True):
        flags = {"co": co_mode, "b2b": b2b, "spread": spread}
        if mcr_ok:
            flags["mcr"] = True
        return flags

    tiers = []
    if co_feasible():
        tiers.append(tier("cap1"))
    tiers.append(tier("spread"))
    tiers.append(tier(None))
    tiers.append(tier(None, b2b=False))
    if mcr_ok:
        tiers.append({"mcr": True})

    def resting_candidates(rnd, must_rest, cannot_rest, enforce_mcr, co, rest_counts):
        """Resting sets for this round, exact size, best-first ordering."""
        units = units_per_round[rnd]
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

    def dfs(rnd, rest_counts, consec_play, consec_rest, co, co_done, prev_resting, flags, budget):
        if rnd == num_rounds:
            if flags.get("co") == "spread":
                for phase_units, phase_co in co_done + ((units_per_round[rnd - 1], co),):
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
            return []
        round_num = rnd + 1
        must_rest = {p for p in players if consec_play[p] >= consecutive_limits.get(p, no_limit)}
        cannot_rest = {p for p in players if consec_rest[p] >= max_consecutive_rest} - must_rest

        # Fixed pairs activating: co-rest history starts fresh for the new
        # (merged) unit structure; the completed phase is kept for the final
        # spread check.
        if round_num == pair_start_round:
            phase_co = {}
            phase_done = co_done + ((units_per_round[rnd - 1] if rnd else units_per_round[0], co),)
        else:
            phase_co = co
            phase_done = co_done

        for resting in resting_candidates(rnd, must_rest, cannot_rest, flags.get("mcr"), phase_co, rest_counts):
            budget[0] -= 1
            if budget[0] < 0:
                raise _SearchBudgetExceeded()
            if flags.get("b2b") and prev_resting is not None and resting == prev_resting:
                continue

            new_counts = dict(rest_counts)
            for p in resting:
                new_counts[p] += 1
            if flags.get("spread"):
                values = new_counts.values()
                if max(values) - min(values) > 1:
                    continue

            new_co = dict(phase_co)
            units = units_per_round[rnd]
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
                pair_count = unit_count * (unit_count - 1) // 2
                if pair_count and new_co:
                    events = sum(new_co.values())
                    allowed_max = events // pair_count + 1
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

            tail = dfs(rnd + 1, new_counts, new_cp, new_cr, new_co, phase_done, resting, flags, budget)
            if tail is not None:
                return [resting] + tail
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
                        fixed_pairs, pairs_active, rng, attempts=300):
    """Pick this round's resting set.

    Precedence (C-1-REQUIREMENTS.md §3): organizer limits first (must_rest
    honored, cannot_rest avoided), then whole pair units, then rest-count
    balance, then co-rest variety, then no repeat of last round's rest set.
    All ties are broken by the seeded RNG, so round-1 resters depend on the
    seed rather than on input order (M-28).

    Returns the set of resting players.
    """
    if num_resting <= 0:
        return set()

    pair_map = {}
    if pairs_active:
        for a, b in fixed_pairs:
            pair_map[a] = b
            pair_map[b] = a

    units = _rest_units(players, fixed_pairs, pairs_active)

    def full_resting_units(resting):
        return [frozenset(u) for u in units if set(u) <= resting]

    def build_attempt():
        resting = set(must_rest)
        budget = num_resting - len(resting)

        # Limits first: complete forced players to whole pair units while
        # the budget allows (rest-as-unit outranks count balance).
        if pairs_active:
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


def _fairness_warnings(rounds, players, fixed_pairs, pair_start_round):
    """Derive rest-fairness warnings purely from the generated roster.

    Rules (C-1-REQUIREMENTS.md §5): rest_spread, rest_unit_split,
    corest_spread. Strings are prefixed with the rule name so later layers
    can structure them; the planner shows them as-is.
    """
    warnings = []

    rest_counts = Counter()
    for r in rounds:
        for p in r["resting"]:
            rest_counts[p] += 1
    counts = [rest_counts.get(p, 0) for p in players]
    if counts and max(counts) - min(counts) > 1:
        high = [p for p in players if rest_counts.get(p, 0) == max(counts)]
        low = [p for p in players if rest_counts.get(p, 0) == min(counts)]
        warnings.append(
            f"rest_spread: {', '.join(high)} rest {max(counts)}× "
            f"while {', '.join(low)} rest {min(counts)}×"
        )

    phases = {}
    for r in rounds:
        active = r["round"] >= pair_start_round
        resting = set(r["resting"])
        if active:
            for pair in fixed_pairs:
                overlap = resting & set(pair)
                if overlap and len(overlap) < len(pair):
                    warnings.append(
                        f"rest_unit_split: {pair[0]} & {pair[1]} split in round {r['round']}"
                    )
        units = _rest_units(players, fixed_pairs, active)
        phase = phases.setdefault(active, {"units": units, "co": Counter()})
        full = [frozenset(u) for u in units if set(u) <= resting]
        for a, b in combinations(full, 2):
            phase["co"][_co_key(a, b)] += 1

    for phase in phases.values():
        unit_pairs = list(combinations(phase["units"], 2))
        if not unit_pairs:
            continue
        values = [
            phase["co"].get(_co_key(frozenset(a), frozenset(b)), 0)
            for a, b in unit_pairs
        ]
        if max(values) - min(values) > 1:
            hottest = [
                f"{' & '.join(k[0])} + {' & '.join(k[1])}"
                for k, v in phase["co"].items()
                if v == max(values)
            ][:3]
            warnings.append(
                f"corest_spread: {'; '.join(hottest)} rest together {max(values)}× "
                f"while some units never rest together"
            )

    return warnings


def _score_assignment(courts, partner_history, opponent_history, fixed_pairs,
                      fixed_pair_counts, pair_target, pairs_active):
    score = 0
    for team_a, team_b in courts:
        score += partner_history.get(tuple(sorted(team_a)), 0) * 3
        score += partner_history.get(tuple(sorted(team_b)), 0) * 3
        for pa in team_a:
            for pb in team_b:
                score += opponent_history.get(tuple(sorted([pa, pb])), 0)

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
                score += 100
        else:
            if together:
                score += 200

    return score


def _best_court_assignment(playing, num_courts, partner_history, opponent_history,
                           fixed_pairs, fixed_pair_counts, pair_target,
                           pairs_active, attempts=500, rng=None):
    shuffler = rng if rng is not None else random
    playing_set = set(playing)
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
                              pairs_active)
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
    fixed_pair_counts = {p: 0 for p in fixed_pairs}
    rounds = []

    # C-1: plan the whole-session rest schedule first (tiered fairness
    # rules via backtracking); fall back to the greedy per-round selection
    # when planning fails. All randomness flows through the seeded rng, so
    # the plan is reproducible per seed and varies across seeds.
    rest_plan = _plan_rest_schedule(
        players, num_rounds, num_resting, consecutive_limits,
        fixed_pairs, pair_start_round, max_consecutive_rest, rng,
    )

    # Co-rest bookkeeping for the greedy fallback: how often each pair of
    # rest units rested together. Reset when the unit structure changes
    # (fixed pairs activating).
    co_rest = {}
    last_resting = None
    pairs_active_previous = False

    for rnd in range(num_rounds):
        round_num = rnd + 1
        pairs_active = round_num >= pair_start_round
        if pairs_active != pairs_active_previous:
            co_rest = {}
        pairs_active_previous = pairs_active

        if rest_plan is not None:
            resting = set(rest_plan[rnd])
        else:
            no_limit = num_rounds + 1
            must_rest = {p for p in players if consec_play[p] >= consecutive_limits.get(p, no_limit)}
            cannot_rest = {p for p in players if consec_rest[p] >= max_consecutive_rest} - must_rest

            resting = _select_resting_set(
                players, num_resting, must_rest, cannot_rest,
                rest_counts, consec_play, co_rest, last_resting,
                fixed_pairs, pairs_active, rng,
            )
        last_resting = frozenset(resting)

        units = _rest_units(players, fixed_pairs, pairs_active)
        fully_resting = [frozenset(u) for u in units if set(u) <= resting]
        for unit_a, unit_b in combinations(fully_resting, 2):
            key = _co_key(unit_a, unit_b)
            co_rest[key] = co_rest.get(key, 0) + 1

        playing = [p for p in players if p not in resting]

        courts = _best_court_assignment(
            playing, num_courts, partner_history, opponent_history,
            fixed_pairs, fixed_pair_counts, pair_target,
            pairs_active, rng=rng,
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

        for team_a, team_b in courts:
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

    warnings.extend(_fairness_warnings(rounds, players, fixed_pairs, pair_start_round))
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
