import { expect } from "@playwright/test";
import { createPlayer } from "./session";

// Create `count` directory players and add them all to the planner selection.
export async function addPlannerPlayers(page, request, suffix, count, prefix) {
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

// Pair two selected players through the session-player list.
export async function pairPlayers(page, first, second) {
  await page.getByText(first.fullName, { exact: true }).click();
  await page.getByText(second.fullName, { exact: true }).click();
}

// Walk the planner to a generated roster: 4 players, 1 court, default rounds.
export async function generatePlannerRoster(page, request, suffix, prefix) {
  const players = await addPlannerPlayers(page, request, suffix, 4, prefix);
  await page.getByRole("button", { name: "Next: Settings" }).click();
  for (let i = 0; i < 4; i += 1) {
    await page.getByRole("button", { name: "Decrease Courts" }).click();
  }
  await page.getByRole("button", { name: "Next: Review" }).click();
  await page.getByRole("button", { name: "Generate Roster" }).click();
  await expect(page.getByText("Roster edits")).toBeVisible();
  return players;
}

// Player buttons of the first court's two teams, on desktop (table) or mobile (cards).
// Returns { teamA, teamB, roundCount } where teamA/teamB are lists of player-slot buttons.
export async function getFirstCourtPlayerButtons(page) {
  const hasDesktopTable = await page.locator("table").isVisible().catch(() => false);
  if (hasDesktopTable) {
    const firstRow = page.locator("table tbody tr").first();
    return {
      teamA: firstRow.locator("td").nth(2).getByRole("button"),
      teamB: firstRow.locator("td").nth(3).getByRole("button"),
      rounds: page.locator("table tbody tr"),
      offset: 1,
    };
  }
  const firstCourt = page
    .locator("details")
    .nth(0)
    .locator("div.rounded-lg.border.border-gray-200.bg-white.p-3.shadow-sm")
    .first();
  const teams = firstCourt.locator("div.mt-3.space-y-2 > div");
  return {
    teamA: teams.nth(0).getByRole("button"),
    teamB: teams.nth(1).getByRole("button"),
    rounds: page.locator("details"),
    offset: 1,
  };
}
