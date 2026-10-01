"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { usePid } from "../../layout";
import { PriceChart } from "@/components/charts";
import { Empty, ErrorBox, Loading, SampleBadge, Stat } from "@/components/ui";
import { base, useData } from "@/lib/api";
import { money, percent, qty } from "@/lib/format";
import type { HoldingDetail } from "@/lib/types";

export default function HoldingPage() {
  const { symbol } = useParams<{ symbol: string }>();
  const { data: d, error } = useData<HoldingDetail>(`${base(usePid())}/holdings/${symbol}`);
  if (error) return <ErrorBox error={error} />;
  if (!d) return <Loading />;
  const h = d.holding;
  return (
    <div className="space-y-4">
      <Link href="/holdings" className="text-sm text-blue-700 underline">← Holdings</Link>
      <h1 className="flex items-center gap-2 text-2xl font-semibold">{d.symbol} <span className="text-base font-normal text-slate-600">{d.name}</span><SampleBadge show={d.is_sample_data} /></h1>
      {h ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Quantity" value={qty(h.quantity)} />
          <Stat label="Market value" value={money(h.market_value)} sub={`@ ${money(h.latest_price)}`} />
          <Stat label="Cost basis" value={money(h.cost_basis)} sub={`avg ${money(h.average_cost)}`} />
          <Stat label="Unrealized G/L" value={money(h.unrealized_gain_loss)} tone={h.unrealized_gain_loss} sub={percent(h.unrealized_gain_loss_pct)} />
        </div>
      ) : <Empty>No open position in {d.symbol}.</Empty>}
      <section className="card"><h2 className="mb-2 font-semibold">Price history {d.is_sample_data && "(sample prices)"}</h2>
        {d.price_history.length ? <PriceChart data={d.price_history} symbol={d.symbol} /> : <Empty>No price data available.</Empty>}</section>
      <section className="card"><h2 className="mb-2 font-semibold">Quantity and cost basis over time</h2>
        {d.position_history.length === 0 ? <Empty>No trades yet.</Empty> : (
          <table className="w-full"><thead><tr><th className="th">After trade on</th><th className="th">Quantity</th><th className="th">Cost basis</th></tr></thead>
            <tbody>{d.position_history.map((p, i) => <tr key={i} className="row"><td className="td">{p.date}</td><td className="td">{qty(p.quantity)}</td><td className="td">{money(p.cost_basis)}</td></tr>)}</tbody></table>)}</section>
      <section className="card"><h2 className="mb-2 font-semibold">Transactions</h2>
        {d.transactions.length === 0 ? <Empty>No transactions.</Empty> : (
          <table className="w-full"><thead><tr><th className="th">Date</th><th className="th">Type</th><th className="th">Qty</th><th className="th">Price</th><th className="th">Fee</th><th className="th">Cash</th></tr></thead>
            <tbody>{d.transactions.map((t) => (
              <tr key={t.id} className="row"><td className="td">{t.trade_date.slice(0, 10)}</td><td className="td">{t.type}</td><td className="td">{t.quantity ? qty(t.quantity) : "—"}</td>
                <td className="td">{money(t.price)}</td><td className="td">{money(t.fee)}</td><td className="td">{money(t.cash_amount)}</td></tr>))}</tbody></table>)}</section>
    </div>
  );
}
