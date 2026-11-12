import { expect, test } from "@playwright/test";
import { createPlayer } from "./helpers/session";

test("planner steps can be clicked to jump between stages", async ({ page, request }, testInfo) => {
  const suffix = testInfo.project.name;
  const players = [
    { fullName: `Stepper Alpha ${suffix}`, shortName: `SA1${suffix}` },
    { fullName: `Stepper Bravo ${suffix}`, shortName: `SB1${suffix}` },
    { fullName: `Stepper Charlie ${suffix}`, shortName: `SC1${suffix}` },
    { fullName: `Stepper Delta ${suffix}`, shortName: `SD1${suffix}` },
  ];

  for (const player of players) {
    await createPlayer(request, player);
  }

  await page.goto("/");

  const searchInput = page.getByPlaceholder("Search players...");
  const directorySection = page.locator("section").filter({ has: page.getByRole("heading", { name: "Player Directory" }) });
  for (const player of players) {
    await searchInput.fill(player.shortName);
    const card = directorySection.locator("div").filter({ hasText: player.fullName }).first();
    await card.getByRole("button", { name: "Add" }).click();
  }

  await page.getByRole("button", { name: "Next: Settings" }).click();
  await expect(page.getByRole("button", { name: /Step 3 Review & Start/i })).toBeDisabled();
  await page.getByRole("button", { name: "Next: Review" }).click();
  await expect(page.getByRole("heading", { name: "Review and start" })).toBeVisible();

  await page.getByRole("button", { name: /Step 1 Players & Pairs/i }).click();
  await expect(page.getByRole("heading", { name: "Players and pairs" })).toBeVisible();
});
