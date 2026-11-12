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
