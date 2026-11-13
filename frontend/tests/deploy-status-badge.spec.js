import { expect, test } from "@playwright/test";

// The header badge answers "is the latest code deployed?" at a glance:
// green when the running build matches main, amber naming the gap when
// behind, gray when unknown (local dev / GitHub unreachable).

const UP_TO_DATE = {
  deployed_sha: "a1b2c3d4e5f60000000000000000000000000000",
  latest_main_sha: "a1b2c3d4e5f60000000000000000000000000000",
  latest_main_at: "2026-11-13T08:00:00Z",
  ahead_by: 0,
  status: "up_to_date",
};

const BEHIND = {
  deployed_sha: "a1b2c3d4e5f60000000000000000000000000000",
  latest_main_sha: "f00dcafe00000000000000000000000000000000",
  latest_main_at: "2026-11-13T09:00:00Z",
  ahead_by: 3,
  status: "behind",
};

test("header shows a green deployed badge when the running build matches main", async ({ page }) => {
  await page.route("**/api/deploy-info", (route) =>
    route.fulfill({ json: UP_TO_DATE })
  );
  await page.goto("/");
  const badge = page.getByTestId("deploy-status");
  await expect(badge).toBeVisible();
  await expect(badge).toContainText("Deployed");
  await expect(badge).toContainText("a1b2c3d");
});

test("header shows an amber behind badge naming the commit gap", async ({ page }) => {
  await page.route("**/api/deploy-info", (route) =>
    route.fulfill({ json: BEHIND })
  );
  await page.goto("/");
  const badge = page.getByTestId("deploy-status");
  await expect(badge).toBeVisible();
  await expect(badge).toContainText("Behind 3");
  await expect(badge).toContainText("a1b2c3d");
  // Hover detail names both ends of the comparison.
  await expect(badge).toHaveAttribute(
    "title",
    /a1b2c3d4e5f60000000000000000000000000000/
  );
});

test("badge stays quiet when deploy info is unavailable", async ({ page }) => {
  await page.route("**/api/deploy-info", (route) =>
    route.fulfill({ status: 503, body: "unavailable" })
  );
  await page.goto("/");
  await expect(page.getByTestId("deploy-status")).toHaveCount(0);
});
