import { useEffect, useState } from "react";
import { getLeagueKnockoutCourts, getLeagueKnockoutIssue, withCourtCount } from "../hooks/appStateUtils";

const DRAW_FORMATS = [
  {
    id: "round_robin",
    title: "Round Robin",
    description: "Keep cycling league rounds and rank everyone by the session table.",
  },
  {
    id: "league_knockout",
    title: "League + Knockout",
    description: "Play league rounds first, then promote the top-ranked pairs into playoffs.",
  },
];

function NumericField({ fieldKey, label, min, max, hint, value, onAdjust, onDraftChange, onCommit }) {
  return (
    <div>
      <label className="flex items-center gap-1.5 text-xs font-medium text-gray-600 mb-1">
        {label}
        <span className="relative group">
          <svg className="w-3.5 h-3.5 text-gray-400 hover:text-indigo-500 transition-colors cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 px-2.5 py-1.5 text-xs text-white bg-gray-800 rounded-md shadow-lg whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-20">
            {hint}
          </span>
        </span>
      </label>
      <div className="flex items-stretch gap-2">
        <button
          type="button"
          onClick={() => onAdjust(fieldKey, min, max, -1)}
          className="inline-flex min-h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-gray-300 bg-white text-lg font-semibold text-gray-700 transition-colors hover:bg-gray-50"
          aria-label={`Decrease ${label}`}
        >
          -
        </button>
        <input
          type="number"
          min={min}
          max={max}
          value={value}
          onChange={(e) => onDraftChange(fieldKey, e.target.value)}
          onBlur={() => onCommit(fieldKey, min, max)}
          className="w-full rounded-lg border border-gray-300 px-3 py-3 text-center text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
        <button
          type="button"
          onClick={() => onAdjust(fieldKey, min, max, 1)}
          className="inline-flex min-h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-gray-300 bg-white text-lg font-semibold text-gray-700 transition-colors hover:bg-gray-50"
          aria-label={`Increase ${label}`}
        >
          +
        </button>
      </div>
    </div>
  );
}

