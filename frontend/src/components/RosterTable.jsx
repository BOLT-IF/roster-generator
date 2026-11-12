function CollapsibleSummary({ title, hint }) {
  return (
    <summary className="flex min-h-[72px] cursor-pointer list-none items-center justify-between gap-3 px-5 py-4">
      <div>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-700">{title}</h3>
        <p className="mt-1 text-xs text-gray-400">{hint}</p>
      </div>
      <span className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-gray-200 bg-gray-50 text-gray-500 transition-transform group-open:rotate-180">
        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </span>
    </summary>
  );
}

export default function RosterTable({
  data,
  fixedPairs,
  editable = false,
  editMode = null,
  selectedTarget = null,
  editTitle = "",
  editSummary = "",
  editHint = null,
  cancelSelectionLabel = "Cancel",
  onCancelSelection,
  onTapPlayer,
  onTapTeam,
  onTapRound,
  editLoading = false,
  expectedRepeatCount = 0,
}) {
  if (!data) return null;

  const { rounds, court_numbers, rest_counts, fixed_pair_counts, violations, warnings } = data;
  const fixedPairSet = new Set(fixedPairs.map(([a, b]) => [a, b].sort().join("|")));

  function isFixedPairTeam(team) {
    return team.length === 2 && fixedPairSet.has([...team].sort().join("|"));
  }

  function isSelectedPlayer(slot) {
    return Boolean(
      selectedTarget &&
      selectedTarget.mode === "player" &&
      selectedTarget.roundIndex === slot.roundIndex &&
      selectedTarget.courtIndex === slot.courtIndex &&
      selectedTarget.teamKey === slot.teamKey &&
      selectedTarget.playerIndex === slot.playerIndex
    );
  }

  function isSelectedTeam(target) {
    return Boolean(
      selectedTarget &&
      selectedTarget.mode === "team" &&
      selectedTarget.roundIndex === target.roundIndex &&
      selectedTarget.courtIndex === target.courtIndex &&
      selectedTarget.teamKey === target.teamKey
    );
  }

  function isSelectedRound(roundIndex) {
    return Boolean(selectedTarget && selectedTarget.mode === "round" && selectedTarget.roundIndex === roundIndex);
  }

  function renderPlayerButton(player, slot, highlighted) {
    const selected = isSelectedPlayer(slot);
    const disabled = editLoading || !editable || (editMode && editMode !== "player");

    return (
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          onTapPlayer?.(slot);
        }}
        disabled={disabled}
        className={`w-full rounded-md border px-2 py-1.5 text-left transition-all ${
          selected
            ? "border-indigo-700 bg-indigo-600 text-white shadow-md ring-2 ring-indigo-200"
            : highlighted
              ? "border-transparent bg-indigo-50 text-indigo-700 hover:border-indigo-200 hover:bg-indigo-100"
              : "border-transparent bg-white/80 text-gray-800 hover:border-indigo-200 hover:bg-indigo-50"
        } ${disabled ? "cursor-default" : "cursor-pointer"} ${editLoading ? "opacity-70" : ""} pointer-events-auto relative z-20`}
      >
        <span className="block text-sm font-medium">{player}</span>
        {selected ? <span className="mt-1 block text-[10px] font-semibold uppercase tracking-wide">Selected</span> : null}
      </button>
    );
  }

  function renderTeamCard(team, target, highlighted, content) {
    const selected = isSelectedTeam(target);
    const disabled = editLoading || !editable || (editMode && editMode !== "team");

    return (
      <div className={`relative w-full rounded-lg ${editLoading ? "opacity-70" : ""}`}>
        <button
          type="button"
          aria-label={`Swap team ${team.join(" & ")}`}
          onClick={() => onTapTeam?.(target)}
          disabled={disabled}
          className={`absolute inset-0 rounded-lg border transition-all focus:outline-none focus:ring-2 focus:ring-sky-200 ${
            selected
              ? "border-sky-700 bg-sky-600 text-white shadow-md ring-2 ring-sky-200"
              : highlighted
                ? "border-indigo-200 bg-indigo-50 text-indigo-700 hover:bg-indigo-100"
                : "border-gray-200 bg-gray-50 text-gray-800 hover:border-sky-200 hover:bg-sky-50"
          } ${disabled ? "cursor-default" : "cursor-pointer"}`}
        />
        <div className="relative z-10 pointer-events-none px-3 py-2">
          <div className="mb-2 flex items-center justify-end gap-3">
            {selected ? <span className="rounded-full bg-white/20 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">Selected</span> : null}
          </div>
          {content}
        </div>
      </div>
    );
  }

  function renderTeamSectionLabel(label, highlighted, selected) {
    return (
      <p className={`mb-2 text-xs font-semibold uppercase tracking-wide ${selected ? "text-white/80" : highlighted ? "text-indigo-600" : "text-gray-500"}`}>
        {label}
      </p>
    );
  }

  function renderRoundButton(roundIndex, label, className = "") {
    const selected = isSelectedRound(roundIndex);
    const disabled = editLoading || !editable || (editMode && editMode !== "round");

    return (
      <button
        type="button"
        onClick={() => onTapRound?.(roundIndex)}
        disabled={disabled}
        className={`${className} rounded-md border px-2 py-1 text-left transition-all ${
          selected
            ? "border-sky-700 bg-sky-600 text-white shadow-md ring-2 ring-sky-200"
            : "border-transparent hover:border-sky-200 hover:bg-sky-50"
        } ${disabled ? "cursor-default" : "cursor-pointer"} ${editLoading ? "opacity-70" : ""}`}
      >
        <span className="block">{label}</span>
        {selected ? <span className="mt-1 block text-[10px] font-semibold uppercase tracking-wide">Selected</span> : null}
      </button>
    );
  }

  const maxResting = Math.max(...rounds.map((round) => round.resting.length), 0);

  return (
    <div className="space-y-6">
      {warnings.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
          <p className="mb-1 text-sm font-medium text-amber-800">Warnings</p>
          {warnings.map((warning, index) => (
            <p key={index} className="text-sm text-amber-700">{warning}</p>
          ))}
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        <div className="flex flex-col gap-1 border-b border-gray-100 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
          <h2 className="text-lg font-semibold text-gray-800">Roster</h2>
          <span className="text-sm text-gray-500">
            {rounds.length} rounds &middot; {rounds[0]?.courts.length} courts
          </span>
        </div>

        {editable && !selectedTarget ? (
          <div className="sticky top-0 z-10 border-b border-sky-100 bg-white/95 px-4 py-3 backdrop-blur sm:px-5">
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-wide text-sky-700">{editTitle}</p>
              <p className="mt-1 text-sm font-medium text-slate-900">{editLoading ? "Applying swap..." : editSummary}</p>
              {editHint ? <p className="mt-1 text-xs text-slate-600">{editHint}</p> : null}
            </div>
          </div>
        ) : null}

        <div className="block space-y-4 p-4 lg:hidden">
          {rounds.map((round, roundIndex) => (
            <details
              key={round.round}
              className={`relative rounded-xl border ${isSelectedRound(roundIndex) ? "border-sky-300 bg-sky-50" : "border-gray-200 bg-gray-50"}`}
              open={round.round === 1}
            >
              <summary
                className={`flex cursor-pointer list-none flex-col gap-2 px-4 py-4 pr-28 transition-colors ${
                  selectedTarget?.mode === "round" && !isSelectedRound(roundIndex)
                    ? "hover:bg-sky-50"
                    : ""
                }`}
                onClick={(event) => {
                  if (selectedTarget?.mode === "round" && !isSelectedRound(roundIndex)) {
                    event.preventDefault();
                    onTapRound?.(roundIndex);
                  }
                }}
              >
                <span className="text-base font-semibold text-gray-900">Round {round.round}</span>
                <span className="text-xs font-medium text-gray-500">
                  {round.courts.length} courts{round.resting.length > 0 ? ` • ${round.resting.length} resting` : ""}
                </span>
              </summary>
              {editable ? (
                <button
                  type="button"
                  onClick={() => onTapRound?.(roundIndex)}
                  disabled={editLoading || (editMode && editMode !== "round")}
                  className={`absolute right-4 top-4 inline-flex min-h-10 shrink-0 items-center justify-center rounded-lg border px-3 py-2 text-xs font-semibold transition-all ${
                    isSelectedRound(roundIndex)
                      ? "border-sky-700 bg-sky-600 text-white shadow-md ring-2 ring-sky-200"
                      : "border-sky-200 bg-white text-sky-900 hover:bg-sky-50"
                  } ${(editLoading || (editMode && editMode !== "round")) ? "cursor-default opacity-70" : "cursor-pointer"}`}
                >
                  Swap
                </button>
              ) : null}

              <div className="border-t border-gray-200 px-4 py-4">
                <div className="space-y-3">
                  {round.courts.map((court, courtIndex) => {
                    const pairA = isFixedPairTeam(court.team_a);
                    const pairB = isFixedPairTeam(court.team_b);
                    return (
                      <div key={`${round.round}-${courtIndex}`} className="rounded-lg border border-gray-200 bg-white p-3 shadow-sm">
                        <div className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-gray-500 sm:flex-row sm:items-center sm:justify-between">
                          <span>Court {court_numbers?.[courtIndex] ?? courtIndex + 1}</span>
                          {pairA || pairB ? <span className="text-indigo-600">Fixed Pair Match</span> : null}
                        </div>
                        <div className="mt-3 space-y-2">
                          <div>
                            {renderTeamCard(
                              court.team_a,
                              { roundIndex, courtIndex, teamKey: "team_a" },
                              pairA,
                              <>
                                {renderTeamSectionLabel("Team A", pairA, isSelectedTeam({ roundIndex, courtIndex, teamKey: "team_a" }))}
                                <div className="space-y-2">
                                  {court.team_a.map((player, playerIndex) => (
                                    <div key={`mobile-a-${round.round}-${courtIndex}-${playerIndex}`}>
                                      {renderPlayerButton(player, { roundIndex, courtIndex, teamKey: "team_a", playerIndex }, pairA)}
                                    </div>
                                  ))}
                                </div>
                              </>
                            )}
                          </div>
                          <div>
                            {renderTeamCard(
                              court.team_b,
                              { roundIndex, courtIndex, teamKey: "team_b" },
                              pairB,
                              <>
                                {renderTeamSectionLabel("Team B", pairB, isSelectedTeam({ roundIndex, courtIndex, teamKey: "team_b" }))}
                                <div className="space-y-2">
                                  {court.team_b.map((player, playerIndex) => (
                                    <div key={`mobile-b-${round.round}-${courtIndex}-${playerIndex}`}>
                                      {renderPlayerButton(player, { roundIndex, courtIndex, teamKey: "team_b", playerIndex }, pairB)}
                                    </div>
                                  ))}
                                </div>
                              </>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {round.resting.length > 0 && (
                  <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-amber-700">Resting</p>
                    <p className="mt-1 text-sm text-amber-900">{round.resting.join(", ")}</p>
                  </div>
                )}
              </div>
            </details>
          ))}
        </div>

        <div className="hidden overflow-x-auto lg:block">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-xs uppercase tracking-wide text-gray-600">
                <th className="px-3 py-2.5 text-left font-semibold">Round</th>
                <th className="px-3 py-2.5 text-left font-semibold">Court</th>
                <th className="px-3 py-2.5 text-left font-semibold">Team A</th>
                <th className="px-3 py-2.5 text-left font-semibold">Team B</th>
                {Array.from({ length: maxResting }, (_, index) => (
                  <th key={index} className="px-3 py-2.5 text-left font-semibold">Rest {index + 1}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rounds.map((round, roundIndex) =>
                round.courts.map((court, courtIndex) => {
                  const isFirstCourt = courtIndex === 0;
                  const pairA = isFixedPairTeam(court.team_a);
                  const pairB = isFixedPairTeam(court.team_b);
                  return (
                    <tr
                      key={`${round.round}-${courtIndex}`}
                      className={`border-t border-gray-100 hover:bg-gray-50 ${isFirstCourt ? "border-t-gray-300" : ""} ${isSelectedRound(roundIndex) ? "bg-sky-50" : ""}`}
                    >
                      <td className="px-3 py-2 font-medium text-gray-700">
                        {isFirstCourt ? renderRoundButton(roundIndex, `${round.round}`) : ""}
                      </td>
                      <td className="px-3 py-2 text-gray-600">{court_numbers?.[courtIndex] ?? courtIndex + 1}</td>
                      <td className="px-3 py-2">
                        {renderTeamCard(
                          court.team_a,
                          { roundIndex, courtIndex, teamKey: "team_a" },
                          pairA,
                          <>
                            {renderTeamSectionLabel("Team A", pairA, isSelectedTeam({ roundIndex, courtIndex, teamKey: "team_a" }))}
                            <div className="space-y-2">
                              {court.team_a.map((player, playerIndex) => (
                                <div key={`desktop-a-${round.round}-${courtIndex}-${playerIndex}`}>
                                  {renderPlayerButton(player, { roundIndex, courtIndex, teamKey: "team_a", playerIndex }, pairA)}
                                </div>
                              ))}
                            </div>
                          </>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        {renderTeamCard(
                          court.team_b,
                          { roundIndex, courtIndex, teamKey: "team_b" },
                          pairB,
                          <>
                            {renderTeamSectionLabel("Team B", pairB, isSelectedTeam({ roundIndex, courtIndex, teamKey: "team_b" }))}
                            <div className="space-y-2">
                              {court.team_b.map((player, playerIndex) => (
                                <div key={`desktop-b-${round.round}-${courtIndex}-${playerIndex}`}>
                                  {renderPlayerButton(player, { roundIndex, courtIndex, teamKey: "team_b", playerIndex }, pairB)}
                                </div>
                              ))}
                            </div>
                          </>
                        )}
                      </td>
                      {Array.from({ length: maxResting }, (_, restIndex) => (
                        <td key={restIndex} className="px-3 py-2 text-gray-400">
                          {isFirstCourt ? round.resting[restIndex] || "" : ""}
                        </td>
                      ))}
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {editable && selectedTarget ? (
        <div className="pointer-events-none fixed inset-x-4 bottom-4 z-40 sm:left-1/2 sm:right-auto sm:w-[min(42rem,calc(100vw-2rem))] sm:-translate-x-1/2">
          <div className="pointer-events-auto rounded-2xl border border-sky-300 bg-sky-950/96 p-4 text-white shadow-2xl ring-1 ring-sky-200/20 backdrop-blur">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-sky-200">{editTitle}</p>
                <p className="mt-1 text-sm font-semibold text-white">{editLoading ? "Applying swap..." : editSummary}</p>
                {editHint ? <p className="mt-1 text-sm text-sky-100/90">{editHint}</p> : null}
              </div>
              <button
                type="button"
                onClick={onCancelSelection}
                className="inline-flex min-h-11 shrink-0 items-center justify-center rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-sky-950 transition-colors hover:bg-sky-50"
              >
                {cancelSelectionLabel}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 md:items-start">
        <details className="group self-start rounded-xl border border-gray-200 bg-white shadow-sm">
          <CollapsibleSummary title="Rest Distribution" hint="Tap to expand the player-by-player balance." />
          <div className="border-t border-gray-100 px-5 py-4">
            <div className="space-y-1.5">
              {Object.entries(rest_counts)
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([player, rested]) => {
                  const played = rounds.length - rested;
                  return (
                    <div key={player} className="flex flex-col gap-1 text-sm sm:flex-row sm:items-start sm:justify-between">
                      <span className="break-words text-gray-700">{player}</span>
                      <div className="flex shrink-0 gap-3 text-xs">
                        <span className="font-medium text-green-600">Played {played}</span>
                        <span className="text-gray-400">Rested {rested}</span>
                      </div>
                    </div>
                  );
                })}
            </div>
          </div>
        </details>

        <div className="space-y-4">
          {Object.keys(fixed_pair_counts).length > 0 && (
            <details className="group self-start rounded-xl border border-gray-200 bg-white shadow-sm">
              <CollapsibleSummary title="Fixed Pair Games" hint="Tap to expand the partnership totals." />
              <div className="border-t border-gray-100 px-5 py-4">
                <div className="space-y-1.5">
                  {Object.entries(fixed_pair_counts)
                    .sort(([a], [b]) => a.localeCompare(b))
                    .map(([pair, count]) => (
                      <div key={pair} className="flex flex-col gap-1 text-sm sm:flex-row sm:items-start sm:justify-between">
                        <span className="break-words text-gray-700">{pair}</span>
                        <span className="shrink-0 font-medium text-indigo-600">{count} games</span>
                      </div>
                    ))}
                </div>
              </div>
            </details>
          )}

          {violations.length > 0 && (
            <div className="rounded-xl border border-red-200 bg-red-50 p-5">
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-red-700">Constraint Violations</h3>
              {violations.map((violation, index) => (
                <p key={index} className="text-sm text-red-600">{violation}</p>
              ))}
            </div>
          )}

          {violations.length === 0 && (
            <div className="rounded-xl border border-green-200 bg-green-50 p-5">
              <p className="text-sm font-medium text-green-700">All constraints satisfied.</p>
            </div>
          )}

          {expectedRepeatCount > 0 && (
            <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-5">
              <p className="text-sm text-indigo-800">
                Play Twice: each pair meets every other pair twice, so {expectedRepeatCount} repeat matchup{expectedRepeatCount === 1 ? " is" : "s are"} expected and not counted as violations.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
