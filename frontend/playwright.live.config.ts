import { defineConfig, devices } from "@playwright/test";

// The same journey against the deployed site (no local servers): `npm run screenshots:live`.
// The live backend has Claude switched on, so plan pages it opens may write new reasons.
export default defineConfig({
  testDir: "./e2e",
  timeout: 240_000,
  expect: { timeout: 120_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    ...devices["iPhone 13"],
    browserName: "chromium",
    baseURL: process.env.LIVE_URL ?? "https://fpl-mini-league-planner.vercel.app",
  },
});
