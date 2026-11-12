import { expect, test } from "@playwright/test";
import { navigateToSection } from "./helpers/navigation";
import { createSharedSession, generateRoster, postRoundAction, postScore } from "./helpers/session";

test("editing a player keeps existing completed stats mapped to the same player", async ({ page, request }, testInfo) => {
  const suffix = testInfo.project.name;
  const roster = await generateRoster(request, {
    players: [`Legacy Alpha ${suffix}`, `Legacy Bravo ${suffix}`, `Legacy Charlie ${suffix}`, `Legacy Delta ${suffix}`],
    num_courts: 1,
    court_numbers: ["1"],
    rounds: 1,
    seed: 7,
  });

  const session = await createSharedSession(request, {
    name: `Legacy Edit Session ${suffix}`,
    roster,
    drawConfig: {
      draw_type: "round_robin",
      league_meetings: 1,
      knockout_qualifiers: 4,
    },
  });

  await postRoundAction(request, session.session_id, session.edit_token, "start-round", {
    stage: "league",
    round_index: 0,
  });
  await postScore(request, session.session_id, session.edit_token, {
    stage: "league",
    round_index: 0,
    court_index: 0,
    team_key: "teamA",
    value: 21,
  });
  await postScore(request, session.session_id, session.edit_token, {
    stage: "league",
    round_index: 0,
    court_index: 0,
    team_key: "teamB",
    value: 12,
  });
  await postRoundAction(request, session.session_id, session.edit_token, "end-round", {
    stage: "league",
    round_index: 0,
  });

  await page.goto("/");
  await navigateToSection(page, "Players");

  const directorySection = page.locator("section").filter({ has: page.getByRole("heading", { name: "Registered players" }) });
  const directoryCard = directorySection.locator("div.rounded-2xl").filter({ hasText: `Legacy Alpha ${suffix}` }).first();
  await directoryCard.scrollIntoViewIfNeeded();
  await directoryCard.getByRole("button", { name: "Edit" }).click();

  await page.getByLabel("Full Name").last().fill(`Alpha Prime ${suffix}`);
  await page.getByLabel("Short Name").last().fill(`AP${suffix}`);
  await page.getByRole("button", { name: "Save Changes" }).click();

  await expect(page.getByText(`Alpha Prime ${suffix}`)).toBeVisible();
  const primeCard = directorySection.locator("div.rounded-2xl").filter({ hasText: `Alpha Prime ${suffix}` }).first();
  await expect(primeCard.getByText("Also matched from older names:", { exact: false })).toBeVisible();

  await navigateToSection(page, "Player Stats");
  await expect(page.getByRole("button", { name: new RegExp(`Alpha Prime ${suffix}`) })).toBeVisible();
});
