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

test("chips: chips left and playing your Free Hit", async ({ page }) => {
  test.skip(claudeOnly);
  test.setTimeout(240_000);
  await page.goto(`/team/${TEAM}?league=${LEAGUE}`);
  await expect(page.getByTestId("team-budget")).toContainText("free transfer"); // next to the tiles now
  await expect(page.getByTestId("chips-left")).not.toBeVisible(); // folded away
  await page.getByTestId("team-details").locator("summary").click();
  await expect(page.getByTestId("chips-left")).toContainText("Free Hit");
  await page.goto(`/plans?team=${TEAM}&league=${LEAGUE}&strategy=protect&horizon=4&hits=0`);
  await expect(page.getByTestId("plan-card").first()).toBeVisible(); // 1-3 plans (a timed-out plan is dropped)
  // One plan is open; the others are one-line rows. Details and settings are folded away.
  await expect(page.getByTestId("plan-card")).toHaveCount(1);
  await expect(page.getByTestId("plan-details")).toHaveCount(0);
  await page.getByTestId("plan-more").click();
  await expect(page.getByTestId("plan-details")).toBeVisible();
  const rows = page.getByTestId("plan-row");
  if (await rows.count()) {
    await rows.first().click();
    await expect(page.getByTestId("plan-card")).toHaveCount(1);
    await expect(page.getByTestId("plan-card")).toContainText("Plan 2");
    await expect(page.getByTestId("plan-row").first()).toContainText("Plan 1");
  }
  await expect(page.getByTestId("chip-controls")).toHaveCount(0);
  await page.getByTestId("plan-settings").click();
  await expect(page.getByTestId("chip-controls")).toBeVisible();
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

test("phase 8: weak spots, replacements and the what-if sandbox", async ({ page }) => {
  test.skip(claudeOnly);
  test.setTimeout(300_000);
  await page.goto(`/team/${TEAM}?league=${LEAGUE}`);
  await expect(page.getByTestId("pitch-player")).toHaveCount(11);
  await page.getByRole("group", { name: "Show on pitch" }).getByRole("button", { name: "Weak spots" }).click();
  await expect(page.getByTestId("weak-legend")).toContainText("Red", { timeout: 120_000 });
  await shot(page, "20-team-weak-spots");

  // Tap a red (or amber) player and try the top replacement in what-if.
  const flagged = page.locator('[data-ring="red"], [data-ring="amber"]').first();
  await flagged.click();
  await expect(page.getByTestId("replacements")).toBeVisible();
  await shot(page, "21-player-replacements");
  await page.getByTestId("replacements").getByRole("link", { name: /Try in what-if/ }).first().click();
  await expect(page).toHaveURL(/what-if\?.*m=/);
  await expect(page.getByTestId("whatif-total")).toBeVisible({ timeout: 120_000 });
  await expect(page.getByTestId("whatif-moves")).toBeVisible();
  await expect(page.getByText(/^for /).first()).toBeVisible();
  const gain = await page.getByTestId("whatif-total").innerText();
  expect(gain).toMatch(/[+−]\d/);
  await shot(page, "22-whatif-with-swap");

  // Make a different starter captain.
  const nonCaptain = page.getByTestId("pitch-player").filter({ hasNot: page.getByLabel("Captain") }).nth(2);
  await nonCaptain.click();
  const makeCap = page.getByRole("button", { name: /Make captain/ });
  if (await makeCap.isVisible()) {
    await makeCap.click();
    await expect(page).toHaveURL(/c=/);
  } else {
    await page.getByRole("button", { name: "Close" }).first().click();
  }

  // Transfer someone out via the search list, then undo and reset.
  await page.getByRole("group", { name: "Gameweek" }).getByRole("button").nth(1).click();
  await page.getByTestId("pitch-player").first().click();
  await page.getByRole("button", { name: /Transfer out in GW/ }).click();
  await expect(page.getByTestId("replacement-picker")).toBeVisible();
  await shot(page, "23-whatif-picker");
  await page.getByTestId("replacement-picker").getByRole("button").first().click();
  await expect(page.getByTestId("whatif-moves").locator("div.border-t")).toHaveCount(2, { timeout: 60_000 });
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByTestId("whatif-moves").locator("div.border-t")).toHaveCount(1, { timeout: 60_000 });
  await page.getByRole("button", { name: "Reset" }).click();
  await expect(page.getByTestId("whatif-moves")).toHaveCount(0, { timeout: 60_000 });
  await expect(page.getByTestId("whatif-total")).toContainText("+0.0");
});

test("phase 9: save, rename, compare and delete drafts", async ({ page }) => {
  test.skip(claudeOnly);
  test.setTimeout(300_000);
  // Start from a what-if with the analysis' top swap, then save it.
  await page.goto(`/team/${TEAM}?league=${LEAGUE}`);
  await page.getByRole("group", { name: "Show on pitch" }).getByRole("button", { name: "Weak spots" }).click();
  await page.locator('[data-ring="red"], [data-ring="amber"]').first().click();
  await page.getByTestId("replacements").getByRole("link", { name: /Try in what-if/ }).first().click();
  await expect(page.getByTestId("whatif-total")).toBeVisible({ timeout: 120_000 });
  await page.getByRole("button", { name: "Save as draft" }).click();
  await page.getByLabel("Draft name").fill("Swap A");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page).toHaveURL(/draft=/);
  await expect(page.getByRole("heading", { name: "What-if: Swap A" })).toBeVisible();

  // A second variation: add a GW12 transfer, then save as new.
  await page.getByRole("group", { name: "Gameweek" }).getByRole("button").nth(1).click();
  await page.getByTestId("pitch-player").nth(5).click();
  await page.getByRole("button", { name: /Transfer out in GW/ }).click();
  await page.getByTestId("replacement-picker").getByRole("button").first().click();
  await expect(page.getByTestId("whatif-moves").locator("div.border-t")).toHaveCount(2, { timeout: 60_000 });
  await page.getByRole("button", { name: "Save draft…" }).click();
  await page.getByLabel("Draft name").fill("Swap B");
  await page.getByRole("button", { name: "Save as new" }).click();
  await expect(page.getByRole("heading", { name: "What-if: Swap B" })).toBeVisible();

  // My drafts: both listed with live scores; rename, compare, delete.
  await page.getByTestId("my-drafts-link").click();
  await expect(page.getByTestId("draft")).toHaveCount(2);
  await expect(page.getByTestId("draft").first()).not.toContainText("…", { timeout: 60_000 });
  await page.getByTestId("draft").filter({ hasText: "Swap A" }).getByRole("button", { name: "Rename" }).click();
  await page.getByLabel("New name").fill("Swap A (Van Hecke)");
  await page.getByRole("button", { name: "Save name" }).click();
  await expect(page.getByTestId("draft-list")).toContainText("Swap A (Van Hecke)");
  await page.getByLabel("Compare Swap B").check();
  await page.getByLabel("Compare Swap A (Van Hecke)").check();
  await expect(page.getByTestId("draft-compare")).toContainText("Total vs no transfers", { timeout: 60_000 });
  await shot(page, "24-drafts-compare");
  await page.getByTestId("draft").filter({ hasText: "Swap B" }).getByRole("button", { name: "Delete" }).click();
  await page.getByTestId("draft").filter({ hasText: "Swap B" }).getByRole("button", { name: "Yes" }).click();
  await expect(page.getByTestId("draft")).toHaveCount(1);
});

