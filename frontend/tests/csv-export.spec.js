import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";
import { createPlayer } from "./helpers/session";

test("CSV export escapes commas/quotes, neutralizes formulas and adds a BOM (M-31)", async ({ page, request }, testInfo) => {
  const suffix = testInfo.project.name;
  const players = ["A", "B", "C", "D"].map((letter) => ({
    fullName: `Csv ${letter} ${suffix}`,
    shortName: `CS${letter}${suffix}`,
  }));
  for (const player of players) {
    await createPlayer(request, player);
  }

  // Return a roster whose names are hostile to naive CSV writers.
  await page.route("**/api/generate", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    const court = body.rounds[0].courts[0];
    court.team_a = ["Smith, John", 'Ann "Ace" Lee'];
    court.team_b = ["=HYPERLINK(\"http://evil\")", "+1+1"];
    body.rounds[0].resting = ["@SUM(A1)"];
    await route.fulfill({ response, json: body });
  });

  await page.goto("/");
  const searchInput = page.getByPlaceholder("Search players...");
  for (const player of players) {
    await searchInput.fill(player.shortName);
    const card = page.locator("section").filter({ has: page.getByText(player.fullName) }).last();
    await card.getByRole("button", { name: "Add" }).click();
  }
  await page.getByRole("button", { name: "Next: Settings" }).click();
  await page.getByRole("button", { name: "Next: Review" }).click();
  await page.getByRole("button", { name: "Generate Roster" }).click();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download CSV" }).click();
  const download = await downloadPromise;
  const path = await download.path();
  const raw = await readFile(path);

  // UTF-8 BOM so Excel detects the encoding.
  expect([...raw.subarray(0, 3)]).toEqual([0xef, 0xbb, 0xbf]);

  const text = raw.toString("utf8").replace(/^\uFEFF/, "");
  const [, firstRow] = text.split("\r\n");

  // Commas and quotes: RFC 4180 quoting with doubled quotes.
  expect(firstRow).toContain('"Smith, John"');
  expect(firstRow).toContain('"Ann ""Ace"" Lee"');
  // Formula prefixes are neutralized with a leading apostrophe (and quoted when needed).
  expect(firstRow).toContain("\"'=HYPERLINK(\"\"http://evil\"\")\"");
  expect(firstRow).toContain("'+1+1");
  expect(firstRow).toContain("'@SUM(A1)");
  expect(firstRow).not.toMatch(/(^|,)[=+\-@]/);
});
