import { useEffect, useState } from "react";
import { Link, matchPath, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import AppShell from "./components/AppShell";
import { appCopy } from "./content/uiCopy";
import PlannerRoute from "./routes/PlannerRoute";
import PlayersRoute from "./routes/PlayersRoute";
import ActiveSessionsRoute from "./routes/ActiveSessionsRoute";
import HistoryRoute from "./routes/HistoryRoute";
import PlayerStatsRoute from "./routes/PlayerStatsRoute";
import ScoringRoute from "./routes/ScoringRoute";
import useSessionTiming from "./hooks/useSessionTiming";
import usePlayerStatsData from "./hooks/usePlayerStatsData";
import usePlayersData from "./hooks/usePlayersData";
import usePlannerState from "./hooks/usePlannerState";
import useSessionsData from "./hooks/useSessionsData";
import useScoringSession from "./hooks/useScoringSession";
import {
  PLAIN_SESSION_WAIT_LABELS,
  ROUTE_PATHS,
  buildSessionPath,
  getLegacySessionContext,
  getRoutePathForView,
  getViewFromPathname,
} from "./hooks/appStateUtils";

function RootRouteRedirect() {
  const location = useLocation();
  const legacySession = getLegacySessionContext(location.search);

  if (legacySession?.sessionId) {
    return <Navigate to={buildSessionPath(legacySession.sessionId, legacySession.editToken)} replace />;
  }

  return <Navigate to={ROUTE_PATHS.planner} replace />;
}

function NotFoundRoute() {
  return (
    <section className="mx-auto max-w-xl rounded-2xl border border-gray-200 bg-white p-8 text-center shadow-sm">
      <h1 className="text-2xl font-semibold text-gray-900">Page not found</h1>
      <p className="mt-2 text-sm text-gray-600">
        We could not find the page you were looking for. The link may be mistyped or out of date.
      </p>
      <Link
        to={ROUTE_PATHS.planner}
        className="mt-6 inline-flex min-h-11 items-center justify-center rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-700"
      >
        Back to the planner
      </Link>
    </section>
  );
}

function RenameSessionDialog({
  open,
  value,
  loading,
  error,
  onChange,
  onCancel,
  onSubmit,
}) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
      <div className="w-full max-w-md rounded-2xl border border-gray-200 bg-white p-5 shadow-xl">
        <p className="text-sm font-semibold uppercase tracking-wide text-gray-500">{appCopy.renameDialog.eyebrow}</p>
        <h3 className="mt-1 text-lg font-semibold text-gray-900">{appCopy.renameDialog.title}</h3>
        <form
          className="mt-4 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit();
          }}
        >
          {error ? (
            <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {error}
            </div>
          ) : null}
          <label className="block text-sm font-medium text-gray-700" htmlFor="rename-session-name">
            {appCopy.renameDialog.fieldLabel}
            <input
              id="rename-session-name"
              type="text"
              value={value}
              onChange={(event) => onChange(event.target.value)}
              disabled={loading}
              maxLength={120}
              className="mt-2 block w-full rounded-lg border border-gray-300 bg-white px-3 py-3 text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 disabled:bg-gray-100"
            />
          </label>
          <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <button
              type="button"
              onClick={onCancel}
              disabled={loading}
              className="inline-flex min-h-11 items-center justify-center rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-semibold text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-60"
            >
              {appCopy.renameDialog.cancel}
            </button>
            <button
              type="submit"
              disabled={loading || !value.trim()}
              className="inline-flex min-h-11 items-center justify-center rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500"
            >
              {loading ? appCopy.renameDialog.submitLoading : appCopy.renameDialog.submit}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function OrganizerTokenDialog({
  open,
  loading,
  value,
  error,
  onChange,
  onCancel,
  onSubmit,
}) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
      <div className="w-full max-w-md rounded-2xl border border-amber-200 bg-white p-5 shadow-xl">
        <p className="text-sm font-semibold uppercase tracking-wide text-amber-600">{appCopy.organizerDialog.eyebrow}</p>
        <h3 className="mt-1 text-lg font-semibold text-gray-900">{appCopy.organizerDialog.title}</h3>
        <p className="mt-2 text-sm text-gray-600">
          {appCopy.organizerDialog.description}
        </p>
        <form
          className="mt-4 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit();
          }}
        >
          <label className="block text-sm font-medium text-gray-700" htmlFor="organizer-token">
            {appCopy.organizerDialog.fieldLabel}
            <input
              id="organizer-token"
              type="password"
              value={value}
              onChange={(event) => onChange(event.target.value)}
              disabled={loading}
              placeholder={appCopy.organizerDialog.fieldPlaceholder}
              className="mt-2 block w-full rounded-lg border border-gray-300 bg-white px-3 py-3 text-gray-900 focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-500/20 disabled:bg-gray-100"
            />
          </label>
          {error ? (
            <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {error}
            </div>
          ) : null}
          <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <button
              type="button"
              onClick={onCancel}
              disabled={loading}
              className="inline-flex min-h-11 items-center justify-center rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-semibold text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-60"
            >
              {appCopy.organizerDialog.cancel}
            </button>
            <button
              type="submit"
              disabled={loading || !value.trim()}
              className="inline-flex min-h-11 items-center justify-center rounded-lg bg-amber-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-amber-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500"
            >
              {loading ? appCopy.organizerDialog.submitLoading : appCopy.organizerDialog.submit}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  const view = getViewFromPathname(location.pathname);
  const scoringRouteMatch = matchPath({ path: ROUTE_PATHS.scoring, end: true }, location.pathname);
  const routeSessionId = scoringRouteMatch?.params?.sessionId || null;
  const routeEditToken = new URLSearchParams(location.search).get("edit");

  const playerStats = usePlayerStatsData({ view });
  const players = usePlayersData({
    onPlayerDeleted: () => {},
    refreshPlayerStats: playerStats.loadPlayerStats,
  });
  const planner = usePlannerState({
    directoryPlayers: players.directoryPlayers,
    directoryLoaded: players.directoryLoaded,
    navigateToPlanner: () => navigate(ROUTE_PATHS.planner),
  });
  const sessions = useSessionsData({
    navigate,
    refreshPlayerStats: playerStats.loadPlayerStats,
    view,
  });
  const scoring = useScoringSession({
    location,
    navigate,
    routeEditToken,
    routeSessionId,
    sessionAccess: sessions.sessionAccess,
    rememberSessionAccess: sessions.rememberSessionAccess,
    view,
    refreshSupportingViews: sessions.refreshSupportingViews,
  });

  const appError = scoring.pageError || sessions.pageError || playerStats.pageError || null;

  const sessionLoading = scoring.sessionLoading || sessions.sessionMutationLoading;
  const sessionLoadingLabel = scoring.sessionLoading ? scoring.sessionLoadingLabel : sessions.sessionMutationLabel;
  const timing = useSessionTiming({
    loading: planner.loading,
    sessionLoading,
    sessionsLoading: sessions.sessionsLoading,
  });

  useEffect(() => {
    // Intentional: reset transient UI state whenever the route changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMobileNavOpen(false);
    sessions.clearPageError();
    scoring.clearPageError();
    playerStats.clearPageError();
  }, [location.pathname]);

  function navigateToView(nextView) {
    navigate(getRoutePathForView(nextView));
    setMobileNavOpen(false);
  }

  async function handleOpenSession(sessionId) {
    await scoring.openSession(sessionId, sessions.sessionAccess[sessionId] || null, location.pathname + location.search);
  }

  async function handleDeleteSession(sessionId) {
    const deleted = await sessions.handleDeleteSession(sessionId, scoring.currentSession);
    if (deleted && scoring.currentSession?.sessionId === sessionId) {
      scoring.setCurrentSession(null);
    }
  }

  async function handleRenameSession() {
    const updated = await sessions.handleRenameSession(scoring.currentSession);
    if (updated && scoring.currentSession?.sessionId === updated.sessionId) {
      scoring.setCurrentSession(updated);
    }
  }

  async function handleLockRoster() {
    const startedSession = await sessions.handleLockRoster(planner);
    if (!startedSession) return;

    scoring.setCurrentSession(startedSession);
    planner.resetAfterSessionStart();
    scoring.setPreviousNonScoringPath(ROUTE_PATHS.sessions);
    navigate(buildSessionPath(startedSession.sessionId, startedSession.editToken));
  }

  async function handleOrganizerDialogSubmit() {
    const startedSession = await sessions.handleOrganizerDialogSubmit(planner);
    if (!startedSession) return;

    scoring.setCurrentSession(startedSession);
    planner.resetAfterSessionStart();
    scoring.setPreviousNonScoringPath(ROUTE_PATHS.sessions);
    navigate(buildSessionPath(startedSession.sessionId, startedSession.editToken));
  }

  function handleBackToPlanner() {
    planner.setPlannerStep(planner.roster ? 3 : 1);
    navigate(scoring.getPreviousNonScoringPath());
  }

  const navItems = [
    { key: "planner", label: "Planner", icon: "planner", path: ROUTE_PATHS.planner },
    { key: "players", label: "Players", icon: "players", path: ROUTE_PATHS.players },
    { key: "sessions", label: "Active Sessions", icon: "sessions", path: ROUTE_PATHS.sessions },
    { key: "history", label: "History", icon: "history", path: ROUTE_PATHS.history },
    { key: "player-stats", label: "Player Stats", icon: "stats", path: ROUTE_PATHS.playerStats },
  ];

  const sessionsRoute = {
    ...sessions,
    openSession: handleOpenSession,
    handleDeleteSession,
  };

  // An ?edit= token was supplied for this session, yet the server opened it read-only.
  const invalidEditLink = Boolean(
    routeEditToken &&
      routeSessionId &&
      !scoring.sessionLoading &&
      scoring.currentSession?.sessionId === routeSessionId &&
      !scoring.currentSession.canEdit
  );

  const scoringRoute = {
    ...scoring,
    invalidEditLink,
    handleBackToPlanner,
    openRenameDialog: sessions.openRenameDialog,
  };

  return (
    <AppShell
      view={view}
      currentSessionName={scoring.currentSession?.name || null}
      mobileNavOpen={mobileNavOpen}
      onToggleMobileNav={() => setMobileNavOpen((current) => !current)}
      onCloseMobileNav={() => setMobileNavOpen(false)}
      onNavigate={navigateToView}
      onHome={() => {
        navigate(ROUTE_PATHS.planner);
        planner.setPlannerStep(1);
        sessions.clearPageError();
        scoring.clearPageError();
        playerStats.clearPageError();
        planner.clearPlannerError();
        setMobileNavOpen(false);
      }}
      navItems={navItems}
    >
      {sessionLoading && view === "scoring" ? (
        <div className="fixed inset-x-4 bottom-4 z-50 sm:inset-x-auto sm:right-4 sm:top-20 sm:bottom-auto sm:w-[360px]">
          <div className="rounded-2xl border border-blue-200 bg-blue-50 p-4 shadow-lg">
            <p className="text-sm font-medium text-blue-700">{timing.sessionWaitText(sessionLoadingLabel)}</p>
            {timing.sessionElapsed >= 5 && !PLAIN_SESSION_WAIT_LABELS.has(sessionLoadingLabel) ? (
              <p className="mt-2 text-sm text-blue-600">
                The backend may be waking up. This can take a little longer on cold start.
              </p>
            ) : null}
          </div>
        </div>
      ) : null}

      <OrganizerTokenDialog
        open={sessions.organizerDialogOpen}
        loading={sessionLoading}
        value={sessions.organizerTokenDraft}
        error={sessions.organizerDialogError}
        onChange={(value) => {
          sessions.setOrganizerTokenDraft(value);
          if (sessions.organizerDialogError) {
            sessions.setOrganizerDialogError(null);
          }
        }}
        onCancel={() => {
          if (sessionLoading) return;
          sessions.setOrganizerDialogOpen(false);
          sessions.setOrganizerDialogError(null);
          sessions.setOrganizerTokenDraft(sessions.organizerToken);
        }}
        onSubmit={handleOrganizerDialogSubmit}
      />

      {appError ? (
        <div className="mb-6 rounded-lg border border-red-200 bg-red-50 p-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-red-800">{appCopy.errors.bannerTitle}</p>
              <p className="mt-1 text-sm font-medium text-red-700">{appError}</p>
            </div>
            <button
              type="button"
              onClick={() => {
                sessions.clearPageError();
                scoring.clearPageError();
                playerStats.clearPageError();
              }}
              className="inline-flex min-h-10 items-center justify-center rounded-lg border border-red-200 bg-white px-3 py-2 text-sm font-semibold text-red-700 transition-colors hover:bg-red-50"
            >
              {appCopy.errors.dismiss}
            </button>
          </div>
        </div>
      ) : null}

      {sessionLoading && view !== "scoring" ? (
        <div className="mb-6 rounded-lg border border-blue-200 bg-blue-50 p-4">
          <p className="text-sm font-medium text-blue-700">{timing.sessionWaitText(sessionLoadingLabel)}</p>
          {timing.sessionElapsed >= 5 && !PLAIN_SESSION_WAIT_LABELS.has(sessionLoadingLabel) ? (
            <p className="mt-2 text-sm text-blue-600">The backend may be waking up. This can take a little longer on cold start.</p>
          ) : null}
        </div>
      ) : null}

      <Routes>
        <Route path={ROUTE_PATHS.root} element={<RootRouteRedirect />} />
        <Route
          path={ROUTE_PATHS.planner}
          element={
            <PlannerRoute
              planner={{
                ...planner,
                directoryPlayers: players.directoryPlayers,
              }}
              navigateToView={navigateToView}
              sessionLoading={sessionLoading}
              onLockRoster={handleLockRoster}
              timing={timing}
            />
          }
        />
        <Route path={ROUTE_PATHS.players} element={<PlayersRoute players={players} />} />
        <Route
          path={ROUTE_PATHS.sessions}
          element={
            <ActiveSessionsRoute
              sessions={sessionsRoute}
              sessionWaitText={timing.sessionWaitText}
              currentSessionId={scoring.currentSession?.sessionId || null}
            />
          }
        />
        <Route
          path={ROUTE_PATHS.history}
          element={<HistoryRoute history={sessions} sessions={sessionsRoute} />}
        />
        <Route path={ROUTE_PATHS.playerStats} element={<PlayerStatsRoute playerStats={playerStats} />} />
        <Route path={ROUTE_PATHS.scoring} element={<ScoringRoute scoring={scoringRoute} />} />
        <Route path="*" element={<NotFoundRoute />} />
      </Routes>

      <RenameSessionDialog
        open={sessions.renameDialog.open}
        value={sessions.renameValue}
        loading={sessions.renameLoading}
        error={sessions.renameError}
        onChange={(value) => {
          sessions.setRenameValue(value);
          if (sessions.renameError) {
            sessions.clearRenameError();
          }
        }}
        onCancel={sessions.closeRenameDialog}
        onSubmit={handleRenameSession}
      />
    </AppShell>
  );
}
