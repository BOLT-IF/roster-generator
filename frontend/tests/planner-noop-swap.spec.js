import { expect, test } from "@playwright/test";
import { generatePlannerRoster, getFirstCourtPlayerButtons } from "./helpers/planner";

// Wait for the roster revalidation round-trip that every applied swap triggers.
function waitForRevalidate(page) {
  return page.waitForResponse((response) => response.url().includes("/api/rosters/revalidate"));
}

test("only a swap that changes the roster marks it as edited (L-09d)", async ({ page, request }, testInfo) => {
  await generatePlannerRoster(page, request, testInfo.project.name, "NSW");
  const { teamA, teamB } = await getFirstCourtPlayerButtons(page);
  // teamX.nth(0) is the "Swap team" control; the players follow it.
  const firstOfA = teamA.nth(1);
  const secondOfA = teamA.nth(2);
  const firstOfB = teamB.nth(1);

  // Selecting the same slot twice just cancels the selection.
  await firstOfA.click();
  await firstOfA.click();
  await expect(page.getByText(/Selected .*\./)).toHaveCount(0);
  await expect(page.getByText("Edited roster")).toHaveCount(0);

  // Swapping the two players of one team yields the same team (the server
  // normalises team order), so the roster content is unchanged.
  await firstOfA.click();
  const noopRevalidate = waitForRevalidate(page);
  await secondOfA.click();
  await noopRevalidate;
  await expect(page.getByText(/Selected .*\./)).toHaveCount(0);
  await expect(page.getByText("Edited roster")).toHaveCount(0);

  // A real swap across teams still marks the roster edited.
  await firstOfA.click();
  const realRevalidate = waitForRevalidate(page);
  await firstOfB.click();
  await realRevalidate;
  await expect(page.getByText("Edited roster")).toBeVisible();
});
