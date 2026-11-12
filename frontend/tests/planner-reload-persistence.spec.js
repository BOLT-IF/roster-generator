import { expect, test } from "@playwright/test";
import { createPlayer } from "./helpers/session";

test("reloading the planner preserves selections, pairs, limits and roster validity (H-06)", async ({ page, request }, testInfo) => {
  const suffix = testInfo.project.name;
  const players = [
    { fullName: `Reload Alpha ${suffix}`, shortName: `RLA${suffix}` },
    { fullName: `Reload Bravo ${suffix}`, shortName: `RLB${suffix}` },
    { fullName: `Reload Charlie ${suffix}`, shortName: `RLC${suffix}` },
    { fullName: `Reload Delta ${suffix}`, shortName: `RLD${suffix}` },
  ];

  for (const player of players) {
    await createPlayer(request, player);
  }

  await page.goto("/");

  const searchInput = page.getByPlaceholder("Search players...");
  for (const player of players) {
    await searchInput.fill(player.shortName);
    const card = page.locator("section").filter({ has: page.getByText(player.fullName) }).last();
    await card.getByRole("button", { name: "Add" }).click();
  }

  // Pair the first two players.
  await page.getByText(players[0].fullName, { exact: true }).click();
  await page.getByText(players[1].fullName, { exact: true }).click();
  await expect(page.getByLabel(/^Remove pair /)).toHaveCount(1);

  await page.getByRole("button", { name: "Next: Settings" }).click();
  for (let i = 0; i < 4; i += 1) {
    await page.getByRole("button", { name: "Decrease Courts" }).click();
  }
  await page.getByText("Advanced Settings").click();
  await page.locator("select").selectOption(players[2].shortName);
  // A generous limit keeps the generated roster free of constraint violations.
  await page.locator('input[type="number"][max="20"]').last().fill("20");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByText(`${players[2].shortName}: max 20`)).toBeVisible();

  await page.getByRole("button", { name: "Next: Review" }).click();
  await page.getByRole("button", { name: "Generate Roster" }).click();
  await expect(page.getByRole("button", { name: "Start Session" })).toBeEnabled();

  await page.reload();

  // Selections and pairs survive the reload.
  await expect(page.getByText("4 selected")).toBeVisible();
  await expect(page.getByLabel(/^Remove pair /)).toHaveCount(1);

  // Limits survive the reload.
  await page.getByRole("button", { name: "Next: Settings" }).click();
  await page.getByText("Advanced Settings").click();
  await expect(page.getByText(`${players[2].shortName}: max 20`)).toBeVisible();

  // The saved roster is still considered valid, not stale.
  await page.getByRole("button", { name: "Next: Review" }).click();
  await expect(page.getByText("Roster is out of date")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Start Session" })).toBeEnabled();
});
