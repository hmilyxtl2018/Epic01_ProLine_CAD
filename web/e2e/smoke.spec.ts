import { expect, test } from "@playwright/test";

// Smoke: unauthenticated visit to / redirects to /login, login form renders.
//
// This test relies on the dashboard backend running with a sane
// DASHBOARD_DEV_PASSWORD; it deliberately does NOT log in, only verifies
// the redirect + the form is reachable. Authenticated flows live in
// auth-flow.spec.ts (gated behind PLAYWRIGHT_E2E_PASSWORD env var).

test("anonymous visitor lands on /login", async ({ page }) => {
  await page.goto("/runs");
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(page.getByLabel("Email")).toBeVisible();
  await expect(page.getByLabel("Password")).toBeVisible();
  await expect(page.getByLabel("Role")).toBeVisible();
});

test("login page submit button is present", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("button", { name: /sign in/i })).toBeEnabled();
});
