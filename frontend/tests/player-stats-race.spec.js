import { expect, test } from "@playwright/test";
import { navigateToSection } from "./helpers/navigation";
import { completeRoundRobinSession } from "./helpers/session";

test("rapid player A then B selection never shows A's profile under B (M-25)", async ({ page, request }, testInfo) => {
  await completeRoundRobinSession(request, `Stats Race ${testInfo.project.name}`);

  await page.goto("/");
  await navigateToSection(page, "Player Stats");
  await expect(page.getByRole("heading", { name: "Leaderboard" })).toBeVisible();

  // A's detail is slow; B's is fast. A therefore resolves AFTER B.
  let releaseA;
  const gateA = new Promise((resolve) => {
    releaseA = resolve;
  });
  let aRequested = false;
  let aFulfilled = false;
  await page.route("**/api/stats/players/A", async (route) => {
    aRequested = true;
    await gateA;
    await route.continue().catch(() => {});
    aFulfilled = true;
  });

  await page.getByRole("button", { name: /^A\b/ }).click();
  await expect.poll(() => aRequested).toBe(true);
  // On narrow viewports the profile replaces the leaderboard, so go back first.
  const backButton = page.getByRole("button", { name: "Back to leaderboard" });
  if (await backButton.isVisible()) {
    await backButton.click();
  }
  await page.getByRole("button", { name: /^B\b/ }).click();

  const heading = (name) => page.getByRole("heading", { name, exact: true });
  await expect(heading("B")).toBeVisible();

  // Let A's stale response land, then confirm B is still what is shown.
  releaseA();
  await expect.poll(() => aFulfilled).toBe(true);
  await page.waitForTimeout(400);

  await expect(heading("B")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Best-performing partners for B" })).toBeVisible();
  await expect(heading("A")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Best-performing partners for A" })).toHaveCount(0);
});
