/** Display-only formatting of decimal strings from the API. Calculations stay on the backend. */
let currency = "USD";
/** Set by the layout whenever the selected portfolio changes (USD or INR). */
export const setCurrency = (c: string) => { currency = c; };
export const getCurrency = () => currency;

const locale = () => (currency === "INR" ? "en-IN" : "en-US");
const nf = (opts: Intl.NumberFormatOptions) => new Intl.NumberFormat(locale(), { style: "currency", currency, ...opts });
const pct = new Intl.NumberFormat("en-US", { style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const money = (v: string | number | null | undefined) => (v == null ? "—" : nf({}).format(Number(v)));
export const moneyCompact = (v: number) => nf({ notation: "compact", maximumFractionDigits: 1 }).format(v);
export const symbolOf = () => nf({ maximumFractionDigits: 0 }).format(0).replace(/[\d.,\s]/g, "");
export const percent = (v: number | null | undefined) => (v == null ? "—" : pct.format(v));
export const qty = (v: string | number) => Number(v).toLocaleString("en-US", { maximumFractionDigits: 8 });
export const signClass = (v: string | number | null | undefined) =>
  v == null || Number(v) === 0 ? "" : Number(v) > 0 ? "text-emerald-700" : "text-red-700";
export const TYPE_LABEL: Record<string, string> = { STOCK: "Stock", ETF: "ETF", MUTUAL_FUND: "Mutual fund" };
