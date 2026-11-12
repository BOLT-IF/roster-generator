import { useEffect, useRef, useState } from "react";
import {
  batchUpdateSharedScores,
  editSharedRound,
  endSharedRound,
  fetchSharedSession,
  startSharedRound,
  updateSharedScore,
} from "../api";
import {
  ACTIVE_EDIT_GRACE_MS,
  ROUTE_PATHS,
  SESSION_POLL_INTERVAL_MS,
  SESSION_STORAGE_KEY,
  buildSessionPath,
  getScoreSyncKey,
  mergePendingScoreEdits,
  normalizeSession,
  readStorage,
  removeStorage,
  waitForNextPaint,
  writeStorage,
} from "./appStateUtils";

export default function useScoringSession({
  location,
  navigate,
  routeEditToken,
  routeSessionId,
  sessionAccess,
  rememberSessionAccess,
  view,
  refreshSupportingViews,
}) {
  const savedSession = useRef(readStorage(SESSION_STORAGE_KEY, null)).current;
  const pendingScoreEditsRef = useRef({});
  const scoreMutationQueueRef = useRef(Promise.resolve());
  const lastLocalEditAtRef = useRef(0);
  const previousNonScoringPathRef = useRef(ROUTE_PATHS.planner);

  const [currentSession, setCurrentSession] = useState(() => {
    try {
      return normalizeSession(savedSession);
    } catch {
      // A structurally invalid persisted session must not crash the app.
      return null;
    }
  });
  const [loading, setLoading] = useState(false);
  const [loadingLabel, setLoadingLabel] = useState("Syncing shared session...");
  const [pendingRoundAction, setPendingRoundAction] = useState(null);
  const [pageError, setPageError] = useState(null);
  // Set when the session behind the current route could not be loaded.
  const [sessionLoadError, setSessionLoadError] = useState(null);

  useEffect(() => {
    if (currentSession) {
      writeStorage(SESSION_STORAGE_KEY, currentSession);
    } else {
      removeStorage(SESSION_STORAGE_KEY);
    }
  }, [currentSession]);

  useEffect(() => {
    if (view === "scoring" || !view || view === "root") return;
    previousNonScoringPathRef.current = location.pathname + location.search;
  }, [location.pathname, location.search, view]);

  useEffect(() => {
    if (view !== "scoring" || !routeSessionId) return;

    // Aborted when the route session changes or the view unmounts, so a slow
    // response for one session can never render under another session's URL.
    const controller = new AbortController();
    const { signal } = controller;

    setLoadingLabel("Opening shared session...");
    setLoading(true);
    setPageError(null);
    setSessionLoadError(null);
    fetchSharedSession(routeSessionId, routeEditToken, { signal })
      .then((session) => {
        if (signal.aborted) return;
        const normalized = mergePendingScoreEdits(normalizeSession(session), pendingScoreEditsRef.current);
        rememberSessionAccess(normalized.sessionId, normalized.editToken);
        setCurrentSession(normalized);
      })
      .catch((error) => {
        if (signal.aborted) return;
        // A failed load must not leave a previously opened (editable) session on screen.
        pendingScoreEditsRef.current = {};
        setCurrentSession(null);
        setSessionLoadError({ sessionId: routeSessionId, message: error.message });
      })
      .finally(() => {
        if (!signal.aborted) setLoading(false);
      });

    return () => {
      controller.abort();
      setLoading(false);
    };
  }, [rememberSessionAccess, routeEditToken, routeSessionId, view]);

  useEffect(() => {
    if (!currentSession?.sessionId) return;

    const { sessionId, editToken, version } = currentSession;
    const controller = new AbortController();
    const { signal } = controller;
    // At most one poll in flight per effect run; ticks that arrive meanwhile are skipped.
    let pollInFlight = false;

    const intervalId = window.setInterval(async () => {
      if (pollInFlight) return;
      if (Object.keys(pendingScoreEditsRef.current).length > 0) return;
      if (Date.now() - lastLocalEditAtRef.current < ACTIVE_EDIT_GRACE_MS) return;

      pollInFlight = true;
      try {
        const latest = mergePendingScoreEdits(
          normalizeSession(await fetchSharedSession(sessionId, editToken, { signal })),
          pendingScoreEditsRef.current
        );
        if (signal.aborted) return;
        // Only a strictly newer version may replace local state; a delayed older
        // response must never roll the session back.
        if (latest.version > version) {
          rememberSessionAccess(latest.sessionId, latest.editToken);
          setCurrentSession((current) =>
            current && current.sessionId === latest.sessionId && latest.version > current.version ? latest : current
          );
        }
      } catch {
        // Keep local state; next successful poll will resync.
      } finally {
        pollInFlight = false;
      }
    }, SESSION_POLL_INTERVAL_MS);

    return () => {
      controller.abort();
      window.clearInterval(intervalId);
    };
  }, [currentSession?.editToken, currentSession?.sessionId, currentSession?.version, rememberSessionAccess]);

  function enqueueScoreMutation(task) {
    const nextOperation = scoreMutationQueueRef.current.then(task, task);
    scoreMutationQueueRef.current = nextOperation.catch(() => {});
    return nextOperation;
  }

  async function openSession(sessionId, editTokenOverride = null, sourcePath = null) {
    setLoadingLabel("Opening shared session...");
    setLoading(true);
    setPageError(null);
    try {
      const editToken = editTokenOverride || sessionAccess[sessionId] || null;
      const latest = mergePendingScoreEdits(
        normalizeSession(await fetchSharedSession(sessionId, editToken)),
        pendingScoreEditsRef.current
      );
      rememberSessionAccess(latest.sessionId, latest.editToken);
      setCurrentSession(latest);
      if (sourcePath) {
        previousNonScoringPathRef.current = sourcePath;
      }
      navigate(buildSessionPath(latest.sessionId, latest.editToken));
      refreshSupportingViews();
    } catch (error) {
      setPageError(error.message);
    } finally {
      setLoading(false);
    }
  }

  function setPreviousNonScoringPath(path) {
    previousNonScoringPathRef.current = path;
  }

  function getPreviousNonScoringPath() {
    return previousNonScoringPathRef.current || ROUTE_PATHS.sessions;
  }

  async function handleStartRound(stage, roundIndex) {
    if (!currentSession?.sessionId || !currentSession.canEdit) return;
    const { sessionId, editToken } = currentSession;

    setPendingRoundAction({ stage, roundIndex, action: "start" });
    setLoadingLabel(`Starting ${stage === "knockout" ? "playoff" : "league"} round...`);
    setLoading(true);
    setPageError(null);
    try {
      const updated = await startSharedRound(sessionId, {
        stage,
        round_index: roundIndex,
      }, editToken);
      const normalized = mergePendingScoreEdits(normalizeSession(updated), pendingScoreEditsRef.current);
      rememberSessionAccess(normalized.sessionId, normalized.editToken);
      setCurrentSession(normalized);
      refreshSupportingViews({ includeHistory: true, includePlayerStats: true });
    } catch (error) {
      setPageError(error.message);
    } finally {
      setPendingRoundAction(null);
      setLoading(false);
    }
  }

  async function handleEndRound(stage, roundIndex) {
    if (!currentSession?.sessionId || !currentSession.canEdit) return;
    const { sessionId, editToken } = currentSession;

    setPendingRoundAction({ stage, roundIndex, action: "end" });
    setLoadingLabel("Ending round...");
    setLoading(true);
    setPageError(null);
    try {
      await waitForNextPaint();
      await flushRoundScoreEdits(sessionId, stage, roundIndex, editToken);
      const updated = await endSharedRound(sessionId, {
        stage,
        round_index: roundIndex,
      }, editToken);
      const normalized = mergePendingScoreEdits(normalizeSession(updated), pendingScoreEditsRef.current);
      rememberSessionAccess(normalized.sessionId, normalized.editToken);
      setCurrentSession(normalized);
      refreshSupportingViews({ includeHistory: true, includePlayerStats: true });
    } catch (error) {
      setPageError(error.message);
    } finally {
      setPendingRoundAction(null);
      setLoading(false);
    }
  }

  async function handleEditRound(stage, roundIndex) {
    if (!currentSession?.sessionId || !currentSession.canEdit) return;
    const { sessionId, editToken } = currentSession;

    let confirmKnockoutWipe = false;
    if (stage === "league") {
      const knockoutStarted =
        currentSession.endedKnockoutRounds?.some(Boolean) ||
        (currentSession.knockoutScoresByRound ?? []).some((round) =>
          round.some((score) => score.teamA !== "" || score.teamB !== "")
        );
      if (knockoutStarted) {
        const accepted = window.confirm(
          "Re-opening a league round deletes all knockout scores and results for this session. Continue?"
        );
        if (!accepted) return;
        confirmKnockoutWipe = true;
      }
    }

    setPendingRoundAction({ stage, roundIndex, action: "edit" });
    setLoadingLabel("Re-opening round...");
    setLoading(true);
    setPageError(null);
    try {
      await waitForNextPaint();
      await flushRoundScoreEdits(sessionId, stage, roundIndex, editToken);
      const updated = await editSharedRound(sessionId, {
        stage,
        round_index: roundIndex,
        confirm_knockout_wipe: confirmKnockoutWipe,
      }, editToken);
      const normalized = mergePendingScoreEdits(normalizeSession(updated), pendingScoreEditsRef.current);
      rememberSessionAccess(normalized.sessionId, normalized.editToken);
      setCurrentSession(normalized);
    } catch (error) {
      setPageError(error.message);
    } finally {
      setPendingRoundAction(null);
      setLoading(false);
    }
  }

  function applyLocalScoreChange(session, stage, roundIndex, courtIndex, teamKey, rawValue) {
    if (!session) return session;

    const scoresKey = stage === "league" ? "leagueScoresByRound" : "knockoutScoresByRound";

    return normalizeSession({
      ...session,
      [scoresKey]: session[scoresKey].map((roundScores, currentRoundIndex) => {
        if (currentRoundIndex !== roundIndex) return roundScores;

        return roundScores.map((courtScore, currentCourtIndex) => {
          if (currentCourtIndex !== courtIndex) return courtScore;
          return { ...courtScore, [teamKey]: rawValue };
        });
      }),
    });
  }

  // Drop a failed pending edit and put the cell back to the last value the
  // server confirmed, so the UI never shows a score that was not saved and
  // polling is no longer blocked by the dead entry.
  function rollbackScoreEdit(syncKey, expectedRawValue) {
    const edit = pendingScoreEditsRef.current[syncKey];
    if (!edit) return;
    // A newer edit for the same cell supersedes this failure.
    if (expectedRawValue !== undefined && edit.rawValue !== expectedRawValue) return;

    delete pendingScoreEditsRef.current[syncKey];
    lastLocalEditAtRef.current = 0;
    setCurrentSession((session) =>
      applyLocalScoreChange(session, edit.stage, edit.roundIndex, edit.courtIndex, edit.teamKey, edit.serverValue ?? "")
    );
  }

  async function pushScoreUpdate(sessionId, editToken, stage, roundIndex, courtIndex, teamKey, rawValue) {
    const syncKey = getScoreSyncKey(stage, roundIndex, courtIndex, teamKey);

    return enqueueScoreMutation(async () => {
      // Nothing pending for this cell (already saved or rolled back): skip the write.
      if (!pendingScoreEditsRef.current[syncKey]) return;
      try {
        const result = await updateSharedScore(sessionId, {
          stage,
          round_index: roundIndex,
          court_index: courtIndex,
          team_key: teamKey,
          value: rawValue === "" ? null : Math.min(99, Math.max(0, Number.parseInt(rawValue, 10) || 0)),
        }, editToken || sessionAccess[sessionId] || null);
        if (pendingScoreEditsRef.current[syncKey]?.rawValue === rawValue) {
          delete pendingScoreEditsRef.current[syncKey];
        }

        setCurrentSession((session) => (session ? { ...session, version: result.version ?? session.version } : session));
        setPageError(null);
      } catch (error) {
        rollbackScoreEdit(syncKey, rawValue);
        setPageError(error.message);
        throw error;
      }
    });
  }

  async function flushRoundScoreEdits(sessionId, stage, roundIndex, editToken) {
    const pendingEntries = Object.entries(pendingScoreEditsRef.current).filter(([, edit]) =>
      edit.stage === stage && edit.roundIndex === roundIndex
    );

    if (pendingEntries.length === 0) return;

    await enqueueScoreMutation(async () => {
      try {
        await sendBatch();
      } catch (error) {
        pendingEntries.forEach(([syncKey, edit]) => rollbackScoreEdit(syncKey, edit.rawValue));
        throw error;
      }
    });

    async function sendBatch() {
      const updates = pendingEntries.map(([, edit]) => ({
        stage,
        round_index: roundIndex,
        court_index: edit.courtIndex,
        team_key: edit.teamKey,
        value: edit.rawValue === "" ? null : Math.min(99, Math.max(0, Number.parseInt(edit.rawValue, 10) || 0)),
      }));

      const result = await batchUpdateSharedScores(sessionId, {
        stage,
        round_index: roundIndex,
        updates,
      }, editToken || sessionAccess[sessionId] || null);

      pendingEntries.forEach(([syncKey, edit]) => {
        if (pendingScoreEditsRef.current[syncKey]?.rawValue === edit.rawValue) {
          delete pendingScoreEditsRef.current[syncKey];
        }
      });

      setCurrentSession((session) => (session ? { ...session, version: result.version ?? session.version } : session));
      setPageError(null);
    }
  }

  function clearPageError() {
    setPageError(null);
  }

  function handleScoreChange(stage, roundIndex, courtIndex, teamKey, rawValue) {
    if (!currentSession?.sessionId || !currentSession.canEdit) return;

    lastLocalEditAtRef.current = Date.now();
    const syncKey = getScoreSyncKey(stage, roundIndex, courtIndex, teamKey);
    const scoresKey = stage === "league" ? "leagueScoresByRound" : "knockoutScoresByRound";
    // Remember the value the server last confirmed (the first edit's starting point).
    const serverValue =
      syncKey in pendingScoreEditsRef.current
        ? pendingScoreEditsRef.current[syncKey].serverValue
        : currentSession[scoresKey]?.[roundIndex]?.[courtIndex]?.[teamKey] ?? "";
    pendingScoreEditsRef.current[syncKey] = {
      stage,
      roundIndex,
      courtIndex,
      teamKey,
      rawValue,
      serverValue,
    };
    setCurrentSession((session) =>
      applyLocalScoreChange(session, stage, roundIndex, courtIndex, teamKey, rawValue)
    );
  }

  function handleScoreCommit(stage, roundIndex, courtIndex, teamKey, rawValue) {
    if (!currentSession?.sessionId || !currentSession.canEdit) return;
    // pushScoreUpdate already rolls back and surfaces the failure via setPageError;
    // the catch only logs so the rethrown error is not an unhandled rejection.
    pushScoreUpdate(
      currentSession.sessionId,
      currentSession.editToken,
      stage,
      roundIndex,
      courtIndex,
      teamKey,
      rawValue
    ).catch((error) => {
      console.error("Score update failed:", error);
    });
  }

  return {
    currentSession,
    setCurrentSession,
    sessionLoading: loading,
    sessionLoadingLabel: loadingLabel,
    pendingRoundAction,
    pageError,
    sessionLoadError,
    openSession,
    handleStartRound,
    handleEndRound,
    handleEditRound,
    handleScoreChange,
    handleScoreCommit,
    clearPageError,
    getPreviousNonScoringPath,
    setPreviousNonScoringPath,
  };
}
