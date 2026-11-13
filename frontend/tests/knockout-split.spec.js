import { expect, test } from "@playwright/test";
import {
  createSharedSession,
  generateRoster,
  openSession,
  postRoundAction,
  postScore,
} from "./helpers/session";

// C-2 follow-up (AC-KO1/KO2): on a single court, the two semifinal matches
// cannot share a round - they split into "Semifinals, part 1", "Semifinals,
// part 2" and then the Final. The frontend bracket, the backend stats
// mirror and the completion count must stay in lockstep. Verified red on
// main, which renders an unsplit 2-match round the 1-court session can
// never finish.

async function createOneCourtKnockoutSession(request, name) {
  const roster = await generateRoster(request, {
    players: ["KO A", "KO B", "KO C", "KO D", "KO E", "KO F", "KO G", "KO H"],
    fixed_pairs: [
      ["KO A", "KO B"],
      ["KO C", "KO D"],
      ["KO E", "KO F"],
      ["KO G", "KO H"],
    ],
    num_courts: 1,
    court_numbers: ["1"],
    draw_type: "league_knockout",
    league_meetings: 1,
    pair_games: 3,
  });

  return createSharedSession(request, {
    name,
    roster,
    drawConfig: {
      draw_type: "league_knockout",
      league_meetings: 1,
      knockout_qualifiers: 4,
    },
    fixed_pairs: [
      ["KO A", "KO B"],
      ["KO C", "KO D"],
      ["KO E", "KO F"],
      ["KO G", "KO H"],
    ],
    pair_games: 3,
  });
}

test("single-court knockout splits the semifinals and finishes with a champion", async ({ page, request }, testInfo) => {
  const session = await createOneCourtKnockoutSession(
    request,
    `KO split ${testInfo.project.name}`
  );
  const { session_id: sessionId, edit_token: editToken } = session;

  // Play the six league rounds (one match each) through the API, giving
  // pair A/B a perfect record so seeds are deterministic.
  const leagueRounds = session.roster.rounds;
  for (let roundIndex = 0; roundIndex < leagueRounds.length; roundIndex += 1) {
    await postRoundAction(request, sessionId, editToken, "start-round", {
      stage: "league",
      round_index: roundIndex,
    });
    const courts = leagueRounds[roundIndex].courts;
    for (let courtIndex = 0; courtIndex < courts.length; courtIndex += 1) {
      const court = courts[courtIndex];
      if (court.friendly) continue;
      const pairOnePlaysA =
        court.team_a.includes("KO A") || court.team_a.includes("KO B");
      const values = pairOnePlaysA ? [21, 15] : [19, 21];
      await postScore(request, sessionId, editToken, {
        stage: "league",
        round_index: roundIndex,
        court_index: courtIndex,
        team_key: "teamA",
        value: values[0],
      });
      await postScore(request, sessionId, editToken, {
        stage: "league",
        round_index: roundIndex,
        court_index: courtIndex,
        team_key: "teamB",
        value: values[1],
      });
    }
    await postRoundAction(request, sessionId, editToken, "end-round", {
      stage: "league",
      round_index: roundIndex,
    });
  }

  await openSession(page, sessionId, editToken);
  await expect(page.getByText("Upcoming Knockout Rounds")).toBeVisible();
  await page.getByText("Upcoming Knockout Rounds").click();

  // The split bracket: part 1 first, one match only (AC-KO1).
  await expect(
    page.getByRole("heading", { name: "Semifinals, part 1", exact: true })
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Semifinals, part 2", exact: true })
  ).toBeVisible();
  await expect(page.getByText("Semifinals", { exact: true })).toHaveCount(0);

  // Play both parts through the API, then reopen: the final must exist.
  for (const roundIndex of [0, 1]) {
    await postRoundAction(request, sessionId, editToken, "start-round", {
      stage: "knockout",
      round_index: roundIndex,
    });
    await postScore(request, sessionId, editToken, {
      stage: "knockout",
      round_index: roundIndex,
      court_index: 0,
      team_key: "teamA",
      value: 21,
    });
    await postScore(request, sessionId, editToken, {
      stage: "knockout",
      round_index: roundIndex,
      court_index: 0,
      team_key: "teamB",
      value: 15,
    });
    await postRoundAction(request, sessionId, editToken, "end-round", {
      stage: "knockout",
      round_index: roundIndex,
    });
  }

  await openSession(page, sessionId, editToken);
  await expect(
    page.getByRole("heading", { name: /Start Final when you are ready/ })
  ).toBeVisible();

  // Play the final and confirm the session completes with a champion
  // (KO A / KO B won every match).
  await postRoundAction(request, sessionId, editToken, "start-round", {
    stage: "knockout",
    round_index: 2,
  });
  await postScore(request, sessionId, editToken, {
    stage: "knockout",
    round_index: 2,
    court_index: 0,
    team_key: "teamA",
    value: 21,
  });
  await postScore(request, sessionId, editToken, {
    stage: "knockout",
    round_index: 2,
    court_index: 0,
    team_key: "teamB",
    value: 15,
  });
  await postRoundAction(request, sessionId, editToken, "end-round", {
    stage: "knockout",
    round_index: 2,
  });

  await openSession(page, sessionId, editToken);
  await expect(page.getByRole("heading", { name: "Session complete" })).toBeVisible({
    timeout: 15000,
  });
  // The champion pair (KO A / KO B) won every match they played.
  await expect(page.getByText("Playoffs complete. This pair won the final.")).toBeVisible();
});
