"""Badminton doubles roster generation engine (library, no CLI)."""

import random


class RosterError(Exception):
    """Raised when roster generation fails due to invalid input."""


def _normalize_pair(pair):
    return tuple(sorted(pair))


def _team_label(team):
    return " & ".join(team)


def _select_resting_players(players, num_resting, must_rest, cannot_rest,
                            rest_counts, consec_play, fixed_pairs):
    resting = set(must_rest)

    still_needed = num_resting - len(resting)
    if still_needed > 0:
        candidates = [p for p in players if p not in resting and p not in cannot_rest]
        candidates.sort(key=lambda p: (rest_counts[p], -consec_play[p]))

        pair_map = {}
        for a, b in fixed_pairs:
            pair_map[a] = b
            pair_map[b] = a

        selected = []
        used = set()
        for c in candidates:
            if len(selected) >= still_needed:
                break
            if c in used:
                continue
            selected.append(c)
            used.add(c)
            partner = pair_map.get(c)
            if partner and partner in candidates and partner not in used and len(selected) < still_needed:
                if partner not in cannot_rest and partner not in resting:
                    selected.append(partner)
                    used.add(partner)

        resting.update(selected[:still_needed])
    elif still_needed < 0:
        overflow = sorted(must_rest, key=lambda p: consec_play[p])
        for p in overflow:
            if still_needed >= 0:
                break
            resting.discard(p)
            still_needed += 1

    return resting


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

    for rnd in range(num_rounds):
        round_num = rnd + 1
        pairs_active = round_num >= pair_start_round

        no_limit = num_rounds + 1
        must_rest = {p for p in players if consec_play[p] >= consecutive_limits.get(p, no_limit)}
        cannot_rest = {p for p in players if consec_rest[p] >= max_consecutive_rest} - must_rest

        resting = _select_resting_players(
            players, num_resting, must_rest, cannot_rest,
            rest_counts, consec_play, fixed_pairs,
        )
        playing = [p for p in players if p not in resting]

        courts = _best_court_assignment(
            playing, num_courts, partner_history, opponent_history,
            fixed_pairs, fixed_pair_counts, pair_target,
            pairs_active, rng=rng,
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
