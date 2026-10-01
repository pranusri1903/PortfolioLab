"use client";
import { useState } from "react";
import { useSWRConfig } from "swr";
import { ErrorBox } from "@/components/ui";
import { base, useApi } from "@/lib/api";
import type { Asset, Tx } from "@/lib/types";

const TYPES = ["BUY", "SELL", "DIVIDEND", "DEPOSIT", "WITHDRAWAL", "FEE"];
const TRADE = ["BUY", "SELL"];

const Field = ({ label, children }: { label: string; children: React.ReactNode }) => <label className="block text-sm">{label}<div className="mt-1">{children}</div></label>;

export function TxForm({ pid, assets, tx, defaultDate, onDone }: { pid: string; assets: Asset[]; tx?: Tx; defaultDate: string; onDone: () => void }) {
  const api = useApi();
  const { mutate } = useSWRConfig();
  const [type, setType] = useState(tx?.type ?? "BUY");
  const [error, setError] = useState<Error>();

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const val = (k: string) => (f.get(k) as string)?.trim() || null;
    const body = {
      type, trade_date: val("trade_date"), symbol: val("symbol"), notes: val("notes"), fee: TRADE.includes(type) ? val("fee") ?? "0" : "0",
      quantity: TRADE.includes(type) ? val("quantity") : null, price: TRADE.includes(type) ? val("price") : null,
      cash_amount: TRADE.includes(type) ? null : val("cash_amount"),
    };
    try {
      await api(tx ? `${base(pid)}/transactions/${tx.id}` : `${base(pid)}/transactions`, { method: tx ? "PATCH" : "POST", body: JSON.stringify(body) });
      await mutate(() => true);
      onDone();
    } catch (err) { setError(err as Error); }
  }

  const needsSymbol = type !== "DEPOSIT" && type !== "WITHDRAWAL" && type !== "FEE";
  return (
    <form onSubmit={submit} className="card space-y-3" aria-label={tx ? "Edit transaction" : "Add transaction"}>
      <h2 className="font-semibold">{tx ? "Edit transaction" : "Add transaction"}</h2>
      {error && <ErrorBox error={error} />}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Field label="Type"><select name="type" className="input w-full" value={type} onChange={(e) => setType(e.target.value)}>{TYPES.map((t) => <option key={t}>{t}</option>)}</select></Field>
        <Field label="Date"><input name="trade_date" type="date" required className="input w-full" defaultValue={tx?.trade_date.slice(0, 10) ?? defaultDate} /></Field>
        {needsSymbol && <Field label="Symbol"><select name="symbol" required className="input w-full" defaultValue={tx?.symbol ?? ""}><option value="" disabled>Select…</option>{assets.map((a) => <option key={a.symbol} value={a.symbol}>{a.symbol}</option>)}</select></Field>}
        {TRADE.includes(type) ? (<>
          <Field label="Quantity"><input name="quantity" required inputMode="decimal" className="input w-full" defaultValue={tx?.quantity ?? ""} /></Field>
          <Field label="Price"><input name="price" required inputMode="decimal" className="input w-full" defaultValue={tx?.price ?? ""} /></Field>
          <Field label="Fee"><input name="fee" inputMode="decimal" className="input w-full" defaultValue={tx?.fee ?? "0"} /></Field>
        </>) : <Field label="Amount (USD)"><input name="cash_amount" required inputMode="decimal" className="input w-full" defaultValue={tx?.cash_amount ?? ""} /></Field>}
        <Field label="Notes"><input name="notes" maxLength={500} className="input w-full" defaultValue={tx?.notes ?? ""} /></Field>
      </div>
      <div className="flex gap-2"><button className="btn-primary">Save</button><button type="button" className="btn" onClick={onDone}>Cancel</button></div>
    </form>
  );
}
