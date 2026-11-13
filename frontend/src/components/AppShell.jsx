import { useEffect, useState } from "react";
import { appCopy } from "../content/uiCopy";
import { fetchDeployInfo } from "../api";

function shortSha(sha) {
  return sha ? sha.slice(0, 7) : "?";
}

function DeployStatusBadge({ info }) {
  if (!info || !info.deployed_sha) return null;

  const title = [
    `deployed ${info.deployed_sha}`,
    info.latest_main_sha ? `main ${info.latest_main_sha}` : null,
    info.latest_main_at ? `main at ${new Date(info.latest_main_at).toLocaleString()}` : null,
  ]
    .filter(Boolean)
    .join(" \u00b7 ");

  const upToDate = info.status === "up_to_date";
  const behind = info.status === "behind" && typeof info.ahead_by === "number";

  const styles = upToDate
    ? "border-green-200 bg-green-50 text-green-700"
    : behind
      ? "border-amber-300 bg-amber-50 text-amber-800"
      : "border-gray-200 bg-gray-50 text-gray-500";

  return (
    <span
      data-testid="deploy-status"
      title={title}
      className={`inline-flex min-h-8 items-center rounded-full border px-3 py-1 text-xs font-semibold ${styles}`}
    >
      <span
        aria-hidden="true"
        className={`mr-1.5 h-2 w-2 rounded-full ${
          upToDate ? "bg-green-500" : behind ? "bg-amber-500" : "bg-gray-400"
        }`}
      />
      {upToDate
        ? `Deployed \u00b7 ${shortSha(info.deployed_sha)}`
        : behind
          ? `Behind ${info.ahead_by} \u00b7 ${shortSha(info.deployed_sha)}`
          : info.status === "behind"
            ? `Behind \u00b7 ${shortSha(info.deployed_sha)}`
            : `Deploy status unknown \u00b7 ${shortSha(info.deployed_sha)}`}
    </span>
  );
}

