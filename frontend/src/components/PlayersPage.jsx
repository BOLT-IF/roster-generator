import { useId, useState } from "react";
import ModalDialog from "./ModalDialog";
import { playersPageCopy } from "../content/uiCopy";

function PlayersIcon({ kind, className = "h-5 w-5" }) {
  const props = {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "1.8",
    strokeLinecap: "round",
    strokeLinejoin: "round",
    className,
    "aria-hidden": true,
  };

  switch (kind) {
    case "add":
      return (
        <svg {...props}>
          <path d="M12 12.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" />
          <path d="M5.5 19.5a6.5 6.5 0 0 1 8.2-6.2" />
          <path d="M18 11v6M15 14h6" />
        </svg>
      );
    case "directory":
      return (
        <svg {...props}>
          <rect x="4.5" y="4.5" width="15" height="15" rx="2.5" />
          <path d="M8 8h8M8 12h8M8 16h5" />
        </svg>
      );
    default:
      return null;
  }
}

function EmptyState({ title, description }) {
  return (
    <div className="rounded-2xl border border-dashed border-gray-300 bg-gray-50 p-6 text-center">
      <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-white text-cyan-600 shadow-sm">
        <PlayersIcon kind="directory" />
      </div>
      <p className="mt-4 text-sm font-semibold text-gray-900">{title}</p>
      <p className="mt-2 text-sm text-gray-500">{description}</p>
    </div>
  );
}

function PlayerEditorFields({ draft, setDraft }) {
  return (
    <>
      <label className="block text-sm font-medium text-gray-700">
        {playersPageCopy.addPlayer.fullName}
        <input
          type="text"
          value={draft.fullName}
          onChange={(event) => setDraft((current) => ({ ...current, fullName: event.target.value }))}
          placeholder={playersPageCopy.addPlayer.fullNamePlaceholder}
          className="mt-2 block w-full rounded-xl border border-gray-300 px-3 py-3 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-cyan-500"
        />
      </label>

      <label className="block text-sm font-medium text-gray-700">
        {playersPageCopy.addPlayer.shortName}
        <input
          type="text"
          value={draft.shortName}
          onChange={(event) => setDraft((current) => ({ ...current, shortName: event.target.value }))}
          placeholder={playersPageCopy.addPlayer.shortNamePlaceholder}
          className="mt-2 block w-full rounded-xl border border-gray-300 px-3 py-3 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-cyan-500"
        />
      </label>
    </>
  );
}

function PlayerEditor({ title, submitLabel, draft, setDraft, loading, error, onSubmit, onCancel }) {
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-gray-500">{title}</p>
        <div className="mt-1 flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-50 text-cyan-600">
            <PlayersIcon kind="add" />
          </span>
          <h3 className="text-lg font-semibold text-gray-900">{playersPageCopy.addPlayer.title}</h3>
        </div>
        <p className="mt-2 text-sm text-gray-600">
          {playersPageCopy.addPlayer.description}
        </p>
      </div>

      <form
        className="mt-5 space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <PlayerEditorFields draft={draft} setDraft={setDraft} />

        {error ? (
          <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            <p className="font-semibold">{title === playersPageCopy.addPlayer.eyebrow ? playersPageCopy.errors.createTitle : playersPageCopy.errors.editTitle}</p>
            <p className="mt-1">{error}</p>
          </div>
        ) : null}

        <div className="flex flex-col gap-3 sm:flex-row">
          <button
            type="submit"
            disabled={loading || !draft.fullName.trim() || !draft.shortName.trim()}
            className="inline-flex min-h-11 flex-1 items-center justify-center rounded-xl bg-cyan-600 px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-cyan-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500"
          >
            {loading ? `${submitLabel}...` : submitLabel}
          </button>
          {onCancel ? (
            <button
              type="button"
              onClick={onCancel}
              disabled={loading}
              className="inline-flex min-h-11 items-center justify-center rounded-xl border border-gray-300 bg-white px-4 py-3 text-sm font-semibold text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-60"
            >
              Cancel
            </button>
          ) : null}
        </div>
      </form>
    </div>
  );
}

