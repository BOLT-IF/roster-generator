import { useMemo, useState } from "react";
import { playerInputCopy } from "../content/uiCopy";

function SectionIcon({ kind, className = "h-4 w-4" }) {
  const props = {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "1.8",
    strokeLinecap: "round",
    strokeLinejoin: "round",
    className,
    "aria-hidden": true,
  };

  switch (kind) {
    case "session":
      return (
        <svg {...props}>
          <path d="M7.5 11a3.25 3.25 0 1 0 0-6.5 3.25 3.25 0 0 0 0 6.5Z" />
          <path d="M16.5 12.2a2.7 2.7 0 1 0 0-5.4 2.7 2.7 0 0 0 0 5.4Z" />
          <path d="M3.8 19a4.8 4.8 0 0 1 7.4-3.9" />
          <path d="M13 19a4.2 4.2 0 0 1 7.2-3" />
        </svg>
      );
    case "directory":
      return (
        <svg {...props}>
          <rect x="4.5" y="4.5" width="11" height="15" rx="2.5" />
          <path d="M8 8h4.5M8 11.5h4.5M8 15h3" />
          <path d="m18 18 2.5 2.5" />
          <circle cx="17.5" cy="15.5" r="2.5" />
        </svg>
      );
    case "pairs":
      return (
        <svg {...props}>
          <path d="M8.5 8.5a2.5 2.5 0 1 0-3.5 3.5l2 2a2.5 2.5 0 0 0 3.5 0l1.5-1.5" />
          <path d="M15.5 15.5a2.5 2.5 0 1 0 3.5-3.5l-2-2a2.5 2.5 0 0 0-3.5 0L12 11.5" />
        </svg>
      );
    default:
      return null;
  }
}

function EmptyState({ icon, title, description }) {
  return (
    <div className="rounded-2xl border border-dashed border-gray-300 bg-gray-50 p-6 text-center">
      <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-white text-indigo-600 shadow-sm">
        <SectionIcon kind={icon} className="h-5 w-5" />
      </div>
      <p className="mt-4 text-sm font-semibold text-gray-900">{title}</p>
      <p className="mt-2 text-sm text-gray-500">{description}</p>
    </div>
  );
}

function PlayerTile({ player, actionLabel, onAction, selected = false, muted = false }) {
  return (
    <div
      className={`rounded-2xl border p-4 shadow-sm transition-colors ${
        selected
          ? "border-indigo-200 bg-indigo-50"
          : muted
            ? "border-gray-200 bg-gray-50"
            : "border-gray-200 bg-white"
      }`}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-gray-900">{player.fullName}</p>
        </div>
        <button
          type="button"
          onClick={() => onAction(player.playerId)}
          className={`inline-flex min-h-10 items-center justify-center rounded-lg px-3 py-2 text-sm font-semibold transition-colors ${
            selected
              ? "border border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100"
              : "bg-indigo-600 text-white hover:bg-indigo-700"
          }`}
        >
          {actionLabel}
        </button>
      </div>
    </div>
  );
}

