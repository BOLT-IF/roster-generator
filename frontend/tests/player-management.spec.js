import { expect, test } from "@playwright/test";
import { navigateToSection } from "./helpers/navigation";
import { createSharedSession, generateRoster } from "./helpers/session";

test("player directory imports names from existing sessions", async ({ page, request }, testInfo) => {
  const suffix = testInfo.project.name;
  const legacyNames = [`Legacy One ${suffix}`, `Legacy Two ${suffix}`, `Legacy Three ${suffix}`, `Legacy Four ${suffix}`];
  const roster = await generateRoster(request, {
    players: legacyNames,
  });

  await createSharedSession(request, {
    name: `Legacy Import Session ${suffix}`,
    roster,
    drawConfig: {
      draw_type: "round_robin",
      league_meetings: 1,
      knockout_qualifiers: 4,
    },
  });

  await page.goto("/");
  await navigateToSection(page, "Players");

  const directorySection = page.locator("section").filter({ has: page.getByRole("heading", { name: "Registered players" }) });
  const legacyOneCard = directorySection.locator("div.rounded-2xl.border.border-gray-200.bg-gray-50").filter({ hasText: legacyNames[0] }).first();
  const legacyTwoCard = directorySection.locator("div.rounded-2xl.border.border-gray-200.bg-gray-50").filter({ hasText: legacyNames[1] }).first();
  await legacyOneCard.scrollIntoViewIfNeeded();
  await expect(legacyOneCard.getByText(legacyNames[0], { exact: true }).first()).toBeVisible();
  await expect(legacyTwoCard.getByText(legacyNames[1], { exact: true }).first()).toBeVisible();
});

test("players can be created, selected from the planner directory, and used to start a protected session", async ({ page }, testInfo) => {
  const suffix = testInfo.project.name;
  const players = [
    { fullName: `Player Alpha ${suffix}`, shortName: `PA1${suffix}` },
    { fullName: `Player Bravo ${suffix}`, shortName: `PB1${suffix}` },
    { fullName: `Player Charlie ${suffix}`, shortName: `PC1${suffix}` },
    { fullName: `Player Delta ${suffix}`, shortName: `PD1${suffix}` },
  ];

  await page.goto("/");
  await navigateToSection(page, "Players");

  for (const player of players) {
    await page.getByLabel("Full Name").fill(player.fullName);
    await page.getByLabel("Short Name").fill(player.shortName);
    await page.getByRole("button", { name: "Create Player" }).click();
    await expect(page.getByText(player.fullName)).toBeVisible();
  }

  await navigateToSection(page, "Planner");

  const searchInput = page.getByPlaceholder("Search players...");
  const directorySection = page.locator("section").filter({ has: page.getByRole("heading", { name: "Player Directory" }) });
  for (const player of players) {
    await searchInput.fill(player.shortName);
    const card = directorySection.locator("div.rounded-2xl").filter({ has: page.getByText(player.fullName) }).first();
    await card.getByRole("button", { name: "Add" }).click();
  }
  await searchInput.fill("");

  await page.getByRole("button", { name: "Next: Settings" }).click();
  await page.getByRole("button", { name: "Decrease Courts" }).click();
  await page.getByRole("button", { name: "Decrease Courts" }).click();
  await page.getByRole("button", { name: "Decrease Courts" }).click();
  await page.getByRole("button", { name: "Decrease Courts" }).click();
  await page.getByRole("button", { name: "Next: Review" }).click();
  await page.getByRole("button", { name: "Generate Roster" }).click();

  await expect(page.getByRole("heading", { name: "Roster" })).toBeVisible();
  await expect(page.locator("main")).toContainText(`PA1${suffix}`);

  await page.getByRole("button", { name: "Start Session" }).click();
  const organizerDialog = page.locator("div.fixed.inset-0").filter({ hasText: "Enter organizer token to start a session" });
  await expect(organizerDialog.getByRole("heading", { name: "Enter organizer token to start a session" })).toBeVisible();
  await organizerDialog.getByLabel("Organizer token").fill("thisismytoken");
  await organizerDialog.getByRole("button", { name: "Start Session" }).click();

  await expect(page.getByText("Scoring Console")).toBeVisible();
  await expect(page.locator("p").filter({ hasText: /^Session \d{4}-\d{2}-\d{2}/ })).toBeVisible();
});
