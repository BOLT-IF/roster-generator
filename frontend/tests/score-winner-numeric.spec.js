import { expect, test } from "@playwright/test";
import { createRoundRobinSession, openSession } from "./helpers/session";

test("live winner label compares scores numerically, not as strings (M-12)", async ({ page, request }, testInfo) => {
  const session = await createRoundRobinSession(request, `Numeric Winner ${testInfo.project.name}`);
  await openSession(page, session.session_id, session.edit_token);

  await page.getByText("Upcoming League Rounds").click();
  await page.getByRole("button", { name: "Start Round" }).click();

  const liveInputs = page.locator('input[type="number"]:not([disabled])');
  await liveInputs.nth(0).fill("21");
  await liveInputs.nth(1).fill("9");

  const card = page.locator("div.rounded-xl.border.border-gray-200.bg-gray-50").first();
  const teamAName = (await card.locator("p.rounded-lg").nth(0).textContent()).trim();
  const teamBName = (await card.locator("p.rounded-lg").nth(1).textContent()).trim();

  // 21 > 9, so Team A wins (string comparison would pick Team B).
  await expect(card.getByText(/^Winner:/)).toHaveText(`Winner: ${teamAName.replace(/\s*&\s*/g, " & ")}`);

  // Flip the scores: 9 vs 21 -> Team B wins.
  await liveInputs.nth(0).fill("9");
  await liveInputs.nth(1).fill("21");
  await expect(card.getByText(/^Winner:/)).toHaveText(`Winner: ${teamBName.replace(/\s*&\s*/g, " & ")}`);
});
