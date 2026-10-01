"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { usePid } from "../layout";
import { Empty, ErrorBox, Loading, SampleBadge } from "@/components/ui";
import { base, useData } from "@/lib/api";
import { money, percent, qty, signClass } from "@/lib/format";
import type { Holding, Holdings } from "@/lib/types";

const COLS: [keyof Holding, string, boolean][] = [
  ["symbol", "Symbol", false], ["quantity", "Quantity", true], ["latest_price", "Latest price", true],
  ["market_value", "Market value", true], ["average_cost", "Avg cost", true],
  ["unrealized_gain_loss", "Unrealized G/L", true], ["weight", "Weight", true],
];

export default function HoldingsPage() {
  const pid = usePid();
  const { data, error } = useData<Holdings>(`${base(pid)}/holdings`);
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<{ key: keyof Holding; dir: 1 | -1 }>({ key: "market_value", dir: -1 });
  const rows = useMemo(() => {
    const needle = q.toLowerCase();
    const num = (h: Holding) => h[sort.key] as string | number | null;
    return (data?.holdings ?? [])
      .filter((h) => h.symbol.toLowerCase().includes(needle) || h.name.toLowerCase().includes(needle))
      .sort((a, b) => {
        const [x, y] = [num(a), num(b)];
        if (x == null) return 1;
        if (y == null) return -1;
        return (typeof x === "string" && isNaN(Number(x)) ? x.localeCompare(y as string) : Number(x) - Number(y)) * sort.dir;
      });
  }, [data, q, sort]);

  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold tracking-tight">Holdings</h1>
        <div className="flex items-center gap-2"><SampleBadge show={data.is_sample_data} /><span className="text-sm text-slate-500">as of {data.as_of}</span>
          <input aria-label="Search holdings" placeholder="Search symbol or name" className="input" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      </div>
      {!data.value_complete && <p role="alert" className="rounded border border-amber-300 bg-amber-50 p-3 text-sm">Price unavailable for {data.unavailable_symbols.join(", ")}.</p>}
      {rows.length === 0 ? <Empty>No holdings{q ? " match your search" : " yet. Add a BUY transaction."}</Empty> : (
        <div className="card overflow-x-auto p-0">
          <table className="w-full">
            <caption className="sr-only">Current holdings</caption>
            <thead><tr>{COLS.map(([key, label, right]) => (
              <th key={key} scope="col" className={`th ${right ? "text-right" : ""}`}
                aria-sort={sort.key === key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
                <button onClick={() => setSort({ key, dir: sort.key === key ? (-sort.dir as 1 | -1) : -1 })}>{label}{sort.key === key && (sort.dir === 1 ? " ▲" : " ▼")}</button>
              </th>))}</tr></thead>
            <tbody>{rows.map((h) => (
              <tr key={h.symbol} className="row">
                <td className="td"><Link className="font-medium text-blue-700 underline" href={`/holdings/${h.symbol}`}>{h.symbol}</Link><div className="text-xs text-slate-500">{h.name}</div></td>
                <td className="td text-right">{qty(h.quantity)}</td>
                <td className="td text-right">{h.latest_price ? money(h.latest_price) : <span className="text-red-700">Unavailable</span>}
                  {h.price_status === "stale" && <div className="text-xs text-amber-700">stale ({h.price_date})</div>}</td>
                <td className="td text-right">{money(h.market_value)}</td>
                <td className="td text-right">{money(h.average_cost)}</td>
                <td className={`td text-right ${signClass(h.unrealized_gain_loss)}`}>{money(h.unrealized_gain_loss)}<div className="text-xs">{percent(h.unrealized_gain_loss_pct)}</div></td>
                <td className="td text-right">{percent(h.weight)}</td>
              </tr>))}</tbody>
          </table>
        </div>)}
      <p className="text-xs text-slate-500">Cost basis uses the weighted-average method (an analytics convention, not tax accounting).</p>
    </div>
  );
}
