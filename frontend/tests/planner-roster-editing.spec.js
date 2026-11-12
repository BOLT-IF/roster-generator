import { expect, test } from "@playwright/test";
import { createPlayer } from "./helpers/session";

function normalizeSnapshotText(value) {
  return value.replace("Selected", "").replace(/\s+/g, " ").trim();
}

async function getRoundSnapshot(row) {
  const cellTexts = (await row.locator("td").allTextContents()).map((value) => normalizeSnapshotText(value));
  return {
    rowBody: cellTexts.slice(1),
    restText: cellTexts[cellTexts.length - 1] || "",
  };
}

function getTeamCell(row, index) {
  return row.locator("td").nth(index);
}

function getPlayerButton(teamCell, playerIndex) {
  return teamCell.getByRole("button").nth(playerIndex + 1);
}

async function clickTeamCard(teamCell) {
  await teamCell.getByRole("button", { name: /^Swap team / }).click({ position: { x: 12, y: 12 } });
}

async function getMobileRoundSnapshot(roundCard) {
  return normalizeSnapshotText((await roundCard.textContent()) || "").replace(/^Round \d+/, "Round");
}

function getMobileTeamCard(courtCard, index) {
  return courtCard.locator("div.mt-3.space-y-2 > div").nth(index);
}

function getMobilePlayerButton(teamCard, playerIndex) {
  return teamCard.getByRole("button").nth(playerIndex + 1);
}

async function clickMobileTeamCard(teamCard) {
  await teamCard.getByRole("button", { name: /^Swap team / }).click({ position: { x: 12, y: 12 } });
}

