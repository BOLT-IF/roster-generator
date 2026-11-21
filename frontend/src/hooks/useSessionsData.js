import { useCallback, useEffect, useRef, useState } from "react";
import {
  createSharedSession,
  deleteSharedSession,
  listCompletedSessions,
  listSharedSessions,
  renameSharedSession,
} from "../api";
import { appCopy } from "../content/uiCopy";
import {
  ORGANIZER_TOKEN_STORAGE_KEY,
  ROUTE_PATHS,
  SESSION_ACCESS_STORAGE_KEY,
  buildShareUrl,
  createSessionName,
  normalizeCompletedSessionSummary,
  normalizeSession,
  normalizeSessionSummary,
  readStorage,
  writeStorage,
} from "./appStateUtils";

export default function useSessionsData({
  confirmAction,
  navigate,
  refreshPlayerStats,
  view,
}) {
  const savedSessionAccess = useRef(readStorage(SESSION_ACCESS_STORAGE_KEY, {})).current;
  const savedOrganizerToken = useRef(readStorage(ORGANIZER_TOKEN_STORAGE_KEY, "")).current;

  const [sessionAccess, setSessionAccess] = useState(savedSessionAccess);
  const [sessions, setSessions] = useState([]);
  const [historySessions, setHistorySessions] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [sessionsLoadingLabel, setSessionsLoadingLabel] = useState("Refreshing sessions...");
  const [pageError, setPageError] = useState(null);
  const [renameDialog, setRenameDialog] = useState({ open: false, sessionId: null });
  const [renameValue, setRenameValue] = useState("");
  const [renameLoading, setRenameLoading] = useState(false);
  const [renameError, setRenameError] = useState(null);
  const [shareFeedback, setShareFeedback] = useState({ sessionId: null, text: "" });
  const [organizerToken, setOrganizerToken] = useState(savedOrganizerToken || "");
  const [organizerTokenDraft, setOrganizerTokenDraft] = useState(savedOrganizerToken || "");
  const [organizerDialogOpen, setOrganizerDialogOpen] = useState(false);
  const [organizerDialogError, setOrganizerDialogError] = useState(null);
  const [sessionMutationLoading, setSessionMutationLoading] = useState(false);
  const [sessionMutationLabel, setSessionMutationLabel] = useState("Syncing shared session...");

  useEffect(() => {
    writeStorage(SESSION_ACCESS_STORAGE_KEY, sessionAccess);
  }, [sessionAccess]);

  useEffect(() => {
    writeStorage(ORGANIZER_TOKEN_STORAGE_KEY, organizerToken || "");
  }, [organizerToken]);

  useEffect(() => {
    void loadSessions();
  }, []);

  useEffect(() => {
    if (view === "sessions") {
      void loadSessions();
    }
  }, [view]);

  useEffect(() => {
    if (view === "history") {
      void loadHistorySessions();
    }
  }, [view]);

  function clearPageError() {
    setPageError(null);
  }

  const rememberSessionAccess = useCallback((sessionId, editToken) => {
    if (!sessionId || !editToken) return;
    setSessionAccess((current) => ({ ...current, [sessionId]: editToken }));
  }, []);

  const loadSessions = useCallback(async () => {
    setSessionsLoadingLabel("Refreshing session...");
    setSessionsLoading(true);
    setPageError(null);
    try {
      const list = await listSharedSessions();
      setSessions(list.map(normalizeSessionSummary).filter(Boolean));
    } catch (error) {
      setPageError(error.message);
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  const loadHistorySessions = useCallback(async () => {
    setHistoryLoading(true);
    setPageError(null);
    try {
      const list = await listCompletedSessions();
      setHistorySessions(list.map(normalizeCompletedSessionSummary).filter(Boolean));
    } catch (error) {
      setPageError(error.message);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const refreshSupportingViews = useCallback(({ includeHistory = false, includePlayerStats = false } = {}) => {
    void loadSessions();
    if (includeHistory) {
      void loadHistorySessions();
    }
    if (includePlayerStats) {
      void refreshPlayerStats();
    }
  }, [loadHistorySessions, loadSessions, refreshPlayerStats]);

  function openRenameDialog(sessionId, currentName) {
    setRenameDialog({ open: true, sessionId });
    setRenameValue(currentName || "");
    setRenameError(null);
  }

  function closeRenameDialog() {
    if (renameLoading) return;
    setRenameDialog({ open: false, sessionId: null });
    setRenameValue("");
    setRenameError(null);
  }

  function clearRenameError() {
    setRenameError(null);
  }

  async function handleRenameSession(currentSession) {
    if (!renameDialog.sessionId) return;

    const nextName = renameValue.trim();
    if (!nextName) {
      setRenameError(appCopy.renameDialog.requiredError);
      return;
    }

    setRenameLoading(true);
    setSessionMutationLabel("Renaming session...");
    setSessionMutationLoading(true);
    setRenameError(null);
    setPageError(null);
    try {
      const editToken =
        currentSession?.sessionId === renameDialog.sessionId
          ? currentSession.editToken
          : sessionAccess[renameDialog.sessionId] || null;
      const updated = await renameSharedSession(renameDialog.sessionId, { name: nextName }, editToken);
      const normalized = normalizeSession(updated);
      setRenameDialog({ open: false, sessionId: null });
      setRenameValue("");
      refreshSupportingViews({ includeHistory: true, includePlayerStats: true });
      return normalized;
    } catch (error) {
      setRenameError(error.message);
      return null;
    } finally {
      setRenameLoading(false);
      setSessionMutationLoading(false);
    }
  }

  async function handleCopyShareLink(sessionId, mode = "view") {
    if (!sessionId) return;

    const shareUrl = buildShareUrl(sessionId, mode === "scorer" ? sessionAccess[sessionId] || null : null);
    try {
      await navigator.clipboard.writeText(shareUrl);
      setShareFeedback({ sessionId, mode, text: appCopy.sessions.feedback.copied });
      window.setTimeout(() => setShareFeedback({ sessionId: null, text: "" }), 2000);
    } catch {
      setShareFeedback({ sessionId, mode, text: appCopy.sessions.feedback.failed });
      window.setTimeout(() => setShareFeedback({ sessionId: null, text: "" }), 2000);
    }
  }

  async function handleDeleteSession(sessionId, currentSession) {
    if (!sessionId) return;
    const target = sessions.find((session) => session.sessionId === sessionId);
    const shouldDelete = await confirmAction(
      `Delete ${target?.name || "this session"}? This removes the locked roster and all saved scores.`,
      { confirmLabel: "Delete Session" }
    );
    if (!shouldDelete) return;

    setSessionMutationLabel("Deleting session...");
    setSessionMutationLoading(true);
    setPageError(null);
    try {
      await deleteSharedSession(sessionId, sessionAccess[sessionId] || null);
      setSessions((current) => current.filter((session) => session.sessionId !== sessionId));
      setSessionAccess((current) => {
        const next = { ...current };
        delete next[sessionId];
        return next;
      });
      if (currentSession?.sessionId === sessionId) {
        navigate(ROUTE_PATHS.sessions);
      }
      refreshSupportingViews({ includeHistory: true, includePlayerStats: true });
      return true;
    } catch (error) {
      setPageError(error.message);
      return false;
    } finally {
      setSessionMutationLoading(false);
    }
  }

  async function createPlannerSession(planner, adminToken) {
    if (!planner.roster) return false;

    setSessionMutationLabel("Creating session...");
    setSessionMutationLoading(true);
    setPageError(null);
    try {
      const session = await createSharedSession({
        name: planner.sessionDraftName.trim() || createSessionName(),
        roster: planner.roster,
        draw_config: {
          draw_type: planner.config.draw_type,
          league_meetings: planner.config.league_meetings,
          knockout_qualifiers: planner.config.knockout_qualifiers,
        },
        selected_players: planner.selectedPlayers.map((player) => ({
          player_id: player.playerId,
          full_name: player.fullName,
          short_name: player.shortName,
        })),
        fixed_pair_player_ids: planner.fixedPairIds,
        fixed_pairs: planner.fixedPairs,
        limits: planner.config.limits,
        pair_games: planner.config.pair_games,
        pair_start_round: planner.config.pair_start_round,
        max_consecutive_rest: planner.config.max_consecutive_rest,
        admin_token: adminToken,
      });
      const normalized = normalizeSession(session);
      rememberSessionAccess(normalized.sessionId, normalized.editToken);
      setOrganizerToken(adminToken);
      setOrganizerDialogError(null);
      setOrganizerDialogOpen(false);
      refreshSupportingViews();
      return normalized;
    } catch (error) {
      if (error.message === "Organizer token required to start a session") {
        setOrganizerDialogError(error.message);
        setOrganizerTokenDraft(adminToken);
      } else {
        setPageError(error.message);
      }
      return null;
    } finally {
      setSessionMutationLoading(false);
    }
  }

  async function handleLockRoster(planner) {
    if (!planner.roster) return;

    if (!organizerToken.trim()) {
      setOrganizerDialogError(null);
      setOrganizerTokenDraft(organizerToken);
      setOrganizerDialogOpen(true);
      return;
    }

    const startedSession = await createPlannerSession(planner, organizerToken.trim());
    if (!startedSession) {
      setOrganizerDialogOpen(true);
    }
    return startedSession;
  }

  async function handleOrganizerDialogSubmit(planner) {
    const nextToken = organizerTokenDraft.trim();
    if (!nextToken) return;
    return createPlannerSession(planner, nextToken);
  }

  const activeSessions = sessions.filter((session) => session.status !== "completed");

  return {
    sessionAccess,
    rememberSessionAccess,
    sessions,
    activeSessions,
    historySessions,
    historyLoading,
    sessionsLoading,
    sessionsLoadingLabel,
    renameDialog,
    renameValue,
    setRenameValue,
    renameLoading,
    renameError,
    shareFeedback,
    organizerToken,
    organizerTokenDraft,
    organizerDialogOpen,
    organizerDialogError,
    sessionMutationLoading,
    sessionMutationLabel,
    pageError,
    setOrganizerTokenDraft,
    setOrganizerDialogOpen,
    setOrganizerDialogError,
    clearPageError,
    loadSessions,
    loadHistorySessions,
    refreshSupportingViews,
    openRenameDialog,
    closeRenameDialog,
    clearRenameError,
    handleRenameSession,
    handleCopyShareLink,
    handleDeleteSession,
    handleLockRoster,
    handleOrganizerDialogSubmit,
  };
}
