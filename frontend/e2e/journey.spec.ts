import { expect, test, type Page } from "@playwright/test";

// Nikhil's team and mini-league (CLAUDE.md). Uses the live (cached) FPL data via the backend.
const TEAM = process.env.E2E_TEAM ?? "5179483";
const LEAGUE = process.env.E2E_LEAGUE ?? "1883627";
const shot = (page: Page, name: string) => page.screenshot({ path: `e2e/screenshots/${name}.png`, fullPage: true });

const claudeOnly = !!process.env.E2E_CLAUDE; // with E2E_CLAUDE=1 only the reasons test runs, to keep Claude calls few

test("league link → pick yourself → team → plans → plan detail", async ({ page }) => {
  test.skip(claudeOnly);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Beat your mini-league/ })).toBeVisible();
  await shot(page, "01-main");

  await page.getByLabel("Paste a link or ID").fill(`fantasy.premierleague.com/leagues/${LEAGUE}/standings/c`);
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
  await expect(page.getByTestId("plan-card").first()).toBeVisible(); // 1-3 plans (a timed-out plan is dropped)
  await expect(page).toHaveURL(/strategy=protect/); // Nikhil is 1st, so plans start on Protect lead
  await shot(page, "05-plans-protect");

  await page.getByRole("group", { name: "Strategy" }).getByRole("button", { name: "Risky" }).click();
  await expect(page).toHaveURL(/strategy=risky/);
  await expect(page.getByRole("heading", { name: /Transfer plans · GW/ })).toBeVisible();
  await expect(page.getByTestId("plan-card").first()).toBeVisible(); // 1-3 plans (a timed-out plan is dropped)
  await shot(page, "06-plans-risky");

  await page.getByRole("link", { name: "View on pitch →" }).first().click();
  await expect(page.getByRole("heading", { name: /Risky · Plan 1/ })).toBeVisible();
  await expect(page.getByTestId("pitch-player")).toHaveCount(11);
  await shot(page, "07-plan-detail-after");
  await page.getByRole("group", { name: "Squad view" }).getByRole("button", { name: "Before" }).click();
  await shot(page, "08-plan-detail-before");
});

test("team ID, light theme and a bad link", async ({ page }) => {
  test.skip(claudeOnly);
  await page.goto("/");
  await page.getByLabel("Paste a link or ID").fill("https://example.com/not-fpl");
  await page.getByRole("button", { name: "Find" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "We accept" })).toBeVisible();
  await shot(page, "09-main-bad-link");

  await page.getByLabel("Paste a link or ID").fill(TEAM);
  await page.getByRole("button", { name: "Find" }).click();
  await expect(page.getByTestId("pitch-player")).toHaveCount(11);
  await page.getByRole("button", { name: "Switch to light mode" }).click();
  await shot(page, "10-team-light");
});

// E2E_CLAUDE=1 npx playwright test -g reasons
// Uses real Claude reasons for the Balanced plans (cached after the first run).
test.describe("reasons", () => {
  test.skip(!process.env.E2E_CLAUDE, "Set E2E_CLAUDE=1 to include Claude reasons (costs a few cents the first time).");
  test("Claude reasons on the plans and plan detail", async ({ page }) => {
    test.setTimeout(240_000);
    await page.goto(`/plans?team=${TEAM}&league=${LEAGUE}&strategy=balanced&horizon=4&hits=0`);
    await expect(page.getByTestId("plan-card").first()).toBeVisible(); // 1-3 plans (a timed-out plan is dropped)
    await expect(page.getByTestId("why")).toHaveCount(3, { timeout: 180_000 });
    await shot(page, "11-plans-reasons");
    await page.getByRole("link", { name: "View on pitch →" }).first().click();
    await expect(page.getByTestId("why")).toHaveCount(1);
    await shot(page, "12-plan-detail-reason");
  });
});

