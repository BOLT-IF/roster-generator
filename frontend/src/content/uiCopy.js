export const appCopy = {
  brand: {
    eyebrow: "Organiser",
    title: "Badminton Session Planner",
  },
  errors: {
    bannerTitle: "Something went wrong",
    dismiss: "Dismiss",
  },
  renameDialog: {
    eyebrow: "Rename Session",
    title: "Update the session name",
    fieldLabel: "Session name",
    requiredError: "Session name is required.",
    cancel: "Cancel",
    submit: "Save Name",
    submitLoading: "Saving...",
  },
  planner: {
    eyebrow: "Planner",
    title: "Build the next session from scratch",
    description:
      "Add players, configure the format, generate the roster, and start a new session.",
    editBannerTitle: "Roster edits",
    editedBadge: "Edited roster",
    editedHint: "Manual swaps are active in this preview. Regenerating will discard them and start fresh.",
    selectionIdle: "Tap a player, team, or round to edit.",
    swapLoading: "Applying swap...",
    cancelSelection: "Cancel selection",
    selectionPrefix: "Selected {item}.",
    playerSwapInvalid: "Pick another player in the same round to swap.",
    teamSwapInvalid: "Pick another team in the same round to swap.",
    roundSwapInvalid: "Pick another round to swap.",
    errors: {
      generateTitle: "Roster could not be generated",
      actionTitle: "Roster edit issue",
    },
    selectionHints: {
      player: "Select another player in the same round or tap the same player again to cancel.",
      team: "Select another team in the same round or tap the same team again to cancel.",
      round: "Select another round or tap the same round again to cancel.",
    },
    regenerateConfirm: "Regenerating will discard all manual roster swaps and rebuild from the current planner inputs. Continue?",
    duplicateDialog: {
      eyebrow: "Knockout Schedule Warning",
      title: "Some fixed pairs are scheduled against the same opponent more than once",
      description:
        "The roster is still shown below so you can repair it manually before starting the session.",
      dismiss: "Review Roster",
    },
    badges: [
      "Player-first setup",
      "Fast roster generation",
      "History-aware sessions",
    ],
  },
  organizerDialog: {
    eyebrow: "Organizer Check",
    title: "Enter organizer token to start a session",
    description:
      "This is a temporary safeguard until login exists. The token is remembered on this device so organizers do not need to re-enter it every time.",
    fieldLabel: "Organizer token",
    fieldPlaceholder: "Enter Password",
    cancel: "Cancel",
    submit: "Start Session",
    submitLoading: "Checking...",
  },
  sessions: {
    feedback: {
      copied: "Copied",
      failed: "Failed",
    },
  },
};

export const activeSessionsPageCopy = {
  hero: {
    eyebrow: "Active Sessions",
    title: "Resume, share, and manage ongoing sessions",
    description:
      "Completed sessions move to History once results are locked in.",
  },
  section: {
    eyebrow: "Ongoing Work",
    title: "Sessions that are ready or in progress",
    description: "Existing sessions.",
    refresh: "Refresh Sessions",
    accessScorer: "Scorer access available on this device",
    accessViewOnly: "View-only link available",
    updatedPrefix: "Updated",
    openScorer: "Open Scorer View",
    openView: "Open View Link",
    copyView: "Copy View",
    copyScorer: "Copy Scorer",
    rename: "Rename",
    delete: "Delete",
    emptyTitle: "No active sessions right now",
    emptyDescription: "Create one from the Planner when you are ready to score.",
  },
};

export const playerInputCopy = {
  sessionPlayers: {
    title: "Session Players",
    description:
      "Pick players from the registry for this session. Using the directory avoids typos and keeps names consistent.",
    countSuffix: "selected",
    manage: "Manage Players",
    emptyTitle: "No session players yet",
    emptyDescription: "Add players from the directory to start building this session roster.",
    pairPromptPrefix: "Select a partner for",
    pairPromptSuffix: "or tap the same player again to cancel.",
    pairedWith: "paired with",
    remove: "Remove",
  },
  directory: {
    title: "Player Directory",
    description: "Search by full name, short name, or player ID.",
    countSuffix: "total",
    searchPlaceholder: "Search players...",
    add: "Add",
    noMatchTitle: "No players match this search",
    noMatchDescription: "Try a different name, short name, or player ID.",
    emptyTitle: "No players in the directory yet",
    emptyDescription: "Create players first, then come back here to build a session.",
  },
  fixedPairs: {
    title: "Fixed Pairs",
    description: "Current locked partnerships for this session.",
    countSuffix: "pairs",
  },
};

