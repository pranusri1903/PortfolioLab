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

  await page.getByRole("link", { name: "Transactions", exact: true }).click();
  await page.getByRole("button", { name: "Add transaction" }).click();
  const form = page.getByRole("form", { name: "Add transaction" });
  await form.getByLabel("Type").selectOption("DEPOSIT");
  await form.getByLabel("Amount (USD)").fill("1234.56");
  await form.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("cell", { name: "$1,234.56" })).toBeVisible();

  await page.getByRole("link", { name: "Dashboard", exact: true }).click();
  await expect(cash).not.toHaveText(before);
});

test("holdings are searchable and link to detail with sample label", async ({ page }) => {
  await signIn(page, `e2e_h_${Date.now()}`);
  await loadDemo(page);
  await page.getByRole("link", { name: "Holdings", exact: true }).click();
  await page.getByLabel("Search holdings").fill("acme");
  await expect(page.getByRole("link", { name: "ACME" })).toBeVisible();
  await expect(page.getByRole("link", { name: "BNCH" })).toHaveCount(0);
  await page.getByRole("link", { name: "ACME" }).click();
  await expect(page.getByText("(sample prices)")).toBeVisible();
});

test("transaction import previews errors, then imports valid rows", async ({ page }) => {
  await signIn(page, `e2e_c_${Date.now()}`);
  await page.getByRole("button", { name: "Start empty" }).click();
  await page.getByRole("link", { name: "Import transactions" }).click();
  const csv = "trade_date,type,symbol,quantity,price,fee,cash_amount,notes\n2025-01-10,DEPOSIT,,,,,500.00,ok\n2025-99-10,DEPOSIT,,,,,5.00,bad date\n";
  await page.getByLabel("CSV or Excel file").setInputFiles({ name: "t.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page.getByRole("status")).toContainText("1 valid");
  await expect(page.getByText("not a real calendar date")).toBeVisible();
  await page.getByRole("button", { name: /Confirm import of 1 rows/ }).click();
  await expect(page.getByRole("status")).toContainText("Imported 1");
});

test("a trades-only file prompts to fund purchases automatically", async ({ page }) => {
  await signIn(page, `e2e_f_${Date.now()}`);
  await page.getByRole("button", { name: "Start empty" }).click();
  await page.getByRole("link", { name: "Import transactions" }).click();
  const csv = "trade_date,type,symbol,quantity,price,fee,cash_amount,notes\n2025-01-13,BUY,ACME,10,50,0,,tradebook\n";
  await page.getByLabel("CSV or Excel file").setInputFiles({ name: "t.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "no cash" })).toContainText("no cash to pay");
  await page.getByRole("button", { name: /Fund purchases automatically/ }).click();
  await expect(page.getByRole("status")).toContainText("1 valid");
  await page.getByRole("button", { name: /Confirm import of 1 rows/ }).click();
  await expect(page.getByRole("status")).toContainText("Imported 1");
});

test("holdings file with different column names is mapped and imported", async ({ page }) => {
  await signIn(page, `e2e_h2_${Date.now()}`);
  await page.getByRole("button", { name: "Start empty" }).click();
  await page.getByRole("link", { name: "Import holdings" }).click();
  const csv = "Symbol,Qty,Avg Price,Buy Date\nACME,10,50,2025-01-10\nBOLT,5,80,2025-01-10\n";
  await page.getByLabel("CSV or Excel file").setInputFiles({ name: "h.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await expect(page.getByText("Match your file's columns")).toBeVisible();
  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page.getByRole("status")).toContainText("2 valid");
  await page.getByRole("button", { name: /Confirm import of 2 rows/ }).click();
  await expect(page.getByRole("status")).toContainText("Imported 2");
  await page.getByRole("link", { name: "View holdings" }).click();
  await expect(page.getByRole("link", { name: "ACME" })).toBeVisible();
  await expect(page.getByRole("link", { name: "BOLT" })).toBeVisible();
});

test("the Mutual funds tab rejects stocks and accepts funds", async ({ page }) => {
  await signIn(page, `e2e_mf_${Date.now()}`);
  await page.getByRole("button", { name: "Start empty" }).click();
  await page.getByRole("link", { name: "Import holdings" }).click();
  await page.getByRole("button", { name: "Mutual funds" }).click();
  const csv = "symbol,quantity,average_price,date\nACME,10,50,2025-01-10\nGRWF,25,40,2025-01-10\n";
  await page.getByLabel("CSV or Excel file").setInputFiles({ name: "h.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page.getByRole("status")).toContainText("1 valid");
  await expect(page.getByText("import it under stocks & ETFs")).toBeVisible();
});

test("rupee demo portfolio shows ₹ amounts and Indian holdings", async ({ page }) => {
  await signIn(page, `e2e_inr_${Date.now()}`);
  await page.getByRole("button", { name: /Indian Rupee/ }).click();
  await loadDemo(page);
  await expect(page.locator(".hero")).toContainText("₹");
  await page.getByRole("link", { name: "Holdings", exact: true }).click();
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
  await page.getByRole("link", { name: "Analytics", exact: true }).click();
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
  await page.getByRole("link", { name: "SIPs", exact: true }).click();
  const card = page.getByRole("region", { name: "SIP GRWF" });
  await expect(card.getByText("Active", { exact: true })).toBeVisible();
  await card.getByRole("button", { name: "Pause" }).click();
  await expect(card.getByText("Paused")).toBeVisible();
});

test("a demo portfolio can be abandoned, freeing the slot for my own", async ({ page }) => {
  page.on("dialog", (d) => d.accept());
  await signIn(page, `e2e_ab_${Date.now()}`);
  await loadDemo(page);
  await expect(page.getByRole("note")).toContainText("demo USD portfolio");
  await page.getByRole("button", { name: "Abandon demo" }).click();
  await expect(page.getByRole("heading", { name: "Create your portfolio" })).toBeVisible();
  await page.getByRole("button", { name: "Start empty" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByRole("note")).toHaveCount(0); // no demo banner on a real portfolio
  await expect(page.getByText("Your USD portfolio is empty")).toBeVisible();
});

test("my own USD portfolio can sit alongside the USD demo", async ({ page }) => {
  await signIn(page, `e2e_both_${Date.now()}`);
  await loadDemo(page);
  await page.getByRole("button", { name: "Add portfolio" }).click();
  await expect(page.getByRole("button", { name: "Load demo portfolio" })).toBeDisabled(); // demo already exists
  await page.getByRole("button", { name: "Start empty" }).click();
  await expect(page.getByText("Your USD portfolio is empty")).toBeVisible();
  await expect(page.getByLabel("Portfolio").locator("option")).toHaveCount(2);
});

test("a statement with stacked tables imports from the right one", async ({ page }) => {
  await signIn(page, `e2e_st_${Date.now()}`);
  await page.getByRole("button", { name: "Start empty" }).click();
  await page.getByRole("link", { name: "Import holdings" }).click();
  const sheet = [
    "Personal Details", "Name,Test User", "PAN,AAAAA0000A", "", "",
    "HOLDING SUMMARY", "",
    "Total Investments,Current Portfolio Value,Profit/Loss,Profit/Loss %,XIRR", "9000,9500,500,5%,4%", "", "",
    "HOLDINGS AS ON 2026-10-02", "",
    "Symbol,Exchange,Category,Source,Qty,Invested Value,Current Value", "",
    "ACME,NYSE,Equity,Broker,10,500,520",
    "BOLT,NYSE,Equity,Broker,5,400,410",
  ].join("\n");
  await page.getByLabel("CSV or Excel file").setInputFiles({ name: "statement.csv", mimeType: "text/csv", buffer: Buffer.from(sheet) });
  await expect(page.getByText("This file contains 2 tables")).toBeVisible();
  await expect(page.getByText(/no buy-date column/)).toBeVisible();
  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page.getByRole("status")).toContainText("2 valid");
  await page.getByRole("button", { name: /Confirm import of 2 rows/ }).click();
  await expect(page.getByRole("status")).toContainText("Imported 2");
  await page.getByRole("link", { name: "View holdings" }).click();
  await expect(page.getByRole("link", { name: "ACME" })).toBeVisible();
  await expect(page.getByRole("link", { name: "BOLT" })).toBeVisible();
});

test("the file is shown as a sheet; tables stacked with no gaps can be switched by clicking", async ({ page }) => {
  await signIn(page, `e2e_sv_${Date.now()}`);
  await page.getByRole("button", { name: "Start empty" }).click();
  await page.getByRole("link", { name: "Import holdings" }).click();
  const sheet = [
    "Personal Details", "Name,Test User", "PAN,AAAAA0000A", "HOLDING SUMMARY",
    "Total Investments,Current Portfolio Value,Profit/Loss,Profit/Loss %,XIRR", "9000,9500,500,5%,4%",
    "HOLDINGS AS ON 2026-10-02",
    "Symbol,Exchange,Category,Source,Qty,Invested Value,Current Value", "ACME,NYSE,Equity,Broker,10,500,520", "BOLT,NYSE,Equity,Broker,5,400,410",
  ].join("\n");
  await page.getByLabel("CSV or Excel file").setInputFiles({ name: "stmt.csv", mimeType: "text/csv", buffer: Buffer.from(sheet) });
  await expect(page.getByText("Your file as we see it")).toBeVisible();
  await expect(page.getByText("This file contains 2 tables")).toBeVisible();
  const chip = page.locator("label", { hasText: "stmt.csv" });
  await expect(chip).toContainText("2 rows"); // the holdings table was picked, not the summary
  // personal details are visible as rows of the sheet but masked
  await expect(page.getByRole("cell", { name: "Personal Details" })).toBeVisible();
  await expect(page.getByText("Test User")).toHaveCount(0);
  await expect(page.getByText("AAAAA0000A")).toHaveCount(0);
  // click into the summary table to switch to it, then back
  await page.getByRole("cell", { name: "9500", exact: true }).click();
  await expect(chip).toContainText("1 rows");
  await page.getByRole("cell", { name: "ACME", exact: true }).click();
  await expect(chip).toContainText("2 rows");
  await page.getByRole("button", { name: "Preview" }).click();
  await expect(page.getByRole("status")).toContainText("2 valid");
  await page.getByRole("button", { name: /Confirm import of 2 rows/ }).click();
  await expect(page.getByRole("status")).toContainText("Imported 2");
});
