import { expect, test } from "@playwright/test";

test("an unknown route shows a friendly not-found page that links home (L-09e)", async ({ page }) => {
  await page.goto("/nowhere-xyz");

  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
  await page.getByRole("link", { name: "Back to the planner" }).click();

  await expect(page).toHaveURL(/\/planner$/);
  await expect(page.getByRole("heading", { name: "Build the next session from scratch" })).toBeVisible();
});

test("nested unknown routes are also handled", async ({ page }) => {
  await page.goto("/players/does/not/exist");
  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
});
