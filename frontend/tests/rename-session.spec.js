import { expect, test } from "@playwright/test";
import { navigateToSection } from "./helpers/navigation";
import { createRoundRobinSession, openSession } from "./helpers/session";

test("@smoke session can be renamed from scoring view and session list", async ({ page, request }, testInfo) => {
  const suffix = testInfo.project.name;
  const session = await createRoundRobinSession(request, `Rename Session Seed ${suffix}`);

  await openSession(page, session.session_id, session.edit_token);
  await expect(page.getByRole("button", { name: "Rename Session", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Rename Session", exact: true }).click();
  await page.getByLabel("Session name").fill(`Evening Ladder ${suffix}`);
  await page.getByRole("button", { name: "Save Name" }).click();
  await expect(page.getByText(`Session Evening Ladder ${suffix}`)).toBeVisible();

  await page.getByRole("button", { name: "Back to Roster" }).click();
  await navigateToSection(page, "Active Sessions");
  await expect(page.getByRole("heading", { name: `Evening Ladder ${suffix}` }).first()).toBeVisible();

  const activeSessionCard = page.locator("div.rounded-2xl").filter({ hasText: `Evening Ladder ${suffix}` }).first();
  await activeSessionCard.getByRole("button", { name: "Rename" }).click();
  await page.getByLabel("Session name").fill(`Thursday Club ${suffix}`);
  await page.getByRole("button", { name: "Save Name" }).click();
  await expect(page.getByRole("heading", { name: `Thursday Club ${suffix}` }).first()).toBeVisible();

  const renamedSessionCard = page.locator("div.rounded-2xl").filter({ hasText: `Thursday Club ${suffix}` }).first();
  await renamedSessionCard.getByRole("button", { name: "Open Scorer View" }).click();
  await expect(page.getByText(`Session Thursday Club ${suffix}`)).toBeVisible();
});
