import { useEffect, useRef, useState } from "react";

import { formatSessionPill, scoringCopy } from "../content/uiCopy";
import {
  areEndedRoundsComplete,
  buildIndividualStandings,
  buildKnockoutRounds,
  buildPairStandings,
  createScoresForRounds,
  filterScoresByEndedRounds,
  getMatchWinner,
  isScoreComplete,
} from "../scoring";

function getRoundStatus(roundIndex, activeRound, endedRounds) {
  if (endedRounds[roundIndex]) {
    return "completed";
  }
  if (roundIndex <= activeRound) {
    return "live";
  }
  return "pending";
}

function formatPointDifference(value) {
  return value > 0 ? `+${value}` : value;
}

function StatusBadge({ status }) {
  const styles = {
    completed: "bg-green-100 text-green-700 border-green-200",
    live: "bg-indigo-100 text-indigo-700 border-indigo-200",
    pending: "bg-gray-100 text-gray-600 border-gray-200",
  };

  const labels = {
    completed: "Completed",
    live: "Live",
    pending: "Pending",
  };

  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium ${styles[status]}`}>
      {labels[status]}
    </span>
  );
}

function formatTeamName(team) {
  return Array.isArray(team) && team.length > 0 ? team.join(" & ") : "TBD";
}

function getBracketMatchState(score, winner, roundEnded) {
  if (winner) return "decided";
  if (roundEnded) return "ended";
  if (isScoreComplete(score)) return "scored";
  return "waiting";
}

function BracketMatchCard({ title, court, score, winner, roundEnded }) {
  const matchState = getBracketMatchState(score, winner, roundEnded);
  const teamARowActive = winner && winner.join(" & ") === court.team_a.join(" & ");
  const teamBRowActive = winner && winner.join(" & ") === court.team_b.join(" & ");

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">{title}</p>
        <span
          className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
            matchState === "decided"
              ? "bg-emerald-100 text-emerald-700"
              : matchState === "scored"
                ? "bg-amber-100 text-amber-700"
                : "bg-slate-100 text-slate-600"
          }`}
        >
          {matchState === "decided" ? "Winner Locked" : matchState === "scored" ? "Ready to End" : "Awaiting Result"}
        </span>
      </div>

      <div className="mt-4 space-y-2">
        <div
          className={`flex items-center justify-between rounded-xl border px-3 py-3 ${
            teamARowActive ? "border-emerald-200 bg-emerald-50" : "border-slate-200 bg-slate-50"
          }`}
        >
          <p className="text-sm font-semibold text-slate-900">{formatTeamName(court.team_a)}</p>
          <p className="text-lg font-bold text-slate-700">{score?.teamA !== "" ? score.teamA : "-"}</p>
        </div>
        <div
          className={`flex items-center justify-between rounded-xl border px-3 py-3 ${
            teamBRowActive ? "border-emerald-200 bg-emerald-50" : "border-slate-200 bg-slate-50"
          }`}
        >
          <p className="text-sm font-semibold text-slate-900">{formatTeamName(court.team_b)}</p>
          <p className="text-lg font-bold text-slate-700">{score?.teamB !== "" ? score.teamB : "-"}</p>
        </div>
      </div>

      <div className="mt-3 min-h-6 text-sm font-medium text-slate-600">
        {winner ? `Advances: ${formatTeamName(winner)}` : roundEnded ? "Round ended without a winner" : "Winner will advance here"}
      </div>
    </div>
  );
}

function ChampionCard({ winner }) {
  return (
    <div className="rounded-3xl border border-amber-200 bg-gradient-to-br from-amber-100 via-yellow-50 to-white p-6 text-center shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.25em] text-amber-700">
        {winner ? "Champion" : "Title Match"}
      </p>
      <p className="mt-3 text-2xl font-bold text-slate-900">{winner ? formatTeamName(winner) : "Champion TBD"}</p>
      <p className="mt-2 text-sm text-amber-800">
        {winner ? "Playoffs complete. This pair won the final." : "The final winner will be highlighted here."}
      </p>
    </div>
  );
}

