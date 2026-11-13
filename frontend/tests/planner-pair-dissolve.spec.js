import { expect, test } from "@playwright/test";
import { addPlannerPlayers, pairPlayers } from "./helpers/planner";

test("a fixed pair is only dissolved through an explicit remove control (L-09b)", async ({ page, request }, testInfo) => {
  const players = await addPlannerPlayers(page, request, testInfo.project.name, 4, "PDS");
  await pairPlayers(page, players[0], players[1]);

  const removePair = page.getByRole("button", { name: /^Remove pair / });
  await expect(removePair).toHaveCount(1);
  await expect(page.getByText(`paired with ${players[1].shortName}`)).toBeVisible();

  // Clicking the two cards of an existing pair used to dissolve it with no feedback.
  // It must now leave the pair alone and say how to remove it.
  await page.getByText(players[0].fullName, { exact: true }).click();
  await page.getByText(players[1].fullName, { exact: true }).click();
  await expect(removePair).toHaveCount(1);
  await expect(page.getByText(`paired with ${players[1].shortName}`)).toBeVisible();
  await expect(page.getByText(`paired with ${players[0].shortName}`)).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "already paired" })).toBeVisible();

  // The explicit control removes it, with a visible state change.
  await removePair.click();
  await expect(removePair).toHaveCount(0);
  await expect(page.getByText(/paired with/)).toHaveCount(0);
  await expect(page.getByRole("status").filter({ hasText: "already paired" })).toHaveCount(0);
});
