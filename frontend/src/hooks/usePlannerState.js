import { useEffect, useRef, useState } from "react";
import { generateRoster, revalidateRoster } from "../api";
import { appCopy } from "../content/uiCopy";
import {
  DUPLICATE_KNOCKOUT_VIOLATION_PREFIX,
  PLANNER_STORAGE_KEY,
  createSessionName,
  getLeagueKnockoutIssue,
  getLeagueRequestPayload,
  getPlannerRosterSignature,
  getRosterRevalidatePayload,
  normalizeConfig,
  readStorage,
  sanitizePlannerState,
  swapRosterRounds,
  swapRosterSlots,
  swapRosterTeams,
  writeStorage,
} from "./appStateUtils";

export default function usePlannerState({ directoryPlayers, directoryLoaded = true, navigateToPlanner }) {
  const plannerState = useRef(sanitizePlannerState(readStorage(PLANNER_STORAGE_KEY, null))).current;
  const reviewStepRef = useRef(null);

  const [selectedPlayerIds, setSelectedPlayerIds] = useState(plannerState?.selectedPlayerIds || []);
  const [fixedPairIds, setFixedPairIds] = useState(plannerState?.fixedPairIds || []);
  const [config, setConfig] = useState(normalizeConfig(plannerState?.config));
  const [roster, setRoster] = useState(plannerState?.roster || null);
  const [generatedRosterBaseline, setGeneratedRosterBaseline] = useState(plannerState?.generatedRosterBaseline || null);
  const [rosterSignature, setRosterSignature] = useState(plannerState?.rosterSignature || null);
  const [hasManualRosterEdits, setHasManualRosterEdits] = useState(Boolean(plannerState?.hasManualRosterEdits));
  const [selectedRosterTarget, setSelectedRosterTarget] = useState(null);
  const [loading, setLoading] = useState(false);
  const [generateError, setGenerateError] = useState(null);
  const [plannerError, setPlannerError] = useState(null);
  const [plannerStep, setPlannerStep] = useState(1);
  const [sessionDraftName, setSessionDraftName] = useState(createSessionName());
  const [rosterEditLoading, setRosterEditLoading] = useState(false);
  const [duplicateKnockoutViolations, setDuplicateKnockoutViolations] = useState([]);

  const playersById = new Map(directoryPlayers.map((player) => [player.playerId, player]));
  const selectedPlayers = selectedPlayerIds
    .map((playerId) => playersById.get(playerId))
    .filter(Boolean);
  const selectedPlayerShortNames = selectedPlayers.map((player) => player.shortName);
  const fixedPairs = fixedPairIds
    .map(([firstId, secondId]) => {
      const firstPlayer = playersById.get(firstId);
      const secondPlayer = playersById.get(secondId);
      if (!firstPlayer || !secondPlayer) return null;
      return [firstPlayer.shortName, secondPlayer.shortName].sort();
    })
    .filter(Boolean);
  const plannerRosterSignature = getPlannerRosterSignature(selectedPlayerIds, fixedPairIds, config, directoryPlayers);
  // Until the directory has loaded, the signature is computed against an empty
  // directory and would always differ from the saved one, so never call the
  // roster stale before we can actually compare.
  const isRosterStale = Boolean(
    directoryLoaded && roster && rosterSignature && rosterSignature !== plannerRosterSignature
  );

  const selectedEditSummary = (() => {
    if (!roster || !selectedRosterTarget) return "";
    if (selectedRosterTarget.mode === "player") {
      const player = roster.rounds[selectedRosterTarget.roundIndex]
        ?.courts[selectedRosterTarget.courtIndex]?.[selectedRosterTarget.teamKey]?.[selectedRosterTarget.playerIndex];
      return player ? `${player} in Round ${selectedRosterTarget.roundIndex + 1}` : "";
    }
    if (selectedRosterTarget.mode === "team") {
      const team = roster.rounds[selectedRosterTarget.roundIndex]
        ?.courts[selectedRosterTarget.courtIndex]?.[selectedRosterTarget.teamKey];
      return team ? `${team.join(" & ")} in Round ${selectedRosterTarget.roundIndex + 1}` : "";
    }
    return `Round ${selectedRosterTarget.roundIndex + 1}`;
  })();

  useEffect(() => {
    writeStorage(PLANNER_STORAGE_KEY, {
      selectedPlayerIds,
      fixedPairIds,
      config,
      roster,
      generatedRosterBaseline,
      rosterSignature,
      hasManualRosterEdits,
    });
  }, [config, fixedPairIds, generatedRosterBaseline, hasManualRosterEdits, roster, rosterSignature, selectedPlayerIds]);

  useEffect(() => {
    if (!roster) {
      setSelectedRosterTarget(null);
    }
  }, [roster]);

  useEffect(() => {
    const hasRosterFixedPairs = roster && Object.keys(roster.fixed_pair_counts || {}).length > 0;
    if (!roster || config.draw_type !== "league_knockout" || !hasRosterFixedPairs) {
      setDuplicateKnockoutViolations([]);
      return;
    }

    const duplicateViolations = (roster.violations || []).filter((violation) =>
      violation.startsWith(DUPLICATE_KNOCKOUT_VIOLATION_PREFIX)
    );
    setDuplicateKnockoutViolations(duplicateViolations);
  }, [config.draw_type, roster]);

  useEffect(() => {
    if (isRosterStale) {
      setSelectedRosterTarget(null);
      setPlannerError(null);
    }
  }, [isRosterStale]);

  useEffect(() => {
    if (directoryPlayers.length === 0) return;

    if ((!plannerState?.selectedPlayerIds || plannerState.selectedPlayerIds.length === 0) && Array.isArray(plannerState?.players)) {
      const legacyIds = plannerState.players
        .map((name) => directoryPlayers.find((player) => player.shortName === name || player.fullName === name)?.playerId)
        .filter(Boolean);
      if (legacyIds.length > 0 && selectedPlayerIds.length === 0) {
        setSelectedPlayerIds(legacyIds);
      }
    }

    if ((!plannerState?.fixedPairIds || plannerState.fixedPairIds.length === 0) && Array.isArray(plannerState?.fixedPairs)) {
      const legacyPairIds = plannerState.fixedPairs
        .map(([firstName, secondName]) => {
          const firstId = directoryPlayers.find((player) => player.shortName === firstName || player.fullName === firstName)?.playerId;
          const secondId = directoryPlayers.find((player) => player.shortName === secondName || player.fullName === secondName)?.playerId;
          if (!firstId || !secondId) return null;
          return [firstId, secondId].sort();
        })
        .filter(Boolean);
      if (legacyPairIds.length > 0 && fixedPairIds.length === 0) {
        setFixedPairIds(legacyPairIds);
      }
    }
  }, [directoryPlayers, fixedPairIds.length, plannerState, selectedPlayerIds.length]);

  useEffect(() => {
    if (!directoryLoaded) return;
    const nextPlayersById = new Map(directoryPlayers.map((player) => [player.playerId, player]));
    const validSelectedIds = selectedPlayerIds.filter((playerId) => nextPlayersById.has(playerId));
    if (validSelectedIds.length !== selectedPlayerIds.length) {
      setSelectedPlayerIds(validSelectedIds);
    }
  }, [directoryLoaded, directoryPlayers, selectedPlayerIds]);

  useEffect(() => {
    if (!directoryLoaded) return;
    const selectedIdSet = new Set(selectedPlayerIds);
    const validPairs = fixedPairIds.filter(
      ([firstId, secondId]) =>
        selectedIdSet.has(firstId) &&
        selectedIdSet.has(secondId) &&
        firstId !== secondId
    );
    if (validPairs.length !== fixedPairIds.length) {
      setFixedPairIds(validPairs);
    }
  }, [directoryLoaded, fixedPairIds, selectedPlayerIds]);

  useEffect(() => {
    if (!directoryLoaded) return;
    const nextPlayersById = new Map(directoryPlayers.map((player) => [player.playerId, player]));
    const selectedShortNameSet = new Set(
      selectedPlayerIds
        .map((playerId) => nextPlayersById.get(playerId)?.shortName)
        .filter(Boolean)
    );
    setConfig((current) => {
      const nextLimits = Object.fromEntries(
        Object.entries(current.limits || {}).filter(([playerName]) => selectedShortNameSet.has(playerName))
      );
      if (Object.keys(nextLimits).length === Object.keys(current.limits || {}).length) {
        return current;
      }
      return { ...current, limits: nextLimits };
    });
  }, [directoryLoaded, directoryPlayers, selectedPlayerIds]);

  async function handleGenerate() {
    if (hasManualRosterEdits && typeof window !== "undefined") {
      const shouldContinue = window.confirm(appCopy.planner.regenerateConfirm);
      if (!shouldContinue) return;
    }

    setLoading(true);
    setPlannerError(null);
    setGenerateError(null);
    try {
      const result = await generateRoster(getLeagueRequestPayload(selectedPlayerShortNames, fixedPairs, config));
      setRoster(result);
      setGeneratedRosterBaseline(result);
      setRosterSignature(plannerRosterSignature);
      setHasManualRosterEdits(false);
      setSelectedRosterTarget(null);
      setPlannerStep(3);
      navigateToPlanner();
    } catch (error) {
      setGenerateError(error.message);
      setRoster(null);
      setGeneratedRosterBaseline(null);
      setRosterSignature(null);
      setHasManualRosterEdits(false);
      setSelectedRosterTarget(null);
      window.setTimeout(() => {
        reviewStepRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 0);
    } finally {
      setLoading(false);
    }
  }

  async function applyRosterEdit(nextRoster) {
    setRosterEditLoading(true);
    setPlannerError(null);
    try {
      const normalized = await revalidateRoster(
        getRosterRevalidatePayload(nextRoster, selectedPlayerShortNames, fixedPairs, config)
      );
      setRoster(normalized);
      setHasManualRosterEdits(true);
      setSelectedRosterTarget(null);
    } catch (error) {
      setPlannerError(error.message);
      setSelectedRosterTarget(null);
    } finally {
      setRosterEditLoading(false);
    }
  }

  function clearRosterSelection() {
    setSelectedRosterTarget(null);
    setPlannerError(null);
  }

  function clearPlannerError() {
    setPlannerError(null);
  }

  function dismissDuplicateKnockoutViolations() {
    setDuplicateKnockoutViolations([]);
  }

  async function handleRosterPlayerTap(slot) {
    if (!roster || rosterEditLoading || isRosterStale) return;

    if (!selectedRosterTarget) {
      setSelectedRosterTarget({ mode: "player", ...slot });
      setPlannerError(null);
      return;
    }
    if (selectedRosterTarget.mode !== "player") {
      setPlannerError(appCopy.planner.playerSwapInvalid);
      return;
    }

    const sameSlot =
      selectedRosterTarget.roundIndex === slot.roundIndex &&
      selectedRosterTarget.courtIndex === slot.courtIndex &&
      selectedRosterTarget.teamKey === slot.teamKey &&
      selectedRosterTarget.playerIndex === slot.playerIndex;

    if (sameSlot) {
      setSelectedRosterTarget(null);
      return;
    }

    if (selectedRosterTarget.roundIndex !== slot.roundIndex) {
      setPlannerError(appCopy.planner.playerSwapInvalid);
      return;
    }

    await applyRosterEdit(swapRosterSlots(roster, selectedRosterTarget, slot));
  }

  async function handleRosterTeamTap(team) {
    if (!roster || rosterEditLoading || isRosterStale) return;

    if (!selectedRosterTarget) {
      setSelectedRosterTarget({ mode: "team", ...team });
      setPlannerError(null);
      return;
    }
    if (selectedRosterTarget.mode !== "team") {
      setPlannerError(appCopy.planner.teamSwapInvalid);
      return;
    }

    const sameTeam =
      selectedRosterTarget.roundIndex === team.roundIndex &&
      selectedRosterTarget.courtIndex === team.courtIndex &&
      selectedRosterTarget.teamKey === team.teamKey;

    if (sameTeam) {
      setSelectedRosterTarget(null);
      return;
    }

    if (selectedRosterTarget.roundIndex !== team.roundIndex) {
      setPlannerError(appCopy.planner.teamSwapInvalid);
      return;
    }

    await applyRosterEdit(swapRosterTeams(roster, selectedRosterTarget, team));
  }

  async function handleRosterRoundTap(roundIndex) {
    if (!roster || rosterEditLoading || isRosterStale) return;

    if (!selectedRosterTarget) {
      setSelectedRosterTarget({ mode: "round", roundIndex });
      setPlannerError(null);
      return;
    }
    if (selectedRosterTarget.mode !== "round") {
      setPlannerError(appCopy.planner.roundSwapInvalid);
      return;
    }

    if (selectedRosterTarget.roundIndex === roundIndex) {
      setSelectedRosterTarget(null);
      return;
    }

    await applyRosterEdit(swapRosterRounds(roster, selectedRosterTarget.roundIndex, roundIndex));
  }

  function resetAfterSessionStart() {
    setRoster(null);
    setGeneratedRosterBaseline(null);
    setRosterSignature(null);
    setHasManualRosterEdits(false);
    setSelectedRosterTarget(null);
    setPlannerStep(1);
    setSessionDraftName(createSessionName());
  }

  function removeDeletedPlayer(playerId) {
    setSelectedPlayerIds((current) => current.filter((value) => value !== playerId));
    setFixedPairIds((current) =>
      current.filter(([firstId, secondId]) => firstId !== playerId && secondId !== playerId)
    );
  }

  const canContinueFromPlayers = selectedPlayerIds.length >= 4;
  const configIssue = getLeagueKnockoutIssue({
    drawType: config.draw_type,
    playerCount: selectedPlayerIds.length,
    pairCount: fixedPairIds.length,
  });
  const canContinueFromSettings = config.num_courts >= 1 && !configIssue;

  return {
    plannerStep,
    setPlannerStep,
    selectedPlayerIds,
    setSelectedPlayerIds,
    fixedPairIds,
    setFixedPairIds,
    config,
    setConfig,
    roster,
    generatedRosterBaseline,
    rosterSignature,
    hasManualRosterEdits,
    selectedRosterTarget,
    loading,
    generateError,
    sessionDraftName,
    setSessionDraftName,
    rosterEditLoading,
    plannerError,
    reviewStepRef,
    selectedPlayers,
    selectedPlayerShortNames,
    fixedPairs,
    plannerRosterSignature,
    isRosterStale,
    selectedEditSummary,
    duplicateKnockoutViolations,
    canContinueFromPlayers,
    canContinueFromSettings,
    configIssue,
    handleGenerate,
    clearPlannerError,
    dismissDuplicateKnockoutViolations,
    clearRosterSelection,
    handleRosterPlayerTap,
    handleRosterTeamTap,
    handleRosterRoundTap,
    resetAfterSessionStart,
    removeDeletedPlayer,
  };
}
