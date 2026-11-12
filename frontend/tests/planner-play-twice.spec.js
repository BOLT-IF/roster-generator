import { expect, test } from "@playwright/test";
import { createPlayer } from "./helpers/session";

async function setupPlanner(page, request, suffix, prefix) {
  const players = Array.from({ length: 8 }, (_, index) => ({
    fullName: `${prefix} Player ${index + 1} ${suffix}`,
    shortName: `${prefix}-${index + 1}-${suffix}`,
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
  for (let index = 0; index < 8; index += 2) {
    await page.getByText(players[index].fullName, { exact: true }).click();
    await page.getByText(players[index + 1].fullName, { exact: true }).click();
  }

  await page.getByRole("button", { name: "Next: Settings" }).click();
  await page.getByRole("button", { name: /League \+ Knockout/ }).click();
  return players;
}

test("Play Twice does not report its by-design repeat matchups as violations", async ({ page, request }, testInfo) => {
  await setupPlanner(page, request, testInfo.project.name, "PTA");
  await page.getByRole("button", { name: "Play Twice" }).click();
  await page.getByRole("button", { name: "Next: Review" }).click();
  await page.getByRole("button", { name: "Generate Roster" }).click();

  await expect(page.getByRole("button", { name: "Start Session" })).toBeVisible();
  // No misleading warning dialog or red violation list for expected repeats.
  await expect(page.getByText("Knockout Schedule Warning")).toHaveCount(0);
  await expect(page.getByText("Constraint Violations")).toHaveCount(0);
  await expect(page.getByText("All constraints satisfied.")).toBeVisible();
  // An explanatory note tells the organiser why repeats are fine.
  await expect(page.getByText(/Play Twice: each pair meets every other pair twice/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Start Session" })).toBeEnabled();
});

test("Start Session is disabled while real constraint violations exist", async ({ page, request }, testInfo) => {
  await setupPlanner(page, request, testInfo.project.name, "PTB");
  await page.getByRole("button", { name: "Play Twice" }).click();
  await page.getByRole("button", { name: "Next: Review" }).click();

  // Inject one real violation (a fixed pair that never plays together) into the generated roster.
  await page.route("**/api/generate", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.violations = [...(body.violations || []), "X & Y: played 0 games together (target 3)"];
    await route.fulfill({ response, json: body });
  });
  await page.getByRole("button", { name: "Generate Roster" }).click();

  await expect(page.getByText("Constraint Violations").first()).toBeVisible();
  await expect(page.getByText("X & Y: played 0 games together (target 3)").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Start Session" })).toBeDisabled();
  await expect(page.getByText("Resolve the constraint violations to start", { exact: true })).toBeVisible();
});