function EditPlayerDialog({ player, open, loading, error, draft, setDraft, onCancel, onConfirm }) {
  const headingId = useId();

  return (
    <ModalDialog
      open={Boolean(open && player)}
      onClose={onCancel}
      labelledBy={headingId}
      className="max-w-lg border-cyan-200"
    >
      <p className="text-sm font-semibold uppercase tracking-wide text-cyan-600">{playersPageCopy.editPlayer.eyebrow}</p>
      <h3 id={headingId} className="mt-1 text-xl font-semibold text-gray-900">{playersPageCopy.editPlayer.title}</h3>
      <p className="mt-2 text-sm text-gray-600">
        {playersPageCopy.editPlayer.description}
      </p>

      <form
          className="mt-5 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            onConfirm();
          }}
        >
          <PlayerEditorFields draft={draft} setDraft={setDraft} />

          {error ? (
            <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              <p className="font-semibold">{playersPageCopy.errors.editTitle}</p>
              <p className="mt-1">{error}</p>
            </div>
          ) : null}

          <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            <button
              type="button"
              onClick={onCancel}
              disabled={loading}
              className="inline-flex min-h-11 items-center justify-center rounded-xl border border-gray-300 bg-white px-4 py-3 text-sm font-semibold text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-60"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !draft.fullName.trim() || !draft.shortName.trim()}
              className="inline-flex min-h-11 items-center justify-center rounded-xl bg-cyan-600 px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-cyan-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500"
            >
              {loading ? playersPageCopy.editPlayer.submitLoading : playersPageCopy.editPlayer.submit}
            </button>
          </div>
        </form>
    </ModalDialog>
  );
}

function DeletePlayerDialog({
  player,
  open,
  loading,
  error,
  draft,
  setDraft,
  onCancel,
  onConfirm,
}) {
  const headingId = useId();
  const dialogOpen = Boolean(open && player);

  return (
    <ModalDialog
      open={dialogOpen}
      onClose={onCancel}
      labelledBy={headingId}
      className="max-w-lg border-rose-200"
    >
      {dialogOpen && player ? (
        <>
          <p className="text-sm font-semibold uppercase tracking-wide text-rose-600">{playersPageCopy.deletePlayer.eyebrow}</p>
          <h3 id={headingId} className="mt-1 text-xl font-semibold text-gray-900">{playersPageCopy.deletePlayer.title}</h3>
          <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
          <p className="font-semibold">
            {playersPageCopy.deletePlayer.descriptionLead} <span className="font-bold">{player.full_name}</span> {playersPageCopy.deletePlayer.descriptionMiddle}
          </p>
          <p className="mt-2">
            {playersPageCopy.deletePlayer.descriptionOne}
          </p>
          <p className="mt-2">
            {playersPageCopy.deletePlayer.descriptionTwo}
          </p>
        </div>

        <div className="mt-5 space-y-4">
          <label className="block text-sm font-medium text-gray-700">
            {playersPageCopy.deletePlayer.tokenLabel}
            <input
              type="password"
              value={draft.adminToken}
              onChange={(event) => setDraft((current) => ({ ...current, adminToken: event.target.value }))}
              placeholder={playersPageCopy.deletePlayer.tokenPlaceholder}
              className="mt-2 block w-full rounded-xl border border-gray-300 px-3 py-3 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-rose-500"
            />
          </label>

          <label className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            <input
              type="checkbox"
              checked={draft.deleteHistory}
              onChange={(event) => setDraft((current) => ({ ...current, deleteHistory: event.target.checked }))}
              className="mt-1 h-4 w-4 rounded border-amber-300 text-amber-600 focus:ring-amber-500"
            />
            <span>
              {playersPageCopy.deletePlayer.deleteHistory}
            </span>
          </label>

          {error ? (
            <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              <p className="font-semibold">{playersPageCopy.errors.deleteTitle}</p>
              <p className="mt-1">{error}</p>
            </div>
          ) : null}
        </div>

        <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onCancel}
            disabled={loading}
            className="inline-flex min-h-11 items-center justify-center rounded-xl border border-gray-300 bg-white px-4 py-3 text-sm font-semibold text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-60"
          >
            {playersPageCopy.deletePlayer.cancel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading || !draft.adminToken.trim()}
            className="inline-flex min-h-11 items-center justify-center rounded-xl bg-rose-600 px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-rose-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500"
          >
            {loading ? playersPageCopy.deletePlayer.submitLoading : playersPageCopy.deletePlayer.submit}
          </button>
        </div>
        </>
      ) : null}
    </ModalDialog>
  );
}