function LiveBracket({ rounds, scoresByRound, endedRounds }) {
  if (rounds.length === 0) return null;

  const bracketRounds = rounds.map((round, roundIndex) => ({
    ...round,
    roundEnded: endedRounds[roundIndex],
    matches: round.courts.map((court, courtIndex) => {
      const score = scoresByRound[roundIndex]?.[courtIndex];
      return {
        id: `${round.id || round.label}-${courtIndex}`,
        title: round.courts.length > 1 ? `Match ${courtIndex + 1}` : round.label,
        court,
        score,
        winner: endedRounds[roundIndex] ? getMatchWinner(score, court) : null,
      };
    }),
  }));

  const champion = bracketRounds.at(-1)?.matches?.[0]?.winner || null;

  return (
    <div className="rounded-3xl border border-slate-200 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-800 p-5 text-white shadow-sm sm:p-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-medium text-slate-300">Live Bracket</p>
          <h3 className="mt-1 text-xl font-semibold">Follow the playoff path to the title</h3>
        </div>
        <p className="text-sm text-slate-300">The bracket updates as knockout rounds are ended.</p>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
        <div className="grid gap-4">
          {bracketRounds.map((round) => (
            <div key={round.id} className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <div className="mb-3 flex items-center justify-between gap-3">
                <h4 className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-200">{round.label}</h4>
                <span className="rounded-full bg-white/10 px-2.5 py-1 text-xs font-semibold text-slate-200">
                  {round.matches.length} match{round.matches.length > 1 ? "es" : ""}
                </span>
              </div>
              <div className="grid gap-3">
                {round.matches.map((match) => (
                  <BracketMatchCard
                    key={match.id}
                    title={match.title}
                    court={match.court}
                    score={match.score}
                    winner={match.winner}
                    roundEnded={round.roundEnded}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>

        <div className="hidden items-center justify-center lg:flex">
          <div className="h-full w-px bg-white/10" />
        </div>

        <div className="flex items-center">
          <ChampionCard winner={champion} />
        </div>
      </div>
    </div>
  );
}

function RankingTable({ title, emptyText, label, standings }) {
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">{title}</h3>
      {standings.length > 0 ? (
        <div className="mt-4 space-y-3 md:hidden">
          {standings.map(([name, stats]) => (
            <div key={name} className="rounded-xl border border-gray-200 bg-gray-50 p-3">
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm font-semibold text-gray-900 break-words">{name}</p>
                <span className="shrink-0 rounded-full bg-indigo-100 px-2.5 py-1 text-xs font-semibold text-indigo-700">
                  {stats.points} pts
                </span>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
                <div className="rounded-lg bg-white px-2 py-2">
                  <p className="text-gray-400">Wins</p>
                  <p className="mt-1 font-semibold text-green-700">{stats.wins}</p>
                </div>
                <div className="rounded-lg bg-white px-2 py-2">
                  <p className="text-gray-400">Losses</p>
                  <p className="mt-1 font-semibold text-rose-600">{stats.losses}</p>
                </div>
                <div className="rounded-lg bg-white px-2 py-2">
                  <p className="text-gray-400">Diff</p>
                  <p className="mt-1 font-semibold text-gray-700">{formatPointDifference(stats.pointDifference)}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : null}
      {standings.length > 0 ? (
        <div className="mt-4 hidden overflow-hidden rounded-xl border border-gray-200 md:block">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-3 py-2 text-left font-semibold">{label}</th>
                <th className="px-3 py-2 text-right font-semibold">Points</th>
                <th className="px-3 py-2 text-right font-semibold">Win</th>
                <th className="px-3 py-2 text-right font-semibold">Loss</th>
                <th className="px-3 py-2 text-right font-semibold">Point Difference</th>
              </tr>
            </thead>
            <tbody>
              {standings.map(([name, stats]) => (
                <tr key={name} className="border-t border-gray-100 bg-white">
                  <td className="px-3 py-2 font-medium text-gray-800">{name}</td>
                  <td className="px-3 py-2 text-right font-semibold text-indigo-700">{stats.points}</td>
                  <td className="px-3 py-2 text-right font-semibold text-green-700">{stats.wins}</td>
                  <td className="px-3 py-2 text-right font-semibold text-rose-600">{stats.losses}</td>
                  <td className="px-3 py-2 text-right font-semibold text-gray-700">
                    {formatPointDifference(stats.pointDifference)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="mt-3 text-sm text-gray-500">{emptyText}</p>
      )}
    </div>
  );
}

function CollapsibleSection({ title, description, count, defaultOpen = false, children }) {
  return (
    <details className="group rounded-2xl border border-gray-200 bg-white shadow-sm" open={defaultOpen}>
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4">
        <div>
          <p className="text-base font-semibold text-gray-900">{title}</p>
          {description ? <p className="mt-1 text-sm text-gray-500">{description}</p> : null}
        </div>
        <span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs font-semibold text-gray-600">{count}</span>
      </summary>
      <div className="border-t border-gray-100 p-5 pt-4">{children}</div>
    </details>
  );
}

function SummaryMetric({ label, value, tone = "default" }) {
  const tones = {
    default: "border-slate-200 bg-white text-slate-900",
    indigo: "border-indigo-200 bg-indigo-50 text-indigo-900",
    emerald: "border-emerald-200 bg-emerald-50 text-emerald-900",
    amber: "border-amber-200 bg-amber-50 text-amber-900",
  };

  return (
    <div className={`rounded-2xl border p-4 shadow-sm ${tones[tone]}`}>
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">{label}</p>
      <p className="mt-2 text-lg font-semibold">{value}</p>
    </div>
  );
}

function SummaryCallout({ children }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600 shadow-sm">
      {children}
    </div>
  );
}

function TournamentSummary({
  drawConfig,
  sessionName,
  totalRounds,
  completedRounds,
  champion,
  pairStandings,
  individualStandings,
}) {
  const topPair = pairStandings[0] || null;
  const topPlayer = individualStandings[0] || null;
  const isKnockout = drawConfig?.draw_type === "league_knockout";

  return (
    <div className="space-y-6">
      <div className="rounded-3xl border border-emerald-200 bg-gradient-to-br from-emerald-50 via-white to-sky-50 p-6 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-[0.25em] text-emerald-700">Tournament Results</p>
        <h3 className="mt-2 text-2xl font-bold text-slate-900">Session complete</h3>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          {sessionName} is wrapped up. Review the final standings, the winning pair, and the completed results from the
          session here.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SummaryMetric
          label="Format"
          value={drawConfig?.draw_type === "league_knockout" ? "League + Knockout" : "Round Robin"}
          tone="indigo"
        />
        <SummaryMetric label="Rounds Completed" value={`${completedRounds} / ${totalRounds}`} tone="emerald" />
        <SummaryMetric label="Top Pair In League" value={topPair ? topPair[0] : "No league pair standings yet"} tone="amber" />
        <SummaryMetric label="Top Individual In League" value={topPlayer ? topPlayer[0] : "No league player standings yet"} />
      </div>

      <SummaryCallout>
        League standings are based on completed league rounds only. Playoff matches decide the champion, but they do not
        change the league table.
      </SummaryCallout>

      {isKnockout ? <ChampionCard winner={champion} /> : null}

      <div className="space-y-6">
        <CollapsibleSection
          title="Final League Pair Rankings"
          description="Based on completed league rounds only. Playoff matches do not change this table."
          count={pairStandings.length}
        >
          <RankingTable
            title="Final League Pair Rankings"
            emptyText="League pair rankings will appear after completed rounds."
            label="Pair"
            standings={pairStandings}
          />
        </CollapsibleSection>

        <CollapsibleSection
          title="Final League Individual Rankings"
          description="Based on completed league rounds only. Playoff matches do not change this table."
          count={individualStandings.length}
        >
          <RankingTable
            title="Final League Individual Rankings"
            emptyText="League individual rankings will appear after completed rounds."
            label="Player"
            standings={individualStandings}
          />
        </CollapsibleSection>
      </div>
    </div>
  );
}

function RoundList({
  title,
  rounds,
  scoresByRound,
  activeRound,
  endedRounds,
  canEdit,
  stage,
  onStartRound,
  onEndRound,
  onEditRound,
  onScoreChange,
  onScoreCommit,
  pendingRoundAction,
}) {
  if (rounds.length === 0) return null;

  return (
    <div className="space-y-5">
      {title ? (
        <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
          <h3 className="text-base font-semibold text-gray-900">{title}</h3>
          <p className="text-sm text-gray-500">{rounds.length} round{rounds.length > 1 ? "s" : ""}</p>
        </div>
      ) : null}

      {rounds.map((round, roundIndex) => {
        const sourceIndex = round.sourceIndex ?? roundIndex;
        const roundScores = scoresByRound[sourceIndex] || createScoresForRounds([round])[0];
        const status = getRoundStatus(sourceIndex, activeRound, endedRounds);
        // The next round's Start stays disabled until the current round is
        // ended - one live round at a time (the backend enforces the same
        // rule; field bug 2026-11-14 showed starting early stranded the
        // live round forever).
        const canStart =
          sourceIndex === activeRound + 1 &&
          (activeRound < 0 || endedRounds[activeRound]);
        const isEnded = endedRounds[sourceIndex];
        const isLive = status === "live";
        const hasTiedMatch = roundScores.some(
          (score) => isScoreComplete(score) && score.teamA === score.teamB
        );
        const canEnd = isLive && roundScores.every(isScoreComplete) && !(stage === "knockout" && hasTiedMatch);
        const isPendingAction =
          pendingRoundAction?.stage === stage && pendingRoundAction?.roundIndex === sourceIndex;
        const actionLabel = isEnded ? "Edit Scores" : isLive ? "End Round" : "Start Round";
        const pendingActionLabel =
          pendingRoundAction?.action === "end"
            ? "Ending Round..."
            : pendingRoundAction?.action === "edit"
              ? "Reopening Round..."
              : pendingRoundAction?.action === "start"
                ? "Starting Round..."
                : actionLabel;
        const actionClassName = isEnded
          ? "bg-amber-500 hover:bg-amber-600"
          : isLive
            ? "bg-rose-600 hover:bg-rose-700"
            : "bg-indigo-600 hover:bg-indigo-700";
        const actionDisabled = isPendingAction || !canEdit || (isEnded ? false : isLive ? !canEnd : !canStart);
        const handleRoundAction = () =>
          isEnded
            ? onEditRound(stage, sourceIndex)
            : isLive
              ? onEndRound(stage, sourceIndex)
              : onStartRound(stage, sourceIndex);

        return (
          <section
            key={`${stage}-${round.id || round.round}`}
            className={`overflow-hidden rounded-2xl border bg-white shadow-sm transition-colors ${
              status === "live" ? "border-indigo-200" : "border-gray-200"
            }`}
          >
            <div className="flex flex-col gap-3 border-b border-gray-100 px-4 py-4 sm:px-5 md:flex-row md:items-center md:justify-between">
              <div>
                <div className="flex items-center gap-3">
                  <h4 className="text-lg font-semibold text-gray-900">{round.label || `Round ${round.round}`}</h4>
                  <StatusBadge status={status} />
                </div>
                <p className="mt-1 text-sm text-gray-500">
                  {round.courts.length} court{round.courts.length > 1 ? "s" : ""} scheduled
                  {round.resting?.length > 0 ? ` • Resting: ${round.resting.join(", ")}` : " • No one resting"}
                </p>
              </div>
              {isLive ? (
                <button
                  onClick={handleRoundAction}
                  disabled={actionDisabled}
                  className={`hidden min-h-11 items-center justify-center rounded-lg px-4 py-2.5 text-sm font-semibold text-white transition-colors disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500 md:inline-flex ${actionClassName}`}
                >
                  {isPendingAction ? pendingActionLabel : actionLabel}
                </button>
              ) : (
                <button
                  onClick={handleRoundAction}
                  disabled={actionDisabled}
                  className={`inline-flex min-h-11 items-center justify-center rounded-lg px-4 py-2.5 text-sm font-semibold text-white transition-colors disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500 ${actionClassName}`}
                >
                  {isPendingAction ? pendingActionLabel : actionLabel}
                </button>
              )}
            </div>

            <div className="space-y-4 p-4 sm:p-5">
              {round.courts.map((court, courtIndex) => {
                const score = roundScores[courtIndex];
                const winner = getMatchWinner(score, court);
                const hasCompleteTeams =
                  Array.isArray(court.team_a) &&
                  court.team_a.length > 0 &&
                  Array.isArray(court.team_b) &&
                  court.team_b.length > 0;
                const inputsEnabled = canEdit && sourceIndex <= activeRound && !isEnded && hasCompleteTeams;

                return (
                  <div key={courtIndex} className="rounded-xl border border-gray-200 bg-gray-50 p-4">
                    <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
                      <div className="space-y-3">
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                            {stage === "league" ? `Court ${round.court_numbers?.[courtIndex] ?? courtIndex + 1}` : "Match"}
                            {court.friendly ? (
                              <span className="ml-1.5 rounded-full border border-amber-300 bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700">
                                Friendly
                              </span>
                            ) : null}
                          </p>
                          <div className="mt-2 flex flex-col gap-2 text-sm text-gray-800">
                            <p className="rounded-lg bg-white px-3 py-2 font-medium shadow-sm">
                              {formatTeamName(court.team_a)}
                            </p>
                            <p className="rounded-lg bg-white px-3 py-2 font-medium shadow-sm">
                              {formatTeamName(court.team_b)}
                            </p>
                          </div>
                        </div>
                        {!hasCompleteTeams ? (
                          <p className="text-sm font-medium text-amber-700">Waiting for the previous playoff result.</p>
                        ) : null}
                        {winner && (
                          <p className="text-sm font-medium text-green-700">Winner: {winner.join(" & ")}</p>
                        )}
                      </div>

                      <div className="grid grid-cols-[1fr_auto_1fr] items-end gap-3 sm:max-w-xs">
                        <label className="text-xs font-medium uppercase tracking-wide text-gray-500">
                          Team A
                          <input
                            type="number"
                            min={0}
                            value={score.teamA}
                            disabled={!inputsEnabled}
                            onChange={(event) => onScoreChange(stage, sourceIndex, courtIndex, "teamA", event.target.value)}
                            onBlur={(event) => onScoreCommit(stage, sourceIndex, courtIndex, "teamA", event.target.value)}
                            className="mt-1 block w-full min-w-0 rounded-lg border border-gray-300 bg-white px-3 py-3 text-center text-lg font-semibold text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 disabled:cursor-not-allowed disabled:bg-gray-100"
                          />
                        </label>
                        <span className="pb-3 text-center text-sm font-semibold text-gray-400">vs</span>
                        <label className="text-xs font-medium uppercase tracking-wide text-gray-500">
                          Team B
                          <input
                            type="number"
                            min={0}
                            value={score.teamB}
                            disabled={!inputsEnabled}
                            onChange={(event) => onScoreChange(stage, sourceIndex, courtIndex, "teamB", event.target.value)}
                            onBlur={(event) => onScoreCommit(stage, sourceIndex, courtIndex, "teamB", event.target.value)}
                            className="mt-1 block w-full min-w-0 rounded-lg border border-gray-300 bg-white px-3 py-3 text-center text-lg font-semibold text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 disabled:cursor-not-allowed disabled:bg-gray-100"
                          />
                        </label>
                      </div>
                    </div>
                  </div>
                );
              })}

              {isLive ? (
                <div className="md:hidden">
                  <button
                    onClick={handleRoundAction}
                    disabled={actionDisabled}
                    className={`inline-flex min-h-11 w-full items-center justify-center rounded-lg px-4 py-3 text-sm font-semibold text-white transition-colors disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500 ${actionClassName}`}
                  >
                    {isPendingAction ? pendingActionLabel : "End Round and Update Rankings"}
                  </button>
                </div>
              ) : null}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function PanelTabs({ activePanel, onChange, hasBracket, showSummary }) {
  const tabs = [
    ...(showSummary ? [{ id: "summary", label: "Results" }] : []),
    { id: "matches", label: "Matches" },
    ...(hasBracket ? [{ id: "bracket", label: "Bracket" }] : []),
    { id: "rankings", label: "Rankings" },
  ];

  return (
    <div className="sticky top-[6.5rem] z-20 -mx-1 rounded-2xl border border-gray-200 bg-white/95 p-2 shadow-sm backdrop-blur supports-[backdrop-filter]:bg-white/80 md:static md:mx-0 md:bg-white md:p-2 md:backdrop-blur-0">
      <div className="grid grid-cols-2 gap-2 sm:grid-flow-col sm:auto-cols-fr">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onChange(tab.id)}
            className={`rounded-xl px-4 py-3 text-sm font-semibold transition-colors ${
              activePanel === tab.id
                ? "bg-indigo-600 text-white"
                : "bg-gray-50 text-gray-600 hover:bg-gray-100"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function CollapsibleRoundGroup({ title, description, rounds, defaultOpen = false, ...roundListProps }) {
  if (rounds.length === 0) return null;

  return (
    <details className="group rounded-2xl border border-gray-200 bg-white shadow-sm" open={defaultOpen}>
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4">
        <div>
          <p className="text-base font-semibold text-gray-900">{title}</p>
          <p className="mt-1 text-sm text-gray-500">{description}</p>
        </div>
        <span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs font-semibold text-gray-600">
          {rounds.length}
        </span>
      </summary>
      <div className="border-t border-gray-100 p-5 pt-4">
        <RoundList rounds={rounds} {...roundListProps} />
      </div>
    </details>
  );
}

export default function ScoringPage({
  roster,
  drawConfig,
  sessionName,
  canEdit,
  invalidEditLink = false,
  leagueScoresByRound,
  activeLeagueRound,
  endedLeagueRounds,
  knockoutScoresByRound,
  activeKnockoutRound,
  endedKnockoutRounds,
  onBack,
  onEditRound,
  onStartRound,
  onEndRound,
  onScoreChange,
  onScoreCommit,
  pendingRoundAction,
  onRenameSession,
}) {
  const leagueRounds = roster.rounds.map((round) => ({
    ...round,
    label: `Round ${round.round}`,
    court_numbers: roster.court_numbers,
  }));

  const endedLeagueScores = filterScoresByEndedRounds(roster.rounds, leagueScoresByRound, endedLeagueRounds);
  const individualStandings = buildIndividualStandings(roster.rounds, endedLeagueScores);
  const pairStandings = buildPairStandings(roster.rounds, endedLeagueScores);
  const knockoutRounds = buildKnockoutRounds(
    drawConfig,
    roster,
    leagueScoresByRound,
    knockoutScoresByRound,
    endedLeagueRounds,
    endedKnockoutRounds
  );
  const leagueComplete = areEndedRoundsComplete(roster.rounds, leagueScoresByRound, endedLeagueRounds);
  const totalRounds = leagueRounds.length + knockoutRounds.length;
  const completedRounds =
    endedLeagueRounds.filter(Boolean).length + endedKnockoutRounds.slice(0, knockoutRounds.length).filter(Boolean).length;

  const nextLeagueRound =
    activeLeagueRound + 1 < leagueRounds.length ? leagueRounds[activeLeagueRound + 1].label : null;
  const nextKnockoutRound =
    activeKnockoutRound + 1 < knockoutRounds.length ? knockoutRounds[activeKnockoutRound + 1].label : null;
  const nextRoundLabel = nextLeagueRound || nextKnockoutRound;
  const hasBracket = drawConfig?.draw_type === "league_knockout";
  const knockoutComplete =
    hasBracket &&
    leagueComplete &&
    (knockoutRounds.length === 0 || areEndedRoundsComplete(knockoutRounds, knockoutScoresByRound, endedKnockoutRounds));
  const sessionFinished = hasBracket ? knockoutComplete : leagueComplete;
  const finalRound = knockoutRounds.at(-1);
  const finalScore = finalRound ? knockoutScoresByRound[knockoutRounds.length - 1]?.[0] : null;
  const champion =
    finalRound && endedKnockoutRounds[knockoutRounds.length - 1]
      ? getMatchWinner(finalScore, finalRound.courts[0])
      : null;
  const [activePanel, setActivePanel] = useState(() => (sessionFinished ? "summary" : "matches"));
  const summaryActivationRef = useRef(sessionFinished ? `${sessionName}:${completedRounds}:${totalRounds}` : "");

  useEffect(() => {
    const activationKey = sessionFinished ? `${sessionName}:${completedRounds}:${totalRounds}` : "";

    if (sessionFinished && summaryActivationRef.current !== activationKey) {
      summaryActivationRef.current = activationKey;
      const timeoutId = window.setTimeout(() => {
        setActivePanel("summary");
      }, 0);
      return () => window.clearTimeout(timeoutId);
    }

    if (!sessionFinished) {
      summaryActivationRef.current = "";
    }

    if (!sessionFinished && activePanel === "summary") {
      const timeoutId = window.setTimeout(() => {
        setActivePanel("matches");
      }, 0);
      return () => window.clearTimeout(timeoutId);
    }
  }, [activePanel, completedRounds, sessionFinished, sessionName, totalRounds]);

  const annotateRounds = (rounds, activeRound, endedRounds) =>
    rounds.map((round, roundIndex) => ({
      ...round,
      sourceIndex: roundIndex,
      status: getRoundStatus(roundIndex, activeRound, endedRounds),
    }));

  const groupedLeagueRounds = annotateRounds(leagueRounds, activeLeagueRound, endedLeagueRounds);
  const liveLeagueRounds = groupedLeagueRounds.filter((round) => round.status === "live");
  const pendingLeagueRounds = groupedLeagueRounds.filter((round) => round.status === "pending");
  const endedLeagueOnlyRounds = groupedLeagueRounds.filter((round) => round.status === "completed");

  const groupedKnockoutRounds = annotateRounds(knockoutRounds, activeKnockoutRound, endedKnockoutRounds);
  const liveKnockoutRounds = groupedKnockoutRounds.filter((round) => round.status === "live");
  const pendingKnockoutRounds = groupedKnockoutRounds.filter((round) => round.status === "pending");
  const endedKnockoutOnlyRounds = groupedKnockoutRounds.filter((round) => round.status === "completed");

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-indigo-100 bg-gradient-to-r from-indigo-600 via-indigo-500 to-sky-500 p-4 text-white shadow-sm sm:p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-sm font-medium text-indigo-100">Scoring Console</p>
            <h2 className="mt-1 text-xl font-bold sm:text-2xl">
              {drawConfig?.draw_type === "league_knockout" ? "Run league play and playoffs" : "Run the session round by round"}
            </h2>
            <p className="mt-2 max-w-2xl text-sm text-indigo-50">
              Start each round when you are ready, enter scores court by court, and end the round to lock results and refresh the rankings. When league play is complete, playoff rounds are seeded automatically from the pair table.
            </p>
            <p className="mt-3 inline-flex rounded-full border border-white/20 bg-white/10 px-3 py-1 text-xs font-semibold tracking-wide text-white">
              {formatSessionPill(sessionName)}
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
            <div className="rounded-xl border border-white/20 bg-white/10 px-4 py-3 text-sm">
              <p className="text-indigo-100">Progress</p>
              <p className="font-semibold text-white">{completedRounds} / {totalRounds} rounds ended</p>
            </div>
            <div className="rounded-xl border border-white/20 bg-white/10 px-4 py-3 text-sm">
              <p className="text-indigo-100">Access</p>
              <p className="font-semibold text-white">{canEdit ? "Scorer" : "View Only"}</p>
            </div>
            {canEdit ? (
              <button
                onClick={onRenameSession}
                className="inline-flex min-h-11 items-center justify-center rounded-lg border border-white/25 bg-white/10 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-white/20"
              >
                Rename Session
              </button>
            ) : null}
            <button
              onClick={onBack}
              className="inline-flex min-h-11 items-center justify-center rounded-lg border border-white/25 bg-white/10 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-white/20"
            >
              Back to Roster
            </button>
          </div>
        </div>
      </div>

      {invalidEditLink ? (
        <div role="alert" className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {scoringCopy.invalidEditLink}
        </div>
      ) : null}

      {canEdit && activeLeagueRound + 1 < leagueRounds.length && liveLeagueRounds.length === 0 ? (
        <div className="md:hidden">
          <button
            type="button"
            onClick={() => onStartRound("league", activeLeagueRound + 1)}
            disabled={Boolean(pendingRoundAction)}
            className="inline-flex min-h-11 w-full items-center justify-center rounded-lg bg-indigo-600 px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500"
          >
            {scoringCopy.startNextRound}
          </button>
        </div>
      ) : null}

      <PanelTabs
        activePanel={activePanel}
        onChange={setActivePanel}
        hasBracket={hasBracket}
        showSummary={sessionFinished}
      />

      {activePanel === "summary" && sessionFinished ? (
        <TournamentSummary
          drawConfig={drawConfig}
          sessionName={sessionName}
          totalRounds={totalRounds}
          completedRounds={completedRounds}
          champion={champion}
          pairStandings={pairStandings}
          individualStandings={individualStandings}
        />
      ) : null}

      {activePanel === "matches" ? (
        <div className="space-y-6">
          <div className="space-y-5">
            <div className="rounded-2xl border border-indigo-200 bg-indigo-50 p-5 shadow-sm">
              <p className="text-sm font-semibold uppercase tracking-wide text-indigo-700">Current Focus</p>
              <h3 className="mt-1 text-lg font-semibold text-gray-900">
                {liveLeagueRounds.length > 0 || liveKnockoutRounds.length > 0
                  ? "Live rounds stay expanded so score entry is always in reach."
                  : nextRoundLabel
                    ? `Start ${nextRoundLabel} when you are ready.`
                    : "All rounds have been started."}
              </h3>
            </div>

              <RoundList
                title="Live League Rounds"
                rounds={liveLeagueRounds}
              scoresByRound={leagueScoresByRound}
              activeRound={activeLeagueRound}
              endedRounds={endedLeagueRounds}
              canEdit={canEdit}
              stage="league"
              onStartRound={onStartRound}
              onEndRound={onEndRound}
                onEditRound={onEditRound}
                onScoreChange={onScoreChange}
                onScoreCommit={onScoreCommit}
                pendingRoundAction={pendingRoundAction}
              />

            <CollapsibleRoundGroup
              title="Upcoming League Rounds"
              description="Start these later as courts free up."
              rounds={pendingLeagueRounds}
              scoresByRound={leagueScoresByRound}
              activeRound={activeLeagueRound}
              endedRounds={endedLeagueRounds}
              canEdit={canEdit}
              stage="league"
              onStartRound={onStartRound}
              onEndRound={onEndRound}
                onEditRound={onEditRound}
                onScoreChange={onScoreChange}
                onScoreCommit={onScoreCommit}
                pendingRoundAction={pendingRoundAction}
              />

            <CollapsibleRoundGroup
              title="Completed League Rounds"
              description="Review finished league results without crowding the live workflow."
              rounds={endedLeagueOnlyRounds}
              scoresByRound={leagueScoresByRound}
              activeRound={activeLeagueRound}
              endedRounds={endedLeagueRounds}
              canEdit={canEdit}
              stage="league"
              onStartRound={onStartRound}
              onEndRound={onEndRound}
                onEditRound={onEditRound}
                onScoreChange={onScoreChange}
                onScoreCommit={onScoreCommit}
                pendingRoundAction={pendingRoundAction}
              />

            {hasBracket ? (
              <div className="space-y-5">
                <div className="rounded-2xl border border-slate-200 bg-slate-900 p-5 text-white shadow-sm">
                  <p className="text-sm font-medium text-slate-200">Playoff Stage</p>
                  <h3 className="mt-1 text-lg font-semibold">
                    {leagueComplete
                      ? "League table locked. Knockout rounds are ready below."
                      : "End each league round to unlock the playoff stage."}
                  </h3>
                </div>

                {knockoutRounds.length > 0 ? (
                  <>
                    <RoundList
                      title="Live Knockout Rounds"
                      rounds={liveKnockoutRounds}
                      scoresByRound={knockoutScoresByRound}
                      activeRound={activeKnockoutRound}
                      endedRounds={endedKnockoutRounds}
                      canEdit={canEdit}
                      stage="knockout"
                      onStartRound={onStartRound}
                      onEndRound={onEndRound}
                      onEditRound={onEditRound}
                      onScoreChange={onScoreChange}
                      onScoreCommit={onScoreCommit}
                      pendingRoundAction={pendingRoundAction}
                    />

                    <CollapsibleRoundGroup
                      title="Upcoming Knockout Rounds"
                      description="Future playoff rounds stay tucked away until they matter."
                      rounds={pendingKnockoutRounds}
                      scoresByRound={knockoutScoresByRound}
                      activeRound={activeKnockoutRound}
                      endedRounds={endedKnockoutRounds}
                      canEdit={canEdit}
                      stage="knockout"
                      onStartRound={onStartRound}
                      onEndRound={onEndRound}
                      onEditRound={onEditRound}
                      onScoreChange={onScoreChange}
                      onScoreCommit={onScoreCommit}
                      pendingRoundAction={pendingRoundAction}
                    />

                    <CollapsibleRoundGroup
                      title="Completed Knockout Rounds"
                      description="Revisit playoff results without adding scroll to live scoring."
                      rounds={endedKnockoutOnlyRounds}
                      scoresByRound={knockoutScoresByRound}
                      activeRound={activeKnockoutRound}
                      endedRounds={endedKnockoutRounds}
                      canEdit={canEdit}
                      stage="knockout"
                      onStartRound={onStartRound}
                      onEndRound={onEndRound}
                      onEditRound={onEditRound}
                      onScoreChange={onScoreChange}
                      onScoreCommit={onScoreCommit}
                      pendingRoundAction={pendingRoundAction}
                    />
                  </>
                ) : (
                  <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
                    <p className="text-sm text-gray-600">
                      {leagueComplete
                        ? "Not enough ranked pairs are available to seed the configured playoff bracket yet."
                        : "The knockout bracket will appear once league play is fully ended."}
                    </p>
                  </div>
                )}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {activePanel === "bracket" && hasBracket ? (
        <div className="space-y-5">
          {knockoutRounds.length > 0 ? (
            <LiveBracket
              rounds={knockoutRounds}
              scoresByRound={knockoutScoresByRound}
              endedRounds={endedKnockoutRounds}
            />
          ) : (
            <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
              <p className="text-sm font-semibold uppercase tracking-wide text-gray-500">Live Bracket</p>
              <p className="mt-3 text-sm text-gray-600">
                {leagueComplete
                  ? "The bracket will appear once enough qualifying pairs are available."
                  : "Finish and end the league rounds first. The bracket will appear automatically."}
              </p>
            </div>
          )}
        </div>
      ) : null}

      {activePanel === "rankings" ? (
        <div className="space-y-6">
          <CollapsibleSection
            title="League Pair Rankings"
            description="Based on completed league rounds only. Playoff matches do not change this table."
            count={pairStandings.length}
            defaultOpen
          >
            <RankingTable
              title="League Pair Rankings"
              emptyText="League pair rankings will appear only after a pair has completed a match in an ended round."
              label="Pair"
              standings={pairStandings}
            />
          </CollapsibleSection>

          <CollapsibleSection
            title="League Individual Rankings"
            description="Based on completed league rounds only. Playoff matches do not change this table."
            count={individualStandings.length}
          >
            <RankingTable
              title="League Individual Rankings"
              emptyText="League individual rankings will appear once an ended round is available."
              label="Player"
              standings={individualStandings}
            />
          </CollapsibleSection>
        </div>
      ) : null}
    </div>
  );
}
