import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { createPlayer } from "./helpers/session";

// Canonical fixtures shared with bolt-club-hq (contracts/roster-import-v1/).
const fixturesDir = resolve(dirname(fileURLToPath(import.meta.url)), "../../contracts/roster-import-v1");

function loadFixture(relativePath) {
  return JSON.parse(readFileSync(resolve(fixturesDir, relativePath), "utf8"));
}

function encodeFragment(payload) {
  const json = typeof payload === "string" ? payload : JSON.stringify(payload);
  return Buffer.from(json, "utf8").toString("base64url");
}

function importUrl(encoded) {
  return `/planner#import=${encoded}`;
}

const SHEET_HEADING = "Import from club event";

// Directory players the golden fixtures match against. Suffix keeps parallel
// projects from colliding in the shared database.
async function seedDirectory(request, suffix) {
  const players = [
    { fullName: `Elin Varga ${suffix}`, shortName: `Elin${suffix}` },
    { fullName: `Marko Hale ${suffix}`, shortName: `Marko${suffix}` },
    { fullName: `Tove Sandqvist ${suffix}`, shortName: `Tove${suffix}` },
  ];
  for (const player of players) {
    await createPlayer(request, player);
  }
  return players;
}

function fixtureForSuffix(fixture, suffix) {
  // Rewrite fixture names so they match the suffixed directory seed above.
  const copy = structuredClone(fixture);
  copy.players = copy.players.map((player) => ({
    ...player,
    name: player.name.includes(" ") ? `${player.name} ${suffix}` : player.name,
    short: player.short ? `${player.short}${suffix}` : player.short,
  }));
  return copy;
}

