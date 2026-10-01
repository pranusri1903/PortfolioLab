import { expect, test, type Page } from "@playwright/test";

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
  await page.getByRole("button", { name: "Load demo portfolio" }).click();

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
  await page.getByRole("button", { name: "Load demo portfolio" }).click();
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
