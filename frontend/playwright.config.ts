import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

const python = path.resolve(__dirname, "../backend/.venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");

// Claude reasons cost money, so the backend runs with the key blanked unless E2E_CLAUDE=1.
const backendEnv: Record<string, string> = { ...(process.env as Record<string, string>) };
if (!process.env.E2E_CLAUDE) backendEnv.ANTHROPIC_API_KEY = "";

// Walks the real journey on a phone-sized screen and saves screenshots to e2e/screenshots/.
// Starts the FastAPI backend (cached FPL client) and the built Next.js app.
export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  expect: { timeout: 60_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    ...devices["iPhone 13"],
    browserName: "chromium",
    baseURL: "http://127.0.0.1:3000",
  },
  webServer: [
    {
      command: `"${python}" -m uvicorn app.api.main:app --port 8000`,
      cwd: "../backend",
      env: backendEnv,
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: "npx next start -p 3000",
      url: "http://127.0.0.1:3000",
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
});
