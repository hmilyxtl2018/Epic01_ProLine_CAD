import { defineConfig } from "@playwright/test";

// Playwright smoke harness for the dashboard.
//
// CI invocation:
//   PLAYWRIGHT_BASE_URL=http://localhost:3000 npm run test:e2e
//
// The dashboard backend + Next dev server must already be running. We do
// NOT start them via webServer here because they have a fairly heavy
// startup (Postgres, Redis) that the calling job is expected to manage.
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { browserName: "chromium" },
    },
  ],
});
