"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { usePid } from "../layout";
import { Empty, ErrorBox, Loading, PageTitle, SampleBadge, Seg } from "@/components/ui";
import { base, useData } from "@/lib/api";
import { TYPE_LABEL, money, percent, qty, signClass } from "@/lib/format";
import type { Holding, Holdings } from "@/lib/types";

const COLS: [keyof Holding, string, boolean][] = [
  ["symbol", "Holding", false], ["quantity", "Units", true], ["latest_price", "Price / NAV", true],
  ["market_value", "Market value", true], ["average_cost", "Avg cost", true],
  ["unrealized_gain_loss", "Unrealized G/L", true], ["weight", "Weight", true],
];
const CLASSES = [["", "All"], ["STOCK", "Stocks"], ["ETF", "ETFs"], ["MUTUAL_FUND", "Mutual funds"]];
const RESULTS = [["", "All"], ["gain", "In profit"], ["loss", "In loss"]];

export default function HoldingsPage() {
  const pid = usePid();
  const [kind, setKind] = useState("");
  const [result, setResult] = useState("");
  const { data, error } = useData<Holdings>(`${base(pid)}/holdings${kind ? `?asset_type=${kind}` : ""}`);
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<{ key: keyof Holding; dir: 1 | -1 }>({ key: "market_value", dir: -1 });
  const rows = useMemo(() => {
    const needle = q.toLowerCase();
    const num = (h: Holding) => h[sort.key] as string | number | null;
    return (data?.holdings ?? [])
      .filter((h) => h.symbol.toLowerCase().includes(needle) || h.name.toLowerCase().includes(needle))
      .filter((h) => !result || (result === "gain" ? Number(h.unrealized_gain_loss) > 0 : Number(h.unrealized_gain_loss) < 0))
      .sort((a, b) => {
        const [x, y] = [num(a), num(b)];
        if (x == null) return 1;
        if (y == null) return -1;
        return (typeof x === "string" && isNaN(Number(x)) ? x.localeCompare(y as string) : Number(x) - Number(y)) * sort.dir;
      });
  }, [data, q, sort, result]);

  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  const total = rows.reduce((s, h) => s + Number(h.market_value ?? 0), 0);
  const gl = rows.reduce((s, h) => s + Number(h.unrealized_gain_loss ?? 0), 0);
  return (
    <div className="space-y-4">
      <PageTitle title="Holdings" sub={<span className="flex items-center gap-2"><SampleBadge show={data.is_sample_data} />as of {data.as_of}</span>}>
        <input aria-label="Search holdings" placeholder="Search symbol or name" className="input" value={q} onChange={(e) => setQ(e.target.value)} />
      </PageTitle>
      <div className="flex flex-wrap items-center gap-3">
        <Seg label="Asset class" opts={CLASSES} value={kind} set={setKind} />
        <Seg label="Result" opts={RESULTS} value={result} set={setResult} />
        <span className="ml-auto text-sm text-slate-500">{rows.length} holdings · {money(total)} · <span className={signClass(gl)}>{money(gl)}</span></span>
      </div>
      {!data.value_complete && <p role="alert" className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm">Price unavailable for {data.unavailable_symbols.join(", ")}.</p>}
      {rows.length === 0 ? <Empty>No holdings{q || kind || result ? " match your filters" : " yet. Add a BUY transaction or a SIP."}</Empty> : (
        <div className="card overflow-x-auto p-0">
          <table className="w-full">
            <caption className="sr-only">Current holdings</caption>
            <thead><tr>{COLS.map(([key, label, right]) => (
              <th key={key} scope="col" className={`th ${right ? "text-right" : ""}`} aria-sort={sort.key === key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
                <button onClick={() => setSort({ key, dir: sort.key === key ? (-sort.dir as 1 | -1) : -1 })}>{label}{sort.key === key && (sort.dir === 1 ? " ▲" : " ▼")}</button>
              </th>))}</tr></thead>
            <tbody>{rows.map((h) => (
              <tr key={h.symbol} className="row">
                <td className="td"><Link className="font-medium text-blue-700 underline" href={`/holdings/${h.symbol}`}>{h.symbol}</Link>
                  <span className="chip ml-2 bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">{TYPE_LABEL[h.asset_type] ?? h.asset_type}</span>
                  <div className="text-xs text-slate-500">{h.name}</div></td>
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
      <p className="text-xs text-slate-500">Cost basis uses the weighted-average method (an analytics convention, not tax accounting). Full per-holding analytics are on the Analytics page.</p>
    </div>
  );
}
