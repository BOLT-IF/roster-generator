import { expect, test } from "@playwright/test";

// The hamburger menu only exists below the md breakpoint, so run at a phone-sized
// viewport on every project (instead of skipping on desktop).
test.use({ viewport: { width: 390, height: 844 } });

test("tapping the page below the header closes the mobile navigation (M-25/M-26)", async ({ page }) => {
  await page.goto("/planner");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(page.locator("#mobile-global-nav")).toBeVisible();

  // The backdrop must cover the whole viewport, not just the header area.
  const viewport = page.viewportSize();
  const backdrop = page.locator("div.fixed.inset-0[aria-hidden='true']");
  const box = await backdrop.boundingBox();
  expect(box).not.toBeNull();
  expect(box.height).toBeGreaterThanOrEqual(viewport.height - 1);
  expect(box.width).toBeGreaterThanOrEqual(viewport.width - 1);

  // Tap the page near the bottom of the screen, well below the header and menu.
  await page.mouse.click(8, viewport.height - 8);
  await expect(page.locator("#mobile-global-nav")).toHaveCount(0);
});
