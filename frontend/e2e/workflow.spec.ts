import { expect, test, type Page } from "@playwright/test";

const loadDemo = async (page: Page) => {
  await page.getByRole("button", { name: "Load demo portfolio" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
};

const signIn = async (page: Page, user: string) => {
  await page.goto("/sign-in");
  await page.getByLabel("User ID").fill(user);
  await page.getByRole("button", { name: "Sign in" }).click();
};

test("unauthenticated visitors are sent to sign-in", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/sign-in/);
});

test("sign in, review demo, add a transaction, see the portfolio update", async ({ page }) => {
  await signIn(page, `e2e_${Date.now()}`);
  await loadDemo(page);

  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByText("Sample data").first()).toBeVisible();
  await expect(page.getByText("Prices as of 2026-09-30")).toBeVisible();
  await page.getByRole("button", { name: "3M" }).click();
  await expect(page.getByRole("button", { name: "3M" })).toHaveAttribute("aria-pressed", "true");

  const cash = page.locator(".card", { hasText: "Cash balance" }).first().locator(".text-2xl");
  const before = await cash.innerText();

  await page.getByRole("link", { name: "Transactions" }).click();
  await page.getByRole("button", { name: "Add transaction" }).click();
  const form = page.getByRole("form", { name: "Add transaction" });
  await form.getByLabel("Type").selectOption("DEPOSIT");
  await form.getByLabel("Amount (USD)").fill("1234.56");
  await form.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("cell", { name: "$1,234.56" })).toBeVisible();

  await page.getByRole("link", { name: "Dashboard" }).click();
  await expect(cash).not.toHaveText(before);
});

test("holdings are searchable and link to detail with sample label", async ({ page }) => {
  await signIn(page, `e2e_h_${Date.now()}`);
  await loadDemo(page);
  await page.getByRole("link", { name: "Holdings" }).click();
  await page.getByLabel("Search holdings").fill("acme");
  await expect(page.getByRole("link", { name: "ACME" })).toBeVisible();
  await expect(page.getByRole("link", { name: "BNCH" })).toHaveCount(0);
  await page.getByRole("link", { name: "ACME" }).click();
  await expect(page.getByText("(sample prices)")).toBeVisible();
});

test("CSV import previews errors, then imports valid rows", async ({ page }) => {
  await signIn(page, `e2e_c_${Date.now()}`);
  await page.getByRole("button", { name: "Start empty" }).click();
  await page.getByRole("link", { name: "Transactions" }).click();
  await page.getByRole("button", { name: "Import CSV" }).click();
  const csv = "trade_date,type,symbol,quantity,price,fee,cash_amount,notes\n2025-01-10,DEPOSIT,,,,,500.00,ok\n2025-99-10,DEPOSIT,,,,,5.00,bad date\n";
  await page.getByLabel("CSV file").setInputFiles({ name: "t.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page.getByRole("status")).toContainText("1 valid");
  await expect(page.getByText("not a real calendar date")).toBeVisible();
  await page.getByRole("button", { name: /Confirm import of 1 rows/ }).click();
  await expect(page.getByRole("status")).toContainText("Imported 1");
});

test("rupee demo portfolio shows ₹ amounts and Indian holdings", async ({ page }) => {
  await signIn(page, `e2e_inr_${Date.now()}`);
  await page.getByRole("button", { name: /Indian Rupee/ }).click();
  await loadDemo(page);
  await expect(page.locator(".hero")).toContainText("₹");
  await page.getByRole("link", { name: "Holdings" }).click();
  await expect(page.getByRole("link", { name: "INFX" })).toBeVisible();
  await expect(page.getByRole("link", { name: "ACME" })).toHaveCount(0); // USD asset never appears in a rupee portfolio
});

test("quick start builds a portfolio from what I own", async ({ page }) => {
  await signIn(page, `e2e_q_${Date.now()}`);
  await page.getByRole("button", { name: "Enter my holdings" }).click();
  await expect(page.getByRole("heading", { name: "Enter what you own" })).toBeVisible();
  await page.getByLabel("Stock, ETF or fund").fill("ACME");
  await page.getByRole("option", { name: /ACME/ }).click();
  await page.getByLabel("Units / shares").fill("10");
  await page.getByLabel(/Avg price/).fill("50");
  await page.getByLabel("First bought").fill("2025-01-10");
  await page.getByLabel(/Cash balance/).fill("100");
  await page.getByRole("button", { name: "Build my portfolio" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await page.getByRole("link", { name: "Holdings", exact: true }).click();
  await expect(page.getByRole("link", { name: "ACME" })).toBeVisible();
});

test("analytics page lists every holding including funds, with filters", async ({ page }) => {
  await signIn(page, `e2e_a_${Date.now()}`);
  await loadDemo(page);
  await page.getByRole("link", { name: "Analytics" }).click();
  await expect(page.getByText("Portfolio XIRR")).toBeVisible();
  await expect(page.getByRole("link", { name: "GRWF" })).toBeVisible();
  await page.getByRole("button", { name: "Mutual funds" }).click();
  await expect(page.getByRole("link", { name: "GRWF" })).toBeVisible();
  await expect(page.getByRole("link", { name: "ACME" })).toHaveCount(0);
  await page.getByRole("button", { name: "Closed" }).click();
  await expect(page.getByText("No holdings for this filter")).toBeVisible();
});

test("SIP page shows the demo SIP and can pause it", async ({ page }) => {
  await signIn(page, `e2e_s_${Date.now()}`);
  await loadDemo(page);
  await page.getByRole("link", { name: "SIPs" }).click();
  const card = page.getByRole("region", { name: "SIP GRWF" });
  await expect(card.getByText("Active", { exact: true })).toBeVisible();
  await card.getByRole("button", { name: "Pause" }).click();
  await expect(card.getByText("Paused")).toBeVisible();
});
