import PlayerInput from "../components/PlayerInput";
import ConfigPanel from "../components/ConfigPanel";
import RosterTable from "../components/RosterTable";
import DownloadCSV from "../components/DownloadCSV";
import { appCopy } from "../content/uiCopy";

function KnockoutDuplicateDialog({ violations, onDismiss }) {
  if (!violations || violations.length === 0) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
      <div className="w-full max-w-2xl rounded-2xl border border-amber-200 bg-white p-5 shadow-xl">
        <p className="text-sm font-semibold uppercase tracking-wide text-amber-600">
          {appCopy.planner.duplicateDialog.eyebrow}
        </p>
        <h3 className="mt-1 text-lg font-semibold text-gray-900">
          {appCopy.planner.duplicateDialog.title}
        </h3>
        <p className="mt-2 text-sm text-gray-600">
          {appCopy.planner.duplicateDialog.description}
        </p>
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
          {violations.map((violation, index) => (
            <p key={index} className="text-sm text-amber-800">
              {violation}
            </p>
          ))}
        </div>
        <div className="mt-4 flex justify-end">
          <button
            type="button"
            onClick={onDismiss}
            className="inline-flex min-h-11 items-center justify-center rounded-lg bg-amber-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-amber-700"
          >
            {appCopy.planner.duplicateDialog.dismiss}
          </button>
        </div>
      </div>
    </div>
  );
}

function PlannerStepCard({ step, title, description, tone = "default", children }) {
  const tones = {
    default: "border-gray-200 bg-white",
    indigo: "border-indigo-200 bg-indigo-50",
    slate: "border-slate-200 bg-slate-900 text-white",
  };

  const descriptionTone = tone === "slate" ? "text-slate-300" : "text-gray-600";
  const stepTone = tone === "slate" ? "text-slate-300" : "text-gray-500";
  const titleTone = tone === "slate" ? "text-white" : "text-gray-900";

  return (
    <section className={`rounded-2xl border p-5 shadow-sm ${tones[tone]}`}>
      <div className="mb-4">
        <p className={`text-sm font-semibold uppercase tracking-wide ${stepTone}`}>{step}</p>
        <h3 className={`mt-1 text-lg font-semibold ${titleTone}`}>{title}</h3>
        <p className={`mt-2 text-sm ${descriptionTone}`}>{description}</p>
      </div>
      {children}
    </section>
  );
}

function PlannerStepper({ currentStep, onStepChange }) {
  const steps = [
    { id: 1, label: "Players & Pairs" },
    { id: 2, label: "Settings" },
    { id: 3, label: "Review & Start" },
  ];

  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {steps.map((step) => {
        const isActive = currentStep === step.id;
        const isComplete = currentStep > step.id;
        const isClickable = step.id <= currentStep;

        return (
          <button
            key={step.id}
            type="button"
            onClick={() => {
              if (isClickable) onStepChange(step.id);
            }}
            disabled={!isClickable}
            className={`rounded-xl border px-4 py-3 ${
              isActive
                ? "border-indigo-200 bg-indigo-50"
                : isComplete
                  ? "border-emerald-200 bg-emerald-50"
                  : "border-white/15 bg-white/10"
            }`}
          >
            <p className={`text-xs font-semibold uppercase tracking-wide ${isActive || isComplete ? "text-gray-500" : "text-indigo-100"}`}>
              Step {step.id}
            </p>
            <p className={`mt-1 text-sm font-semibold ${isActive || isComplete ? "text-gray-900" : "text-white"}`}>{step.label}</p>
          </button>
        );
      })}
    </div>
  );
}

function BadgeIcon({ kind, className = "h-4 w-4" }) {
  const commonProps = {
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
    case "players":
      return (
        <svg {...commonProps}>
          <path d="M12 12.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" />
          <path d="M5.5 19.5a6.5 6.5 0 0 1 13 0" />
        </svg>
      );
    case "spark":
      return (
        <svg {...commonProps}>
          <path d="m12 3 1.7 4.8L18.5 9.5l-4.8 1.7L12 16l-1.7-4.8L5.5 9.5l4.8-1.7L12 3Z" />
        </svg>
      );
    case "stats":
      return (
        <svg {...commonProps}>
          <path d="M5 18.5h14" />
          <path d="M7.5 16V11.5" />
          <path d="M12 16V8.5" />
          <path d="M16.5 16V6" />
        </svg>
      );
    default:
      return null;
  }
}

