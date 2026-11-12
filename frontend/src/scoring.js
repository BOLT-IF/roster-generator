export function createEmptyScore() {
  return { teamA: "", teamB: "" };
}

export function createScoresForRounds(rounds) {
  if (!rounds) return [];
  return rounds.map((round) => round.courts.map(() => createEmptyScore()));
}

export function isScoreComplete(score) {
  if (!score) return false;
  return score.teamA !== "" && score.teamB !== "";
}

export function getMatchWinner(score, court) {
  if (!isScoreComplete(score) || score.teamA === score.teamB) {
    return null;
  }

  return score.teamA > score.teamB ? court.team_a : court.team_b;
}

function rankStandings(entries) {
  return [...entries].sort(([nameA, statsA], [nameB, statsB]) => {
    if (statsB.points !== statsA.points) return statsB.points - statsA.points;
    if (statsB.pointDifference !== statsA.pointDifference) {
      return statsB.pointDifference - statsA.pointDifference;
    }
    if (statsB.wins !== statsA.wins) return statsB.wins - statsA.wins;
    return nameA.localeCompare(nameB);
  });
}

export function buildPairStandings(rounds, scoresByRound) {
  const standings = new Map();

  rounds.forEach((round, roundIndex) => {
    round.courts.forEach((court, courtIndex) => {
      const score = scoresByRound[roundIndex]?.[courtIndex];
      const teamAKey = court.team_a.join(" & ");
      const teamBKey = court.team_b.join(" & ");

      if (!isScoreComplete(score)) return;

      if (!standings.has(teamAKey)) {
        standings.set(teamAKey, { points: 0, wins: 0, losses: 0, pointDifference: 0, played: 0 });
      }

      if (!standings.has(teamBKey)) {
        standings.set(teamBKey, { points: 0, wins: 0, losses: 0, pointDifference: 0, played: 0 });
      }

      const teamAStats = standings.get(teamAKey);
      const teamBStats = standings.get(teamBKey);
      const pointDelta = score.teamA - score.teamB;

      teamAStats.played += 1;
      teamBStats.played += 1;
      teamAStats.pointDifference += pointDelta;
      teamBStats.pointDifference -= pointDelta;

      if (score.teamA === score.teamB) return;

      if (score.teamA > score.teamB) {
        teamAStats.points += 2;
        teamAStats.wins += 1;
        teamBStats.losses += 1;
      } else {
        teamBStats.points += 2;
        teamBStats.wins += 1;
        teamAStats.losses += 1;
      }
    });
  });

  return rankStandings(standings.entries());
}

export function buildIndividualStandings(rounds, scoresByRound) {
  const standings = new Map();

  rounds.forEach((round, roundIndex) => {
    round.courts.forEach((court, courtIndex) => {
      const score = scoresByRound[roundIndex]?.[courtIndex];
      if (!isScoreComplete(score)) return;

      const pointDelta = score.teamA - score.teamB;
      const winningTeam = getMatchWinner(score, court);
      const losingTeam =
        winningTeam === court.team_a ? court.team_b : winningTeam === court.team_b ? court.team_a : null;

      [...court.team_a, ...court.team_b].forEach((player) => {
        if (!standings.has(player)) {
          standings.set(player, { points: 0, wins: 0, losses: 0, pointDifference: 0, played: 0 });
        }
      });

      court.team_a.forEach((player) => {
        const stats = standings.get(player);
        stats.played += 1;
        stats.pointDifference += pointDelta;
      });

      court.team_b.forEach((player) => {
        const stats = standings.get(player);
        stats.played += 1;
        stats.pointDifference -= pointDelta;
      });

      if (!winningTeam || !losingTeam) return;

      winningTeam.forEach((player) => {
        const stats = standings.get(player);
        stats.points += 2;
        stats.wins += 1;
      });

      losingTeam.forEach((player) => {
        standings.get(player).losses += 1;
      });
    });
  });

  return rankStandings(standings.entries());
}

export function areRoundsComplete(rounds, scoresByRound) {
  return rounds.every((round, roundIndex) =>
    round.courts.every((_, courtIndex) => isScoreComplete(scoresByRound[roundIndex]?.[courtIndex]))
  );
}

export function filterScoresByEndedRounds(rounds, scoresByRound, endedRounds = []) {
  return rounds.map((round, roundIndex) => {
    if (!endedRounds[roundIndex]) {
      return round.courts.map(() => createEmptyScore());
    }

    return round.courts.map((_, courtIndex) => scoresByRound[roundIndex]?.[courtIndex] || createEmptyScore());
  });
}

export function areEndedRoundsComplete(rounds, scoresByRound, endedRounds = []) {
  return rounds.every((round, roundIndex) => {
    if (!endedRounds[roundIndex]) {
      return false;
    }

    return round.courts.every((_, courtIndex) => isScoreComplete(scoresByRound[roundIndex]?.[courtIndex]));
  });
}

function createKnockoutRound(label, round, matches) {
  return {
    id: label.toLowerCase().replace(/\s+/g, "-"),
    label,
    round,
    courts: matches.map(([teamA, teamB]) => ({ team_a: teamA, team_b: teamB })),
    resting: [],
  };
}

export function buildKnockoutRounds(
  drawConfig,
  roster,
  leagueScoresByRound,
  knockoutScoresByRound,
  endedLeagueRounds = [],
  endedKnockoutRounds = []
) {
  if (drawConfig?.draw_type !== "league_knockout") return [];
  if (!areEndedRoundsComplete(roster.rounds, leagueScoresByRound, endedLeagueRounds)) return [];

  const pairStandings = buildPairStandings(
    roster.rounds,
    filterScoresByEndedRounds(roster.rounds, leagueScoresByRound, endedLeagueRounds)
  );
  // Mirror the server's normalization: legacy sessions can hold odd
  // qualifier counts (3, 5, ...); normalize to the bracket the standings
  // support so seeds[3] can never be undefined.
  let qualifierCount = Math.min(drawConfig.knockout_qualifiers || 4, pairStandings.length);
  if (qualifierCount >= 2 && qualifierCount !== 2 && qualifierCount !== 4) {
    qualifierCount = pairStandings.length >= 4 ? 4 : 2;
  }
  if (qualifierCount < 2) return [];

  const seeds = pairStandings.slice(0, qualifierCount).map(([pairName]) => pairName.split(" & "));
  const baseRound = roster.rounds.length;

  if (qualifierCount === 2) {
    return [createKnockoutRound("Final", baseRound + 1, [[seeds[0], seeds[1]]])];
  }

  const semifinalRound = createKnockoutRound("Semifinals", baseRound + 1, [
    [seeds[0], seeds[3]],
    [seeds[1], seeds[2]],
  ]);

  const rounds = [semifinalRound];
  const semifinalScores = knockoutScoresByRound[0] || [];
  const semifinalWinners = semifinalRound.courts.map((court, courtIndex) =>
    endedKnockoutRounds[0] ? getMatchWinner(semifinalScores[courtIndex], court) : null
  );

  if (semifinalWinners.every(Boolean)) {
    rounds.push(createKnockoutRound("Final", baseRound + 2, [[semifinalWinners[0], semifinalWinners[1]]]));
  }

  return rounds;
}
