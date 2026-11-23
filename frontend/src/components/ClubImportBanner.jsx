import { CLUB_IMPORT_COPY } from "../lib/clubImport";

// Non-blocking notice for a bad or unsupported import link. The planner keeps
// working underneath it.
export default function ClubImportBanner({ error, onDismiss }) {
  if (!error) return null;

  return (
    <div role="status" className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
      <div className="flex items-start justify-between gap-4">
        <p className="text-sm text-amber-800">{error}</p>
        <button
          type="button"
          onClick={onDismiss}
          className="inline-flex min-h-10 shrink-0 items-center justify-center rounded-lg border border-amber-300 bg-white px-3 py-2 text-sm font-semibold text-amber-800 transition-colors hover:bg-amber-100"
        >
          {CLUB_IMPORT_COPY.bannerDismiss}
        </button>
      </div>
    </div>
  );
}
