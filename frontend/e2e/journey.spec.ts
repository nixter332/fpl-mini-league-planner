import { expect, test, type Page } from "@playwright/test";

// Nikhil's team and mini-league (CLAUDE.md). Uses the live (cached) FPL data via the backend.
const TEAM = process.env.E2E_TEAM ?? "5179483";
const LEAGUE = process.env.E2E_LEAGUE ?? "1883627";
const shot = (page: Page, name: string) => page.screenshot({ path: `e2e/screenshots/${name}.png`, fullPage: true });

test("league link → pick yourself → team → plans → plan detail", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Beat your mini-league/ })).toBeVisible();
  await shot(page, "01-main");

  await page.getByLabel("Paste a link or team ID").fill(`fantasy.premierleague.com/leagues/${LEAGUE}/standings/c`);
  await page.getByRole("button", { name: "Find" }).click();
  const members = page.getByTestId("league-members");
  await expect(members).toBeVisible();
  await shot(page, "02-main-league-members");

  await members.getByRole("button").filter({ hasText: "Nikhil" }).first().click();
  await page.getByRole("button", { name: "That's me, continue" }).click();
  await expect(page).toHaveURL(new RegExp(`/team/${TEAM}`));
  await expect(page.getByTestId("pitch-player")).toHaveCount(11);
  await shot(page, "03-team-gw-next");

  await page.getByRole("group", { name: "Gameweek" }).getByRole("button").nth(1).click();
  await page.getByRole("group", { name: "Show on pitch" }).getByRole("button", { name: "Rivals own" }).click();
  await expect(page.getByText(/^Owned \d+\/\d+$/).first()).toBeVisible();
  await shot(page, "04-team-gw2-rivals-own");

  await page.getByRole("link", { name: "See transfer plans" }).click();
  await expect(page.getByTestId("plan-card")).toHaveCount(3);
  await shot(page, "05-plans-balanced");

  await page.getByRole("group", { name: "Strategy" }).getByRole("button", { name: "Risky" }).click();
  await expect(page.getByTestId("plan-card")).toHaveCount(3);
  await shot(page, "06-plans-risky");

  await page.getByRole("link", { name: "View on pitch →" }).first().click();
  await expect(page.getByRole("heading", { name: /Risky · Plan 1/ })).toBeVisible();
  await expect(page.getByTestId("pitch-player")).toHaveCount(11);
  await shot(page, "07-plan-detail-after");
  await page.getByRole("group", { name: "Squad view" }).getByRole("button", { name: "Before" }).click();
  await shot(page, "08-plan-detail-before");
});

test("team ID, light theme and a bad link", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Paste a link or team ID").fill("https://example.com/not-fpl");
  await page.getByRole("button", { name: "Find" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "We accept" })).toBeVisible();
  await shot(page, "09-main-bad-link");

  await page.getByLabel("Paste a link or team ID").fill(TEAM);
  await page.getByRole("button", { name: "Find" }).click();
  await expect(page.getByTestId("pitch-player")).toHaveCount(11);
  await page.getByRole("button", { name: "Switch to light mode" }).click();
  await shot(page, "10-team-light");
});
