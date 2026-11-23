import { useId } from "react";
import ModalDialog from "./ModalDialog";
import { CLUB_IMPORT_COPY } from "../lib/clubImport";

function ImportRow({ row, onAddToDirectory }) {
  const inDirectory = row.status === "matched" || row.added;

  return (
    <li className="flex flex-col gap-3 rounded-xl border border-gray-200 bg-white p-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold text-gray-900">{row.name}</p>
        <p className="mt-0.5 text-xs text-gray-500">
          {row.shortName}
          {row.guest ? (
            <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 font-semibold text-amber-800">
              {CLUB_IMPORT_COPY.guest}
            </span>
          ) : null}
        </p>
      </div>
      <div className="flex flex-col items-start gap-1 sm:items-end">
        {inDirectory ? (
          <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
            {CLUB_IMPORT_COPY.inDirectory}
          </span>
        ) : (
          <button
            type="button"
            onClick={() => onAddToDirectory(row)}
            disabled={row.adding}
            className="inline-flex min-h-10 items-center justify-center rounded-lg border border-cyan-300 bg-cyan-50 px-3 py-2 text-sm font-semibold text-cyan-800 transition-colors hover:bg-cyan-100 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {row.adding ? CLUB_IMPORT_COPY.adding : CLUB_IMPORT_COPY.addToDirectory}
          </button>
        )}
        {row.addError ? (
          <p role="alert" className="text-xs text-rose-700">
            {row.addError}
          </p>
        ) : null}
      </div>
    </li>
  );
}

export default function ClubImportSheet({
  sheetOpen,
  sheetEvent,
  rows,
  directoryLoaded,
  closeSheet,
  importSelection,
  addToDirectory,
}) {
  const headingId = useId();
  const matchedCount = rows.filter((row) => row.status === "matched").length;

  return (
    <ModalDialog open={sheetOpen} onClose={closeSheet} labelledBy={headingId} className="max-w-2xl">
      <p className="text-sm font-semibold uppercase tracking-wide text-indigo-600">{CLUB_IMPORT_COPY.sheetEyebrow}</p>
      <h3 id={headingId} className="mt-1 text-lg font-semibold text-gray-900">
        {CLUB_IMPORT_COPY.sheetTitle}
      </h3>
      {sheetEvent?.title ? <p className="mt-1 text-sm font-medium text-gray-800">{sheetEvent.title}</p> : null}
      <p className="mt-2 text-sm text-gray-600">{CLUB_IMPORT_COPY.sheetDescription}</p>

      {!directoryLoaded ? (
        <p className="mt-4 text-sm text-gray-500">{CLUB_IMPORT_COPY.directoryLoading}</p>
      ) : (
        <>
          <p className="mt-4 text-xs font-semibold uppercase tracking-wide text-gray-500">
            {matchedCount} of {rows.length} matched
          </p>
          <ul className="mt-2 max-h-[50vh] space-y-2 overflow-y-auto pr-1">
            {rows.map((row) => (
              <ImportRow key={row.index} row={row} onAddToDirectory={addToDirectory} />
            ))}
          </ul>
        </>
      )}

      <div className="mt-5 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
        <button
          type="button"
          onClick={closeSheet}
          className="inline-flex min-h-11 items-center justify-center rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-semibold text-gray-700 transition-colors hover:bg-gray-50"
        >
          {CLUB_IMPORT_COPY.close}
        </button>
        <button
          type="button"
          onClick={importSelection}
          disabled={!directoryLoaded || rows.length === 0}
          className="inline-flex min-h-11 items-center justify-center rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500"
        >
          {CLUB_IMPORT_COPY.importPlayers}
        </button>
      </div>
    </ModalDialog>
  );
}
