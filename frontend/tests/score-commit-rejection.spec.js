import { readFile } from "node:fs/promises";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { createRoundRobinSession, openSession, postRoundAction } from "./helpers/session";

test("a failed score commit does not raise an unhandled promise rejection", async ({ page, request }, testInfo) => {
  const session = await createRoundRobinSession(request, `Rejection ${testInfo.project.name}`);
  const { session_id: sessionId, edit_token: editToken } = session;
  await postRoundAction(request, sessionId, editToken, "start-round", { stage: "league", round_index: 0 });

  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  const consoleErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await openSession(page, sessionId, editToken);
  const teamAInput = page.locator('input[type="number"]:not([disabled])').first();
  await expect(teamAInput).toBeVisible();

  await page.route("**/api/sessions/*/score?*", (route) =>
    route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "Score write exploded" }) })
  );
  await teamAInput.fill("21");
  await teamAInput.blur();

  // The failure is still surfaced to the user...
  await expect(page.getByText("Score write exploded")).toBeVisible();
  // ...but is not leaked as an unhandled rejection (the error is only logged).
  expect(pageErrors).toEqual([]);
  expect(consoleErrors.some((text) => text.includes("Score write exploded"))).toBeTruthy();
});

test("the never-used undoSharedSession client is gone", async () => {
  const source = await readFile(path.join(process.cwd(), "src", "api.js"), "utf8");
  expect(source).not.toContain("undoSharedSession");
  expect(source).not.toContain("/undo");
});
