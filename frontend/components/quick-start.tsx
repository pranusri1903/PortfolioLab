"use client";
import { Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useSWRConfig } from "swr";
import { SymbolPicker } from "@/components/symbol-picker";
import { ErrorBox } from "@/components/ui";
import { base, useApi } from "@/lib/api";
import { getCurrency, symbolOf } from "@/lib/format";

type Row = { key: number; symbol: string; quantity: string; price: string; date: string };
let counter = 0;
const blank = (): Row => ({ key: ++counter, symbol: "", quantity: "", price: "", date: "" });

/** "What I own" wizard: becomes one opening deposit plus one BUY per holding. */
export function QuickStart({ pid }: { pid: string }) {
  const api = useApi();
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const [rows, setRows] = useState<Row[]>([blank()]);
  const [cash, setCash] = useState("");
  const [error, setError] = useState<Error>();
  const cur = getCurrency();
  const set = (key: number, patch: Partial<Row>) => setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api(`${base(pid)}/quick-start`, { method: "POST", body: JSON.stringify({
        cash: cash || "0",
        holdings: rows.filter((r) => r.symbol).map((r) => ({ symbol: r.symbol, quantity: r.quantity, average_price: r.price, date: r.date })),
      }) });
      await mutate(() => true);
      router.push("/dashboard");
    } catch (err) { setError(err as Error); }
  }

  return (
    <form onSubmit={submit} className="card space-y-4" aria-label="Quick start">
      <div>
        <h2 className="text-lg font-semibold">Enter what you own</h2>
        <p className="text-sm text-slate-500">Stocks, ETFs or mutual funds. Use your average buy price and the date you first bought. Returns before that date are approximate.</p>
      </div>
      {error && <ErrorBox error={error} />}
      {rows.map((r, i) => (
        <div key={r.key} className="grid items-end gap-3 md:grid-cols-[2fr_1fr_1fr_1fr_auto]">
          <SymbolPicker currency={cur} label={i === 0 ? "Stock, ETF or fund" : "Holding"} onSelect={(a) => set(r.key, { symbol: a.symbol })} />
          <label className="block text-sm">Units / shares<input className="input mt-1 w-full" inputMode="decimal" required value={r.quantity} onChange={(e) => set(r.key, { quantity: e.target.value })} /></label>
          <label className="block text-sm">Avg price ({symbolOf()})<input className="input mt-1 w-full" inputMode="decimal" required value={r.price} onChange={(e) => set(r.key, { price: e.target.value })} /></label>
          <label className="block text-sm">First bought<input type="date" className="input mt-1 w-full" required value={r.date} onChange={(e) => set(r.key, { date: e.target.value })} /></label>
          <button type="button" className="btn" aria-label="Remove holding" disabled={rows.length === 1} onClick={() => setRows(rows.filter((x) => x.key !== r.key))}><Trash2 size={15} /></button>
        </div>))}
      <button type="button" className="btn" onClick={() => setRows([...rows, blank()])}><Plus size={15} />Add another holding</button>
      <label className="block max-w-xs text-sm">Cash balance ({symbolOf()}, optional)<input className="input mt-1 w-full" inputMode="decimal" value={cash} onChange={(e) => setCash(e.target.value)} /></label>
      <button className="btn-primary" disabled={!rows.some((r) => r.symbol) && !cash}>Build my portfolio</button>
    </form>
  );
}
