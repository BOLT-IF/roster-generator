import { expect, test } from "@playwright/test";
import { createRoundRobinSession, openSession, postRoundAction, postScore } from "./helpers/session";

test("a failed score write rolls back, surfaces the error and keeps polling (H-07)", async ({ page, request }, testInfo) => {
  const session = await createRoundRobinSession(request, `Score Failure ${testInfo.project.name}`);
  const { session_id: sessionId, edit_token: editToken } = session;

  await postRoundAction(request, sessionId, editToken, "start-round", { stage: "league", round_index: 0 });

  await page.clock.install();
  await openSession(page, sessionId, editToken);

  const teamAInput = page.locator('input[type="number"]:not([disabled])').nth(0);
  const teamBInput = page.locator('input[type="number"]:not([disabled])').nth(1);
  await expect(teamAInput).toBeVisible();

  // Every single-score write fails with a server error.
  await page.route("**/api/sessions/*/score?*", (route) =>
    route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "Score write exploded" }) })
  );

  await teamAInput.fill("21");
  await teamAInput.blur();

  // The error is surfaced and the local cell goes back to the server value (empty).
  await expect(page.getByText("Score write exploded")).toBeVisible();
  await expect(teamAInput).toHaveValue("");

  // The failed edit must not leave a pending entry behind: a score changed on the
  // server by someone else shows up on the next poll.
  await page.unroute("**/api/sessions/*/score?*");
  await postScore(request, sessionId, editToken, {
    stage: "league",
    round_index: 0,
    court_index: 0,
    team_key: "teamB",
    value: 7,
  });
  await page.clock.runFor(40_000);
  await expect(teamBInput).toHaveValue("7");

  // End Round reflects the real server state (A is still empty), so it is not offered.
  await expect(page.getByRole("button", { name: /End Round/ }).first()).toBeDisabled();
});
