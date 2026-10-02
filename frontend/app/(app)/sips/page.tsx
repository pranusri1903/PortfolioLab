"use client";
import { Pause, Play, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useSWRConfig } from "swr";
import { usePid, usePortfolio } from "../layout";
import { SymbolPicker } from "@/components/symbol-picker";
import { Empty, ErrorBox, Loading, PageTitle, Stat } from "@/components/ui";
import { base, useApi, useData } from "@/lib/api";
import { TYPE_LABEL, money, percent, qty, signClass, symbolOf } from "@/lib/format";
import type { Sip } from "@/lib/types";

export default function SipsPage() {
  const pid = usePid();
  const cur = usePortfolio().base_currency;
  const api = useApi();
  const { mutate } = useSWRConfig();
  const { data, error } = useData<Sip[]>(`${base(pid)}/sips`);
  const [adding, setAdding] = useState(false);
  const [symbol, setSymbol] = useState("");
  const [err, setErr] = useState<Error>();

  async function create(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    try {
      await api(`${base(pid)}/sips`, { method: "POST", body: JSON.stringify({
        symbol, amount: f.get("amount"), day_of_month: Number(f.get("day")), start_date: f.get("start"), end_date: f.get("end") || null }) });
      await mutate(() => true);
      setAdding(false); setErr(undefined);
    } catch (e2) { setErr(e2 as Error); }
  }
  const act = (fn: () => Promise<unknown>) => fn().then(() => mutate(() => true)).catch(setErr);

  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  const invested = data.reduce((s, x) => s + Number(x.invested), 0);
  const value = data.reduce((s, x) => s + Number(x.current_value ?? 0), 0);
  return (
    <div className="space-y-5">
      <PageTitle title="SIPs" sub="Recurring monthly investments. Each installment buys units at that day's NAV or close.">
        <button className="btn-primary" onClick={() => setAdding(!adding)}><Plus size={15} />New SIP</button>
      </PageTitle>
      {err && <ErrorBox error={err} />}
      {adding && (
        <form onSubmit={create} className="card grid items-end gap-3 md:grid-cols-5" aria-label="New SIP">
          <div className="md:col-span-2"><SymbolPicker currency={cur} label="Fund, ETF or stock" onSelect={(a) => setSymbol(a.symbol)} /></div>
          <label className="block text-sm">Monthly amount ({symbolOf()})<input name="amount" required inputMode="decimal" className="input mt-1 w-full" /></label>
          <label className="block text-sm">Day of month (1–28)<input name="day" type="number" min={1} max={28} defaultValue={5} required className="input mt-1 w-full" /></label>
          <label className="block text-sm">Start date<input name="start" type="date" required className="input mt-1 w-full" /></label>
          <label className="block text-sm">End date (optional)<input name="end" type="date" className="input mt-1 w-full" /></label>
          <div className="flex gap-2 md:col-span-4"><button className="btn-primary" disabled={!symbol}>Create SIP</button><button type="button" className="btn" onClick={() => setAdding(false)}>Cancel</button></div>
        </form>)}
      {data.length === 0 ? <Empty>No SIPs yet. Create one to track monthly investments automatically; past installments are filled in from historical prices.</Empty> : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Total invested via SIP" value={money(invested)} />
            <Stat label="Current value" value={money(value)} />
            <Stat label="Gain / loss" value={money(value - invested)} tone={value - invested} sub={invested ? percent((value - invested) / invested) : undefined} />
            <Stat label="Active plans" value={String(data.filter((x) => x.active).length)} sub={`${data.length} total`} />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            {data.map((x) => (
              <section key={x.id} className="card space-y-3" aria-label={`SIP ${x.symbol}`}>
                <div className="flex items-start justify-between gap-2">
                  <div><h2 className="font-semibold">{x.name}</h2>
                    <p className="text-xs text-slate-500">{x.symbol} · {TYPE_LABEL[x.asset_type] ?? x.asset_type} · {money(x.amount)} on day {x.day_of_month} · since {x.start_date}</p></div>
                  <span className={`chip ${x.active ? "bg-emerald-100 text-emerald-800" : "bg-slate-200 text-slate-600"}`}>{x.active ? "Active" : "Paused"}</span>
                </div>
                <dl className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
                  <div><dt className="text-xs text-slate-500">Installments</dt><dd className="font-semibold">{x.installments}</dd></div>
                  <div><dt className="text-xs text-slate-500">Invested</dt><dd className="font-semibold">{money(x.invested)}</dd></div>
                  <div><dt className="text-xs text-slate-500">Value</dt><dd className="font-semibold">{money(x.current_value)}</dd></div>
                  <div><dt className="text-xs text-slate-500">XIRR</dt><dd className={`font-semibold ${signClass(x.xirr)}`}>{percent(x.xirr)}</dd></div>
                </dl>
                <p className="text-xs text-slate-500">{qty(x.units)} units · gain <span className={signClass(x.gain_loss)}>{money(x.gain_loss)}</span>{x.next_date && ` · next ${x.next_date}`}</p>
                <div className="flex gap-2">
                  <button className="btn" onClick={() => act(() => api(`${base(pid)}/sips/${x.id}`, { method: "PATCH", body: JSON.stringify({ active: !x.active }) }))}>{x.active ? <Pause size={14} /> : <Play size={14} />}{x.active ? "Pause" : "Resume"}</button>
                  <button className="btn" onClick={() => confirm(`Stop SIP in ${x.symbol}? Past installments stay in your history.`) && act(() => api(`${base(pid)}/sips/${x.id}`, { method: "DELETE" }))}><Trash2 size={14} />Stop</button>
                </div>
              </section>))}
          </div>
        </>)}
      <p className="text-xs text-slate-500">Installments run on the first trading day (or NAV date) on/after your chosen day. Units are rounded down, so a tiny remainder stays in cash. Each installment appears in Transactions as a deposit plus a buy, so returns exclude the money you pay in.</p>
    </div>
  );
}
