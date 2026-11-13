import { expect, test } from "@playwright/test";
import { createPlayer } from "./helpers/session";

// C-2 PR3 (AC-R1, AC-R2, AC-F3): league+knockout courts are a free choice
// from 1 up to pairs/2, rounds derive as ceil(matches/courts) and update
// live, and friendlies are labeled on the roster. Verified red on the PR2
// tree: the client auto-pinned courts to pairs/2 (6 pairs forced to 3
// courts) and derived the old cycle-based round count.

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

async function pairUp(page, players) {
  for (let i = 0; i < players.length; i += 2) {
    await page.getByText(players[i].fullName, { exact: true }).click();
    await page.getByText(players[i + 1].fullName, { exact: true }).click();
  }
}

function courtsInput(page) {
  return page.getByLabel("Decrease Courts").locator("xpath=following-sibling::input[1]");
}

test("six pairs on two courts: derived rounds, no court pinning, friendly labeled", async ({ page, request }, testInfo) => {
  const players = await addPlayers(page, request, testInfo.project.name, 12, "LK6");
  await pairUp(page, players);
  await page.getByRole("button", { name: "Next: Settings" }).click();

  await page.getByRole("button", { name: /League \+ Knockout/ }).click();

  // Courts stay a free choice: 6 pairs allow up to 3, two is fine (AC-R2).
  await courtsInput(page).click();
  await courtsInput(page).press("ControlOrMeta+a");
  await courtsInput(page).pressSequentially("2");
  await courtsInput(page).blur();
  await expect(courtsInput(page)).toHaveValue("2");

  // Rounds derive as ceil(15 / 2) = 8 with exactly one friendly (AC-R1/D3).
  await expect(page.getByText("8 rounds (6 teams, play once, 2 courts, 1 friendly)")).toBeVisible();

  await page.getByRole("button", { name: "Next: Review" }).click();
  await page.getByRole("button", { name: "Generate Roster" }).click();
  await expect(page.getByRole("button", { name: "Start Session" })).toBeEnabled();
  await expect(page.getByText("Roster could not be generated")).toHaveCount(0);

  // The friendly is labeled on the roster (AC-F3). Desktop and mobile views
  // both render the badge; exactly one of them is visible per viewport, so
  // assert presence in the DOM rather than visibility.
  expect(await page.getByText("Friendly", { exact: true }).count()).toBeGreaterThanOrEqual(1);
  // Fairness issues never block: the panel is present and Start stays enabled.
  await expect(page.getByRole("button", { name: "Start Session" })).toBeEnabled();
});

test("fewer courts stretch the league and the preview updates live", async ({ page, request }, testInfo) => {
  const players = await addPlayers(page, request, testInfo.project.name, 10, "LK5");
  await pairUp(page, players);
  await page.getByRole("button", { name: "Next: Settings" }).click();
  await page.getByRole("button", { name: /League \+ Knockout/ }).click();

  // 5 pairs / 2 courts: 10 matches, 5 rounds, no friendlies.
  await expect(page.getByText("5 rounds (5 teams, play once, 2 courts)")).toBeVisible();

  // Play Twice doubles the matches: 10 rounds.
  await page.getByRole("button", { name: "Play Twice" }).click();
  await expect(page.getByText("10 rounds (5 teams, play twice, 2 courts)")).toBeVisible();

  // One court stretches the same league to 10 rounds (play once again).
  await page.getByRole("button", { name: "Play Once" }).click();
  await courtsInput(page).click();
  await courtsInput(page).press("ControlOrMeta+a");
  await courtsInput(page).pressSequentially("1");
  await courtsInput(page).blur();
  await expect(page.getByText("10 rounds (5 teams, play once, 1 court)")).toBeVisible();
});
