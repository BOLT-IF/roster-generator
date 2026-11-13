import { expect, test } from "@playwright/test";
import { addPlannerPlayers, getFirstCourtPlayerButtons } from "./helpers/planner";
import { createPlayer } from "./helpers/session";

const PLANNER_STORAGE_KEY = "badminton-roster:planner";

// Slow CI runners can stall Playwright's actionability checks (visible /
// enabled / stable) indefinitely on these small setup targets, even when
// the element is plainly on screen. Setup clicks are therefore dispatched
// directly on the DOM element - deterministic, no actionability waiting -
// while the real verification stays with the expect() assertions below.
async function domClick(locator) {
  await locator.waitFor({ state: "visible", timeout: 10000 });
  await locator.evaluate((el) => el.click());
}

// Pairing six pairs through the UI clicks 24 cards through a list that
// re-renders after every pairing - three CI runners in a row timed out
// there. The pairing UI itself is covered by planner-pair-dissolve and
// planner-roster-editing; this spec cares about the fairness panel, so it
// seeds the planner state (selection + pairs) directly into localStorage
// before the app boots - deterministic and fast on any runner.
async function seedPlannerWithPairs(page, request, testInfo, count, prefix) {
  const players = [];
  for (let index = 1; index <= count; index += 1) {
    players.push(
      await createPlayer(request, {
        fullName: `${prefix} Player ${index} ${testInfo.project.name}`,
        shortName: `${prefix}${index}${testInfo.project.name}`,
      })
    );
  }
  const ids = players.map((player) => player.player_id);
  const fixedPairIds = [];
  for (let index = 0; index < count; index += 2) {
    fixedPairIds.push([ids[index], ids[index + 1]].sort());
  }
  const state = {
    selectedPlayerIds: ids,
    fixedPairIds,
    config: {
      draw_type: "round_robin",
      league_meetings: 1,
      knockout_qualifiers: 4,
      num_courts: 1,
      rounds: 10,
      pair_games: 3,
      // Pair Start Round 1 matches the field-scenario shape (the UI default
      // of 5 splits the co-rest phases and adds warnings this spec isn't
      // about).
      pair_start_round: 1,
      max_consecutive_rest: 1,
      limits: {},
      court_numbers: ["1"],
      seed: 1,
    },
    roster: null,
    generatedRosterBaseline: null,
    rosterSignature: null,
    hasManualRosterEdits: false,
  };
  await page.addInitScript((payload) => {
    window.localStorage.setItem(payload.key, JSON.stringify(payload.state));
  }, { key: PLANNER_STORAGE_KEY, state });
  return players;
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
  const players = await seedPlannerWithPairs(page, request, testInfo, 12, "FRW");
  await page.goto("/");
  await expect(page.getByText(players[0].short_name, { exact: false }).first()).toBeVisible();
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
