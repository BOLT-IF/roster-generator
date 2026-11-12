import { expect, test } from "@playwright/test";
import { generatePlannerRoster, getFirstCourtPlayerButtons } from "./helpers/planner";

test("a failed regenerate keeps the previous roster and manual edits and shows the error (L-09c)", async ({ page, request }, testInfo) => {
  await generatePlannerRoster(page, request, testInfo.project.name, "GFL");

  // Make a real manual edit so the regenerate confirm dialog appears.
  const { teamA, teamB, rounds, offset } = await getFirstCourtPlayerButtons(page);
  await teamA.nth(offset).click();
  await teamB.nth(offset).click();
  await expect(page.getByText("Edited roster")).toBeVisible();
  const roundCount = await rounds.count();
  expect(roundCount).toBeGreaterThan(1);

  await page.route("**/api/generate", (route) =>
    route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "Generator exploded" }) })
  );
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Regenerate Roster" }).click();

  // The error is surfaced...
  await expect(page.getByText("Roster could not be generated")).toBeVisible();
  await expect(page.getByText("Generator exploded")).toBeVisible();

  // ...and the previous roster and its manual edits are still there.
  await expect(page.getByText("Roster edits")).toBeVisible();
  await expect(page.getByText("Edited roster")).toBeVisible();
  await expect(rounds).toHaveCount(roundCount);
  await expect(page.getByRole("button", { name: "Start Session" })).toBeEnabled();
});
