import { useEffect, useRef, useState } from "react";
import { fetchPlayerStats, listPlayerStats } from "../api";
import { normalizePlayerDetail, normalizePlayerSummary } from "./appStateUtils";

export default function usePlayerStatsData({ view }) {
  const [playerStats, setPlayerStats] = useState([]);
  const [playerStatsLoading, setPlayerStatsLoading] = useState(false);
  const [selectedPlayer, setSelectedPlayer] = useState(null);
  const [playerStatsDetail, setPlayerStatsDetail] = useState(null);
  const [playerStatsDetailLoading, setPlayerStatsDetailLoading] = useState(false);
  const [pageError, setPageError] = useState(null);
  // Monotonic id of the latest detail request; older completions are ignored.
  const detailRequestIdRef = useRef(0);

  useEffect(() => {
    if (view === "player-stats") {
      void loadPlayerStats();
    }
  }, [view]);

  useEffect(() => {
    if (playerStats.length === 0) {
      if (selectedPlayer) {
        setSelectedPlayer(null);
      }
      if (playerStatsDetail) {
        setPlayerStatsDetail(null);
      }
      return;
    }

    if (selectedPlayer && !playerStats.some((player) => player.playerName === selectedPlayer)) {
      setSelectedPlayer(null);
    }
  }, [playerStats, playerStatsDetail, selectedPlayer]);

  useEffect(() => {
    // Selection changed: drop the previous player's profile right away and
    // invalidate any request still in flight for it.
    detailRequestIdRef.current += 1;
    setPlayerStatsDetail(null);
    if (view !== "player-stats" || !selectedPlayer) {
      setPlayerStatsDetailLoading(false);
      return;
    }
    void loadPlayerStatsDetail(selectedPlayer, detailRequestIdRef.current);
  }, [selectedPlayer, view]);  // eslint-disable-line react-hooks/exhaustive-deps

  async function loadPlayerStats() {
    setPlayerStatsLoading(true);
    setPageError(null);
    try {
      const list = await listPlayerStats();
      setPlayerStats(list.map(normalizePlayerSummary).filter(Boolean));
    } catch (error) {
      setPageError(error.message);
    } finally {
      setPlayerStatsLoading(false);
    }
  }

  async function loadPlayerStatsDetail(playerName, requestId) {
    setPlayerStatsDetailLoading(true);
    setPageError(null);
    try {
      const detail = await fetchPlayerStats(playerName);
      if (requestId !== detailRequestIdRef.current) return;
      setPlayerStatsDetail(normalizePlayerDetail(detail));
    } catch (error) {
      if (requestId !== detailRequestIdRef.current) return;
      setPageError(error.message);
    } finally {
      if (requestId === detailRequestIdRef.current) {
        setPlayerStatsDetailLoading(false);
      }
    }
  }

  function clearPageError() {
    setPageError(null);
  }

  return {
    playerStats,
    playerStatsLoading,
    selectedPlayer,
    setSelectedPlayer,
    playerStatsDetail,
    playerStatsDetailLoading,
    pageError,
    loadPlayerStats,
    clearPageError,
  };
}
