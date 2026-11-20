import { expect, test } from "@playwright/test";
import { navigateToSection } from "./helpers/navigation";
import { completeRoundRobinSession } from "./helpers/session";

test("player stats page shows completed-session analytics", async ({ page, request }) => {
  await completeRoundRobinSession(request, "Player Stats Complete");

  await page.goto("/");
  await navigateToSection(page, "Player Stats");

  await expect(page.getByRole("heading", { name: "Leaderboard" })).toBeVisible();
  const leaderboard = page.locator("section").filter({ has: page.getByRole("heading", { name: "Leaderboard" }) });
  await leaderboard.getByRole("button", { name: /^A\b/ }).click();
  const profileSection = page.locator("section").filter({ has: page.getByRole("heading", { name: "A", exact: true }) });
  await expect(profileSection.getByRole("heading", { name: "A", exact: true })).toBeVisible();
  await expect(profileSection.getByText("Sessions", { exact: true })).toBeVisible();
  await expect(profileSection.getByText("Matches", { exact: true })).toBeVisible();
  await expect(profileSection.getByText(/\d+ wins/, { exact: false }).first()).toBeVisible();
  await expect(profileSection.getByText("Last completed session:", { exact: false })).toBeVisible();
  await expect(profileSection.getByText("Most-played partner", { exact: true })).toBeVisible();
  await expect(profileSection.getByText("Best-performing partners for A")).toBeVisible();
  await expect(profileSection.getByText("% win rate", { exact: false }).first()).toBeVisible();
});

test("mobile player stats keeps leaderboard visible until a player is selected", async ({ page, request }, testInfo) => {
  test.skip(!["iphone", "android", "android-firefox"].includes(testInfo.project.name), "Mobile-only regression test");

  await completeRoundRobinSession(request, "Mobile Player Stats");

  await page.goto("/");
  await navigateToSection(page, "Player Stats");

  const leaderboardHeading = page.getByRole("heading", { name: "Leaderboard" });
  await expect(leaderboardHeading).toBeVisible();
  await expect(page.getByText("Select a player", { exact: true })).not.toBeVisible();

  await page.getByRole("button", { name: /^A\b/ }).click();
  await expect(page.getByRole("button", { name: "Back to leaderboard" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "A", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Back to leaderboard" }).click();
  await expect(leaderboardHeading).toBeVisible();
});
