import { afterEach, expect, test } from "vitest";
import { getCurrency, money, moneyCompact, percent, qty, setCurrency, signClass, symbolOf } from "@/lib/format";

afterEach(() => setCurrency("USD"));

test("money formats decimal strings and handles null", () => {
  expect(money("1234.5")).toBe("$1,234.50");
  expect(money(null)).toBe("—");
});
test("rupees use Indian digit grouping", () => {
  setCurrency("INR");
  expect(getCurrency()).toBe("INR");
  expect(money("1234567.5")).toContain("12,34,567.50");
  expect(symbolOf()).toBe("₹");
  expect(moneyCompact(2_500_000)).toContain("25L");
});
test("percent formats fractions", () => expect(percent(0.1234)).toBe("12.34%"));
test("qty keeps fractional units", () => expect(qty("0.12345678")).toBe("0.12345678"));
test("signClass colours gains and losses", () => {
  expect(signClass("5")).toContain("emerald");
  expect(signClass("-5")).toContain("red");
  expect(signClass(0)).toBe("");
});
