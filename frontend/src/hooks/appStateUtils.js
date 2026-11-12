import { matchPath } from "react-router-dom";
import { buildKnockoutRounds, createScoresForRounds } from "../scoring";

export const PLANNER_STORAGE_KEY = "badminton-roster:planner";
export const SESSION_STORAGE_KEY = "badminton-roster:session";
export const SESSION_ACCESS_STORAGE_KEY = "badminton-roster:session-access";
export const ORGANIZER_TOKEN_STORAGE_KEY = "badminton-roster:organizer-token";
export const SESSION_POLL_INTERVAL_MS = 12000;
export const ACTIVE_EDIT_GRACE_MS = 15000;
export const DUPLICATE_KNOCKOUT_VIOLATION_PREFIX = "Duplicate knockout matchup:";
export const PLAIN_SESSION_WAIT_LABELS = new Set([
  "Ending round...",
  "Re-opening round...",
  "Refreshing session...",
]);

export const DEFAULT_CONFIG = {
  num_courts: 5,
  court_numbers: ["1", "2", "3", "4", "5"],
  rounds: 9,
  limits: { Vikram: 2, Vivek: 3 },
  pair_games: 3,
  pair_start_round: 5,
  max_consecutive_rest: 1,
  seed: null,
  draw_type: "round_robin",
  league_meetings: 1,
  knockout_qualifiers: 4,
};

export const ROUTE_PATHS = {
  root: "/",
  planner: "/planner",
  players: "/players",
  sessions: "/sessions",
  scoring: "/sessions/:sessionId",
  history: "/history",
  playerStats: "/stats",
};

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function hasSameShapeAsFallback(value, fallback) {
  if (Array.isArray(fallback)) return Array.isArray(value);
  if (isPlainObject(fallback)) return isPlainObject(value);
  if (fallback === null || fallback === undefined) return isPlainObject(value);
  return typeof value === typeof fallback;
}

// Safe read: never throws (storage disabled, malformed JSON) and never returns a
// value whose type differs from the fallback (e.g. a stored "null" or "123").
// An optional `isValid(value)` can reject further.
export function readStorage(key, fallback, isValid = null) {
  if (typeof window === "undefined") return fallback;

  try {
    const rawValue = window.localStorage.getItem(key);
    if (!rawValue) return fallback;
    const parsed = JSON.parse(rawValue);
    if (!hasSameShapeAsFallback(parsed, fallback)) return fallback;
    if (isValid && !isValid(parsed)) return fallback;
    return parsed;
  } catch {
    return fallback;
  }
}

// Safe write: quota errors / disabled storage must not crash the render tree.
export function writeStorage(key, value) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Persistence is best-effort.
  }
}

export function removeStorage(key) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(key);
  } catch {
    // Persistence is best-effort.
  }
}

// Coerce whatever was persisted for the planner into a structurally safe shape.
export function sanitizePlannerState(raw) {
  if (!isPlainObject(raw)) return null;

  const stringArray = (value) => (Array.isArray(value) ? value.filter((item) => typeof item === "string") : []);
  const pairArray = (value) =>
    Array.isArray(value)
      ? value.filter(
          (pair) => Array.isArray(pair) && pair.length === 2 && pair.every((item) => typeof item === "string")
        )
      : [];

  const config = isPlainObject(raw.config) ? { ...raw.config } : {};
  if (!isPlainObject(config.limits)) delete config.limits;
  if (!Array.isArray(config.court_numbers)) delete config.court_numbers;

  const rosterIsValid =
    isPlainObject(raw.roster) &&
    Array.isArray(raw.roster.rounds) &&
    raw.roster.rounds.every((round) => isPlainObject(round) && Array.isArray(round.courts));
  const baselineIsValid =
    isPlainObject(raw.generatedRosterBaseline) && Array.isArray(raw.generatedRosterBaseline.rounds);

  return {
    selectedPlayerIds: stringArray(raw.selectedPlayerIds),
    fixedPairIds: pairArray(raw.fixedPairIds),
    config,
    roster: rosterIsValid ? raw.roster : null,
    generatedRosterBaseline: rosterIsValid && baselineIsValid ? raw.generatedRosterBaseline : null,
    rosterSignature: rosterIsValid && typeof raw.rosterSignature === "string" ? raw.rosterSignature : null,
    hasManualRosterEdits: rosterIsValid && Boolean(raw.hasManualRosterEdits),
    // Legacy (pre-directory) fields, only used for migration.
    players: Array.isArray(raw.players) ? raw.players : undefined,
    fixedPairs: Array.isArray(raw.fixedPairs) ? raw.fixedPairs : undefined,
  };
}

