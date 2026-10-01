const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const pct = new Intl.NumberFormat("en-US", { style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Display-only formatting of decimal strings from the API. Calculations stay on the backend. */
export const money = (v: string | number | null | undefined) => (v == null ? "—" : usd.format(Number(v)));
export const percent = (v: number | null | undefined) => (v == null ? "—" : pct.format(v));
export const qty = (v: string | number) => Number(v).toLocaleString("en-US", { maximumFractionDigits: 8 });
export const signClass = (v: string | number | null | undefined) =>
  v == null || Number(v) === 0 ? "" : Number(v) > 0 ? "text-emerald-700" : "text-red-700";
