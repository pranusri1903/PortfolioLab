"use client";
import { CheckCircle2, Download, FileSpreadsheet } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useSWRConfig } from "swr";
import { ErrorBox, Seg } from "@/components/ui";
import { base, useApi } from "@/lib/api";
import { symbolOf } from "@/lib/format";
import type { ImportResult, Inspect } from "@/lib/types";

type Kind = "transactions" | "holdings";
type Cls = "stock" | "fund" | "all";
type Fields = readonly (readonly [string, string])[];

const CLASSES = [["stock", "Stocks & ETFs"], ["fund", "Mutual funds"], ["all", "Both"]] as const;
const CANONICAL = "trade_date,type,symbol,quantity,price,fee,cash_amount,notes";
const COLOR = { valid: "text-emerald-700", invalid: "text-red-700", duplicate: "text-amber-700" };
const DATE_FORMATS = [["%Y-%m-%d", "YYYY-MM-DD"], ["%d/%m/%Y", "DD/MM/YYYY"], ["%m/%d/%Y", "MM/DD/YYYY"], ["%d-%m-%Y", "DD-MM-YYYY"], ["%d-%b-%Y", "DD-Mon-YYYY"]];
const GUESS: Record<string, RegExp[]> = {
  trade_date: [/buy.?date|purchase.?date|trade.?date/i, /date/i], type: [/type|action|side/i, /transaction|narration/i],
  symbol: [/symbol|ticker|scrip|instrument/i, /scheme|fund|isin|name/i], quantity: [/qty|quantity|units|shares/i],
  price: [/avg.*(price|cost)|average/i, /price|rate|nav/i], fee: [/fee|brokerage|charge/i], cash_amount: [/amount|invested|value|net/i], notes: [/note|remark|narration/i],
};
const guess = (field: string, cols: string[]) => { for (const re of GUESS[field] ?? []) { const c = cols.find((x) => re.test(x)); if (c) return c; } return ""; };

const fieldsFor = (kind: Kind, cls: Cls): Fields => {
  const holding = cls === "fund" ? "Fund (scheme name or AMFI code)" : cls === "all" ? "Symbol, fund name or code" : "Symbol / ticker";
  return kind === "transactions"
    ? [["trade_date", "Date"], ["type", "Type / action"], ["symbol", holding], ["quantity", "Units / quantity"], ["price", "Price / NAV"], ["fee", "Fee"], ["cash_amount", "Amount"], ["notes", "Notes"]]
    : [["symbol", holding], ["quantity", "Units / quantity"], ["price", "Average buy price"], ["cash_amount", "Invested amount (if no price)"], ["trade_date", "Buy date (optional)"]];
};

const TEMPLATES: Record<Kind, Record<Cls, string>> = {
  transactions: {
    stock: `${CANONICAL}\n2025-01-10,DEPOSIT,,,,,5000,Funds added\n2025-01-13,BUY,AAPL,10,150.25,1,,Initial buy\n`,
    fund: `${CANONICAL}\n2025-01-06,BUY,MF-122639,198.99,50.25,0,,SIP installment\n`,
    all: `${CANONICAL}\n2025-01-10,DEPOSIT,,,,,5000,Funds added\n2025-01-13,BUY,AAPL,10,150.25,1,,Stock\n`,
  },
  holdings: {
    stock: "symbol,quantity,average_price,date\nAAPL,10,150.25,2024-03-15\n",
    fund: "symbol,quantity,average_price,date\nMF-122639,250.5,52.10,2023-06-05\n",
    all: "symbol,quantity,average_price,date\nAAPL,10,150.25,2024-03-15\nMF-122639,250.5,52.10,2023-06-05\n",
  },
};

