import { expect, test } from "@playwright/test";
import { createRoundRobinSession, openSession } from "./helpers/session";
import { navigateToSection } from "./helpers/navigation";

const POLL_INTERVAL_MS = 12_000;

function sessionUrlPattern(sessionId) {
  return new RegExp(`/api/sessions/${sessionId}(\\?|$)`);
}

// Count GETs for one session without changing the response.
async function countSessionPolls(page, sessionId) {
  const counter = { count: 0 };
  await page.route(sessionUrlPattern(sessionId), async (route) => {
    if (route.request().method() === "GET") counter.count += 1;
    await route.continue();
  });
  return counter;
}

test("polling stops once the session no longer exists (L-09f)", async ({ page, request }, testInfo) => {
  const session = await createRoundRobinSession(request, `Poll Gone ${testInfo.project.name}`);
  await page.clock.install();

  let missing = false;
  let gets = 0;
  await page.route(sessionUrlPattern(session.session_id), async (route) => {
    gets += 1;
    if (!missing) return route.continue();
    return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Session not found" }) });
  });

  await openSession(page, session.session_id, session.edit_token);
  await expect(page.getByRole("button", { name: "Back to Roster" })).toBeVisible();
  expect(gets).toBe(1);

  missing = true;
  await page.clock.runFor(POLL_INTERVAL_MS + 500);
  await expect.poll(() => gets).toBe(2);

  // The 404 is terminal: a further minute of clock time must not produce more requests.
  await page.clock.runFor(POLL_INTERVAL_MS * 5);
  await page.waitForTimeout(300);
  expect(gets).toBe(2);
});

test("polling stops when the user leaves the scoring page (L-09f)", async ({ page, request }, testInfo) => {
  const session = await createRoundRobinSession(request, `Poll Leave ${testInfo.project.name}`);
  await page.clock.install();
  const polls = await countSessionPolls(page, session.session_id);

  await openSession(page, session.session_id, session.edit_token);
  await expect(page.getByRole("button", { name: "Back to Roster" })).toBeVisible();

  // Sanity: polling does run while the scoring page is open.
  await page.clock.runFor(POLL_INTERVAL_MS + 500);
  await expect.poll(() => polls.count).toBeGreaterThanOrEqual(2);

  await navigateToSection(page, "Players");
  await expect(page).toHaveURL(/\/players$/);
  await page.waitForTimeout(300);
  const afterLeaving = polls.count;

  await page.clock.runFor(POLL_INTERVAL_MS * 5);
  await page.waitForTimeout(300);
  expect(polls.count).toBe(afterLeaving);
});

test("polling pauses while the tab is hidden and resumes when visible (L-09f)", async ({ page, request }, testInfo) => {
  const session = await createRoundRobinSession(request, `Poll Hidden ${testInfo.project.name}`);
  await page.addInitScript(() => {
    window.__tabHidden = false;
    Object.defineProperty(document, "hidden", { configurable: true, get: () => window.__tabHidden });
  });
  await page.clock.install();
  const polls = await countSessionPolls(page, session.session_id);

  await openSession(page, session.session_id, session.edit_token);
  await expect(page.getByRole("button", { name: "Back to Roster" })).toBeVisible();

  await page.evaluate(() => {
    window.__tabHidden = true;
    document.dispatchEvent(new Event("visibilitychange"));
  });
  const beforeHidden = polls.count;
  await page.clock.runFor(POLL_INTERVAL_MS * 5);
  await page.waitForTimeout(300);
  expect(polls.count).toBe(beforeHidden);

  await page.evaluate(() => {
    window.__tabHidden = false;
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await page.clock.runFor(POLL_INTERVAL_MS + 500);
  await expect.poll(() => polls.count).toBeGreaterThan(beforeHidden);
});
