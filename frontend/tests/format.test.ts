import { expect, test } from "vitest";
import { money, percent, qty, signClass } from "@/lib/format";

test("money formats decimal strings and handles null", () => {
  expect(money("1234.5")).toBe("$1,234.50");
  expect(money(null)).toBe("—");
});
test("percent formats fractions", () => expect(percent(0.1234)).toBe("12.34%"));
test("qty keeps fractional shares", () => expect(qty("0.12345678")).toBe("0.12345678"));
test("signClass colours gains and losses", () => {
  expect(signClass("5")).toContain("emerald");
  expect(signClass("-5")).toContain("red");
  expect(signClass(0)).toBe("");
});
