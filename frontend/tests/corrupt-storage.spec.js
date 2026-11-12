import { expect, test } from "@playwright/test";

const CORRUPT_VARIANTS = {
  "valid JSON of the wrong type": {
    "badminton-roster:session-access": "null",
    "badminton-roster:organizer-token": "123",
    "badminton-roster:planner": JSON.stringify({
      selectedPlayerIds: "not-an-array",
      fixedPairIds: 5,
      config: { limits: 7, court_numbers: "x" },
      roster: { rounds: "nope" },
    }),
    "badminton-roster:session": JSON.stringify({ roster: { rounds: [1, 2] } }),
  },
  "unparseable JSON": {
    "badminton-roster:session-access": "{not json",
    "badminton-roster:organizer-token": "{",
    "badminton-roster:planner": "<<<",
    "badminton-roster:session": "][",
  },
};

for (const [label, entries] of Object.entries(CORRUPT_VARIANTS)) {
  test(`corrupt localStorage (${label}) does not white-screen the app (M-14)`, async ({ page }) => {
    const pageErrors = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));

    await page.addInitScript((seed) => {
      for (const [key, value] of Object.entries(seed)) {
        window.localStorage.setItem(key, value);
      }
    }, entries);

    await page.goto("/sessions");
    await expect(page.getByRole("heading", { name: "Resume, share, and manage ongoing sessions" })).toBeVisible();

    await page.goto("/planner");
    await expect(page.getByRole("heading", { name: "Build the next session from scratch" })).toBeVisible();

    expect(pageErrors).toEqual([]);
  });
}

test("storage that throws on write does not white-screen the app (M-14)", async ({ page }) => {
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.addInitScript(() => {
    Storage.prototype.setItem = () => {
      throw new DOMException("quota exceeded", "QuotaExceededError");
    };
  });

  await page.goto("/planner");
  await expect(page.getByRole("heading", { name: "Build the next session from scratch" })).toBeVisible();
  expect(pageErrors).toEqual([]);
});