test("planner uses selection-first player, team, and round swaps", async ({ page, request }, testInfo) => {
  const suffix = testInfo.project.name;
  const players = [
    { fullName: `Swap Alpha ${suffix}`, shortName: `SWA${suffix}` },
    { fullName: `Swap Bravo ${suffix}`, shortName: `SWB${suffix}` },
    { fullName: `Swap Charlie ${suffix}`, shortName: `SWC${suffix}` },
    { fullName: `Swap Delta ${suffix}`, shortName: `SWD${suffix}` },
    { fullName: `Swap Echo ${suffix}`, shortName: `SWE${suffix}` },
  ];

  for (const player of players) {
    await createPlayer(request, player);
  }

  await page.goto("/");

  const searchInput = page.getByPlaceholder("Search players...");
  for (const player of players) {
    await searchInput.fill(player.shortName);
    const card = page.locator("section").filter({ hasText: player.fullName }).last();
    await card.getByRole("button", { name: "Add" }).first().click();
  }

  await page.getByRole("button", { name: "Next: Settings" }).click();
  await page.getByRole("button", { name: "Decrease Courts" }).click();
  await page.getByRole("button", { name: "Decrease Courts" }).click();
  await page.getByRole("button", { name: "Decrease Courts" }).click();
  await page.getByRole("button", { name: "Decrease Courts" }).click();
  for (let i = 0; i < 7; i += 1) {
    await page.getByRole("button", { name: "Decrease Rounds" }).click();
  }
  await page.getByRole("button", { name: "Next: Review" }).click();

  await page.getByRole("button", { name: "Generate Roster" }).click();
  await expect(page.getByText("Roster edits")).toBeVisible();
  await expect(page.getByText("Tap a player, team, or round to edit.").first()).toBeVisible();

  const hasDesktopTable = await page.locator("table").isVisible().catch(() => false);

  if (!hasDesktopTable) {
    const firstRound = page.locator("details").nth(0);
    const secondRound = page.locator("details").nth(1);
    const firstCourt = firstRound.locator("div.rounded-lg.border.border-gray-200.bg-white.p-3.shadow-sm").first();
    const teamACard = getMobileTeamCard(firstCourt, 0);
    const teamBCard = getMobileTeamCard(firstCourt, 1);

    await getMobilePlayerButton(teamACard, 0).click();
    await expect(page.getByText(/Selected .*\./).first()).toBeVisible();
    await expect(page.getByText("Select another player in the same round or tap the same player again to cancel.").first()).toBeVisible();
    await getMobilePlayerButton(teamBCard, 0).click();
    await expect(page.getByText("Edited roster")).toBeVisible();

    const firstRoundBeforeTeamSwap = await getMobileRoundSnapshot(firstRound);
    await clickMobileTeamCard(teamACard);
    await expect(page.getByText(/Selected .*\./).first()).toBeVisible();
    await expect(page.getByText("Select another team in the same round or tap the same team again to cancel.").first()).toBeVisible();
    await clickMobileTeamCard(teamBCard);
    await expect.poll(async () => getMobileRoundSnapshot(firstRound)).not.toBe(firstRoundBeforeTeamSwap);
    const firstRoundAfterTeamSwap = await getMobileRoundSnapshot(firstRound);
    expect(firstRoundAfterTeamSwap).not.toEqual(firstRoundBeforeTeamSwap);

    const firstRoundBeforeRoundSwap = await getMobileRoundSnapshot(firstRound);
    const secondRoundBeforeRoundSwap = await getMobileRoundSnapshot(secondRound);
    await firstRound.getByRole("button", { name: "Swap", exact: true }).click();
    await expect(page.getByText(/Selected Round 1\./).first()).toBeVisible();
    await secondRound.locator("summary").click();
    await expect.poll(async () => getMobileRoundSnapshot(page.locator("details").nth(0))).toEqual(secondRoundBeforeRoundSwap);
    const firstRoundAfterRoundSwap = await getMobileRoundSnapshot(page.locator("details").nth(0));
    expect(firstRoundAfterRoundSwap).not.toEqual(firstRoundBeforeRoundSwap);

    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "Regenerate Roster" }).click();
    await expect(page.getByText("Edited roster")).toHaveCount(0);
    return;
  }

  const firstRow = page.locator("table tbody tr").first();
  const teamACell = getTeamCell(firstRow, 2);
  const teamBCell = getTeamCell(firstRow, 3);

  await getPlayerButton(teamACell, 0).click();
  await expect(page.getByText(/Selected .*\./).first()).toBeVisible();
  await expect(page.getByText("Select another player in the same round or tap the same player again to cancel.").first()).toBeVisible();
  await getPlayerButton(teamBCell, 0).click();
  await expect(page.getByText("Edited roster")).toBeVisible();

  const firstRowBeforeTeamSwap = await getRoundSnapshot(firstRow);
  await clickTeamCard(getTeamCell(firstRow, 2));
  await expect(page.getByText(/Selected .*\./).first()).toBeVisible();
  await expect(page.getByText("Select another team in the same round or tap the same team again to cancel.").first()).toBeVisible();
  await clickTeamCard(getTeamCell(firstRow, 3));
  await expect.poll(async () => {
    const snapshot = await getRoundSnapshot(firstRow);
    return JSON.stringify(snapshot.rowBody);
  }).not.toBe(JSON.stringify(firstRowBeforeTeamSwap.rowBody));
  const firstRowAfterTeamSwap = await getRoundSnapshot(firstRow);
  expect(firstRowAfterTeamSwap.rowBody).not.toEqual(firstRowBeforeTeamSwap.rowBody);

  const firstRowBeforeRoundSwap = await getRoundSnapshot(page.locator("table tbody tr").nth(0));
  const secondRowBeforeRoundSwap = await getRoundSnapshot(page.locator("table tbody tr").nth(1));
  const roundButtons = page.locator("table tbody tr").locator("td:first-child").getByRole("button");
  await roundButtons.nth(0).click();
  await expect(page.getByText(/Selected Round 1\./).first()).toBeVisible();
  await roundButtons.nth(1).click();
  await expect.poll(async () => {
    const snapshot = await getRoundSnapshot(page.locator("table tbody tr").nth(0));
    return JSON.stringify([snapshot.rowBody, snapshot.restText]);
  }).toBe(JSON.stringify([secondRowBeforeRoundSwap.rowBody, secondRowBeforeRoundSwap.restText]));
  const firstRowAfterRoundSwap = await getRoundSnapshot(page.locator("table tbody tr").nth(0));
  expect(firstRowAfterRoundSwap.rowBody).not.toEqual(firstRowBeforeRoundSwap.rowBody);

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Regenerate Roster" }).click();
  await expect(page.getByText("Edited roster")).toHaveCount(0);
});