export function createSessionName() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  const hours = String(now.getHours()).padStart(2, "0");
  const minutes = String(now.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day} ${hours}:${minutes}`;
}

export function normalizeConfig(config) {
  return { ...DEFAULT_CONFIG, ...config };
}

export function getPlannerRosterSignature(selectedPlayerIds, fixedPairIds, config, directoryPlayers) {
  const playersById = new Map(directoryPlayers.map((player) => [player.playerId, player]));
  const selectedPlayers = selectedPlayerIds
    .map((playerId) => playersById.get(playerId))
    .filter(Boolean)
    .map((player) => ({
      playerId: player.playerId,
      shortName: player.shortName,
    }));

  const normalizedPairs = fixedPairIds
    .map(([firstId, secondId]) => {
      const firstPlayer = playersById.get(firstId);
      const secondPlayer = playersById.get(secondId);
      if (!firstPlayer || !secondPlayer) return null;
      return {
        playerIds: [firstId, secondId].sort(),
        shortNames: [firstPlayer.shortName, secondPlayer.shortName].sort(),
      };
    })
    .filter(Boolean)
    .sort((a, b) => a.playerIds.join("|").localeCompare(b.playerIds.join("|")));

  const normalizedConfig = {
    num_courts: config.num_courts,
    court_numbers: config.court_numbers,
    rounds: config.rounds,
    limits: Object.fromEntries(Object.entries(config.limits || {}).sort(([a], [b]) => a.localeCompare(b))),
    pair_games: config.pair_games,
    pair_start_round: config.pair_start_round,
    max_consecutive_rest: config.max_consecutive_rest,
    seed: config.seed,
    draw_type: config.draw_type,
    league_meetings: config.league_meetings,
    knockout_qualifiers: config.knockout_qualifiers,
  };

  return JSON.stringify({
    players: selectedPlayers,
    fixedPairs: normalizedPairs,
    config: normalizedConfig,
  });
}

export function getLeagueRequestPayload(players, fixedPairs, config) {
  return {
    players,
    fixed_pairs: fixedPairs,
    draw_type: config.draw_type,
    num_courts: config.num_courts,
    court_numbers: config.court_numbers,
    rounds: config.rounds,
    limits: config.limits,
    pair_games: config.pair_games,
    pair_start_round: config.pair_start_round,
    max_consecutive_rest: config.max_consecutive_rest,
    seed: config.seed,
  };
}

export function getRosterRevalidatePayload(roster, players, fixedPairs, config) {
  return {
    roster,
    ...getLeagueRequestPayload(players, fixedPairs, config),
  };
}

export function swapRosterSlots(roster, firstSlot, secondSlot) {
  if (!roster) return roster;
  if (!firstSlot || !secondSlot) return roster;
  if (firstSlot.roundIndex !== secondSlot.roundIndex) return roster;

  const nextRoster = {
    ...roster,
    rounds: roster.rounds.map((round, roundIndex) => {
      if (roundIndex !== firstSlot.roundIndex) return round;
      return {
        ...round,
        courts: round.courts.map((court) => ({
          ...court,
          team_a: [...court.team_a],
          team_b: [...court.team_b],
        })),
        resting: [...round.resting],
      };
    }),
  };

  const round = nextRoster.rounds[firstSlot.roundIndex];
  const firstValue = round.courts[firstSlot.courtIndex]?.[firstSlot.teamKey]?.[firstSlot.playerIndex];
  const secondValue = round.courts[secondSlot.courtIndex]?.[secondSlot.teamKey]?.[secondSlot.playerIndex];
  if (!firstValue || !secondValue) return roster;

  round.courts[firstSlot.courtIndex][firstSlot.teamKey][firstSlot.playerIndex] = secondValue;
  round.courts[secondSlot.courtIndex][secondSlot.teamKey][secondSlot.playerIndex] = firstValue;
  return nextRoster;
}

export function swapRosterTeams(roster, firstTeam, secondTeam) {
  if (!roster || !firstTeam || !secondTeam) return roster;
  if (firstTeam.roundIndex !== secondTeam.roundIndex) return roster;

  const nextRoster = {
    ...roster,
    rounds: roster.rounds.map((round, roundIndex) => {
      if (roundIndex !== firstTeam.roundIndex) return round;
      return {
        ...round,
        courts: round.courts.map((court) => ({
          ...court,
          team_a: [...court.team_a],
          team_b: [...court.team_b],
        })),
        resting: [...round.resting],
      };
    }),
  };

  const round = nextRoster.rounds[firstTeam.roundIndex];
  const firstValue = round.courts[firstTeam.courtIndex]?.[firstTeam.teamKey];
  const secondValue = round.courts[secondTeam.courtIndex]?.[secondTeam.teamKey];
  if (!firstValue || !secondValue) return roster;

  round.courts[firstTeam.courtIndex][firstTeam.teamKey] = [...secondValue];
  round.courts[secondTeam.courtIndex][secondTeam.teamKey] = [...firstValue];
  return nextRoster;
}

export function swapRosterRounds(roster, firstRoundIndex, secondRoundIndex) {
  if (!roster) return roster;
  if (firstRoundIndex === secondRoundIndex) return roster;
  if (firstRoundIndex < 0 || secondRoundIndex < 0) return roster;
  if (firstRoundIndex >= roster.rounds.length || secondRoundIndex >= roster.rounds.length) return roster;

  const nextRounds = roster.rounds.map((round) => ({
    ...round,
    courts: round.courts.map((court) => ({
      ...court,
      team_a: [...court.team_a],
      team_b: [...court.team_b],
    })),
    resting: [...round.resting],
  }));

  [nextRounds[firstRoundIndex], nextRounds[secondRoundIndex]] = [nextRounds[secondRoundIndex], nextRounds[firstRoundIndex]];

  return {
    ...roster,
    rounds: nextRounds.map((round, index) => ({
      ...round,
      round: index + 1,
    })),
  };
}

export function getLegacySessionContext(search) {
  const params = new URLSearchParams(search);
  const sessionId = params.get("session");
  if (!sessionId) return null;

  return {
    sessionId,
    editToken: params.get("edit"),
  };
}

export function getRoutePathForView(view) {
  switch (view) {
    case "planner":
      return ROUTE_PATHS.planner;
    case "players":
      return ROUTE_PATHS.players;
    case "sessions":
      return ROUTE_PATHS.sessions;
    case "history":
      return ROUTE_PATHS.history;
    case "player-stats":
      return ROUTE_PATHS.playerStats;
    default:
      return ROUTE_PATHS.planner;
  }
}

export function getViewFromPathname(pathname) {
  if (matchPath({ path: ROUTE_PATHS.planner, end: true }, pathname)) return "planner";
  if (matchPath({ path: ROUTE_PATHS.players, end: true }, pathname)) return "players";
  if (matchPath({ path: ROUTE_PATHS.sessions, end: true }, pathname)) return "sessions";
  if (matchPath({ path: ROUTE_PATHS.history, end: true }, pathname)) return "history";
  if (matchPath({ path: ROUTE_PATHS.playerStats, end: true }, pathname)) return "player-stats";
  if (matchPath({ path: ROUTE_PATHS.scoring, end: true }, pathname)) return "scoring";
  if (pathname === ROUTE_PATHS.root) return "root";
  return null;
}

export function buildSessionPath(sessionId, editToken = null) {
  if (!sessionId) return ROUTE_PATHS.sessions;
  const basePath = `${ROUTE_PATHS.sessions}/${encodeURIComponent(sessionId)}`;
  if (!editToken) return basePath;
  const params = new URLSearchParams({ edit: editToken });
  return `${basePath}?${params.toString()}`;
}

export function buildShareUrl(sessionId, editToken = null) {
  if (typeof window === "undefined" || !sessionId) return "";
  const url = new URL(buildSessionPath(sessionId, editToken), window.location.origin);
  return url.toString();
}

export function normalizeSessionSummary(session) {
  if (!session?.session_id && !session?.sessionId) return null;

  return {
    sessionId: session.sessionId || session.session_id,
    name: session.name || createSessionName(),
    createdAt: session.createdAt || session.created_at || null,
    updatedAt: session.updatedAt || session.updated_at || null,
    drawType: session.drawType || session.draw_type || "round_robin",
    status: session.status || "ready",
    endedRounds: session.endedRounds ?? session.ended_rounds ?? 0,
    totalRounds: session.totalRounds ?? session.total_rounds ?? 0,
    liveRounds: session.liveRounds ?? session.live_rounds ?? 0,
  };
}

export function normalizeSession(session) {
  if (!session?.roster?.rounds) return null;

  const drawConfig = normalizeConfig(session.drawConfig || session.draw_config || {});
  const roster = session.roster;
  const leagueScoresByRound = Array.isArray(session.leagueScoresByRound)
    ? session.leagueScoresByRound
    : Array.isArray(session.league_scores_by_round)
      ? session.league_scores_by_round
      : Array.isArray(session.scoresByRound)
        ? session.scoresByRound
        : createScoresForRounds(roster.rounds);

  const knockoutScoresByRound = Array.isArray(session.knockoutScoresByRound)
    ? session.knockoutScoresByRound
    : Array.isArray(session.knockout_scores_by_round)
      ? session.knockout_scores_by_round
      : [];

  const normalized = {
    sessionId: session.sessionId || session.session_id || null,
    name: session.name || createSessionName(),
    createdAt: session.createdAt || session.created_at || new Date().toISOString(),
    roster,
    drawConfig,
    leagueScoresByRound,
    activeLeagueRound: session.activeLeagueRound ?? session.active_league_round ?? session.activeRound ?? -1,
    endedLeagueRounds: Array.isArray(session.endedLeagueRounds)
      ? session.endedLeagueRounds
      : Array.isArray(session.ended_league_rounds)
        ? session.ended_league_rounds
        : roster.rounds.map(() => false),
    knockoutScoresByRound,
    activeKnockoutRound: session.activeKnockoutRound ?? session.active_knockout_round ?? -1,
    endedKnockoutRounds: Array.isArray(session.endedKnockoutRounds)
      ? session.endedKnockoutRounds
      : Array.isArray(session.ended_knockout_rounds)
        ? session.ended_knockout_rounds
        : [],
    canEdit: session.canEdit ?? session.can_edit ?? false,
    editToken: session.editToken || session.edit_token || null,
    version: session.version || 1,
  };

  const knockoutRounds = buildKnockoutRounds(
    normalized.drawConfig,
    normalized.roster,
    normalized.leagueScoresByRound,
    normalized.knockoutScoresByRound,
    normalized.endedLeagueRounds,
    normalized.endedKnockoutRounds
  );

  return {
    ...normalized,
    knockoutScoresByRound: knockoutRounds.map((round, roundIndex) => {
      const existingScores = normalized.knockoutScoresByRound[roundIndex];
      if (!Array.isArray(existingScores)) return createScoresForRounds([round])[0];
      if (existingScores.length === round.courts.length) return existingScores;
      // Clamp to the round's real court count: drop phantom rows beyond it and
      // pad missing ones, but keep every real score that is already stored.
      const emptyRow = createScoresForRounds([round])[0];
      return round.courts.map((_, courtIndex) => existingScores[courtIndex] ?? emptyRow[courtIndex]);
    }),
    activeKnockoutRound:
      normalized.activeKnockoutRound > knockoutRounds.length - 1
        ? knockoutRounds.length - 1
        : normalized.activeKnockoutRound,
  };
}

export function getScoreSyncKey(stage, roundIndex, courtIndex, teamKey) {
  return `${stage}:${roundIndex}:${courtIndex}:${teamKey}`;
}

export function mergePendingScoreEdits(session, pendingEdits) {
  if (!session) return session;

  let nextSession = session;
  Object.values(pendingEdits).forEach((edit) => {
    const scoresKey = edit.stage === "league" ? "leagueScoresByRound" : "knockoutScoresByRound";
    if (!nextSession[scoresKey]?.[edit.roundIndex]?.[edit.courtIndex]) return;

    nextSession = normalizeSession({
      ...nextSession,
      [scoresKey]: nextSession[scoresKey].map((roundScores, currentRoundIndex) => {
        if (currentRoundIndex !== edit.roundIndex) return roundScores;

        return roundScores.map((courtScore, currentCourtIndex) => {
          if (currentCourtIndex !== edit.courtIndex) return courtScore;
          return { ...courtScore, [edit.teamKey]: edit.rawValue };
        });
      }),
    });
  });

  return nextSession;
}

export function waitForNextPaint() {
  return new Promise((resolve) => {
    window.requestAnimationFrame(() => resolve());
  });
}

export function normalizeCompletedSessionSummary(session) {
  if (!session?.session_id) return null;

  return {
    sessionId: session.session_id,
    sessionName: session.session_name,
    drawType: session.draw_type,
    completedAt: session.completed_at,
    totalPlayers: session.total_players,
    totalMatches: session.total_matches,
    championPair: session.champion_pair || null,
    topPlayer: session.top_player || null,
  };
}

export function normalizePlayerDirectoryEntry(player) {
  if (!player?.player_id) return null;

  return {
    playerId: player.player_id,
    fullName: player.full_name,
    shortName: player.short_name,
    source: player.source || "manual",
    aliases: Array.isArray(player.aliases) ? player.aliases : [],
    createdAt: player.created_at || null,
  };
}

export function normalizePlayerSummary(player) {
  if (!player?.player_name) return null;

  return {
    playerId: player.player_id || null,
    fullName: player.full_name || player.player_name,
    shortName: player.short_name || player.player_name,
    playerName: player.player_name,
    sessionsPlayed: player.sessions_played,
    matchesPlayed: player.matches_played,
    wins: player.wins,
    losses: player.losses,
    draws: player.draws,
    points: player.points,
    pointDifference: player.point_difference,
    leagueMatchesPlayed: player.league_matches_played,
    leagueWins: player.league_wins,
    leagueLosses: player.league_losses,
    leagueDraws: player.league_draws,
    leaguePoints: player.league_points,
    leaguePointDifference: player.league_point_difference,
    knockoutMatchesPlayed: player.knockout_matches_played,
    knockoutWins: player.knockout_wins,
    knockoutLosses: player.knockout_losses,
    knockoutDraws: player.knockout_draws,
    knockoutPoints: player.knockout_points,
    knockoutPointDifference: player.knockout_point_difference,
    championships: player.championships,
    winRate: player.win_rate,
    lastSessionAt: player.last_session_at || null,
  };
}

export function normalizePlayerDetail(detail) {
  if (!detail?.player_name) return null;

  return {
    ...normalizePlayerSummary(detail),
    mostPlayedPartner: detail.most_played_partner
      ? {
          partnerId: detail.most_played_partner.partner_id || null,
          fullName: detail.most_played_partner.full_name || detail.most_played_partner.partner_name,
          shortName: detail.most_played_partner.short_name || detail.most_played_partner.partner_name,
          partnerName: detail.most_played_partner.partner_name,
          matchesPlayed: detail.most_played_partner.matches_played,
          wins: detail.most_played_partner.wins,
          winRate: detail.most_played_partner.win_rate,
        }
      : null,
    topPartners: Array.isArray(detail.top_partners)
      ? detail.top_partners.map((partner) => ({
          partnerId: partner.partner_id || null,
          fullName: partner.full_name || partner.partner_name,
          shortName: partner.short_name || partner.partner_name,
          partnerName: partner.partner_name,
          matchesPlayed: partner.matches_played,
          wins: partner.wins,
          winRate: partner.win_rate,
        }))
      : [],
  };
}
