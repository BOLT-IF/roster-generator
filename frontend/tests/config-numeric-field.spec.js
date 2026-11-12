import { expect, test } from "@playwright/test";
import { createPlayer } from "./helpers/session";

test("typing a multi-digit value in a numeric setting keeps focus and commits it (H-08)", async ({ page, request }, testInfo) => {
  const suffix = testInfo.project.name;
  const players = ["A", "B", "C", "D"].map((letter) => ({
    fullName: `Numeric ${letter} ${suffix}`,
    shortName: `NF${letter}${suffix}`,
  }));
  for (const player of players) {
    await createPlayer(request, player);
  }

  await page.goto("/");
  const searchInput = page.getByPlaceholder("Search players...");
  for (const player of players) {
    await searchInput.fill(player.shortName);
    const card = page.locator("section").filter({ has: page.getByText(player.fullName) }).last();
    await card.getByRole("button", { name: "Add" }).click();
  }
  await page.getByRole("button", { name: "Next: Settings" }).click();

  const roundsInput = page.getByLabel("Decrease Rounds").locator("xpath=following-sibling::input[1]");
  await roundsInput.click();
  await roundsInput.press("ControlOrMeta+a");
  // Type digit by digit like a user; the field must stay mounted and focused.
  await roundsInput.pressSequentially("12");
  await expect(roundsInput).toBeFocused();
  await expect(roundsInput).toHaveValue("12");

  await roundsInput.blur();
  await expect(roundsInput).toHaveValue("12");

  // The committed value must be what the planner uses (signature/preview).
  await expect(page.getByText("12 league rounds", { exact: false }).first()).toBeVisible();
});