test("what-if: choose your own lineup, and clear free-transfer counts", async ({ page }) => {
  test.skip(claudeOnly);
  test.setTimeout(240_000);
  await page.goto(`/team/${TEAM}/what-if?league=${LEAGUE}&strategy=protect`);
  await expect(page.getByTestId("whatif-total")).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText(/\d free · \d used/)).toBeVisible();
  // Bring an outfield bench player on (bench order: keeper first).
  await page.getByTestId("bench-player").nth(1).click();
  await page.getByRole("button", { name: /Bring on in GW/ }).click();
  await page.getByTestId("lineup-picker").getByRole("button").first().click();
  await expect(page).toHaveURL(/[?&]s=/);
  const own = page.getByTestId("own-lineup");
  const problem = page.getByRole("alert").filter({ hasText: /GW\d+:/ }); // not the Next.js route announcer
  await expect(own.or(problem)).toBeVisible({ timeout: 60_000 });
  if (await own.isVisible()) {
    await expect(own).toContainText("best XI");
    await shot(page, "25-whatif-own-lineup");
    await own.getByRole("button", { name: "Use best lineup" }).click();
    await expect(own).toHaveCount(0, { timeout: 60_000 });
  } else {
    await expect(problem).toContainText(/fewer than|more than|goalkeeper/); // an illegal formation is explained
  }
});

