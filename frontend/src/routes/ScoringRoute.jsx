import { Link, useParams } from "react-router-dom";
import ScoringPage from "../components/ScoringPage";
import { ROUTE_PATHS } from "../hooks/appStateUtils";

function SessionNotFound({ message }) {
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-8 text-center shadow-sm">
      <h2 className="text-xl font-semibold text-gray-900">Session not found</h2>
      <p className="mt-2 text-sm text-gray-600">
        {message || "This session does not exist or is no longer available."}
      </p>
      <Link
        to={ROUTE_PATHS.sessions}
        className="mt-5 inline-flex min-h-11 items-center justify-center rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-700"
      >
        Back to Active Sessions
      </Link>
    </div>
  );
}

export default function ScoringRoute({ scoring }) {
  const { sessionId: routeSessionId } = useParams();
  const currentSession = scoring.currentSession;
  const loadError = scoring.sessionLoadError;
  if (!currentSession && loadError && loadError.sessionId === routeSessionId) {
    return <SessionNotFound message={loadError.message} />;
  }
  if (!currentSession) return null;

  return (
    <ScoringPage
      key={currentSession.sessionId || "scoring-session"}
      roster={currentSession.roster}
      drawConfig={currentSession.drawConfig}
      sessionName={currentSession.name}
      canEdit={currentSession.canEdit}
      invalidEditLink={scoring.invalidEditLink}
      leagueScoresByRound={currentSession.leagueScoresByRound}
      activeLeagueRound={currentSession.activeLeagueRound}
      endedLeagueRounds={currentSession.endedLeagueRounds}
      knockoutScoresByRound={currentSession.knockoutScoresByRound}
      activeKnockoutRound={currentSession.activeKnockoutRound}
      endedKnockoutRounds={currentSession.endedKnockoutRounds}
      onBack={scoring.handleBackToPlanner}
      onEditRound={scoring.handleEditRound}
      onStartRound={scoring.handleStartRound}
      onEndRound={scoring.handleEndRound}
      onScoreChange={scoring.handleScoreChange}
      onScoreCommit={scoring.handleScoreCommit}
      pendingRoundAction={scoring.pendingRoundAction}
      onRenameSession={() => scoring.openRenameDialog(currentSession.sessionId, currentSession.name)}
    />
  );
}