test("chips: chips left, advice and playing your Free Hit", async ({ page }) => {
  test.skip(claudeOnly);
  test.setTimeout(240_000);
  await page.goto(`/team/${TEAM}?league=${LEAGUE}`);
  await expect(page.getByTestId("chips-left")).toContainText("Free Hit");
  await page.goto(`/plans?team=${TEAM}&league=${LEAGUE}&strategy=protect&horizon=4&hits=0`);
  await expect(page.getByTestId("plan-card").first()).toBeVisible(); // 1-3 plans (a timed-out plan is dropped)
  await expect(page.getByTestId("chip-controls")).toBeVisible();
  await expect(page.getByTestId("chip-advice")).toBeVisible({ timeout: 120_000 });
  await shot(page, "13-plans-chips");
  const freeHit = page.getByLabel("Free Hit", { exact: true });
  const firstGw = await freeHit.locator("option").nth(1).getAttribute("value");
  await freeHit.selectOption(firstGw!);
  await expect(page).toHaveURL(new RegExp(`freehit=${firstGw}`));
  await expect(page.getByTestId("plan-chips").first()).toContainText(`Free Hit · GW${firstGw}`, { timeout: 120_000 });
  await shot(page, "14-plans-free-hit");
});

test("league by new-style link and by number", async ({ page }) => {
  test.skip(claudeOnly);
  await page.goto("/");
  await page.getByLabel("Paste a link or ID").fill(`https://fantasy.premierleague.com/en/leagues/${LEAGUE}/standings/c`);
  await page.getByRole("button", { name: "Find" }).click();
  await expect(page.getByTestId("league-members")).toBeVisible();

  await page.getByLabel("Paste a link or ID").fill(LEAGUE);
  await page.getByRole("button", { name: "Find" }).click();
  // The number may also be someone's team ID; then the app asks which was meant.
  const choice = page.getByTestId("resolve-choice");
  const members = page.getByTestId("league-members");
  await expect(choice.or(members)).toBeVisible();
  if (await choice.isVisible()) {
    await shot(page, "15-main-team-or-league");
    await choice.getByRole("button", { name: /League/ }).click();
  }
  await expect(members).toBeVisible();
  await expect(members).toContainText("Nikhil");
});

test("pitch stays put across gameweeks, swaps are labelled, team is remembered", async ({ page }) => {
  test.skip(claudeOnly);
  test.setTimeout(240_000);
  await page.goto(`/team/${TEAM}?league=${LEAGUE}`);
  await expect(page.getByTestId("pitch-player")).toHaveCount(11);
  const names = async () => page.getByTestId("pitch-player").locator("div.truncate.bg-white").allInnerTexts();
  const gw1 = await names();
  await page.getByRole("group", { name: "Gameweek" }).getByRole("button").nth(1).click();
  const gw2 = await names();
  const shared = (a: string[], b: string[]) => a.filter((n) => b.includes(n));
  expect(shared(gw1, gw2)).toEqual(shared(gw2, gw1)); // same players keep the same order

  await page.goto(`/plans/1?team=${TEAM}&league=${LEAGUE}&strategy=protect&horizon=4&hits=0`);
  await expect(page.getByTestId("pitch-player")).toHaveCount(11, { timeout: 120_000 });
  const subtitle = await page.locator("h1 + div").innerText();
  if (!subtitle.startsWith("Roll")) {
    await expect(page.getByText(/^for /).first()).toBeVisible();
    await shot(page, "16-plan-after-swaps");
    await page.getByRole("group", { name: "Squad view" }).getByRole("button", { name: "Before" }).click();
    await expect(page.getByText("OUT", { exact: true }).first()).toBeVisible();
    await shot(page, "17-plan-before-out");
  }

  await page.goto("/");
  await expect(page.getByTestId("recent-team")).toContainText("Open my team");
  await shot(page, "18-main-welcome-back");
});

test("feedback on a plan, and no tracking without a PostHog key", async ({ page }) => {
  test.skip(claudeOnly);
  test.setTimeout(240_000);
  const posthogCalls: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("posthog")) posthogCalls.push(r.url());
  });
  const feedback = page.waitForRequest((r) => r.url().endsWith("/api/feedback") && r.method() === "POST");
  await page.goto(`/plans?team=${TEAM}&league=${LEAGUE}&strategy=protect&horizon=4&hits=0`);
  const box = page.getByTestId("plan-feedback").first();
  await expect(box).toBeVisible({ timeout: 120_000 });
  await box.getByRole("button", { name: "Not useful" }).click();
  const body = JSON.parse((await feedback).postData() ?? "{}");
  expect(body).toMatchObject({ kind: "plan", useful: false, context: { page: "plans", strategy: "protect", rank: 1 } });
  expect(JSON.stringify(body)).not.toContain(TEAM); // no team ID in feedback
  await box.getByLabel("Feedback note").fill("Captain choice was confusing");
  await box.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Thanks for the feedback!").first()).toBeVisible();
  await shot(page, "19-plan-feedback");
  expect(posthogCalls).toEqual([]);
});