export default function PlannerRoute({ planner, navigateToView, sessionLoading, onLockRoster, timing }) {
  const {
    plannerStep,
    setPlannerStep,
    reviewStepRef,
    directoryPlayers,
    selectedPlayerIds,
    setSelectedPlayerIds,
    fixedPairIds,
    setFixedPairIds,
    config,
    setConfig,
    selectedPlayerShortNames,
    fixedPairs,
    canContinueFromPlayers,
    canContinueFromSettings,
    configIssue,
    loading,
    roster,
    generateError,
    plannerError,
    isRosterStale,
    hasManualRosterEdits,
    sessionDraftName,
    setSessionDraftName,
    handleGenerate,
    selectedRosterTarget,
    selectedEditSummary,
    duplicateKnockoutViolations,
    clearRosterSelection,
    dismissDuplicateKnockoutViolations,
    rosterEditLoading,
    handleRosterPlayerTap,
    handleRosterTeamTap,
    handleRosterRoundTap,
  } = planner;

  return (
    <div className="space-y-8">
      <KnockoutDuplicateDialog
        violations={duplicateKnockoutViolations}
        onDismiss={dismissDuplicateKnockoutViolations}
      />

      <section className="rounded-2xl border border-indigo-100 bg-gradient-to-r from-indigo-600 via-indigo-500 to-sky-500 p-5 text-white shadow-sm sm:p-6">
        <div className="flex flex-col gap-5">
          <div>
            <p className="text-sm font-medium text-indigo-100">{appCopy.planner.eyebrow}</p>
            <h2 className="mt-1 text-2xl font-bold">{appCopy.planner.title}</h2>
            <p className="mt-2 max-w-3xl text-sm text-indigo-50">{appCopy.planner.description}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <span className="inline-flex items-center rounded-full border border-white/20 bg-white/10 px-3 py-1 text-xs font-semibold text-white">
              <BadgeIcon kind="players" className="mr-1.5 h-3.5 w-3.5" />
              {appCopy.planner.badges[0]}
            </span>
            <span className="inline-flex items-center rounded-full border border-white/20 bg-white/10 px-3 py-1 text-xs font-semibold text-white">
              <BadgeIcon kind="spark" className="mr-1.5 h-3.5 w-3.5" />
              {appCopy.planner.badges[1]}
            </span>
            <span className="inline-flex items-center rounded-full border border-white/20 bg-white/10 px-3 py-1 text-xs font-semibold text-white">
              <BadgeIcon kind="stats" className="mr-1.5 h-3.5 w-3.5" />
              {appCopy.planner.badges[2]}
            </span>
          </div>
        </div>
      </section>

      <div className="space-y-6">
        <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm">
          <PlannerStepper currentStep={plannerStep} onStepChange={setPlannerStep} />
        </section>

        {plannerStep === 1 ? (
          <PlannerStepCard
            step="Step 1"
            title="Players and pairs"
            description="Select players from the directory and set any fixed pairs before moving on."
          >
            <div className="space-y-6">
              <PlayerInput
                availablePlayers={directoryPlayers}
                selectedPlayerIds={selectedPlayerIds}
                setSelectedPlayerIds={setSelectedPlayerIds}
                fixedPairIds={fixedPairIds}
                setFixedPairIds={setFixedPairIds}
                onOpenPlayerManagement={() => navigateToView("players")}
              />
              <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
                <button
                  type="button"
                  onClick={() => navigateToView("sessions")}
                  className="inline-flex min-h-11 items-center justify-center rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-semibold text-gray-700 transition-colors hover:bg-gray-50"
                >
                  Go to Active Sessions
                </button>
                <button
                  type="button"
                  onClick={() => setPlannerStep(2)}
                  disabled={!canContinueFromPlayers}
                  className="inline-flex min-h-11 items-center justify-center rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500"
                >
                  Next: Settings
                </button>
              </div>
            </div>
          </PlannerStepCard>
        ) : null}

        {plannerStep === 2 ? (
          <PlannerStepCard
            step="Step 2"
            title="Settings"
            description="Choose the format and scheduling settings for this roster."
          >
            <div className="space-y-6">
              <ConfigPanel
                config={config}
                setConfig={setConfig}
                players={selectedPlayerShortNames}
                fixedPairs={fixedPairs}
              />
              <div className="flex flex-col gap-3 sm:flex-row sm:justify-between">
                <button
                  type="button"
                  onClick={() => setPlannerStep(1)}
                  className="inline-flex min-h-11 items-center justify-center rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-semibold text-gray-700 transition-colors hover:bg-gray-50"
                >
                  Back
                </button>
                <button
                  type="button"
                  onClick={() => setPlannerStep(3)}
                  disabled={!canContinueFromSettings}
                  className="inline-flex min-h-11 items-center justify-center rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500"
                >
                  Next: Review
                </button>
              </div>
            </div>
          </PlannerStepCard>
        ) : null}

        {plannerStep === 3 ? (
          <div ref={reviewStepRef} className="space-y-4">
            <PlannerStepCard
              step="Step 3"
              title="Review and start"
              description="Generate the roster, review the rounds, then start the session."
              tone={roster ? "slate" : "default"}
            >
              {loading ? (
                <div className="py-8 text-center">
                  <svg className="mx-auto mb-4 h-12 w-12 animate-spin text-indigo-500" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  <p className={`${roster ? "text-slate-200" : "text-gray-700"} font-medium`}>{timing.loadingText()}</p>
                  {timing.elapsed >= 5 ? (
                    <p className={`mt-2 text-sm ${roster ? "text-slate-400" : "text-gray-400"}`}>
                      First request may take up to 30s while the server wakes up
                    </p>
                  ) : null}
                </div>
              ) : (
                <div className="space-y-4">
                  {generateError ? (
                    <div className={`rounded-xl border px-4 py-3 text-sm ${
                      roster ? "border-rose-300 bg-rose-50 text-rose-700" : "border-rose-200 bg-rose-50 text-rose-700"
                    }`}>
                      <p className="font-semibold">{appCopy.planner.errors.generateTitle}</p>
                      <p className="mt-1">{generateError}</p>
                    </div>
                  ) : null}
                  {plannerError ? (
                    <div className={`rounded-xl border px-4 py-3 text-sm ${
                      roster ? "border-rose-300 bg-rose-50 text-rose-700" : "border-rose-200 bg-rose-50 text-rose-700"
                    }`}>
                      <p className="font-semibold">{appCopy.planner.errors.actionTitle}</p>
                      <p className="mt-1">{plannerError}</p>
                    </div>
                  ) : null}
                  {configIssue ? (
                    <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                      {configIssue}
                    </div>
                  ) : null}
                  {isRosterStale ? (
                    <div className={`rounded-xl border px-4 py-3 text-sm ${
                      roster ? "border-amber-300 bg-amber-50 text-amber-800" : "border-amber-200 bg-amber-50 text-amber-800"
                    }`}>
                      <p className="font-semibold">Roster is out of date</p>
                      <p className="mt-1">
                        Players, pairs, or settings changed after the last generation. Regenerate the roster before starting a session.
                      </p>
                    </div>
                  ) : null}
                  {roster && hasManualRosterEdits && !isRosterStale ? (
                    <div className="rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm text-indigo-800">
                      <p className="font-semibold">{appCopy.planner.editedBadge}</p>
                      <p className="mt-1">{appCopy.planner.editedHint}</p>
                    </div>
                  ) : null}
                  <p className={`text-sm ${roster ? "text-slate-300" : "text-gray-600"}`}>
                    {roster
                      ? isRosterStale
                        ? "The roster preview below is from older inputs and needs to be regenerated."
                        : "The latest generated roster is ready to review below."
                      : "Generate a roster to preview the rounds and courts here."}
                  </p>
                  {roster ? (
                    <label className={`block text-sm font-medium ${roster ? "text-slate-100" : "text-gray-700"}`} htmlFor="session-draft-name">
                      Session name
                      <input
                        id="session-draft-name"
                        type="text"
                        value={sessionDraftName}
                        onChange={(event) => setSessionDraftName(event.target.value)}
                        maxLength={120}
                        className={`mt-2 block w-full rounded-lg border px-3 py-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 ${
                          roster
                            ? "border-slate-500/50 bg-slate-950/40 text-white placeholder:text-slate-400"
                            : "border-gray-300 bg-white text-gray-900"
                        }`}
                      />
                    </label>
                  ) : null}
                  <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
                    <button
                      type="button"
                      onClick={handleGenerate}
                      disabled={loading || selectedPlayerIds.length < 4 || Boolean(configIssue)}
                      className="inline-flex min-h-11 items-center justify-center rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500"
                    >
                      {roster ? (isRosterStale ? "Regenerate Updated Roster" : "Regenerate Roster") : "Generate Roster"}
                    </button>
                    {roster ? <DownloadCSV data={roster} /> : null}
                    <button
                      type="button"
                      onClick={onLockRoster}
                      disabled={!roster || isRosterStale || sessionLoading}
                      className="inline-flex min-h-11 items-center justify-center rounded-lg bg-white px-4 py-2.5 text-sm font-semibold text-slate-900 transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-500"
                    >
                      {sessionLoading ? "Creating Session..." : isRosterStale ? "Regenerate To Start" : "Start Session"}
                    </button>
                  </div>
                  <div className="flex">
                    <button
                      type="button"
                      onClick={() => setPlannerStep(2)}
                      className={`inline-flex min-h-11 items-center justify-center rounded-lg border px-4 py-2.5 text-sm font-semibold transition-colors ${
                        roster
                          ? "border-slate-500/40 bg-transparent text-white hover:bg-white/10"
                          : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
                      }`}
                    >
                      Back
                    </button>
                  </div>
                </div>
              )}
            </PlannerStepCard>

            {roster ? (
              <RosterTable
                data={roster}
                fixedPairs={fixedPairs}
                editable={!isRosterStale}
                editMode={selectedRosterTarget?.mode || null}
                selectedTarget={selectedRosterTarget}
                editTitle={appCopy.planner.editBannerTitle}
                editSummary={
                  selectedRosterTarget
                    ? appCopy.planner.selectionPrefix.replace("{item}", selectedEditSummary)
                    : appCopy.planner.selectionIdle
                }
                editHint={selectedRosterTarget ? appCopy.planner.selectionHints[selectedRosterTarget.mode] : null}
                cancelSelectionLabel={appCopy.planner.cancelSelection}
                onCancelSelection={clearRosterSelection}
                editLoading={rosterEditLoading}
                onTapPlayer={handleRosterPlayerTap}
                onTapTeam={handleRosterTeamTap}
                onTapRound={handleRosterRoundTap}
              />
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