export const playersPageCopy = {
  errors: {
    directoryTitle: "Could not refresh players",
    createTitle: "Could not create player",
    editTitle: "Could not update player",
    deleteTitle: "Could not delete player",
  },
  hero: {
    eyebrow: "Players",
    title: "Build a clean player directory once",
    description:
      "Register full names and short names here, then reuse them in Planner without retyping.",
    },
  addPlayer: {
    eyebrow: "Add Player",
    title: "Player details",
    description: "Full name is for the directory. Short name is what shows up in the roster and scoring flow.",
    fullName: "Full Name",
    fullNamePlaceholder: "Arijit Mukherjee",
    shortName: "Short Name",
    shortNamePlaceholder: "Arijit",
    submit: "Create Player",
  },
  editPlayer: {
    eyebrow: "Edit Player",
    title: "Update player details",
    description:
      "This keeps the player ID stable while updating how the player appears in Planner, scoring, and the directory.",
    submit: "Save Changes",
    submitLoading: "Saving...",
  },
  directory: {
    eyebrow: "Directory",
    title: "Registered players",
    description:
      "Registered Players in the club.",
    searchPlaceholder: "Search players...",
    refresh: "Refresh Players",
    refreshLoading: "Refreshing...",
    noMatchTitle: "No players match this search",
    noMatchDescription: "Try a full name, short name, alias, or player ID.",
    emptyTitle: "No players yet",
    emptyDescription: "Add the first player from the form on the left, then they will appear here for quick management.",
    aliasesPrefix: "Also matched from older names:",
    edit: "Edit",
    delete: "Delete",
  },
  deletePlayer: {
    eyebrow: "Delete Player",
    title: "This action is intentionally strict",
    descriptionLead: "You are deleting",
    descriptionMiddle: "from the player directory.",
    descriptionOne: "This hides the player from Planner and Player Management. Existing sessions are not removed automatically.",
    descriptionTwo:
      "If you also tick the historical option below, player analytics records will be deleted as well. Use that only if you truly want to remove the player from historical stats.",
    tokenLabel: "Admin token",
    tokenPlaceholder: "Enter Password to confirm",
    deleteHistory: "Also delete historical player records",
    cancel: "Cancel",
    submit: "Delete Player",
    submitLoading: "Deleting...",
  },
};

export const historyPageCopy = {
  hero: {
    eyebrow: "History",
    title: "Completed sessions and final results",
    description:
      "Finished sessions. Open any result to review the final tables and bracket, or delete it if you still have scorer access.",
  },
  section: {
    eyebrow: "Completed Sessions",
    title: "Historical results",
    refresh: "Refresh History",
    refreshLoading: "Refreshing...",
    completed: "Completed",
    open: "Open Results",
    delete: "Delete",
    championPrefix: "Champion:",
    emptyTitle: "No completed sessions yet",
    emptyDescription:
      "Once a session is fully finished, it will appear here automatically with its final results.",
  },
};

export const playerStatsPageCopy = {
  hero: {
    eyebrow: "Player Stats",
    title: "League and knockout performance in one place",
    description:
      "Browse all-time player results from completed sessions, with a simpler summary of activity, titles, and strongest partnerships.",
  },
  leaderboard: {
    eyebrow: "Players",
    title: "Leaderboard",
    refresh: "Refresh",
    refreshLoading: "Refreshing...",
    sessionsSuffix: "sessions",
    matchesSuffix: "matches",
    titlesSuffix: "titles",
    emptyTitle: "No player stats yet",
    emptyDescription:
      "Complete some sessions first, then player performance will appear here automatically.",
  },
  profile: {
    eyebrow: "Profile",
    lastSessionPrefix: "Last completed session:",
    noSessions: "No completed sessions yet",
    loading: "Loading player details...",
    backToList: "Back to leaderboard",
    emptyTitle: "Select a player",
    emptyDescription: "Choose someone from the leaderboard to view their league and knockout performance.",
  },
  metrics: {
    sessions: "Sessions",
    matches: "Matches",
    winsSuffix: "wins",
    winRate: "Win Rate",
    championships: "Championships",
  },
  partners: {
    eyebrow: "Top Partners",
    titlePrefix: "Best-performing partners for",
    mostPlayedLabel: "Most-played partner",
    mostPlayedDescription: "The teammate they've played with most often.",
    matchesTogetherSuffix: "matches together",
    winsSuffix: "wins",
    winRateSuffix: "win rate",
    emptyTitle: "No ranked partners yet",
    emptyDescription:
      "Once enough completed matches are available, the strongest partnerships will show up here.",
  },
};

export const scoringCopy = {
  invalidEditLink: "This edit link is not valid, so the session opened in view-only mode. Ask the organiser for a fresh scorer link.",
  startNextRound: "Start Next Round",
};

// "Session {name}" would read "Session Session Night" when the name already starts
// with the word, so only add the prefix when it is missing.
export function formatSessionPill(name) {
  const trimmed = String(name ?? "").trim();
  if (/^session\b/i.test(trimmed)) return trimmed;
  return `Session ${trimmed}`;
}
