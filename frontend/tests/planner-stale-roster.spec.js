import { expect, test } from "@playwright/test";
import { createPlayer } from "./helpers/session";

test("changing planner inputs marks the roster stale until it is regenerated", async ({ page, request }, testInfo) => {
  const suffix = testInfo.project.name;
  const players = [
    { fullName: `Stale Alpha ${suffix}`, shortName: `TA1${suffix}` },
    { fullName: `Stale Bravo ${suffix}`, shortName: `TB1${suffix}` },
    { fullName: `Stale Charlie ${suffix}`, shortName: `TC1${suffix}` },
    { fullName: `Stale Delta ${suffix}`, shortName: `TD1${suffix}` },
    { fullName: `Stale Echo ${suffix}`, shortName: `TE1${suffix}` },
  ];

  for (const player of players) {
    await createPlayer(request, player);
  }

  await page.goto("/");

  const searchInput = page.getByPlaceholder("Search players...");
  for (const player of players.slice(0, 4)) {
    await searchInput.fill(player.shortName);
    const card = page.locator("section").filter({ has: page.getByText(player.fullName) }).last();
    await card.getByRole("button", { name: "Add" }).click();
  }

  await page.getByRole("button", { name: "Next: Settings" }).click();
  await page.getByRole("button", { name: "Decrease Courts" }).click();
  await page.getByRole("button", { name: "Decrease Courts" }).click();
  await page.getByRole("button", { name: "Decrease Courts" }).click();
  await page.getByRole("button", { name: "Decrease Courts" }).click();
  await page.getByRole("button", { name: "Next: Review" }).click();

  await page.getByRole("button", { name: "Generate Roster" }).click();
  await expect(page.getByRole("button", { name: "Start Session" })).toBeEnabled();

  await page.getByRole("button", { name: /Step 1 Players & Pairs/i }).click();
  await searchInput.fill(players[4].shortName);
  const newCard = page.locator("section").filter({ has: page.getByText(players[4].fullName) }).last();
  await newCard.getByRole("button", { name: "Add" }).click();

  await page.getByRole("button", { name: "Next: Settings" }).click();
  await page.getByRole("button", { name: "Next: Review" }).click();
  await expect(page.getByText("Roster is out of date")).toBeVisible();
  await expect(page.getByRole("button", { name: "Regenerate To Start" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Regenerate Updated Roster" })).toBeVisible();
});
