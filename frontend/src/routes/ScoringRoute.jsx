import ScoringPage from "../components/ScoringPage";

export default function ScoringRoute({ scoring }) {
  const currentSession = scoring.currentSession;
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
