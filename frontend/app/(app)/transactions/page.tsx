"use client";
import { useState } from "react";
import { useSWRConfig } from "swr";
import { usePid } from "../layout";
import { CsvImport } from "@/components/csv-import";
import { TxForm } from "@/components/tx-form";
import { Empty, ErrorBox, Loading } from "@/components/ui";
import { base, useApi, useData } from "@/lib/api";
import { money, qty } from "@/lib/format";
import type { Summary, Tx, TxPage } from "@/lib/types";

const TYPES = ["BUY", "SELL", "DIVIDEND", "DEPOSIT", "WITHDRAWAL", "FEE"];

export default function Transactions() {
  const pid = usePid();
  const api = useApi();
  const { mutate } = useSWRConfig();
  const [f, setF] = useState({ symbol: "", type: "", asset_type: "", source: "", date_from: "", date_to: "" });
  const [page, setPage] = useState(1);
  const [mode, setMode] = useState<"add" | "import" | Tx | null>(null);
  const [error, setError] = useState<Error>();
  const qs = new URLSearchParams({ ...Object.fromEntries(Object.entries(f).filter(([, v]) => v)), page: String(page), page_size: "15" });
  const { data, error: loadError } = useData<TxPage>(`${base(pid)}/transactions?${qs}`);
  const asOf = useData<Summary>(`${base(pid)}/summary`).data?.as_of ?? new Date().toISOString().slice(0, 10);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => { setF({ ...f, [k]: e.target.value }); setPage(1); };

  async function remove(t: Tx) {
    if (!confirm(`Delete this ${t.type} on ${t.trade_date.slice(0, 10)}?`)) return;
    try { await api(`${base(pid)}/transactions/${t.id}`, { method: "DELETE" }); setError(undefined); await mutate(() => true); } catch (e) { setError(e as Error); }
  }
  async function exportCsv() {
    const url = URL.createObjectURL(new Blob([await api(`${base(pid)}/transactions-export`)], { type: "text/csv" }));
    Object.assign(document.createElement("a"), { href: url, download: "transactions.csv" }).click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold tracking-tight">Transactions</h1>
        <div className="flex gap-2">
          <button className="btn-primary" onClick={() => setMode("add")}>Add transaction</button>
          <button className="btn" onClick={() => setMode("import")}>Import CSV</button>
          <button className="btn" onClick={exportCsv}>Export CSV</button>
        </div>
      </div>
      {mode === "add" && <TxForm pid={pid} defaultDate={asOf} onDone={() => setMode(null)} />}
      {mode === "import" && <CsvImport pid={pid} onClose={() => setMode(null)} />}
      {mode && typeof mode === "object" && <TxForm key={mode.id} pid={pid} tx={mode} defaultDate={asOf} onDone={() => setMode(null)} />}
      <div className="card flex flex-wrap items-end gap-2 p-3" role="search" aria-label="Filter transactions">
        <input aria-label="Symbol" placeholder="Symbol (exact)" className="input w-36" value={f.symbol} onChange={set("symbol")} />
        <select aria-label="Type" className="input" value={f.type} onChange={set("type")}><option value="">All types</option>{TYPES.map((t) => <option key={t}>{t}</option>)}</select>
        <select aria-label="Asset class" className="input" value={f.asset_type} onChange={set("asset_type")}><option value="">All asset classes</option><option value="STOCK">Stocks</option><option value="ETF">ETFs</option><option value="MUTUAL_FUND">Mutual funds</option></select>
        <select aria-label="Source" className="input" value={f.source} onChange={set("source")}><option value="">Manual + SIP</option><option value="manual">Manual only</option><option value="sip">SIP only</option></select>
        <input aria-label="From date" type="date" className="input" value={f.date_from} onChange={set("date_from")} />
        <input aria-label="To date" type="date" className="input" value={f.date_to} onChange={set("date_to")} />
        <button className="btn" onClick={() => { setF({ symbol: "", type: "", asset_type: "", source: "", date_from: "", date_to: "" }); setPage(1); }}>Clear</button>
      </div>
      {error && <ErrorBox error={error} />}
      {loadError ? <ErrorBox error={loadError} /> : !data ? <Loading /> : data.items.length === 0 ? <Empty>No transactions match.</Empty> : (
        <div className="card overflow-x-auto p-0">
          <table className="w-full">
            <caption className="sr-only">Transactions</caption>
            <thead><tr>{["Date", "Type", "Symbol", "Qty", "Price", "Fee", "Cash", "Notes", ""].map((h) => <th key={h} scope="col" className="th">{h}</th>)}</tr></thead>
            <tbody>{data.items.map((t) => (
              <tr key={t.id} className="row">
                <td className="td">{t.trade_date.slice(0, 10)}</td><td className="td">{t.type}{t.notes?.startsWith("SIP") && <span className="chip ml-1 bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-200">SIP</span>}</td><td className="td">{t.symbol ?? "—"}</td>
                <td className="td">{t.quantity ? qty(t.quantity) : "—"}</td><td className="td">{money(t.price)}</td><td className="td">{Number(t.fee) ? money(t.fee) : "—"}</td>
                <td className="td">{money(t.cash_amount)}</td><td className="td max-w-40 truncate">{t.notes}</td>
                <td className="td whitespace-nowrap"><button className="btn mr-1" onClick={() => setMode(t)} aria-label={`Edit ${t.type} ${t.trade_date.slice(0, 10)}`}>Edit</button>
                  <button className="btn" onClick={() => remove(t)} aria-label={`Delete ${t.type} ${t.trade_date.slice(0, 10)}`}>Delete</button></td>
              </tr>))}</tbody>
          </table>
        </div>)}
      {data && (
        <div className="flex items-center gap-3 text-sm">
          <button className="btn" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</button>
          <span>Page {page} of {Math.max(1, Math.ceil(data.total / data.page_size))} ({data.total} total)</span>
          <button className="btn" disabled={page * data.page_size >= data.total} onClick={() => setPage(page + 1)}>Next</button>
        </div>)}
    </div>
  );
}