export default function ConfigPanel({ config, setConfig, players, fixedPairs }) {
  const [limitPlayer, setLimitPlayer] = useState("");
  const [limitValue, setLimitValue] = useState(2);
  const [draftValues, setDraftValues] = useState(() => ({
    num_courts: String(config.num_courts),
    rounds: String(config.rounds),
    pair_games: String(config.pair_games),
    pair_start_round: String(config.pair_start_round),
    max_consecutive_rest: String(config.max_consecutive_rest),
  }));
  const [seedDraft, setSeedDraft] = useState(config.seed ?? "");
  const [limitValueDraft, setLimitValueDraft] = useState(String(limitValue));

  useEffect(() => {
    setDraftValues({
      num_courts: String(config.num_courts),
      rounds: String(config.rounds),
      pair_games: String(config.pair_games),
      pair_start_round: String(config.pair_start_round),
      max_consecutive_rest: String(config.max_consecutive_rest),
    });
    setSeedDraft(config.seed ?? "");
  }, [config]);

  useEffect(() => {
    setLimitValueDraft(String(limitValue));
  }, [limitValue]);

  function update(key, value) {
    setConfig((prev) => {
      const next = { ...prev, [key]: value };
      if (key === "num_courts") {
        const n = value;
        const old = prev.court_numbers || [];
        if (n > old.length) {
          const extended = [...old];
          for (let i = old.length; i < n; i++) extended.push(String(i + 1));
          next.court_numbers = extended;
        } else {
          next.court_numbers = old.slice(0, n);
        }
      }
      return next;
    });
  }

  function getLeagueTeamCount() {
    return fixedPairs.length;
  }

  function getDerivedPairGames(meetings = config.league_meetings) {
    const teamCount = getLeagueTeamCount();
    if (teamCount < 2) return 0;
    return (teamCount - 1) * meetings;
  }

  function getDerivedLeagueRounds(meetings = config.league_meetings) {
    const teamCount = getLeagueTeamCount();
    if (teamCount < 2) return 0;
    const baseRounds = teamCount % 2 === 0 ? teamCount - 1 : teamCount;
    return baseRounds * meetings;
  }

  function updateLeagueFormat(nextValues) {
    setConfig((prev) => {
      const next = { ...prev, ...nextValues };
      const teamCount = fixedPairs.length;
      if (next.draw_type === "league_knockout" && teamCount >= 2) {
        next.rounds = getDerivedLeagueRounds(next.league_meetings);
      }
      if (next.draw_type === "league_knockout") {
        next.pair_start_round = 1;
      }
      if (teamCount >= 2) {
        next.pair_games = getDerivedPairGames(next.league_meetings);
      }
      return next;
    });
  }

  function formatPreview() {
    if (config.draw_type === "league_knockout") {
      const qualifierLabel = config.knockout_qualifiers === 2 ? "top 2 to final" : "top 4 to semifinals";
      return `${config.rounds} league rounds, then ${qualifierLabel}`;
    }

    return `${config.rounds} league rounds with standings only`;
  }

  function updateNumericDraft(key, rawValue) {
    setDraftValues((current) => ({ ...current, [key]: rawValue }));
  }

  function adjustNumericValue(key, min, max, delta) {
    const currentValue = Number.parseInt(draftValues[key], 10);
    const fallbackValue = Number.parseInt(config[key], 10);
    const baseValue = Number.isNaN(currentValue) ? fallbackValue : currentValue;
    const nextValue = Math.min(max, Math.max(min, baseValue + delta));
    update(key, nextValue);
    setDraftValues((current) => ({ ...current, [key]: String(nextValue) }));
  }

  function commitNumericValue(key, min, max) {
    const rawValue = draftValues[key];
    if (rawValue === "") {
      setDraftValues((current) => ({ ...current, [key]: String(config[key]) }));
      return;
    }

    const parsedValue = Number.parseInt(rawValue, 10);
    if (Number.isNaN(parsedValue)) {
      setDraftValues((current) => ({ ...current, [key]: String(config[key]) }));
      return;
    }

    const nextValue = Math.min(max, Math.max(min, parsedValue));
    update(key, nextValue);
    setDraftValues((current) => ({ ...current, [key]: String(nextValue) }));
  }

  function updateCourtNumber(index, value) {
    setConfig((prev) => {
      const nums = [...(prev.court_numbers || [])];
      nums[index] = value;
      return { ...prev, court_numbers: nums };
    });
  }

  function addLimit(e) {
    e.preventDefault();
    if (!limitPlayer) return;
    // Enter submits the form without a blur, so the committed `limitValue` can be
    // stale: resolve the value from what is actually typed in the field.
    const parsedValue = Number.parseInt(limitValueDraft, 10);
    const nextValue = Number.isNaN(parsedValue) ? limitValue : Math.min(20, Math.max(1, parsedValue));
    setLimitValue(nextValue);
    setLimitValueDraft(String(nextValue));
    update("limits", { ...config.limits, [limitPlayer]: nextValue });
    setLimitPlayer("");
  }

  function commitSeedValue() {
    if (seedDraft === "") {
      update("seed", null);
      return;
    }

    const parsedValue = Number.parseInt(seedDraft, 10);
    if (Number.isNaN(parsedValue)) {
      setSeedDraft(config.seed ?? "");
      return;
    }

    update("seed", parsedValue);
    setSeedDraft(parsedValue);
  }

  function commitLimitValue() {
    if (limitValueDraft === "") {
      setLimitValueDraft(String(limitValue));
      return;
    }

    const parsedValue = Number.parseInt(limitValueDraft, 10);
    if (Number.isNaN(parsedValue)) {
      setLimitValueDraft(String(limitValue));
      return;
    }

    const nextValue = Math.min(20, Math.max(1, parsedValue));
    setLimitValue(nextValue);
    setLimitValueDraft(String(nextValue));
  }

  function removeLimit(player) {
    const next = { ...config.limits };
    delete next[player];
    update("limits", next);
  }

  const fields = [
    { key: "num_courts", label: "Courts", min: 1, max: 20, hint: "Number of courts available at the venue" },
    ...(config.draw_type === "round_robin"
      ? [
          { key: "rounds", label: "Rounds", min: 1, max: 30, hint: "Total number of game rounds to schedule" },
          { key: "pair_games", label: "Pair Games", min: 1, max: 15, hint: "How many games each fixed pair plays together" },
        ]
      : []),
    { key: "pair_start_round", label: "Pair Start Round", min: 1, max: 30, hint: "Fixed pairs only play together from this round onwards" },
    { key: "max_consecutive_rest", label: "Max Consec. Rest", min: 1, max: 10, hint: "Max rounds a player can sit out in a row" },
  ];
  const primaryFieldKeys = new Set(["num_courts", "rounds", "pair_games"]);
  const primaryFields = fields.filter(({ key }) => primaryFieldKeys.has(key));
  const advancedFields = fields.filter(({ key }) => !primaryFieldKeys.has(key));

  const courtNumbers = config.court_numbers || [];
  const derivedLeagueRounds = getDerivedLeagueRounds();
  const derivedPairGames = getDerivedPairGames();
  const leagueKnockoutIssue = getLeagueKnockoutIssue({
    drawType: config.draw_type,
    playerCount: players.length,
    pairCount: fixedPairs.length,
  });
  const leagueKnockoutCourts = getLeagueKnockoutCourts(fixedPairs.length);

  // League + Knockout plays pairs / 2 matches per round, so courts are not a free
  // choice: keep them in step with the pair count (and when the draw type changes).
  useEffect(() => {
    if (config.draw_type !== "league_knockout") return;
    if (leagueKnockoutCourts >= 1 && config.num_courts !== leagueKnockoutCourts) {
      setConfig((prev) => withCourtCount(prev, leagueKnockoutCourts));
    }
  }, [config.draw_type, config.num_courts, leagueKnockoutCourts, setConfig]);

  // Round Robin: never keep more courts than the selected players can fill
  // (4 players per court); the backend rejects that at Generate time.
  const maxPlayableCourts = Math.floor(players.length / 4);
  useEffect(() => {
    if (config.draw_type === "league_knockout") return;
    if (maxPlayableCourts >= 1 && config.num_courts > maxPlayableCourts) {
      setConfig((prev) => withCourtCount(prev, maxPlayableCourts));
    }
  }, [config.draw_type, config.num_courts, maxPlayableCourts, setConfig]);

  useEffect(() => {
    if (config.draw_type !== "league_knockout") return;
    if (derivedLeagueRounds > 0 && config.rounds !== derivedLeagueRounds) {
      setConfig((prev) => ({ ...prev, rounds: derivedLeagueRounds, pair_start_round: 1 }));
    }
  }, [config.draw_type, config.rounds, derivedLeagueRounds, setConfig]);

  useEffect(() => {
    if (config.draw_type !== "league_knockout") return;
    if (derivedPairGames > 0 && config.pair_games !== derivedPairGames) {
      setConfig((prev) => ({ ...prev, pair_games: derivedPairGames }));
    }
  }, [config.draw_type, config.pair_games, derivedPairGames, setConfig]);

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">Settings</h2>

      <div className="mb-5 rounded-xl border border-gray-200 bg-gray-50 p-4">
        <p className="text-xs font-medium uppercase tracking-wide text-gray-500">Draw Format</p>
        <div className="mt-3 grid gap-3">
          {DRAW_FORMATS.map((format) => {
            const selected = config.draw_type === format.id;

            return (
              <button
                key={format.id}
                type="button"
                onClick={() => updateLeagueFormat({ draw_type: format.id })}
                className={`rounded-xl border px-4 py-3 text-left transition-colors ${
                  selected
                    ? "border-indigo-300 bg-indigo-50 shadow-sm"
                    : "border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50"
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-gray-900">{format.title}</p>
                    <p className="mt-1 text-sm text-gray-500">{format.description}</p>
                  </div>
                  <span
                    className={`h-4 w-4 rounded-full border ${
                      selected ? "border-indigo-500 bg-indigo-500 ring-4 ring-indigo-100" : "border-gray-300 bg-white"
                    }`}
                  />
                </div>
              </button>
            );
          })}
        </div>
        <div className="mt-3 rounded-lg bg-white px-3 py-2 text-sm text-gray-600">
          <span className="font-medium text-gray-800">Preview:</span> {formatPreview()}
        </div>
      </div>

      {config.draw_type === "league_knockout" && leagueKnockoutIssue ? (
        <div role="alert" className="mb-5 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {leagueKnockoutIssue}
        </div>
      ) : null}
      {config.draw_type === "league_knockout" && !leagueKnockoutIssue ? (
        <div className="mb-5 rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm text-indigo-800">
          League + Knockout uses {leagueKnockoutCourts} court{leagueKnockoutCourts === 1 ? "" : "s"} for {fixedPairs.length} fixed pairs (one match per court each round).
        </div>
      ) : null}

      {config.draw_type === "league_knockout" && (
        <div className="mb-5 rounded-xl border border-slate-200 bg-slate-50 p-4">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-3">
            Playoff Setup
          </p>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                League Meetings
              </label>
              <div className="grid grid-cols-2 gap-2">
                {[1, 2].map((value) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => updateLeagueFormat({ league_meetings: value })}
                    className={`rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
                      config.league_meetings === value
                        ? "border-indigo-300 bg-indigo-50 text-indigo-700"
                        : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50"
                    }`}
                  >
                    {value === 1 ? "Play Once" : "Play Twice"}
                  </button>
                ))}
              </div>
              <p className="mt-1.5 text-xs text-gray-400">
                With {getLeagueTeamCount()} fixed pairs, this becomes {derivedLeagueRounds} league rounds.
              </p>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Knockout Qualifiers
              </label>
              <div className="grid grid-cols-2 gap-2">
                {[2, 4].map((value) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => update("knockout_qualifiers", value)}
                    className={`rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
                      config.knockout_qualifiers === value
                        ? "border-indigo-300 bg-indigo-50 text-indigo-700"
                        : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50"
                    }`}
                  >
                    Top {value}
                  </button>
                ))}
              </div>
              <p className="mt-1.5 text-xs text-gray-400">
                Top 2 creates a final. Top 4 creates semifinals and a final.
              </p>
            </div>
          </div>

          <div className="mt-3 rounded-lg bg-white px-3 py-2 text-sm text-gray-700">
            <span className="font-medium text-gray-900">League rounds:</span>{" "}
            {getLeagueTeamCount() >= 2
              ? `${derivedLeagueRounds} rounds (${getLeagueTeamCount()} teams, ${config.league_meetings === 1 ? "play once" : "play twice"})`
              : "Add at least 2 fixed pairs to calculate league rounds"}
          </div>

          <div className="mt-3 rounded-lg bg-white px-3 py-2 text-sm text-gray-700">
            <span className="font-medium text-gray-900">Pair games target:</span>{" "}
            {getLeagueTeamCount() >= 2
              ? `${derivedPairGames} games per fixed pair`
              : "Add at least 2 fixed pairs to calculate pair games"}
          </div>

          <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            Playoffs are seeded from pair standings, so fixed pairs are strongly recommended. Current fixed pairs: {fixedPairs.length}
          </div>
        </div>
      )}

      <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {primaryFields.map(({ key, label, min, max, hint }) => (
          <NumericField
            key={key}
            fieldKey={key}
            label={label}
            min={min}
            max={max}
            hint={hint}
            value={draftValues[key]}
            onAdjust={adjustNumericValue}
            onDraftChange={updateNumericDraft}
            onCommit={commitNumericValue}
          />
        ))}
      </div>

      <details className="rounded-xl border border-gray-200 bg-gray-50 p-4">
        <summary className="flex cursor-pointer list-none flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
          <div>
            <p className="text-sm font-semibold text-gray-900">Advanced Settings</p>
            <p className="mt-1 text-sm text-gray-500">
              Court labels, rest balancing, seed, and per-player consecutive game limits.
            </p>
          </div>
          <span className="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-gray-600 shadow-sm">
            Optional
          </span>
        </summary>

        <div className="mt-4 space-y-5 border-t border-gray-200 pt-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {advancedFields.map(({ key, label, min, max, hint }) => (
              <NumericField
                key={key}
                fieldKey={key}
                label={label}
                min={min}
                max={max}
                hint={hint}
                value={draftValues[key]}
                onAdjust={adjustNumericValue}
                onDraftChange={updateNumericDraft}
                onCommit={commitNumericValue}
              />
            ))}
            <div>
              <label className="flex items-center gap-1.5 text-xs font-medium text-gray-600 mb-1">
                Seed
                <span className="relative group">
                  <svg className="w-3.5 h-3.5 text-gray-400 hover:text-indigo-500 transition-colors cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 px-2.5 py-1.5 text-xs text-white bg-gray-800 rounded-md shadow-lg whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-20">
                    Same seed = same roster. Leave empty for random.
                  </span>
                </span>
              </label>
              <input
                type="number"
                value={seedDraft}
                onChange={(e) => setSeedDraft(e.target.value)}
                onBlur={commitSeedValue}
                placeholder="Random"
                className="w-full rounded-lg border border-gray-300 px-3 py-3 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          </div>

          <div className="border-t border-gray-200 pt-4">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
              Court Numbers
            </p>
            <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
              {courtNumbers.map((num, i) => (
                <div key={i} className="flex items-center gap-1">
                  <span className="text-xs text-gray-400">#{i + 1}:</span>
                  <input
                    type="text"
                    value={num}
                    onChange={(e) => updateCourtNumber(i, e.target.value)}
                    className="w-full min-w-0 rounded border border-gray-300 px-2 py-2 text-center text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-500 sm:w-14"
                  />
                </div>
              ))}
            </div>
            <p className="text-xs text-gray-400 mt-1.5">
              Set the actual court numbers at your venue (e.g. 3, 7, 12)
            </p>
          </div>

          <div className="border-t border-gray-200 pt-4">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
              Consecutive Game Limits
            </p>
            <form onSubmit={addLimit} noValidate className="mb-3 flex flex-col gap-2 sm:flex-row">
              <select
                value={limitPlayer}
                onChange={(e) => setLimitPlayer(e.target.value)}
                className="flex-1 rounded-lg border border-gray-300 px-3 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="">Select player...</option>
                {players
                  .filter((p) => !(p in config.limits))
                  .map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
              </select>
              <input
                type="number"
                min={1}
                max={20}
                value={limitValueDraft}
                onChange={(e) => setLimitValueDraft(e.target.value)}
                onBlur={commitLimitValue}
                className="w-full rounded-lg border border-gray-300 px-3 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 sm:w-20"
              />
              <button
                type="submit"
                className="inline-flex min-h-11 items-center justify-center rounded-lg bg-gray-100 px-3 py-3 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-200"
              >
                Add
              </button>
            </form>

            {Object.keys(config.limits).length > 0 && (
              <div className="flex flex-wrap gap-2">
                {Object.entries(config.limits).map(([player, limit]) => (
                  <span
                    key={player}
                    className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-orange-50 border border-orange-200 text-orange-700"
                  >
                    {player}: max {limit}
                    <button onClick={() => removeLimit(player)} className="hover:text-red-600 ml-0.5">
                      &times;
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </details>
    </div>
  );
}