export default function PlayerInput({
  availablePlayers,
  selectedPlayerIds,
  setSelectedPlayerIds,
  fixedPairIds,
  setFixedPairIds,
  onOpenPlayerManagement,
}) {
  const [searchQuery, setSearchQuery] = useState("");
  const [pairSelection, setPairSelection] = useState({ active: false, first: "" });
  const [pairNotice, setPairNotice] = useState("");

  const playersById = useMemo(
    () => new Map(availablePlayers.map((player) => [player.playerId, player])),
    [availablePlayers]
  );

  const selectedPlayers = selectedPlayerIds
    .map((playerId) => playersById.get(playerId))
    .filter(Boolean);

  const selectedIdSet = new Set(selectedPlayerIds);
  const availablePool = availablePlayers.filter((player) => !selectedIdSet.has(player.playerId));

  const filteredPlayers = availablePool.filter((player) => {
    const haystack = `${player.fullName} ${player.shortName} ${player.playerId}`.toLowerCase();
    return haystack.includes(searchQuery.trim().toLowerCase());
  });

  function addPlayer(playerId) {
    if (selectedIdSet.has(playerId)) return;
    setSelectedPlayerIds([...selectedPlayerIds, playerId]);
  }

  function removePlayer(playerId) {
    setSelectedPlayerIds(selectedPlayerIds.filter((value) => value !== playerId));
    setFixedPairIds(
      fixedPairIds.filter(([firstId, secondId]) => firstId !== playerId && secondId !== playerId)
    );
    if (pairSelection.first === playerId) {
      setPairSelection({ active: false, first: "" });
    }
  }

  function togglePair(playerId) {
    if (!pairSelection.active) {
      setPairNotice("");
      setPairSelection({ active: true, first: playerId });
      return;
    }

    if (pairSelection.first === playerId) {
      setPairSelection({ active: false, first: "" });
      return;
    }

    const nextPair = [pairSelection.first, playerId].sort();
    const alreadyExists = fixedPairIds.some(
      ([firstId, secondId]) => firstId === nextPair[0] && secondId === nextPair[1]
    );

    if (alreadyExists) {
      // Selecting an existing pair again must not silently dissolve it; removal is
      // an explicit action on the pair chip.
      const names = nextPair.map((id) => playersById.get(id)?.shortName || id).join(" & ");
      setPairNotice(`${names} are already paired. Use the \u00d7 on the pair under Fixed pairs to remove it.`);
    } else {
      setPairNotice("");
      const nextFixedPairs = fixedPairIds.filter(
        ([firstId, secondId]) =>
          firstId !== nextPair[0] &&
          secondId !== nextPair[0] &&
          firstId !== nextPair[1] &&
          secondId !== nextPair[1]
      );
      setFixedPairIds([...nextFixedPairs, nextPair]);
    }

    setPairSelection({ active: false, first: "" });
  }

  function removePair(index) {
    setPairNotice("");
    setFixedPairIds(fixedPairIds.filter((_, currentIndex) => currentIndex !== index));
  }

  function getPairPartner(playerId) {
    for (const [firstId, secondId] of fixedPairIds) {
      if (firstId === playerId) return secondId;
      if (secondId === playerId) return firstId;
    }
    return "";
  }

  const pairColors = [
    "bg-blue-100 border-blue-300",
    "bg-green-100 border-green-300",
    "bg-amber-100 border-amber-300",
    "bg-rose-100 border-rose-300",
    "bg-cyan-100 border-cyan-300",
    "bg-fuchsia-100 border-fuchsia-300",
  ];

  function getPairColor(playerId) {
    const index = fixedPairIds.findIndex(([firstId, secondId]) => firstId === playerId || secondId === playerId);
    if (index === -1) return "";
    return pairColors[index % pairColors.length];
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <section className="order-2 rounded-2xl border border-gray-200 bg-white p-5 shadow-sm xl:order-1">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
                  <SectionIcon kind="session" className="h-5 w-5" />
                </span>
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">{playerInputCopy.sessionPlayers.title}</h2>
                </div>
              </div>
              <p className="mt-1 text-sm text-gray-600">
                {playerInputCopy.sessionPlayers.description}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-gray-100 px-2.5 py-1 text-sm font-medium text-gray-600">
                {selectedPlayers.length} {playerInputCopy.sessionPlayers.countSuffix}
              </span>
              <button
                type="button"
                onClick={onOpenPlayerManagement}
                className="inline-flex min-h-10 items-center justify-center rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-semibold text-gray-700 transition-colors hover:bg-gray-50"
              >
                {playerInputCopy.sessionPlayers.manage}
              </button>
            </div>
          </div>

          {pairNotice && !pairSelection.active ? (
            <div role="status" className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              {pairNotice}
            </div>
          ) : null}

          {pairSelection.active ? (
            <div className="mt-4 rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm text-indigo-700">
              {playerInputCopy.sessionPlayers.pairPromptPrefix}{" "}
              <strong>{playersById.get(pairSelection.first)?.shortName || playersById.get(pairSelection.first)?.fullName}</strong>
              {" "}{playerInputCopy.sessionPlayers.pairPromptSuffix}
            </div>
          ) : null}

          <div className="mt-4 space-y-3">
            {selectedPlayers.length > 0 ? (
              selectedPlayers.map((player) => {
                const partnerId = getPairPartner(player.playerId);
                const partner = partnerId ? playersById.get(partnerId) : null;
                const isFirstSelected = pairSelection.active && pairSelection.first === player.playerId;
                const pairColor = getPairColor(player.playerId);

                return (
                  <div
                    key={player.playerId}
                    className={`rounded-2xl border p-4 shadow-sm transition-colors cursor-pointer ${
                      isFirstSelected
                        ? "border-indigo-300 bg-indigo-100 ring-2 ring-indigo-200"
                        : pairColor || "border-gray-200 bg-white hover:bg-gray-50"
                    }`}
                    onClick={() => togglePair(player.playerId)}
                  >
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-gray-900">{player.fullName}</p>
                        <div className="mt-2 flex flex-wrap gap-2 text-xs text-gray-500">
                          {partner ? (
                            <span className="rounded-full bg-white/80 px-2 py-1 font-medium text-indigo-700">
                              {playerInputCopy.sessionPlayers.pairedWith} {partner.shortName}
                            </span>
                          ) : null}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          removePlayer(player.playerId);
                        }}
                        className="inline-flex min-h-10 items-center justify-center rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm font-semibold text-rose-700 transition-colors hover:bg-rose-100"
                      >
                        {playerInputCopy.sessionPlayers.remove}
                      </button>
                    </div>
                  </div>
                );
              })
            ) : (
              <EmptyState
                icon="session"
                title={playerInputCopy.sessionPlayers.emptyTitle}
                description={playerInputCopy.sessionPlayers.emptyDescription}
              />
            )}
          </div>
        </section>

        <section className="order-1 rounded-2xl border border-gray-200 bg-white p-5 shadow-sm xl:order-2">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-sky-50 text-sky-600">
                  <SectionIcon kind="directory" className="h-5 w-5" />
                </span>
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">{playerInputCopy.directory.title}</h2>
                </div>
              </div>
              <p className="mt-1 text-sm text-gray-600">
                {playerInputCopy.directory.description}
              </p>
            </div>
            <span className="rounded-full bg-indigo-50 px-2.5 py-1 text-sm font-medium text-indigo-700">
              {availablePlayers.length} {playerInputCopy.directory.countSuffix}
            </span>
          </div>

          <div className="mt-4">
            <input
              type="search"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder={playerInputCopy.directory.searchPlaceholder}
              className="block w-full rounded-xl border border-gray-300 px-3 py-3 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <div className="mt-4 max-h-[30rem] space-y-3 overflow-y-auto pr-1">
            {filteredPlayers.length > 0 ? (
              filteredPlayers.map((player) => (
                <PlayerTile
                  key={player.playerId}
                  player={player}
                  actionLabel={playerInputCopy.directory.add}
                  onAction={addPlayer}
                />
              ))
            ) : (
              <EmptyState
                icon="directory"
                title={availablePlayers.length > 0 ? playerInputCopy.directory.noMatchTitle : playerInputCopy.directory.emptyTitle}
                description={
                  availablePlayers.length > 0
                    ? playerInputCopy.directory.noMatchDescription
                    : playerInputCopy.directory.emptyDescription
                }
              />
            )}
          </div>
        </section>
      </div>

      {fixedPairIds.length > 0 ? (
        <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600">
                  <SectionIcon kind="pairs" className="h-5 w-5" />
                </span>
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">{playerInputCopy.fixedPairs.title}</h2>
                </div>
              </div>
              <p className="mt-1 text-sm text-gray-600">
                {playerInputCopy.fixedPairs.description}
              </p>
            </div>
            <span className="rounded-full bg-gray-100 px-2.5 py-1 text-sm font-medium text-gray-600">
              {fixedPairIds.length} {playerInputCopy.fixedPairs.countSuffix}
            </span>
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            {fixedPairIds.map(([firstId, secondId], index) => {
              const firstPlayer = playersById.get(firstId);
              const secondPlayer = playersById.get(secondId);
              if (!firstPlayer || !secondPlayer) return null;

              return (
                <span
                  key={`${firstId}-${secondId}`}
                  className="inline-flex items-center gap-2 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm font-medium text-indigo-700"
                >
                  {firstPlayer.shortName} & {secondPlayer.shortName}
                  <button
                    type="button"
                    onClick={() => removePair(index)}
                    className="text-indigo-500 transition-colors hover:text-rose-600"
                    aria-label={`Remove pair ${firstPlayer.shortName} and ${secondPlayer.shortName}`}
                  >
                    &times;
                  </button>
                </span>
              );
            })}
          </div>
        </section>
      ) : null}
    </div>
  );
}