export function ImportWizard({ pid, kind }: { pid: string; kind: Kind }) {
  const api = useApi();
  const { mutate } = useSWRConfig();
  const [cls, setCls] = useState<Cls>("stock");
  const [file, setFile] = useState<File>();
  const [info, setInfo] = useState<Inspect>();
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [dateFormat, setDateFormat] = useState("%Y-%m-%d");
  const [autoFund, setAutoFund] = useState(false);
  const [defaultDate, setDefaultDate] = useState(new Date().toISOString().slice(0, 10));
  const [cash, setCash] = useState("");
  const [res, setRes] = useState<ImportResult>();
  const [error, setError] = useState<Error>();
  const [busy, setBusy] = useState(false);
  const fields = fieldsFor(kind, cls);
  const canonical = kind === "transactions" && info?.columns.join(",") === CANONICAL;
  const needsFunding = !autoFund && kind === "transactions" && !!res && !res.committed && res.rows.some((r) => r.reasons.some((x) => x.includes("negative")));

  async function pick(f?: File) {
    setFile(f); setRes(undefined); setInfo(undefined); setError(undefined);
    if (!f) return;
    const body = new FormData();
    body.set("file", f);
    try {
      const i: Inspect = await api("/api/v1/import/inspect", { method: "POST", body });
      setInfo(i);
      setMapping(Object.fromEntries(fieldsFor(kind, cls).map(([k]) => [k, guess(k, i.columns)])));
    } catch (e) { setError(e as Error); }
  }

  async function run(commit: boolean, fund = autoFund) {
    setError(undefined); setBusy(true);
    const body = new FormData();
    body.set("file", file!);
    body.set("asset_class", cls);
    if (!canonical) { body.set("mapping", JSON.stringify(mapping)); body.set("date_format", dateFormat); }
    if (kind === "holdings") { body.set("default_date", defaultDate); if (cash) body.set("cash", cash); }
    else body.set("auto_fund", String(fund));
    try {
      setRes(await api(`${base(pid)}/${kind === "holdings" ? "holdings" : "transactions"}/import?commit=${commit}`, { method: "POST", body }));
      if (commit) await mutate(() => true);
    } catch (e) { setError(e as Error); setRes(undefined); } finally { setBusy(false); }
  }

  const download = () => {
    const url = URL.createObjectURL(new Blob([TEMPLATES[kind][cls]], { type: "text/csv" }));
    Object.assign(document.createElement("a"), { href: url, download: `${kind}-${cls}-template.csv` }).click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="card space-y-4" aria-label={`Import ${kind}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Seg label="Asset class" opts={CLASSES} value={cls} set={(v) => { setCls(v as Cls); setRes(undefined); if (info) setMapping(Object.fromEntries(fieldsFor(kind, v as Cls).map(([k]) => [k, guess(k, info.columns)]))); }} />
        <button className="btn" onClick={download}><Download size={15} />Download CSV template</button>
      </div>
      <p className="text-sm text-slate-500">
        {kind === "holdings"
          ? `Upload what you own today. Each row becomes a purchase with a matching deposit, so money paid in is tracked. ${cls === "fund" ? "Funds can be listed by scheme name or AMFI code." : ""}`
          : `Upload your full history of ${cls === "fund" ? "mutual fund purchases, SIPs and redemptions" : cls === "stock" ? "stock and ETF trades" : "trades and fund transactions"}. Statements that list Amount and NAV work too: units are worked out for you.`}
      </p>

      <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-dashed border-slate-300 p-4 text-sm hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800/40">
        <FileSpreadsheet className="text-indigo-400" />
        <span className="flex-1">{file ? <b>{file.name}</b> : "Choose a CSV or Excel (.xlsx) file"}{info && <span className="text-slate-500"> · {info.row_count} rows</span>}</span>
        <input type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" aria-label="CSV or Excel file" className="sr-only" onChange={(e) => pick(e.target.files?.[0])} />
        <span className="btn">Browse</span>
      </label>

      {info && !canonical && (
        <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/50">
          <p className="mb-2 text-sm font-medium">Match your file&apos;s columns</p>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {fields.map(([k, label]) => (
              <label key={k} className="block text-xs">{label}
                <select className="input mt-1 w-full" value={mapping[k] ?? ""} onChange={(e) => setMapping({ ...mapping, [k]: e.target.value })}>
                  <option value="">— none —</option>{info.columns.map((c) => <option key={c}>{c}</option>)}
                </select>
              </label>))}
            <label className="block text-xs">Date format in text cells
              <select className="input mt-1 w-full" value={dateFormat} onChange={(e) => setDateFormat(e.target.value)}>{DATE_FORMATS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
            </label>
          </div>
          {info.sample.length > 0 && (
            <div className="mt-3 overflow-x-auto"><table className="w-full text-xs"><caption className="sr-only">First rows of your file</caption>
              <thead><tr>{info.columns.map((c) => <th key={c} className="th px-2 py-1">{c}</th>)}</tr></thead>
              <tbody>{info.sample.slice(0, 3).map((r, i) => <tr key={i} className="row">{info.columns.map((c) => <td key={c} className="px-2 py-1">{r[c]}</td>)}</tr>)}</tbody></table></div>)}
        </div>)}

      {info && kind === "holdings" && (
        <div className="grid gap-3 md:grid-cols-2">
          <label className="block text-sm">Buy date for rows without one<input type="date" className="input mt-1 w-full" value={defaultDate} max={new Date().toISOString().slice(0, 10)} onChange={(e) => setDefaultDate(e.target.value)} /></label>
          <label className="block text-sm">Cash balance ({symbolOf()}, optional)<input className="input mt-1 w-full" inputMode="decimal" value={cash} onChange={(e) => setCash(e.target.value)} /></label>
        </div>)}
      {info && kind === "transactions" && (
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1" checked={autoFund} onChange={(e) => { setAutoFund(e.target.checked); setRes(undefined); }} />
          <span><b>My file has no deposits</b> — add a deposit for each purchase automatically.<br /><span className="text-xs text-slate-500">Broker tradebooks and fund statements usually list only trades. Leave off if your file already contains deposits and withdrawals.</span></span>
        </label>)}

      {error && <ErrorBox error={error} />}
      <button className="btn" disabled={!file || !info || busy || res?.committed} onClick={() => run(false)}>Preview</button>

      {needsFunding && (
        <p role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-900/50 dark:bg-amber-900/20">
          Purchases were rejected because there&apos;s no cash to pay for them. Does your file lack deposits?
          <button className="btn" onClick={() => { setAutoFund(true); run(false, true); }}>Fund purchases automatically and re-preview</button>
        </p>)}

      {res && (
        <>
          <p role="status" className="flex items-center gap-2 text-sm">
            {res.committed && <CheckCircle2 size={16} className="text-emerald-600" />}
            {res.committed && res.result
              ? `Imported ${res.result.imported}, skipped ${res.result.skipped} duplicates, rejected ${res.result.rejected}.`
              : `${res.valid} valid, ${res.duplicate} duplicate (will be skipped), ${res.invalid} invalid (will be rejected).`}
          </p>
          <div className="max-h-72 overflow-auto">
            <table className="w-full"><thead><tr><th className="th">Row</th><th className="th">Status</th><th className="th">Holding</th><th className="th">Details</th></tr></thead>
              <tbody>{res.rows.map((r) => (
                <tr key={r.row_number} className="row"><td className="td">{r.row_number}</td><td className={`td font-medium ${COLOR[r.status]}`}>{r.status}</td>
                  <td className="td">{r.resolved_symbol ? <><b>{r.resolved_symbol}</b><div className="text-xs text-slate-500">{r.resolved_name}{r.will_add_asset && " · will be added"}</div></> : r.data.symbol || "—"}</td>
                  <td className="td">{r.reasons.join("; ") || `${r.data.type ?? "BUY"} ${r.data.quantity ?? ""} @ ${r.data.price ?? ""} on ${r.data.trade_date}`}</td></tr>))}</tbody></table>
          </div>
        </>)}
      <div className="flex flex-wrap gap-2">
        {res && !res.committed && <button className="btn-primary" disabled={res.valid === 0 || busy} onClick={() => run(true)}>Confirm import of {res.valid} rows</button>}
        {res?.committed && (<><Link href="/dashboard" className="btn-primary">View dashboard</Link><Link href="/holdings" className="btn">View holdings</Link></>)}
      </div>
    </section>
  );
}
