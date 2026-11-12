import { useEffect, useState } from "react";
import { createPlayer, deletePlayer, listPlayers, updatePlayer } from "../api";
import { normalizePlayerDirectoryEntry } from "./appStateUtils";

export default function usePlayersData({ onPlayerDeleted, refreshPlayerStats }) {
  const [directoryPlayers, setDirectoryPlayers] = useState([]);
  const [directoryLoaded, setDirectoryLoaded] = useState(false);
  const [playersLoading, setPlayersLoading] = useState(false);
  const [createPlayerLoading, setCreatePlayerLoading] = useState(false);
  const [updatePlayerLoading, setUpdatePlayerLoading] = useState(false);
  const [deletePlayerLoading, setDeletePlayerLoading] = useState(false);
  const [directoryError, setDirectoryError] = useState(null);
  const [createPlayerError, setCreatePlayerError] = useState(null);
  const [updatePlayerError, setUpdatePlayerError] = useState(null);
  const [deletePlayerError, setDeletePlayerError] = useState(null);

  useEffect(() => {
    void loadPlayers();
  }, []);

  async function loadPlayers() {
    setPlayersLoading(true);
    setDirectoryError(null);
    try {
      const list = await listPlayers();
      setDirectoryPlayers(list.map(normalizePlayerDirectoryEntry).filter(Boolean));
      setDirectoryLoaded(true);
    } catch (error) {
      setDirectoryError(error.message);
    } finally {
      setPlayersLoading(false);
    }
  }

  async function handleCreatePlayer(payload) {
    setCreatePlayerLoading(true);
    setCreatePlayerError(null);
    try {
      const created = await createPlayer(payload);
      const normalized = normalizePlayerDirectoryEntry(created);
      setDirectoryPlayers((current) =>
        [...current.filter((player) => player.playerId !== normalized.playerId), normalized]
          .sort((firstPlayer, secondPlayer) => firstPlayer.fullName.localeCompare(secondPlayer.fullName))
      );
      void loadPlayers();
      void refreshPlayerStats();
      return normalized;
    } catch (error) {
      setCreatePlayerError(error.message);
      return null;
    } finally {
      setCreatePlayerLoading(false);
    }
  }

  async function handleUpdatePlayer(playerId, payload) {
    setUpdatePlayerLoading(true);
    setUpdatePlayerError(null);
    try {
      const updated = await updatePlayer(playerId, payload);
      const normalized = normalizePlayerDirectoryEntry(updated);
      setDirectoryPlayers((current) =>
        current
          .map((player) => (player.playerId === playerId ? normalized : player))
          .sort((firstPlayer, secondPlayer) => firstPlayer.fullName.localeCompare(secondPlayer.fullName))
      );
      void refreshPlayerStats();
      return normalized;
    } catch (error) {
      setUpdatePlayerError(error.message);
      return null;
    } finally {
      setUpdatePlayerLoading(false);
    }
  }

  async function handleDeletePlayer(playerId, payload) {
    setDeletePlayerLoading(true);
    setDeletePlayerError(null);
    try {
      await deletePlayer(playerId, payload);
      setDirectoryPlayers((current) => current.filter((player) => player.playerId !== playerId));
      onPlayerDeleted(playerId);
      void loadPlayers();
      void refreshPlayerStats();
      return true;
    } catch (error) {
      setDeletePlayerError(error.message);
      return false;
    } finally {
      setDeletePlayerLoading(false);
    }
  }

  function clearDirectoryError() {
    setDirectoryError(null);
  }

  function clearCreatePlayerError() {
    setCreatePlayerError(null);
  }

  function clearUpdatePlayerError() {
    setUpdatePlayerError(null);
  }

  function clearDeletePlayerError() {
    setDeletePlayerError(null);
  }

  return {
    directoryPlayers,
    directoryLoaded,
    playersLoading,
    createPlayerLoading,
    updatePlayerLoading,
    deletePlayerLoading,
    directoryError,
    createPlayerError,
    updatePlayerError,
    deletePlayerError,
    loadPlayers,
    handleCreatePlayer,
    handleUpdatePlayer,
    handleDeletePlayer,
    clearDirectoryError,
    clearCreatePlayerError,
    clearUpdatePlayerError,
    clearDeletePlayerError,
  };
}