function BrandIcon({ className = "h-10 w-10" }) {
  return (
    <svg viewBox="0 0 48 48" fill="none" aria-hidden="true" className={className}>
      <defs>
        <linearGradient id="brand-gradient" x1="8" y1="8" x2="40" y2="40" gradientUnits="userSpaceOnUse">
          <stop stopColor="#4F46E5" />
          <stop offset="0.55" stopColor="#0EA5E9" />
          <stop offset="1" stopColor="#14B8A6" />
        </linearGradient>
      </defs>
      <rect x="4" y="4" width="40" height="40" rx="14" fill="url(#brand-gradient)" />
      <path d="M24 11.5 17.5 19 24 22.2 30.5 19 24 11.5Z" fill="white" fillOpacity="0.96" />
      <path d="M24 23.8 15 20.1 18.1 31.5 24 37l5.9-5.5L33 20.1l-9 3.7Z" fill="white" fillOpacity="0.92" />
      <path d="M20.8 27.4 18.7 33.1M24 26.9V37M27.2 27.4l2.1 5.7" stroke="#4F46E5" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function NavIcon({ kind, className = "h-4 w-4" }) {
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
    case "planner":
      return (
        <svg {...commonProps}>
          <path d="M4.5 6.5h15" />
          <path d="M4.5 12h15" />
          <path d="M4.5 17.5h9" />
          <path d="M18 16.8 19.8 18.6 16.5 21H14.7v-1.8L18 16.8Z" />
        </svg>
      );
    case "players":
      return (
        <svg {...commonProps}>
          <path d="M12 12.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" />
          <path d="M5.5 19.5a6.5 6.5 0 0 1 13 0" />
        </svg>
      );
    case "sessions":
      return (
        <svg {...commonProps}>
          <rect x="4.5" y="5.5" width="15" height="13" rx="2.5" />
          <path d="M8 3.8v3.4M16 3.8v3.4M4.5 10h15" />
        </svg>
      );
    case "history":
      return (
        <svg {...commonProps}>
          <path d="M12 6v6l4 2.2" />
          <path d="M4.8 11a7.2 7.2 0 1 1 2.1 6" />
          <path d="M4.5 6.5v4.8h4.8" />
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

function MenuIcon({ open, className = "h-5 w-5" }) {
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

  return open ? (
    <svg {...props}>
      <path d="M6 6 18 18" />
      <path d="m18 6-12 12" />
    </svg>
  ) : (
    <svg {...props}>
      <path d="M4.5 7h15" />
      <path d="M4.5 12h15" />
      <path d="M4.5 17h15" />
    </svg>
  );
}

export default function AppShell({
  view,
  currentSessionName,
  mobileNavOpen,
  onToggleMobileNav,
  onCloseMobileNav,
  onNavigate,
  onHome,
  navItems,
  children,
}) {
  const [deployInfo, setDeployInfo] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetchDeployInfo()
      .then((info) => {
        if (!cancelled) setDeployInfo(info);
      })
      .catch(() => {
        // No badge rather than a broken one.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="sticky top-0 z-40 border-b border-gray-200 bg-white/95 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between gap-3">
            <button type="button" onClick={onHome} className="flex min-w-0 items-center gap-3 text-left">
              <BrandIcon className="h-11 w-11 shrink-0" />
              <div className="min-w-0">
                <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-indigo-500">{appCopy.brand.eyebrow}</p>
                <h1 className="truncate text-lg font-bold text-gray-900 sm:text-xl">{appCopy.brand.title}</h1>
                {view === "scoring" && currentSessionName ? (
                  <p className="truncate text-xs font-medium text-gray-500 md:hidden">{currentSessionName}</p>
                ) : null}
              </div>
            </button>

            <div className="flex items-center gap-2">
              <DeployStatusBadge info={deployInfo} />
              <button
                type="button"
                onClick={onToggleMobileNav}
                aria-expanded={mobileNavOpen}
                aria-controls="mobile-global-nav"
                aria-label="Open navigation"
                className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-xl border border-gray-300 bg-white text-gray-700 shadow-sm transition-colors hover:bg-gray-50 md:hidden"
              >
                <MenuIcon open={mobileNavOpen} />
              </button>
            </div>
          </div>

          <nav className="mt-4 hidden flex-wrap gap-2 md:flex">
            {navItems.map((item) => {
              const isActive = view === item.key;
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => onNavigate(item.key)}
                  className={`inline-flex min-h-10 items-center justify-center rounded-full px-4 py-2 text-sm font-semibold transition-colors ${
                    isActive
                      ? "bg-indigo-600 text-white"
                      : "border border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
                  }`}
                >
                  <NavIcon kind={item.icon} className="mr-2 h-4 w-4" />
                  {item.label}
                </button>
              );
            })}
          </nav>

        </div>
      </header>

      {/* Rendered outside <header>: its backdrop-blur makes it the containing block for
          fixed descendants, which clipped the backdrop to the header's own box. */}
      {mobileNavOpen ? (
        <div className="md:hidden">
          {/* z-30 keeps the header (z-40) and its menu toggle reachable above the backdrop. */}
          <div className="fixed inset-0 z-30 bg-slate-900/35" onClick={onCloseMobileNav} aria-hidden="true" />
          <nav
            id="mobile-global-nav"
            className="fixed inset-x-4 top-[6.5rem] z-50 rounded-3xl border border-gray-200 bg-white p-3 shadow-2xl"
          >
            <p className="px-3 pb-2 text-xs font-semibold uppercase tracking-[0.24em] text-gray-400">Navigate</p>
            <div className="grid gap-2">
              {navItems.map((item) => {
                const isActive = view === item.key;
                return (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => onNavigate(item.key)}
                    className={`flex min-h-12 items-center rounded-2xl px-4 py-3 text-left text-sm font-semibold transition-colors ${
                      isActive
                        ? "bg-indigo-600 text-white"
                        : "bg-gray-50 text-gray-700 hover:bg-gray-100"
                    }`}
                  >
                    <NavIcon kind={item.icon} className="mr-3 h-4 w-4" />
                    {item.label}
                  </button>
                );
              })}
            </div>
          </nav>
        </div>
      ) : null}

      <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>
    </div>
  );
}
