import { expect, test } from "@playwright/test";

test.skip(!process.env.SCREENSHOTS, "set SCREENSHOTS=1 to regenerate docs/screenshots");

for (const theme of ["light", "dark"]) {
  test(`screenshots (${theme})`, async ({ page }) => {
    await page.setViewportSize({ width: 1360, height: 900 });
    await page.addInitScript((t) => localStorage.setItem("pl_theme", t), theme);
    await page.goto("/sign-in");
    if (theme === "light") await page.screenshot({ path: "../docs/screenshots/sign-in.png" });
    await page.getByLabel("User ID").fill(`shot_${theme}_${Date.now()}`);
    await page.getByRole("button", { name: "Sign in" }).click();
    if (theme === "dark") await page.getByRole("button", { name: /Indian Rupee/ }).click();
    await page.getByRole("button", { name: "Load demo portfolio" }).click();
    await page.getByText("Monthly returns").waitFor();
    await page.waitForTimeout(800);
    await page.screenshot({ path: `../docs/screenshots/dashboard-${theme}.png`, fullPage: true });
    await page.getByRole("link", { name: "Analytics" }).click();
    await expect(page.getByRole("heading", { name: /Correlation of daily returns/ })).toBeVisible();
    await page.waitForTimeout(800);
    await page.screenshot({ path: `../docs/screenshots/analytics-${theme}.png`, fullPage: true });
    if (theme === "light") {
      await page.getByRole("link", { name: "SIPs" }).click();
      await page.getByRole("region", { name: "SIP GRWF" }).waitFor();
      await page.screenshot({ path: "../docs/screenshots/sips.png" });
      await page.getByRole("link", { name: "Holdings" }).click();
      await page.getByRole("link", { name: "ACME" }).waitFor();
      await page.screenshot({ path: "../docs/screenshots/holdings.png" });
    }
  });
}
