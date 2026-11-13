import { expect, test } from "@playwright/test";
import { addPlannerPlayers, pairPlayers, getFirstCourtPlayerButtons } from "./helpers/planner";

// C-1 PR3 (AC-W2..W4, PERF-2): the planner surfaces the structured fairness
// report - one line per slipped rule, naming who is affected, marking
// arithmetically forced unevenness as unavoidable - without ever blocking
// Start Session, recomputed after manual roster edits, plus a non-blocking
// generate spinner that only appears after one second.

async function setNumeric(page, label, value) {
  const input = page.getByLabel(`Decrease ${label}`).locator("xpath=following-sibling::input[1]");
  await input.click();
  await input.press("ControlOrMeta+a");
  await input.pressSequentially(String(value));
  await input.blur();
}

// The Organiser shape: 12 players in 6 fixed pairs, 2 courts, 13 rounds,
// pair target 8 - every match pair-vs-pair, with 26 matches over 15
// matchups forcing an unavoidable 11x2 + 4x1 split.
async function generateOrganiserRoster(page, request, testInfo) {
  const players = await addPlannerPlayers(page, request, testInfo.project.name, 12, "FRW");
  for (let i = 0; i < 12; i += 2) {
    await pairPlayers(page, players[i], players[i + 1]);
  }
  await page.getByRole("button", { name: "Next: Settings" }).click();
  await page.getByRole("button", { name: "Increase Courts" }).click();
  await setNumeric(page, "Rounds", 13);
  await setNumeric(page, "Pair Games", 8);
  await page.getByRole("button", { name: "Next: Review" }).click();
  await page.getByRole("button", { name: "Generate Roster" }).click();
  await expect(page.getByText("Roster edits")).toBeVisible();
  return players;
}

test("fairness report shows named, unavoidable matchup unevenness under the roster (AC-W2)", async ({ page, request }, testInfo) => {
  await generateOrganiserRoster(page, request, testInfo);

  const fairnessPanel = page.locator("[data-testid='fairness-report']");
  await expect(fairnessPanel).toBeVisible();

  // One line per slipped rule, friendly label, naming who is affected.
  const matchupLine = fairnessPanel.getByText("Matchup balance", { exact: false });
  await expect(matchupLine).toBeVisible();
  await expect(fairnessPanel.getByText(/unavoidable/i).first()).toBeVisible();
  // The affected matchups are named (shorted pairs are listed).
  await expect(fairnessPanel.getByText(/vs/, { exact: false }).first()).toBeVisible();
  // The rest side is clean on this config: no rest lines.
  await expect(fairnessPanel.getByText("Rest balance", { exact: false })).toHaveCount(0);
  await expect(fairnessPanel.getByText("Rest group variety", { exact: false })).toHaveCount(0);
});

test("Start Session stays enabled while fairness issues are shown (AC-W3)", async ({ page, request }, testInfo) => {
  await generateOrganiserRoster(page, request, testInfo);

  await expect(page.locator("[data-testid='fairness-report']")).toBeVisible();
  await expect(page.getByText("Matchup balance", { exact: false }).first()).toBeVisible();
  const startButton = page.getByRole("button", { name: "Start Session" });
  await expect(startButton).toBeEnabled();
});

test("fairness is recomputed after a manual roster edit (AC-W4)", async ({ page, request }, testInfo) => {
  await generateOrganiserRoster(page, request, testInfo);
  await expect(page.locator("[data-testid='fairness-report']")).toBeVisible();

  // Tamper with the revalidate response to prove the panel renders the
  // recomputed report from the server, not a stale copy: inject a rest
  // balance issue that only exists in the post-swap response.
  await page.route("**/api/rosters/revalidate", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.fairness = {
      rest_spread: 3,
      corest_spread: 0,
      matchup_spread: 1,
      issues: [
        {
          rule: "rest_spread",
          summary: "XX1 rests 9x while XX2 rests 5x",
          affected: ["XX1"],
          unavoidable: false,
        },
      ],
    };
    await route.fulfill({ response, json: body });
  });

  const { teamA, teamB } = await getFirstCourtPlayerButtons(page);
  // nth(0) is the team-swap overlay button; players are nth(1) and nth(2).
  await teamA.nth(1).click();
  await teamB.nth(1).click();

  await expect(page.getByText("Roster edits")).toBeVisible();
  const fairnessPanel = page.locator("[data-testid='fairness-report']");
  await expect(fairnessPanel.getByText("Rest balance", { exact: false })).toBeVisible();
  await expect(fairnessPanel.getByText(/XX1 rests 9x/)).toBeVisible();
});

test("generate spinner appears only after one second and never blocks review content (AC-PERF-2)", async ({ page, request }, testInfo) => {
  const players = await addPlannerPlayers(page, request, testInfo.project.name, 12, "SPN");
  await page.getByRole("button", { name: "Next: Settings" }).click();
  await page.getByRole("button", { name: "Increase Courts" }).click();
  await page.getByRole("button", { name: "Next: Review" }).click();

  await page.route("**/api/generate", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1800));
    const response = await route.fetch();
    await route.fulfill({ response });
  });

  await page.getByRole("button", { name: "Generate Roster" }).click();

  // Under one second: no spinner, and the review content stays rendered.
  // (Explicit wait + immediate count: a retrying assertion would wrongly
  // pass once the spinner legitimately appears at the one-second mark.)
  await page.waitForTimeout(600);
  expect(await page.locator("[data-testid='generate-spinner']").count()).toBe(0);
  await expect(page.getByText("Generate a roster to preview the rounds and courts here.")).toBeVisible();

  // After one second: the spinner appears on the button - while the review
  // content is still there (non-blocking).
  await expect(page.locator("[data-testid='generate-spinner']")).toBeVisible({ timeout: 3000 });
  await expect(page.getByText("Generate a roster to preview the rounds and courts here.")).toBeVisible();

  // Response arrives: spinner gone, roster rendered, session name editable.
  await expect(page.locator("[data-testid='generate-spinner']")).toHaveCount(0, { timeout: 10000 });
  await expect(page.getByText("Roster edits")).toBeVisible();
  await expect(page.getByLabel("Session name")).toBeVisible();
});
