import { expect, test } from "@playwright/test";
import { createRoundRobinSession, openSession } from "./helpers/session";

function sessionUrlPattern(sessionId) {
  return new RegExp(`/api/sessions/${sessionId}(\\?|$)`);
}

// Fetch the real response for a stubbed route, optionally rewriting version/name.
async function fulfillWith(route, overrides = {}) {
  const response = await route.fetch();
  const body = await response.json();
  await route.fulfill({
    response,
    json: { ...body, ...overrides },
  });
}

function pill(page, name) {
  return page.locator("p.rounded-full", { hasText: name });
}

test("a slow response for session A never renders under the URL of session B (M-14a)", async ({ page, request }, testInfo) => {
  const nameA = `Race Alpha ${testInfo.project.name}`;
  const nameB = `Race Bravo ${testInfo.project.name}`;
  const sessionA = await createRoundRobinSession(request, nameA);
  const sessionB = await createRoundRobinSession(request, nameB);

  let releaseA;
  const gateA = new Promise((resolve) => {
    releaseA = resolve;
  });
  let sawA = false;
  await page.route(sessionUrlPattern(sessionA.session_id), async (route) => {
    sawA = true;
    await gateA;
    // The page aborts this request once session B takes over; fulfilling then throws.
    await fulfillWith(route).catch(() => {});
  });

  await openSession(page, sessionA.session_id, sessionA.edit_token);
  await expect.poll(() => sawA).toBe(true);

  // Client-side navigation to session B while A's response is still outstanding.
  await page.evaluate((path) => {
    window.history.pushState({}, "", path);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, `/sessions/${sessionB.session_id}?edit=${sessionB.edit_token}`);

  await expect(pill(page, nameB)).toBeVisible();

  // Now A's (older, slower) response finally arrives.
  releaseA();
  await page.waitForTimeout(400);

  await expect(page).toHaveURL(new RegExp(`/sessions/${sessionB.session_id}`));
  await expect(pill(page, nameB)).toBeVisible();
  await expect(page.getByText(nameA)).toHaveCount(0);
});

test("a delayed older-version poll response cannot overwrite newer state (M-14c)", async ({ page, request }, testInfo) => {
  const baseName = `Poll Version ${testInfo.project.name}`;
  const session = await createRoundRobinSession(request, baseName);
  const { session_id: sessionId, edit_token: editToken } = session;

  await page.clock.install();
  await openSession(page, sessionId, editToken);
  await expect(pill(page, baseName)).toBeVisible();

  let pollCount = 0;
  let olderServed;
  const olderServedPromise = new Promise((resolve) => {
    olderServed = resolve;
  });
  await page.route(sessionUrlPattern(sessionId), async (route) => {
    pollCount += 1;
    if (pollCount === 1) {
      await fulfillWith(route, { version: 50, name: "Newer Poll State" });
    } else {
      // A lagging replica / cache answers with an older version afterwards.
      await fulfillWith(route, { version: 40, name: "Older Poll State" });
      olderServed();
    }
  });

  await page.clock.runFor(13_000);
  await expect(pill(page, "Newer Poll State")).toBeVisible();

  await page.clock.runFor(13_000);
  await olderServedPromise;
  await page.waitForTimeout(400);

  await expect(pill(page, "Newer Poll State")).toBeVisible();
  await expect(page.getByText("Older Poll State")).toHaveCount(0);
});

test("polls do not pile up while one is still in flight (M-14b)", async ({ page, request }, testInfo) => {
  const session = await createRoundRobinSession(request, `Poll InFlight ${testInfo.project.name}`);
  const { session_id: sessionId, edit_token: editToken } = session;

  await page.clock.install();
  await openSession(page, sessionId, editToken);
  await expect(pill(page, `Poll InFlight ${testInfo.project.name}`)).toBeVisible();

  let pollCount = 0;
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  await page.route(sessionUrlPattern(sessionId), async (route) => {
    pollCount += 1;
    await gate;
    await fulfillWith(route).catch(() => {});
  });

  // Three poll intervals elapse while the first request is still outstanding.
  await page.clock.runFor(13_000);
  await expect.poll(() => pollCount).toBe(1);
  await page.clock.runFor(13_000);
  await page.clock.runFor(13_000);
  await page.waitForTimeout(300);
  expect(pollCount).toBe(1);

  release();
});
