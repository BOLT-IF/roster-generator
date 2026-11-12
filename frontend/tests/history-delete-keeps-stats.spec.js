import { expect, test } from "@playwright/test";
import { navigateToSection } from "./helpers/navigation";
import { completeRoundRobinSession } from "./helpers/session";

test("deleting a completed session removes it from history but keeps player stats", async ({ page, request }, testInfo) => {
  const suffix = testInfo.project.name;
  const sessionName = `Delete History Keep Stats ${suffix}`;
  const session = await completeRoundRobinSession(request, sessionName);
  const { session_id: sessionId, edit_token: editToken } = session;

  await page.goto(`/?session=${sessionId}&edit=${editToken}`);
  await page.getByRole("button", { name: "Back to Roster" }).click();

  page.once("dialog", (dialog) => dialog.accept());
  await navigateToSection(page, "History");
  const historyCard = page.locator("div.rounded-2xl").filter({ hasText: sessionName }).first();
  await expect(historyCard.getByText(sessionName)).toBeVisible();
  await historyCard.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(page.getByText(sessionName)).toHaveCount(0);

  await navigateToSection(page, "Player Stats");
  const leaderboard = page.locator("section").filter({ has: page.getByRole("heading", { name: "Leaderboard" }) });
  await expect(leaderboard.getByRole("button", { name: /^A\b/ })).toBeVisible();
});
