import { expect, test } from "@playwright/test";
import {
  createKnockoutSession,
  openSession,
  postRoundAction,
  postScore,
} from "./helpers/session";

async function scoreLeagueRound(request, sessionId, editToken) {
  await postRoundAction(request, sessionId, editToken, "start-round", { stage: "league", round_index: 0 });
  for (const courtIndex of [0, 1]) {
    await postScore(request, sessionId, editToken, { stage: "league", round_index: 0, court_index: courtIndex, team_key: "teamA", value: 21 });
    await postScore(request, sessionId, editToken, { stage: "league", round_index: 0, court_index: courtIndex, team_key: "teamB", value: 10 + courtIndex });
  }
  await postRoundAction(request, sessionId, editToken, "end-round", { stage: "league", round_index: 0 });
}

test("a stored knockout score row beyond the round's court count does not blank the real scores (phantom court)", async ({ page, request }, testInfo) => {
  const session = await createKnockoutSession(request, `Phantom Court ${testInfo.project.name}`);
  const { session_id: sessionId, edit_token: editToken } = session;

  await scoreLeagueRound(request, sessionId, editToken);
  await postRoundAction(request, sessionId, editToken, "start-round", { stage: "knockout", round_index: 0 });
  await postScore(request, sessionId, editToken, { stage: "knockout", round_index: 0, court_index: 0, team_key: "teamA", value: 15 });
  await postScore(request, sessionId, editToken, { stage: "knockout", round_index: 0, court_index: 0, team_key: "teamB", value: 12 });

  // Make the server payload carry a phantom third court row for the 2-match semifinal.
  await page.route(new RegExp(`/api/sessions/${sessionId}(\\?.*)?$`), async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const response = await route.fetch();
    const body = await response.json();
    const rows = body.knockout_scores_by_round?.[0];
    if (rows && rows.length === 2) {
      rows.push({ teamA: 3, teamB: 4 });
    }
    await route.fulfill({ response, json: body });
  });

  await openSession(page, sessionId, editToken);

  const liveInputs = page.locator('input[type="number"]:not([disabled])');
  // Exactly the 2 real matches are rendered (4 inputs), not 3 courts.
  await expect(liveInputs).toHaveCount(4);
  // The real scores are still shown.
  await expect(liveInputs.nth(0)).toHaveValue("15");
  await expect(liveInputs.nth(1)).toHaveValue("12");

  // And typing into a real input sticks.
  await liveInputs.nth(2).fill("21");
  await expect(liveInputs.nth(2)).toHaveValue("21");
});
