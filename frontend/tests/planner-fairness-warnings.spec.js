import { expect, test } from "@playwright/test";
import { addPlannerPlayers, getFirstCourtPlayerButtons } from "./helpers/planner";

// Slow CI runners can stall Playwright's actionability checks (visible /
// enabled / stable) indefinitely on these small setup targets, even when
// the element is plainly on screen. Setup clicks are therefore dispatched
// directly on the DOM element - deterministic, no actionability waiting -
// while the real verification stays with the expect() assertions below.
async function domClick(locator) {
  await locator.waitFor({ state: "visible", timeout: 10000 });
  await locator.evaluate((el) => el.click());
}

// Pairing six pairs in a row re-renders the selected-players list after
// every pairing; later cards may still be settling, so retry around the
// click while the list redraws.
async function pairPlayersReliably(page, first, second) {
  for (const player of [first, second]) {
    const target = page.getByText(player.fullName, { exact: true });
    let clicked = false;
    for (let attempt = 0; attempt < 4 && !clicked; attempt += 1) {
      try {
        await target.scrollIntoViewIfNeeded({ timeout: 5000 });
        await target.evaluate((el) => el.click());
        clicked = true;
      } catch {
        await page.waitForTimeout(600);
      }
    }
    if (!clicked) {
      throw new Error(`could not click ${player.fullName} in the pairing list`);
    }
  }
}

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
    await pairPlayersReliably(page, players[i], players[i + 1]);
  }
  await domClick(page.getByRole("button", { name: "Next: Settings" }));
  await domClick(page.getByRole("button", { name: "Increase Courts" }));
  await setNumeric(page, "Rounds", 13);
  await setNumeric(page, "Pair Games", 8);
  await domClick(page.getByRole("button", { name: "Next: Review" }));
  await domClick(page.getByRole("button", { name: "Generate Roster" }));
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
  await domClick(teamA.nth(1));
  await domClick(teamB.nth(1));

  await expect(page.getByText("Roster edits")).toBeVisible();
  const fairnessPanel = page.locator("[data-testid='fairness-report']");
  await expect(fairnessPanel.getByText("Rest balance", { exact: false })).toBeVisible();
  await expect(fairnessPanel.getByText(/XX1 rests 9x/)).toBeVisible();
});

test("generate spinner appears only after one second and never blocks review content (AC-PERF-2)", async ({ page, request }, testInfo) => {
  const players = await addPlannerPlayers(page, request, testInfo.project.name, 12, "SPN");
  await domClick(page.getByRole("button", { name: "Next: Settings" }));
  await domClick(page.getByRole("button", { name: "Increase Courts" }));
  await domClick(page.getByRole("button", { name: "Next: Review" }));

  await page.route("**/api/generate", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1800));
    const response = await route.fetch();
    await route.fulfill({ response });
  });

  await domClick(page.getByRole("button", { name: "Generate Roster" }));

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