test.describe("club import (roster-import/v1)", () => {
  test("golden basic fixture opens the import sheet with matched and unmatched players", async ({ page, request }, testInfo) => {
    const suffix = testInfo.project.name;
    await seedDirectory(request, suffix);

    const payload = fixtureForSuffix(loadFixture("golden/basic.json"), suffix);
    await page.goto(importUrl(encodeFragment(payload)));

    const sheet = page.getByRole("dialog", { name: SHEET_HEADING });
    await expect(sheet).toBeVisible();
    await expect(sheet.getByText(`Elin Varga ${suffix}`)).toBeVisible();
    await expect(sheet.getByText(`Marko Hale ${suffix}`)).toBeVisible();
    await expect(sheet.getByText(`Tove Sandqvist ${suffix}`)).toBeVisible();
  });

  test("golden guests fixture labels guests and offers Add to directory for unmatched names", async ({ page }, testInfo) => {
    const suffix = testInfo.project.name;
    const payload = fixtureForSuffix(loadFixture("golden/guests.json"), suffix);
    await page.goto(importUrl(encodeFragment(payload)));

    const sheet = page.getByRole("dialog", { name: SHEET_HEADING });
    await expect(sheet).toBeVisible();
    const hugoRow = sheet.locator("li").filter({ hasText: `Hugo Dahl ${suffix}` });
    await expect(hugoRow.getByText("Guest", { exact: true })).toBeVisible();
    // Unmatched guests are labelled and can still be added to the directory.
    await expect(hugoRow.getByRole("button", { name: "Add to directory" })).toBeVisible();
    const kasiaRow = sheet.locator("li").filter({ hasText: `Kasia Nowak ${suffix}` });
    await expect(kasiaRow.getByRole("button", { name: "Add to directory" })).toBeVisible();
  });

  test("matches case-insensitively by short name first, then full name", async ({ page, request }, testInfo) => {
    const suffix = testInfo.project.name;
    await seedDirectory(request, suffix);

    const byShort = fixtureForSuffix(loadFixture("golden/match-case.json"), suffix);
    byShort.players[0].short = `ELIN${suffix.toUpperCase()}`;
    byShort.players[0].name = `ELIN VARGA ${suffix.toUpperCase()}`;
    await page.goto(importUrl(encodeFragment(byShort)));
    const sheet = page.getByRole("dialog", { name: SHEET_HEADING });
    await expect(sheet).toBeVisible();
    await expect(sheet.getByRole("button", { name: "Add to directory" })).toHaveCount(0);
    await page.getByRole("button", { name: "Close" }).click();
    await expect(sheet).toBeHidden();

    // Fresh navigation: a hash-only change on the same page would not re-read the link.
    const byFull = fixtureForSuffix(loadFixture("golden/full-name-match.json"), suffix);
    await page.goto("about:blank");
    await page.goto(importUrl(encodeFragment(byFull)));
    const sheet2 = page.getByRole("dialog", { name: SHEET_HEADING });
    await expect(sheet2).toBeVisible();
    await expect(sheet2.getByRole("button", { name: "Add to directory" })).toHaveCount(0);
  });

  test("malformed base64 shows a banner and the planner still works", async ({ page }) => {
    await page.goto(importUrl("%%%not-base64%%%"));
    await expect(page.getByText(/couldn.t read this import link/i)).toBeVisible();
    await expect(page.getByRole("dialog", { name: SHEET_HEADING })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Players and pairs" })).toBeVisible();
    await expect(page.getByPlaceholder("Search players...")).toBeVisible();
  });

  test("invalid JSON shows a banner and the planner still works", async ({ page }) => {
    await page.goto(importUrl(encodeFragment("{not json")));
    await expect(page.getByText(/couldn.t read this import link/i)).toBeVisible();
    await expect(page.getByRole("dialog", { name: SHEET_HEADING })).toHaveCount(0);
    await expect(page.getByPlaceholder("Search players...")).toBeVisible();
  });

  test("unknown version shows a friendly banner and the planner still works", async ({ page }) => {
    const payload = loadFixture("invalid/unknown-version.json");
    await page.goto(importUrl(encodeFragment(payload)));
    await expect(page.getByText(/newer version of the roster app/i)).toBeVisible();
    await expect(page.getByRole("dialog", { name: SHEET_HEADING })).toHaveCount(0);
    await expect(page.getByPlaceholder("Search players...")).toBeVisible();
  });

  test("missing players or a nameless player shows a banner", async ({ page }) => {
    await page.goto(importUrl(encodeFragment(loadFixture("invalid/missing-players.json"))));
    await expect(page.getByText(/couldn.t read this import link/i)).toBeVisible();
    await expect(page.getByRole("dialog", { name: SHEET_HEADING })).toHaveCount(0);

    await page.goto(importUrl(encodeFragment(loadFixture("invalid/player-without-name.json"))));
    await expect(page.getByText(/couldn.t read this import link/i)).toBeVisible();
    await expect(page.getByPlaceholder("Search players...")).toBeVisible();
  });

  test("oversized fragment shows a banner and the planner still works", async ({ page }) => {
    const players = Array.from({ length: 300 }, (_, index) => ({ name: `Player ${index} ${"x".repeat(100)}`, short: `P${index}`, guest: false }));
    const payload = { v: 1, source: "bolt-club-hq", event: { title: "Huge" }, players };
    await page.goto(importUrl(encodeFragment(payload)));
    await expect(page.getByText(/too large/i)).toBeVisible();
    await expect(page.getByRole("dialog", { name: SHEET_HEADING })).toHaveCount(0);
    await expect(page.getByPlaceholder("Search players...")).toBeVisible();
  });

  test("reloading after import does not re-import", async ({ page, request }, testInfo) => {
    const suffix = testInfo.project.name;
    await seedDirectory(request, suffix);
    const payload = fixtureForSuffix(loadFixture("golden/basic.json"), suffix);
    await page.goto(importUrl(encodeFragment(payload)));

    const sheet = page.getByRole("dialog", { name: SHEET_HEADING });
    await expect(sheet).toBeVisible();
    await sheet.getByRole("button", { name: "Import players" }).click();
    await expect(sheet).toBeHidden();
    await expect.poll(() => new URL(page.url()).hash).toBe("");

    await page.reload();
    await expect(page.getByRole("dialog", { name: SHEET_HEADING })).toHaveCount(0);
  });

  test("unmatched players can be added to the directory from the sheet", async ({ page, request }, testInfo) => {
    const suffix = testInfo.project.name;
    const payload = fixtureForSuffix(loadFixture("golden/guests.json"), suffix);
    await page.goto(importUrl(encodeFragment(payload)));

    const sheet = page.getByRole("dialog", { name: SHEET_HEADING });
    await expect(sheet).toBeVisible();
    const kasiaRow = sheet.locator("li").filter({ hasText: `Kasia Nowak ${suffix}` });
    await kasiaRow.getByRole("button", { name: "Add to directory" }).click();
    await expect(kasiaRow.getByRole("button", { name: "Add to directory" })).toHaveCount(0);
    await expect(kasiaRow.getByText("In directory")).toBeVisible();

    const response = await request.get(`${process.env.PLAYWRIGHT_API_BASE_URL || "http://127.0.0.1:8010"}/api/players`);
    const directory = await response.json();
    expect(directory.some((player) => player.full_name === `Kasia Nowak ${suffix}`)).toBeTruthy();
  });

  test("confirm before replacing an unsaved draft", async ({ page, request }, testInfo) => {
    const suffix = testInfo.project.name;
    await seedDirectory(request, suffix);

    // Create an unsaved draft: select a player in the planner.
    await page.goto("/planner");
    await page.getByPlaceholder("Search players...").fill(`Elin${suffix}`);
    await page.locator("section").filter({ has: page.getByText(`Elin Varga ${suffix}`) }).last()
      .getByRole("button", { name: "Add" }).click();
    await page.getByPlaceholder("Search players...").fill("");

    const payload = fixtureForSuffix(loadFixture("golden/basic.json"), suffix);
    await page.goto(importUrl(encodeFragment(payload)));

    const sheet = page.getByRole("dialog", { name: SHEET_HEADING });
    await expect(sheet).toBeVisible();
    await sheet.getByRole("button", { name: "Import players" }).click();
    const confirm = page.getByRole("dialog", { name: /are you sure/i });
    await expect(confirm).toBeVisible();

    // Cancel keeps the draft (one selected player) and leaves the sheet open.
    await confirm.getByRole("button", { name: "Cancel" }).click();
    await expect(sheet).toBeVisible();
    await expect(page.getByText("1 selected", { exact: true })).toBeVisible();
  });
});
