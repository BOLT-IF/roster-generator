import { expect, test } from "@playwright/test";
import { completeRoundRobinSession, openSession } from "./helpers/session";

test("mobile navigation overlays scoring panel tabs", async ({ page, request }, testInfo) => {
  test.skip(!["iphone", "android", "android-firefox"].includes(testInfo.project.name), "Mobile-only regression test");

  const session = await completeRoundRobinSession(request, "Mobile Nav Overlay");

  await openSession(page, session.session_id, session.edit_token);
  await expect(page.getByRole("button", { name: "Open navigation" })).toBeVisible();

  await page.getByRole("button", { name: "Open navigation" }).click();

  const nav = page.locator("#mobile-global-nav");
  const navButton = nav.getByRole("button", { name: "Planner" });
  const resultsTab = page.getByRole("tab", { name: "Results" });

  await expect(nav).toBeVisible();
  await expect(navButton).toBeVisible();
  await expect(resultsTab).toBeVisible();

  const navBox = await nav.boundingBox();
  const tabBox = await resultsTab.boundingBox();
  expect(navBox).not.toBeNull();
  expect(tabBox).not.toBeNull();

  const overlapLeft = Math.max(navBox.x, tabBox.x);
  const overlapTop = Math.max(navBox.y, tabBox.y);
  const overlapRight = Math.min(navBox.x + navBox.width, tabBox.x + tabBox.width);
  const overlapBottom = Math.min(navBox.y + navBox.height, tabBox.y + tabBox.height);

  const hasOverlap = overlapRight > overlapLeft && overlapBottom > overlapTop;
  if (!hasOverlap) {
    expect(navBox.y + navBox.height).toBeLessThanOrEqual(tabBox.y);
    return;
  }

  const probeX = overlapLeft + 12;
  const probeY = overlapTop + 12;

  const topElementText = await page.evaluate(({ x, y }) => {
    const el = document.elementFromPoint(x, y);
    return el?.textContent || "";
  }, { x: probeX, y: probeY });

  expect(topElementText).toContain("Planner");
});
