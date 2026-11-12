import { expect, test } from "@playwright/test";
import { createPlayer } from "./helpers/session";

test("FastAPI 422 detail arrays are shown as readable text, not [object Object] (M-15b)", async ({ page, request }, testInfo) => {
  const suffix = testInfo.project.name;
  const players = ["A", "B", "C", "D"].map((letter) => ({
    fullName: `ErrMsg ${letter} ${suffix}`,
    shortName: `EM${letter}${suffix}`,
  }));
  for (const player of players) {
    await createPlayer(request, player);
  }

  await page.route("**/api/generate", (route) =>
    route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({
        detail: [
          { type: "less_than_equal", loc: ["body", "num_courts"], msg: "Input should be less than or equal to 20", input: 99 },
          { type: "missing", loc: ["body", "rounds"], msg: "Field required" },
        ],
      }),
    })
  );

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

  const errorBox = page.getByText("Roster could not be generated").locator("..");
  await expect(errorBox).toBeVisible();
  await expect(errorBox).not.toContainText("[object Object]");
  await expect(errorBox).toContainText("num_courts: Input should be less than or equal to 20");
  await expect(errorBox).toContainText("rounds: Field required");
});
