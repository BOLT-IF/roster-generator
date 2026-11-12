import { expect, test } from "@playwright/test";
import { createRoundRobinSession, openSession } from "./helpers/session";

test("an invalid ?edit= token explains why the session is view-only (UX a)", async ({ page, request }, testInfo) => {
  const session = await createRoundRobinSession(request, `Bad Token ${testInfo.project.name}`);

  await openSession(page, session.session_id, "this-is-not-a-valid-token");

  await expect(page.getByText("View Only", { exact: true })).toBeVisible();
  await expect(page.getByRole("alert").filter({ hasText: "edit link" })).toContainText(
    "This edit link is not valid, so the session opened in view-only mode."
  );
});

test("a valid edit link does not show the invalid-link notice (UX a)", async ({ page, request }, testInfo) => {
  const session = await createRoundRobinSession(request, `Good Token ${testInfo.project.name}`);

  await openSession(page, session.session_id, session.edit_token);

  await expect(page.getByText("Scorer", { exact: true })).toBeVisible();
  await expect(page.getByText("This edit link is not valid")).toHaveCount(0);
});

test("the session pill does not repeat the word Session (UX b)", async ({ page, request }, testInfo) => {
  const name = `Session Night ${testInfo.project.name}`;
  const session = await createRoundRobinSession(request, name);

  await openSession(page, session.session_id, session.edit_token);

  const pill = page.locator("p.rounded-full", { hasText: name });
  await expect(pill).toHaveText(name);
  await expect(page.getByText(`Session ${name}`)).toHaveCount(0);
});

test.describe("mobile viewport", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("Start Round is reachable without expanding Upcoming League Rounds (UX c)", async ({ page, request }, testInfo) => {
    const session = await createRoundRobinSession(request, `Start Surface ${testInfo.project.name}`);

    await openSession(page, session.session_id, session.edit_token);

    // Not inside the collapsed "Upcoming League Rounds" card.
    const startButton = page.getByRole("button", { name: "Start Next Round" });
    await expect(startButton).toBeVisible();
    await expect(page.getByText("Upcoming League Rounds")).toBeVisible();

    await startButton.click();
    await expect(page.locator('input[type="number"]:not([disabled])').first()).toBeVisible();
    // Once a round is live the shortcut goes away.
    await expect(page.getByRole("button", { name: "Start Next Round" })).toHaveCount(0);
  });
});
