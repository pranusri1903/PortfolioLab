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
    await page.getByRole("link", { name: "Analytics", exact: true }).click();
    await expect(page.getByRole("heading", { name: /Correlation of daily returns/ })).toBeVisible();
    await page.waitForTimeout(800);
    await page.screenshot({ path: `../docs/screenshots/analytics-${theme}.png`, fullPage: true });
    if (theme === "light") {
      await page.getByRole("link", { name: "SIPs", exact: true }).click();
      await page.getByRole("region", { name: "SIP GRWF" }).waitFor();
      await page.screenshot({ path: "../docs/screenshots/sips.png" });
      await page.getByRole("link", { name: "Import transactions" }).click();
      await page.getByRole("button", { name: "Mutual funds" }).click();
      const stmt = "Date,Scheme Name,Transaction,Amount,NAV,Units\n06/01/2025,Parag Parikh Flexi Cap Fund - Direct Growth,Purchase,10000,50.25,\n05/02/2025,Parag Parikh Flexi Cap Fund - Direct Growth,Systematic Investment,5000,52.5,\n";
      await page.getByLabel("CSV or Excel file").setInputFiles({ name: "statement.csv", mimeType: "text/csv", buffer: Buffer.from(stmt) });
      await page.getByText("Match your file's columns").waitFor();
      await page.screenshot({ path: "../docs/screenshots/import.png" });
      await page.getByRole("link", { name: "Import holdings" }).click();
      await page.getByRole("heading", { name: "Import holdings" }).waitFor();
      const stacked = ["Personal Details", "Name,Test User", "PAN,AAAAA0000A", "", "HOLDING SUMMARY", "Total Investments,Current Portfolio Value,Profit/Loss,Profit/Loss %,XIRR", "76496.2,75291.72,-1204.49,-1.57%,-4.98%", "", "HOLDINGS AS ON 2026-10-02", "Scheme Name,AMC,Category,Sub-category,Folio No.,Source,Units,Invested Value,Current Value,Returns,XIRR", "SBI Gold Direct Plan Growth,SBI Mutual Fund,Commodities,Gold,111,Groww,970.019,43497.83,43521.07,23.24,0.18%", "HDFC Infrastructure Fund Direct Growth,HDFC Mutual Fund,Equity,Sectoral,222,Groww,634.17,32998.37,31770.65,-1227.72,-11.8%"].join("\n");
      await page.getByRole("button", { name: "Mutual funds" }).click();
      await page.getByLabel("CSV or Excel file").setInputFiles({ name: "Holdings_Statement.csv", mimeType: "text/csv", buffer: Buffer.from(stacked) });
      await page.getByText("Your file as we see it").waitFor();
      await page.screenshot({ path: "../docs/screenshots/import-stacked.png", fullPage: true });
      await page.getByRole("link", { name: "Holdings", exact: true }).click();
      await page.getByRole("link", { name: "ACME" }).waitFor();
      await page.screenshot({ path: "../docs/screenshots/holdings.png" });
    }
  });
}
