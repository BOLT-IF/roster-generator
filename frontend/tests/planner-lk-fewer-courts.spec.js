import { expect, test } from "@playwright/test";
import { createPlayer } from "./helpers/session";

// C-2 PR3 (AC-R1, AC-R2, AC-F3): league+knockout courts are a free choice
// from 1 up to pairs/2, rounds derive as ceil(matches/courts) and update
// live, and friendlies are labeled on the roster.
//
// Setup uses the same localStorage seeding as planner-fairness-warnings:
// pairing players through the UI re-renders the list after every pairing
// and timed out on slow CI runners three times before (the pairing UI
// itself is covered by planner-pair-dissolve and planner-roster-editing).

const PLANNER_STORAGE_KEY = "badminton-roster:planner";

async function domClick(locator) {
  await locator.waitFor({ state: "visible", timeout: 10000 });
  await locator.evaluate((el) => el.click());
}

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

function courtsInput(page) {
  return page.getByLabel("Decrease Courts").locator("xpath=following-sibling::input[1]");
}

async function setCourts(page, value) {
  const input = courtsInput(page);
  await input.click();
  await input.press("ControlOrMeta+a");
  await input.pressSequentially(String(value));
  await input.blur();
}

test("six pairs on two courts: derived rounds, no court pinning, friendly labeled", async ({ page, request }, testInfo) => {
  const players = await seedPlannerWithPairs(page, request, testInfo, 12, "LK6");
  await page.goto("/");
  await expect(page.getByText(players[0].short_name, { exact: false }).first()).toBeVisible();
  await domClick(page.getByRole("button", { name: "Next: Settings" }));

  await domClick(page.getByRole("button", { name: /League \+ Knockout/ }));

  // Courts stay a free choice: 6 pairs allow up to 3, two is fine (AC-R2).
  await setCourts(page, 2);
  await expect(courtsInput(page)).toHaveValue("2");

  // Rounds derive as ceil(15 / 2) = 8 with exactly one friendly (AC-R1/D3).
  await expect(page.getByText("8 rounds (6 teams, play once, 2 courts, 1 friendly)")).toBeVisible();

  await domClick(page.getByRole("button", { name: "Next: Review" }));
  await domClick(page.getByRole("button", { name: "Generate Roster" }));
  await expect(page.getByRole("button", { name: "Start Session" })).toBeEnabled();
  await expect(page.getByText("Roster could not be generated")).toHaveCount(0);

  // The friendly is labeled on the roster (AC-F3). Desktop and mobile views
  // both render the badge; exactly one is visible per viewport, so assert
  // presence in the DOM rather than visibility.
  expect(await page.getByText("Friendly", { exact: true }).count()).toBeGreaterThanOrEqual(1);
  // Fairness issues never block: Start stays enabled.
  await expect(page.getByRole("button", { name: "Start Session" })).toBeEnabled();
});

test("fewer courts stretch the league and the preview updates live", async ({ page, request }, testInfo) => {
  const players = await seedPlannerWithPairs(page, request, testInfo, 10, "LK5");
  await page.goto("/");
  await expect(page.getByText(players[0].short_name, { exact: false }).first()).toBeVisible();
  await domClick(page.getByRole("button", { name: "Next: Settings" }));
  await domClick(page.getByRole("button", { name: /League \+ Knockout/ }));

  // 5 pairs / 2 courts: 10 matches, 5 rounds, no friendlies.
  await setCourts(page, 2);
  await expect(page.getByText("5 rounds (5 teams, play once, 2 courts)")).toBeVisible();

  // Play Twice doubles the matches: 10 rounds.
  await domClick(page.getByRole("button", { name: "Play Twice" }));
  await expect(page.getByText("10 rounds (5 teams, play twice, 2 courts)")).toBeVisible();

  // One court stretches the same league to 10 rounds (play once again).
  await domClick(page.getByRole("button", { name: "Play Once" }));
  await setCourts(page, 1);
  await expect(page.getByText("10 rounds (5 teams, play once, 1 court)")).toBeVisible();
});
