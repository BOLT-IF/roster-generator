import { expect, test } from "@playwright/test";
import { addPlannerPlayers } from "./helpers/planner";

test("pressing Enter in the consecutive-limit field commits the typed value (L-09a)", async ({ page, request }, testInfo) => {
  const players = await addPlannerPlayers(page, request, testInfo.project.name, 4, "LIM");

  await page.getByRole("button", { name: "Next: Settings" }).click();
  await page.getByText("Advanced Settings").click();
  await page.locator("select").selectOption(players[0].shortName);

  const limitInput = page.locator('input[type="number"][max="20"]').last();
  await limitInput.fill("7");
  // Enter submits the form without a blur; it must use "7", not the stale default.
  await limitInput.press("Enter");

  await expect(page.getByText(`${players[0].shortName}: max 7`)).toBeVisible();
  await expect(page.getByText(`${players[0].shortName}: max 2`)).toHaveCount(0);

  // The field itself keeps showing the committed value.
  await expect(limitInput).toHaveValue("7");
});

test("Enter clamps an out-of-range limit instead of committing it raw (L-09a)", async ({ page, request }, testInfo) => {
  const players = await addPlannerPlayers(page, request, testInfo.project.name, 4, "LIC");

  await page.getByRole("button", { name: "Next: Settings" }).click();
  await page.getByText("Advanced Settings").click();
  await page.locator("select").selectOption(players[1].shortName);

  const limitInput = page.locator('input[type="number"][max="20"]').last();
  await limitInput.fill("99");
  await limitInput.press("Enter");

  await expect(page.getByText(`${players[1].shortName}: max 20`)).toBeVisible();
});
