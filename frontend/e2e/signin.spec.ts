import { expect, test } from "@playwright/test";

// Optional Google sign-in. Needs a build with the Google variables set (dummy values are fine):
//   GOOGLE_CLIENT_ID=dummy.apps.googleusercontent.com GOOGLE_CLIENT_SECRET=dummy NEXTAUTH_SECRET=dummy \
//     npm run build && E2E_AUTH=1 GOOGLE_CLIENT_ID=... (same) npx playwright test e2e/signin.spec.ts
// It checks the button shows, the backend proxy still works, and clicking it goes to Google
// (the Google page itself is intercepted; nobody actually signs in).
test("Sign in with Google is offered and hands over to Google", async ({ page }) => {
  test.skip(!process.env.E2E_AUTH, "needs a build with the Google sign-in variables");
  await page.goto("/");
  await expect(page.getByTestId("sign-in")).toBeVisible();
  const providers = await page.request.get("/api/auth/providers");
  expect(Object.keys(await providers.json())).toContain("google");
  const health = await page.request.get("/api/health"); // proxied to the backend as before
  expect((await health.json()).status).toBe("ok");
  await page.route(/accounts\.google\.com/, (route) => route.fulfill({ status: 200, body: "google sign-in page" }));
  await page.getByRole("button", { name: /Sign in with Google/ }).click();
  await page.waitForURL(/accounts\.google\.com/);
  expect(page.url()).toContain("client_id=dummy.apps.googleusercontent.com");
  expect(page.url()).toContain(encodeURIComponent("/api/auth/callback/google"));
});
