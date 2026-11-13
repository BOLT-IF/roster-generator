import { expect, test } from "@playwright/test";
import { createPlayer } from "./helpers/session";

async function addPlayers(page, request, suffix, count, prefix) {
  const players = Array.from({ length: count }, (_, index) => ({
    fullName: `${prefix} Player ${index + 1} ${suffix}`,
    shortName: `${prefix}${index + 1}${suffix}`,
  }));
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
  await searchInput.fill("");
  return players;
}

async function pair(page, first, second) {
  await page.getByText(first.fullName, { exact: true }).click();
  await page.getByText(second.fullName, { exact: true }).click();
}

function courtsInput(page) {
  return page.getByLabel("Decrease Courts").locator("xpath=following-sibling::input[1]");
}

test("league + knockout derives courts from the pair count and generates without a backend error", async ({ page, request }, testInfo) => {
  const players = await addPlayers(page, request, testInfo.project.name, 8, "LKA");
  await pair(page, players[0], players[1]);
  await pair(page, players[2], players[3]);
  await pair(page, players[4], players[5]);
  await pair(page, players[6], players[7]);

  await page.getByRole("button", { name: "Next: Settings" }).click();
  // C-2: courts are a free choice from 1 up to pairs/2. A user who lowered
  // courts to 1 for round robin keeps 1 court in League + Knockout - the
  // league simply stretches over more rounds (4 pairs / 1 court = 6 rounds).
  await page.getByRole("button", { name: "Decrease Courts" }).click();
  await expect(courtsInput(page)).toHaveValue("1");
  await page.getByRole("button", { name: /League \+ Knockout/ }).click();
  await expect(courtsInput(page)).toHaveValue("1");
  await expect(page.getByText("League + Knockout uses up to 2 courts for 4 fixed pairs")).toBeVisible();
  await expect(page.getByText("6 rounds (4 teams, play once, 1 court)")).toBeVisible();

  await page.getByRole("button", { name: "Next: Review" }).click();
  await page.getByRole("button", { name: "Generate Roster" }).click();
  await expect(page.getByRole("button", { name: "Start Session" })).toBeEnabled();
  await expect(page.getByText("Roster could not be generated")).toHaveCount(0);
});

test("courts default to what the selected players can fill instead of failing at generate", async ({ page, request }, testInfo) => {
  await addPlayers(page, request, testInfo.project.name, 8, "LKC");

  await page.getByRole("button", { name: "Next: Settings" }).click();
  // 8 players can fill 2 courts; the stock default of 5 would be rejected by the backend.
  await expect(courtsInput(page)).toHaveValue("2");

  await page.getByRole("button", { name: "Next: Review" }).click();
  await page.getByRole("button", { name: "Generate Roster" }).click();
  await expect(page.getByRole("button", { name: "Start Session" })).toBeEnabled();
});

test("league + knockout with unpaired players is blocked before generate with a clear message", async ({ page, request }, testInfo) => {
  const players = await addPlayers(page, request, testInfo.project.name, 8, "LKB");
  await pair(page, players[0], players[1]);
  await pair(page, players[2], players[3]);
  await pair(page, players[4], players[5]);
  // players 7 and 8 are left unpaired.

  await page.getByRole("button", { name: "Next: Settings" }).click();
  await page.getByRole("button", { name: /League \+ Knockout/ }).click();

  await expect(page.getByText("every selected player must be in a fixed pair", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Next: Review" })).toBeDisabled();

  // Switching back to round robin removes the restriction.
  await page.getByRole("button", { name: /Round Robin/ }).click();
  await expect(page.getByRole("button", { name: "Next: Review" })).toBeEnabled();
});