test("deadline countdown, first-visit tips, sharing a plan and the home-screen app", async ({ page, context }) => {
  test.skip(claudeOnly);
  test.setTimeout(240_000);
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto(`/team/${TEAM}?league=${LEAGUE}`);
  await expect(page.getByTestId("pitch-player")).toHaveCount(11);
  await expect(page.getByTestId("countdown")).toContainText(/GW\d+ deadline|has passed/);
  const tips = page.getByTestId("tips");
  await expect(tips).toBeVisible();
  await shot(page, "26-team-countdown-tips");
  await tips.getByRole("button", { name: "Got it" }).click();
  await page.reload();
  await expect(page.getByTestId("pitch-player")).toHaveCount(11);
  await expect(page.getByTestId("tips")).toHaveCount(0); // remembered

  await page.getByRole("link", { name: "See transfer plans" }).click();
  await expect(page.getByTestId("plan-card").first()).toBeVisible({ timeout: 120_000 });
  await expect(page.getByTestId("countdown")).toBeVisible();
  // Headless Chromium has no share sheet, so Share copies the message instead.
  await page.evaluate(() => Object.defineProperty(navigator, "share", { value: undefined }));
  await page.getByTestId("share-plan").first().click();
  await expect(page.getByTestId("share-plan").first()).toHaveText("Copied ✓");
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toMatch(/^My GW\d+ plan \(/);
  expect(copied).toContain("Captain ");
  expect(copied).not.toContain(TEAM); // links to the start page, never to your team
  await shot(page, "27-plans-share");

  // Second visit, tips already closed: the home-screen hint (iPhone steps), until dismissed.
  await page.evaluate(() => localStorage.setItem("visits:v1", "1"));
  const next = await context.newPage(); // a new browser session counts as a new visit
  await next.goto(`/team/${TEAM}?league=${LEAGUE}`);
  const hint = next.getByTestId("install-hint");
  await expect(hint).toContainText("Add to Home Screen");
  await shot(next, "28-team-install-hint");
  await hint.getByRole("button", { name: "Got it" }).click();
  await next.reload();
  await expect(next.getByTestId("pitch-player")).toHaveCount(11);
  await expect(next.getByTestId("install-hint")).toHaveCount(0);

  const manifest = await (await page.request.get("/manifest.webmanifest")).json();
  expect(manifest.short_name).toBe("ML Planner");
  expect((await page.request.get("/icon-192.png")).status()).toBe(200);
});

test("league invite link, and help finding your ID", async ({ page, context }) => {
  test.skip(claudeOnly);
  test.setTimeout(240_000);
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/");
  await page.getByTestId("id-help-toggle").click();
  await expect(page.getByTestId("id-help")).toContainText("Leagues & Cups");
  await shot(page, "29-main-id-help");

  // The team page gives a link to pass on.
  await page.goto(`/team/${TEAM}?league=${LEAGUE}`);
  await expect(page.getByTestId("pitch-player")).toHaveCount(11);
  await page.evaluate(() => Object.defineProperty(navigator, "share", { value: undefined }));
  await page.getByTestId("invite-league").click();
  await expect(page.getByTestId("invite-league")).toHaveText("Invite link copied ✓");
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toContain(`/?league=${LEAGUE}`);
  expect(copied).not.toContain(TEAM); // the league only, never the sharer's team

  // A friend opens it: the league is already found, they tap their name and they're in.
  await page.evaluate(() => localStorage.clear());
  await page.goto(`/?league=${LEAGUE}`);
  const members = page.getByTestId("league-members");
  await expect(members).toContainText("You've been invited");
  await expect(page.getByTestId("recent-team")).toHaveCount(0);
  await shot(page, "30-main-invited");
  await members.getByRole("button").filter({ hasText: "Nikhil" }).first().click();
  await page.getByRole("button", { name: "That's me, continue" }).click();
  await expect(page).toHaveURL(new RegExp(`/team/${TEAM}\\?league=${LEAGUE}`));
});

test("sample team for visitors, new-to-FPL intro and the bottom tabs", async ({ page }) => {
  test.skip(claudeOnly);
  test.setTimeout(240_000);
  await page.goto("/");
  await expect(page.getByTestId("app-nav")).toHaveCount(0); // no tabs before a team is open
  await page.getByTestId("new-to-fpl").click();
  await expect(page.getByTestId("fpl-intro")).toContainText("mini-league");
  await shot(page, "31-main-new-to-fpl");
  await page.getByRole("button", { name: "Try a sample team" }).click();
  await expect(page.getByTestId("pitch-player")).toHaveCount(11);
  await expect(page.getByTestId("demo-banner")).toBeVisible();
  await shot(page, "32-team-demo-tabs");

  // The tabs reach every section and keep the sample banner.
  const nav = page.getByTestId("app-nav");
  await nav.getByRole("link", { name: "Plans" }).click();
  await expect(page.getByTestId("plan-card").first()).toBeVisible({ timeout: 120_000 });
  await expect(nav.getByRole("link", { name: "Plans" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByTestId("demo-banner")).toBeVisible();
  await nav.getByRole("link", { name: "What-if" }).click();
  await expect(page.getByTestId("whatif-total")).toBeVisible({ timeout: 120_000 });
  await page.getByTestId("my-drafts-link").click(); // drafts live under What-if
  await expect(page.getByRole("heading", { name: "My drafts" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "What-if" })).toHaveAttribute("aria-current", "page");
  await nav.getByRole("link", { name: "My team" }).click();
  await expect(page.getByTestId("pitch-player")).toHaveCount(11);

  // Leaving the sample: it was never saved as "your team".
  await page.getByTestId("demo-banner").getByRole("link", { name: "Use my team →" }).click();
  await expect(page.getByRole("heading", { name: /Beat your mini-league/ })).toBeVisible();
  await expect(page.getByTestId("recent-team")).toHaveCount(0);
});

test("ask about a plan, and the This week page", async ({ page }) => {
  test.skip(claudeOnly);
  test.setTimeout(300_000);
  await page.goto(`/plans?team=${TEAM}&league=${LEAGUE}&strategy=protect&horizon=4&hits=0`);
  await expect(page.getByTestId("plan-card").first()).toBeVisible({ timeout: 120_000 });
  // A player's name anywhere opens his fixtures and numbers.
  await page.getByTestId("plan-card").getByTestId("player-tap").first().click();
  const sheet = page.getByTestId("sheet");
  await expect(sheet.getByTestId("fixture-strip")).toBeVisible();
  await expect(sheet).toContainText("Compare with another player");
  await sheet.getByRole("button", { name: "Close" }).click();
  await expect(sheet).toHaveCount(0);
  const ask = page.getByTestId("ask-plan");
  const answer = page.getByTestId("ask-answer");

  // No solve needed: the plan's own numbers.
  await ask.getByRole("button", { name: "What if I make no transfers?" }).click();
  await expect(answer).toContainText("against making no transfers");

  // Each of these re-runs the optimizer with one thing changed.
  await ask.getByRole("button", { name: /^Why / }).first().click();
  await expect(answer).toContainText(/Without .+, the (best plan is|planner finds)/, { timeout: 120_000 });
  await ask.getByRole("button", { name: /^What if I keep / }).first().click();
  await expect(answer).toContainText(/Keeping .+, the (best plan is|planner finds)/, { timeout: 120_000 });
  await ask.getByRole("button", { name: "What if I take a hit?" }).click();
  await expect(answer).toContainText(/hit allowed/, { timeout: 120_000 });
  await expect(answer).toContainText("not written by AI");
  await shot(page, "33-plans-ask");

  await page.getByTestId("app-nav").getByRole("link", { name: "This week" }).click();
  await expect(page.getByRole("heading", { name: /This week · GW\d+/ })).toBeVisible({ timeout: 120_000 });
  await expect(page.getByTestId("week-flags")).toBeVisible();
  await expect(page.getByTestId("week-transfers")).toContainText("IN");
  await expect(page.getByTestId("week-ticker").getByTestId("fixture-strip")).toHaveCount(20);
  await expect(page.getByTestId("week-dream")).toContainText("pts");
  await shot(page, "34-week");
});

test("rivals table, captain options, review, compare and calendar", async ({ page }) => {
  test.skip(claudeOnly);
  test.setTimeout(300_000);
  await page.goto(`/team/${TEAM}?league=${LEAGUE}`);
  await expect(page.getByTestId("pitch-player")).toHaveCount(11);

  // Calendar file: one event per upcoming deadline, with reminders.
  const download = page.waitForEvent("download");
  await page.getByTestId("add-calendar").click();
  const file = await (await download).path();
  const ics = require("fs").readFileSync(file, "utf8");
  expect(ics).toContain("BEGIN:VCALENDAR");
  expect(ics).toMatch(/SUMMARY:FPL GW\d+ deadline/);
  expect(ics).toContain("TRIGGER:-PT3H");
  expect(ics).not.toContain(TEAM);

  // Rivals: the table with projections; a row opens to show what separates you.
  const nav = page.getByTestId("app-nav");
  await nav.getByRole("link", { name: "Rivals" }).click();
  await expect(page.getByTestId("rivals-headline")).toContainText(/Projected after GW\d+/, { timeout: 120_000 });
  const rivalRows = page.getByTestId("rival-row");
  await expect(rivalRows.first()).toContainText("proj");
  await rivalRows.filter({ hasNotText: "(you)" }).first().click();
  await expect(page.getByTestId("rival-details")).toContainText("They have, you don't");
  await page.getByTestId("rival-details").getByTestId("player-tap").first().click();
  await expect(page.getByTestId("sheet").getByTestId("fixture-strip")).toBeVisible();
  await page.getByTestId("sheet").getByRole("button", { name: "Close" }).click();
  await shot(page, "35-rivals");

  // This week: captain options and the review card.
  await nav.getByRole("link", { name: "This week" }).click();
  await expect(page.getByTestId("week-captains")).toContainText("Top pick", { timeout: 120_000 });
  await expect(page.getByTestId("week-review")).toContainText(/You scored|still being played/);
  await shot(page, "36-week-captain-review");

  // Compare: add two players and see them side by side.
  await page.getByRole("link", { name: "Compare players" }).click();
  for (const who of ["Haaland", "ARS"]) {
    await page.getByLabel("Search players").fill(who);
    await page.getByTestId("compare-result").first().click();
  }
  await expect(page).toHaveURL(/p=\d+,\d+/);
  const table = page.getByTestId("compare-table");
  await expect(table).toContainText("Haaland");
  await expect(table).toContainText("xPts per £m");
  await expect(table.getByTestId("fixture-strip")).toHaveCount(2);
  await shot(page, "37-compare");
});
