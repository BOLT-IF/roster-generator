// roster-import/v1: club event → roster deep link. Contract: bolt-club-hq
// docs/PLAN.md §8.1 and contracts/roster-import-v1/README.md.
//
// The payload lives in the URL fragment (`#import=<base64url(JSON)>`), so it is
// never sent to the server. Nothing here writes data; the organizer must act.

export const CLUB_IMPORT_FRAGMENT_KEY = "import";
export const CLUB_IMPORT_VERSION = 1;
export const CLUB_IMPORT_PATH = "/planner";
export const CLUB_IMPORT_MAX_FRAGMENT_LENGTH = 8192;
export const CLUB_IMPORT_MAX_PLAYERS = 200;
export const CLUB_IMPORT_MAX_NAME_LENGTH = 120;

export const CLUB_IMPORT_COPY = {
  sheetEyebrow: "Club event",
  sheetTitle: "Import from club event",
  sheetDescription:
    "Players found in your directory are selected. Players not in the directory can be added with one tap. Guests are labelled.",
  directoryLoading: "Loading your directory before matching players...",
  inDirectory: "In directory",
  notInDirectory: "Not in directory",
  guest: "Guest",
  addToDirectory: "Add to directory",
  adding: "Adding...",
  addFailed: "Could not add this player to the directory. Check the name and try again.",
  close: "Close",
  importPlayers: "Import players",
  replaceConfirm:
    "Importing replaces the players and pairs in your current unsaved planner draft. Continue?",
  bannerDismiss: "Dismiss",
  errors: {
    malformed:
      "We couldn't read this import link. Check that you copied the whole link, or ask the organizer to send it again.",
    unsupportedVersion:
      "This import link needs a newer version of the roster app. Your planner still works as usual.",
    tooLarge:
      "This import link is too large to import. Ask the organizer for a shorter list, or add players by hand.",
  },
};

// Read the raw fragment value for `import` without throwing. Returns null when
// the URL has no import fragment.
export function readImportFragment(hash) {
  if (typeof hash !== "string") return null;
  const trimmed = hash.startsWith("#") ? hash.slice(1) : hash;
  if (!trimmed) return null;
  const params = new URLSearchParams(trimmed);
  if (!params.has(CLUB_IMPORT_FRAGMENT_KEY)) return null;
  return params.get(CLUB_IMPORT_FRAGMENT_KEY);
}

// Returns the fragment without the import key, or "" when nothing is left.
export function stripImportFragment(hash) {
  const trimmed = typeof hash === "string" && hash.startsWith("#") ? hash.slice(1) : hash || "";
  const params = new URLSearchParams(trimmed);
  params.delete(CLUB_IMPORT_FRAGMENT_KEY);
  return params.toString();
}

function decodeBase64Url(value) {
  if (!/^[A-Za-z0-9_-]+$/.test(value)) return null;
  try {
    const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
    const binary = atob(padded);
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    return null;
  }
}

// Returns the trimmed string, undefined when absent, or null when the value is
// present but unusable (wrong type, empty when required, or too long).
function cleanName(value, { required }) {
  if (value === undefined || value === null) return required ? null : undefined;
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!trimmed) return required ? null : undefined;
  if (trimmed.length > CLUB_IMPORT_MAX_NAME_LENGTH) return null;
  return trimmed;
}

// Decode and validate. Returns { ok: true, payload } or { ok: false, reason }
// where reason is "malformed" | "unsupportedVersion" | "tooLarge".
export function decodeClubImport(rawFragment) {
  if (typeof rawFragment !== "string" || rawFragment.length === 0) {
    return { ok: false, reason: "malformed" };
  }
  if (rawFragment.length > CLUB_IMPORT_MAX_FRAGMENT_LENGTH) {
    return { ok: false, reason: "tooLarge" };
  }

  const json = decodeBase64Url(rawFragment);
  if (json === null) return { ok: false, reason: "malformed" };

  let data;
  try {
    data = JSON.parse(json);
  } catch {
    return { ok: false, reason: "malformed" };
  }
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    return { ok: false, reason: "malformed" };
  }

  // Version is checked first so a future shape still gets the friendly
  // "newer version" message rather than a generic failure.
  if (data.v !== CLUB_IMPORT_VERSION) {
    return { ok: false, reason: "unsupportedVersion" };
  }

  if (!Array.isArray(data.players)) return { ok: false, reason: "malformed" };
  if (data.players.length > CLUB_IMPORT_MAX_PLAYERS) return { ok: false, reason: "tooLarge" };

  const players = [];
  for (const entry of data.players) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
      return { ok: false, reason: "malformed" };
    }
    const name = cleanName(entry.name, { required: true });
    const short = cleanName(entry.short, { required: false });
    if (name === null || short === null) return { ok: false, reason: "malformed" };
    players.push({ name, short: short || null, guest: entry.guest === true });
  }

  const event = data.event && typeof data.event === "object" && !Array.isArray(data.event) ? data.event : {};
  return {
    ok: true,
    payload: {
      v: CLUB_IMPORT_VERSION,
      source: typeof data.source === "string" ? data.source : null,
      event: {
        title: cleanName(event.title, { required: false }) || null,
        startsAt: typeof event.starts_at === "string" ? event.starts_at : null,
        format: typeof event.format === "string" ? event.format : null,
      },
      players,
    },
  };
}

// The current path and query with the import fragment removed. Used with
// history.replaceState so a reload does not import again.
export function getLocationWithoutImport(location) {
  const rest = stripImportFragment(location.hash);
  return `${location.pathname}${location.search}${rest ? `#${rest}` : ""}`;
}

// Reads the import link from a location. Returns null when the page has no
// import, otherwise { payload, error } with error set to a user-facing message.
export function readClubImportFromLocation(location) {
  if (!location || location.pathname.replace(/\/+$/, "") !== CLUB_IMPORT_PATH) return null;
  const raw = readImportFragment(location.hash);
  if (raw === null) return null;

  const result = decodeClubImport(raw);
  if (result.ok) return { payload: result.payload, error: null };
  return { payload: null, error: CLUB_IMPORT_COPY.errors[result.reason] };
}

// Short name the directory is matched on: the link's `short`, or the first word
// of the full name when `short` is missing.
export function getImportShortName(player) {
  if (player.short) return player.short;
  return player.name.split(/\s+/)[0];
}

// Match each imported player to the directory. Short name is tried first, then
// full name, both case-insensitively. Each row has `match` (the directory
// player or null) and `status`: "matched" | "unmatched".
export function matchImportedPlayers(players, directory) {
  const byShort = new Map();
  const byFull = new Map();
  for (const player of directory) {
    const shortKey = String(player.shortName || "").trim().toLowerCase();
    const fullKey = String(player.fullName || "").trim().toLowerCase();
    if (shortKey && !byShort.has(shortKey)) byShort.set(shortKey, player);
    if (fullKey && !byFull.has(fullKey)) byFull.set(fullKey, player);
  }

  return players.map((player, index) => {
    const shortName = getImportShortName(player);
    const match = byShort.get(shortName.toLowerCase()) || byFull.get(player.name.toLowerCase()) || null;
    return { index, ...player, shortName, match, status: match ? "matched" : "unmatched" };
  });
}
