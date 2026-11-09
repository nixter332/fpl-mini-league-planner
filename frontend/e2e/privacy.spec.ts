import { expect, test } from "@playwright/test";

// Privacy check for tracking: nothing sent to PostHog contains a team or league ID.
// Build with a dummy key first, then run it (PostHog requests are intercepted, never sent):
//   NEXT_PUBLIC_POSTHOG_KEY=phc_dummy NEXT_PUBLIC_POSTHOG_DEBUG=1 npm run build
//   E2E_PRIVACY=1 npx playwright test e2e/privacy.spec.ts
// (The debug build lets events through from the headless test browser, which PostHog treats as a bot.)
test("PostHog events carry no team or league IDs", async ({ page }) => {
  test.skip(!process.env.E2E_PRIVACY, "needs a build with NEXT_PUBLIC_POSTHOG_KEY set; see the comment above");
  test.setTimeout(240_000);
  const bodies: string[] = [];
  page.on("console", (m) => process.env.E2E_PRIVACY_DEBUG && console.log("console:", m.text().slice(0, 300)));
  page.on("request", (r) => process.env.E2E_PRIVACY_DEBUG && /posthog/.test(r.url()) && console.log("request:", r.method(), r.url()));
  await page.route(/posthog\.com/, async (route) => {
    const req = route.request();
    const raw = req.postData();
    if (raw) {
      // posthog-js may send JSON, a base64 "data=" form field, or base64 JSON: decode all of them.
      let text = raw;
      const form = raw.match(/^data=(.*)$/s);
      const b64 = form ? decodeURIComponent(form[1]) : raw;
      if (!raw.trimStart().startsWith("{") && !raw.trimStart().startsWith("[")) {
        try {
          text = Buffer.from(b64, "base64").toString("utf8");
        } catch {
          /* keep raw */
        }
      }
      bodies.push(`${req.url()}
${text}`);
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  await page.goto("/team/5179483?league=1883627");
  await expect(page.getByTestId("pitch-player").first()).toBeVisible({ timeout: 120_000 });
  await page.goto("/plans?team=5179483&league=1883627&strategy=protect&horizon=4&hits=0");
  await expect(page.getByTestId("plan-card").first()).toBeVisible({ timeout: 120_000 });
  await page.waitForTimeout(3000);
  const all = bodies.join("\n");
  if (process.env.E2E_PRIVACY_DEBUG) console.log(all.slice(0, 1500));
  console.log(`captured ${bodies.length} PostHog requests; events: ${[...all.matchAll(/"event":"([^"]+)"/g)].map((m) => m[1]).join(", ")}`);
  expect(bodies.length).toBeGreaterThan(0);
  expect(all).not.toContain("5179483");
  expect(all).not.toContain("1883627");
  expect(all).toContain('"event":"plans_loaded"');
  expect(all).toContain("/team/:id");
});
