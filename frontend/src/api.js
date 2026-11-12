const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// FastAPI returns `detail` as a string for HTTPException but as an array of
// {loc, msg, ...} objects for request-validation (422) errors. Flatten either
// shape into one readable line so no page ever renders "[object Object]".
export function formatApiErrorDetail(detail, fallback) {
  if (typeof detail === "string") return detail.trim() || fallback;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (!item || typeof item !== "object") return "";
        const msg = typeof item.msg === "string" ? item.msg : typeof item.message === "string" ? item.message : "";
        const loc = Array.isArray(item.loc)
          ? item.loc.filter((part) => part !== "body" && part !== "query" && part !== "path").join(".")
          : "";
        if (!msg) return "";
        return loc ? `${loc}: ${msg}` : msg;
      })
      .filter(Boolean);
    return parts.length > 0 ? parts.join("; ") : fallback;
  }
  if (detail && typeof detail === "object") {
    if (typeof detail.msg === "string") return detail.msg;
    if (typeof detail.message === "string") return detail.message;
  }
  return fallback;
}

async function buildApiError(res) {
  const body = await res.json().catch(() => ({ detail: "Server error" }));
  const error = new Error(formatApiErrorDetail(body?.detail, `HTTP ${res.status}`));
  error.status = res.status;
  return error;
}

function withEditToken(path, editToken) {
  if (!editToken) return `${API_BASE}${path}`;

  const url = new URL(`${API_BASE}${path}`);
  url.searchParams.set("edit_token", editToken);
  return url.toString();
}

export async function generateRoster(payload) {
  const res = await fetch(`${API_BASE}/api/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw await buildApiError(res);
  }

  return res.json();
}

export async function revalidateRoster(payload) {
  const res = await fetch(`${API_BASE}/api/rosters/revalidate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw await buildApiError(res);
  }

  return res.json();
}

async function readJson(res) {
  if (!res.ok) {
    throw await buildApiError(res);
  }

  return res.json();
}

export async function createSharedSession(payload) {
  const res = await fetch(`${API_BASE}/api/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  return readJson(res);
}

export async function fetchSharedSession(sessionId, editToken, { signal } = {}) {
  const res = await fetch(withEditToken(`/api/sessions/${sessionId}`, editToken), { signal });
  return readJson(res);
}

export async function listSharedSessions() {
  const res = await fetch(`${API_BASE}/api/sessions`);
  return readJson(res);
}

export async function deleteSharedSession(sessionId, editToken) {
  const res = await fetch(withEditToken(`/api/sessions/${sessionId}`, editToken), {
    method: "DELETE",
  });

  if (!res.ok) {
    throw await buildApiError(res);
  }
}

export async function renameSharedSession(sessionId, payload, editToken) {
  const res = await fetch(withEditToken(`/api/sessions/${sessionId}/rename`, editToken), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  return readJson(res);
}

export async function startSharedRound(sessionId, payload, editToken) {
  const res = await fetch(withEditToken(`/api/sessions/${sessionId}/start-round`, editToken), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  return readJson(res);
}

export async function endSharedRound(sessionId, payload, editToken) {
  const res = await fetch(withEditToken(`/api/sessions/${sessionId}/end-round`, editToken), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  return readJson(res);
}

export async function editSharedRound(sessionId, payload, editToken) {
  const res = await fetch(withEditToken(`/api/sessions/${sessionId}/edit-round`, editToken), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  return readJson(res);
}

export async function updateSharedScore(sessionId, payload, editToken) {
  const res = await fetch(withEditToken(`/api/sessions/${sessionId}/score`, editToken), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  return readJson(res);
}

export async function batchUpdateSharedScores(sessionId, payload, editToken) {
  const res = await fetch(withEditToken(`/api/sessions/${sessionId}/scores/batch`, editToken), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  return readJson(res);
}

export async function listCompletedSessions() {
  const res = await fetch(`${API_BASE}/api/history/sessions`);
  return readJson(res);
}

export async function listPlayers() {
  const res = await fetch(`${API_BASE}/api/players`);
  return readJson(res);
}

export async function createPlayer(payload) {
  const res = await fetch(`${API_BASE}/api/players`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  return readJson(res);
}

export async function updatePlayer(playerId, payload) {
  const res = await fetch(`${API_BASE}/api/players/${encodeURIComponent(playerId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  return readJson(res);
}

export async function deletePlayer(playerId, payload) {
  const res = await fetch(`${API_BASE}/api/players/${encodeURIComponent(playerId)}/delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw await buildApiError(res);
  }
}

export async function listPlayerStats() {
  const res = await fetch(`${API_BASE}/api/stats/players`);
  return readJson(res);
}

export async function fetchPlayerStats(playerName) {
  const res = await fetch(`${API_BASE}/api/stats/players/${encodeURIComponent(playerName)}`);
  return readJson(res);
}