export default function PlayersPage({
  players,
  loading,
  directoryError,
  createLoading,
  createError,
  updateLoading,
  updateError,
  deleteLoading,
  deleteError,
  onRefresh,
  onClearDirectoryError,
  onCreatePlayer,
  onClearCreateError,
  onUpdatePlayer,
  onClearUpdateError,
  onDeletePlayer,
  onClearDeleteError,
}) {
  const [draft, setDraft] = useState({ fullName: "", shortName: "" });
  const [searchQuery, setSearchQuery] = useState("");
  const [editingPlayerId, setEditingPlayerId] = useState(null);
  const [editDraft, setEditDraft] = useState({ fullName: "", shortName: "" });
  const [deletingPlayer, setDeletingPlayer] = useState(null);
  const [deleteDraft, setDeleteDraft] = useState({ adminToken: "", deleteHistory: false });
  const normalizedSearch = searchQuery.trim().toLowerCase();
  const filteredPlayers = players.filter((player) => {
    const haystack = [
      player.full_name,
      player.short_name,
      player.player_id,
      player.source,
      ...(Array.isArray(player.aliases) ? player.aliases : []),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(normalizedSearch);
  });

  function submitCreate() {
    if (!draft.fullName.trim() || !draft.shortName.trim()) return;
    onCreatePlayer({
      full_name: draft.fullName.trim(),
      short_name: draft.shortName.trim(),
    }).then((created) => {
      if (created) {
        setDraft({ fullName: "", shortName: "" });
      }
    });
  }

  function beginEdit(player) {
    onClearUpdateError?.();
    setEditingPlayerId(player.player_id);
    setEditDraft({
      fullName: player.full_name,
      shortName: player.short_name,
    });
  }

  function submitEdit() {
    if (!editingPlayerId || !editDraft.fullName.trim() || !editDraft.shortName.trim()) return;
    onUpdatePlayer(editingPlayerId, {
      full_name: editDraft.fullName.trim(),
      short_name: editDraft.shortName.trim(),
    }).then((updated) => {
      if (updated) {
        setEditingPlayerId(null);
        setEditDraft({ fullName: "", shortName: "" });
      }
    });
  }

  function submitDelete() {
    if (!deletingPlayer || !deleteDraft.adminToken.trim()) return;
    onDeletePlayer(deletingPlayer.player_id, {
      admin_token: deleteDraft.adminToken.trim(),
      delete_history: deleteDraft.deleteHistory,
    }).then((deleted) => {
      if (deleted) {
        setDeletingPlayer(null);
        setDeleteDraft({ adminToken: "", deleteHistory: false });
      }
    });
  }

  return (
    <div className="space-y-8">
      <section className="rounded-2xl border border-cyan-100 bg-gradient-to-r from-cyan-600 via-sky-500 to-indigo-500 p-5 text-white shadow-sm sm:p-6">
        <p className="text-sm font-medium text-cyan-50">{playersPageCopy.hero.eyebrow}</p>
        <h2 className="mt-1 text-2xl font-bold">{playersPageCopy.hero.title}</h2>
        <p className="mt-2 max-w-3xl text-sm text-sky-50">
          {playersPageCopy.hero.description}
        </p>
      </section>

      <div className="grid gap-6 xl:grid-cols-[420px_minmax(0,1fr)]">
        <div className="space-y-6">
          <PlayerEditor
            title={playersPageCopy.addPlayer.eyebrow}
            submitLabel={playersPageCopy.addPlayer.submit}
            draft={draft}
            setDraft={(updater) => {
              onClearCreateError?.();
              setDraft(updater);
            }}
            loading={createLoading}
            error={createError}
            onSubmit={submitCreate}
          />
        </div>

        <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-sm font-semibold uppercase tracking-wide text-gray-500">{playersPageCopy.directory.eyebrow}</p>
              <div className="mt-1 flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-50 text-cyan-600">
                  <PlayersIcon kind="directory" />
                </span>
                <h3 className="text-lg font-semibold text-gray-900">{playersPageCopy.directory.title}</h3>
              </div>
              <p className="mt-2 text-sm text-gray-600">
                {playersPageCopy.directory.description}
              </p>
            </div>
            <button
              type="button"
              onClick={onRefresh}
              disabled={loading}
              className="inline-flex min-h-11 items-center justify-center rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-semibold text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-60"
            >
              {loading ? playersPageCopy.directory.refreshLoading : playersPageCopy.directory.refresh}
            </button>
          </div>

          <div className="mt-5 space-y-3 border-t border-gray-100 pt-4">
            {directoryError ? (
              <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                <p className="font-semibold">{playersPageCopy.errors.directoryTitle}</p>
                <p className="mt-1">{directoryError}</p>
              </div>
            ) : null}
            <input
              type="search"
              value={searchQuery}
              onChange={(event) => {
                onClearDirectoryError?.();
                setSearchQuery(event.target.value);
              }}
              placeholder={playersPageCopy.directory.searchPlaceholder}
              className="w-full rounded-xl border border-gray-300 px-4 py-3 text-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-cyan-500"
            />
            {filteredPlayers.length > 0 ? (
              filteredPlayers.map((player) => (
                <div key={player.player_id} className="rounded-2xl border border-gray-200 bg-gray-50 p-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-gray-900">{player.full_name}</p>
                      <div className="mt-2 flex flex-wrap gap-2 text-xs text-gray-500">
                        <span className="rounded-full bg-white px-2 py-1 font-medium text-gray-700">
                          {player.short_name}
                        </span>
                        <span className="rounded-full bg-gray-200 px-2 py-1">{player.player_id}</span>
                        <span className="rounded-full bg-gray-200 px-2 py-1 capitalize">{player.source}</span>
                      </div>
                      {player.aliases?.length > 0 ? (
                        <p className="mt-3 text-xs text-gray-500">
                          {playersPageCopy.directory.aliasesPrefix} {player.aliases.join(", ")}
                        </p>
                      ) : null}
                    </div>
                    <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                      <button
                        type="button"
                        onClick={() => beginEdit(player)}
                        className="inline-flex min-h-10 items-center justify-center rounded-lg border border-cyan-200 bg-cyan-50 px-3 py-2 text-sm font-semibold text-cyan-700 transition-colors hover:bg-cyan-100"
                      >
                        {playersPageCopy.directory.edit}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          onClearDeleteError?.();
                          setDeletingPlayer(player);
                          setDeleteDraft({ adminToken: "", deleteHistory: false });
                        }}
                        className="inline-flex min-h-10 items-center justify-center rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm font-semibold text-rose-700 transition-colors hover:bg-rose-100"
                      >
                        {playersPageCopy.directory.delete}
                      </button>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <EmptyState
                title={players.length > 0 ? playersPageCopy.directory.noMatchTitle : playersPageCopy.directory.emptyTitle}
                description={
                  players.length > 0
                    ? playersPageCopy.directory.noMatchDescription
                    : playersPageCopy.directory.emptyDescription
                }
              />
            )}
          </div>
        </section>
      </div>

      <EditPlayerDialog
        player={players.find((player) => player.player_id === editingPlayerId) ?? null}
        open={Boolean(editingPlayerId)}
        loading={updateLoading}
        error={editingPlayerId ? updateError : null}
        draft={editDraft}
        setDraft={(updater) => {
          onClearUpdateError?.();
          setEditDraft(updater);
        }}
        onCancel={() => {
          if (updateLoading) return;
          onClearUpdateError?.();
          setEditingPlayerId(null);
          setEditDraft({ fullName: "", shortName: "" });
        }}
        onConfirm={submitEdit}
      />

      <DeletePlayerDialog
        player={deletingPlayer}
        open={Boolean(deletingPlayer)}
        loading={deleteLoading}
        error={deletingPlayer ? deleteError : null}
        draft={deleteDraft}
        setDraft={(updater) => {
          onClearDeleteError?.();
          setDeleteDraft(updater);
        }}
        onCancel={() => {
          if (deleteLoading) return;
          onClearDeleteError?.();
          setDeletingPlayer(null);
          setDeleteDraft({ adminToken: "", deleteHistory: false });
        }}
        onConfirm={submitDelete}
      />
    </div>
  );
}
