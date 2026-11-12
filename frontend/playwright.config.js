import { defineConfig, devices } from "@playwright/test";

const frontendBaseURL = process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:4174";
const apiBaseURL = process.env.PLAYWRIGHT_API_BASE_URL || "http://127.0.0.1:8010";
const runAgainstRemote = process.env.PLAYWRIGHT_REMOTE === "1";

export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  workers: 1,
  use: {
    baseURL: frontendBaseURL,
    trace: "on-first-retry",
  },
  webServer: runAgainstRemote
    ? undefined
    : [
        {
          command:
            "rm -f /tmp/badminton-roster-rename-e2e.db && PLAYWRIGHT_TEST_MODE=1 DATABASE_URL=sqlite:////tmp/badminton-roster-rename-e2e.db ADMIN_RECOVERY_TOKEN=thisismytoken CACHE_ENABLED=false ../backend/venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8010",
          cwd: "../backend",
          url: `${apiBaseURL}/docs`,
          reuseExistingServer: false,
        },
        {
          command: `VITE_API_URL=${apiBaseURL} npm run build && npx vite preview --host 127.0.0.1 --port 4174 --strictPort`,
          cwd: ".",
          url: frontendBaseURL,
          reuseExistingServer: false,
        },
      ],
  projects: [
    {
      name: "desktop",
      use: {},
    },
    {
      name: "iphone",
      use: {
        ...devices["iPhone 13"],
      },
    },
    {
      name: "android",
      use: {
        ...devices["Pixel 7"],
      },
    },
  ],
});
