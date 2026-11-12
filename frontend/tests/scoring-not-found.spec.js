import { expect, test } from "@playwright/test";
import { createRoundRobinSession, openSession } from "./helpers/session";

test("a bad session id shows a not-found state, not the previously opened session (M-13)", async ({ page, request }, testInfo) => {
  const name = `Not Found Prev ${testInfo.project.name}`;
  const session = await createRoundRobinSession(request, name);

  await openSession(page, session.session_id, session.edit_token);
  await expect(page.getByText(`Session ${name}`)).toBeVisible();
  await expect(page.getByRole("button", { name: "Rename Session" })).toBeVisible();

  // The previous session is still persisted locally; a bogus id must not resurrect it.
  await page.goto("/sessions/does-not-exist-m13");

  await expect(page.getByRole("heading", { name: "Session not found" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Back to Active Sessions" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Rename Session" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Start Round" })).toHaveCount(0);
  await expect(page.getByText(`Session ${name}`)).toHaveCount(0);
  await expect(page.locator('input[type="number"]')).toHaveCount(0);

  // The old session must not linger in storage either.
  const stored = await page.evaluate(() => window.localStorage.getItem("badminton-roster:session"));
  expect(stored).toBeNull();

  // The not-found link leads somewhere that works.
  await page.getByRole("link", { name: "Back to Active Sessions" }).click();
  await expect(page).toHaveURL(/\/sessions$/);
});
