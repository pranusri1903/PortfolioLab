"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { usePid } from "../layout";
import { CorrelationGrid, Donut, DrawdownChart, ProfitBars, RiskReturn } from "@/components/charts";
import { Empty, ErrorBox, Loading, PageTitle, SampleBadge, Seg, Stat } from "@/components/ui";
import { base, useData } from "@/lib/api";
import { TYPE_LABEL, money, percent, qty, signClass } from "@/lib/format";
import type { Analytics, HoldingAnalytics } from "@/lib/types";

const CLASSES = [["", "All"], ["STOCK", "Stocks"], ["ETF", "ETFs"], ["MUTUAL_FUND", "Mutual funds"]];
const STATUS = [["open", "Open"], ["closed", "Closed"], ["all", "All"]];
type SortKey = keyof HoldingAnalytics;

export default function AnalyticsPage() {
  const pid = usePid();
  const [kind, setKind] = useState("");
  const [status, setStatus] = useState("open");
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "current_value", dir: -1 });
  const { data, error } = useData<Analytics>(`${base(pid)}/analytics${kind ? `?asset_type=${kind}` : ""}`);
  const rows = useMemo(() => (data?.holdings ?? []).filter((h) => status === "all" || h.open === (status === "open")).sort((a, b) => {
    const [x, y] = [a[sort.key], b[sort.key]];
    if (x == null) return 1;
    if (y == null) return -1;
    return (typeof x === "string" && isNaN(Number(x)) ? x.localeCompare(String(y)) : Number(x) - Number(y)) * sort.dir;
  }), [data, status, sort]);

  if (error) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  const c = data.concentration;
  const profit = rows.reduce((s, h) => s + Number(h.total_return ?? 0), 0);
  const COLS: [SortKey, string, boolean][] = [
    ["symbol", "Holding", false], ["total_invested", "Invested", true], ["current_value", "Value", true], ["unrealized_gain_loss", "Unrealized", true],
    ["realized_gain_loss", "Realized", true], ["dividends", "Dividends", true], ["total_return", "Total return", true], ["xirr", "XIRR", true],
    ["volatility_1y", "Volatility 1Y", true], ["max_drawdown_1y", "Max DD 1Y", true], ["pct_from_high", "From 52W high", true], ["weight", "Weight", true],
  ];

  return (
    <div className="space-y-5">
      <PageTitle title="Analytics" sub={<span className="flex items-center gap-2"><SampleBadge show={data.is_sample_data} />Every holding, including sold positions · as of {data.as_of}</span>}>
        <Seg label="Asset class" opts={CLASSES} value={kind} set={setKind} />
        <Seg label="Position status" opts={STATUS} value={status} set={setStatus} />
      </PageTitle>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Portfolio XIRR" value={data.portfolio_xirr.value == null ? "—" : percent(data.portfolio_xirr.value)} tone={data.portfolio_xirr.value}
          sub={data.portfolio_xirr.reason ?? "annualised, money-weighted"} hint="Annualised return that accounts for the timing of every deposit and withdrawal." />
        <Stat label="Realized gains" value={money(data.realized_total)} tone={data.realized_total} hint="Profit locked in by selling, net of fees." />
        <Stat label="Dividends" value={money(data.dividends_total)} tone={data.dividends_total} />
        <Stat label="Diversification" value={c.effective_holdings ? `${c.effective_holdings.toFixed(1)} effective` : "—"}
          sub={c.top3 != null ? `Top 3 = ${percent(c.top3)} of holdings` : undefined} hint="1 ÷ Σ(weight²). 10 equal holdings = 10; one holding = 1." />
      </div>

      {rows.length === 0 ? <Empty>No holdings for this filter. Add transactions or a SIP to see analytics.</Empty> : (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <section className="card"><h2 className="mb-3 font-semibold">Total return by holding</h2><ProfitBars rows={rows} />
              <p className="mt-2 text-xs text-slate-500">Unrealized + realized + dividends. Sum: <span className={signClass(profit)}>{money(profit)}</span></p></section>
            <section className="card"><h2 className="mb-1 font-semibold">Risk vs return (1 year)</h2>
              <p className="mb-2 text-xs text-slate-500">Bubble size = portfolio weight. Up and to the left is better.</p><RiskReturn rows={rows} /></section>
          </div>

          <section className="card overflow-x-auto p-0">
            <table className="w-full min-w-[1100px]">
              <caption className="sr-only">Per-holding analytics</caption>
              <thead><tr>{COLS.map(([key, label, right]) => (
                <th key={key} scope="col" className={`th ${right ? "text-right" : ""}`} aria-sort={sort.key === key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
                  <button onClick={() => setSort({ key, dir: sort.key === key ? (-sort.dir as 1 | -1) : -1 })}>{label}{sort.key === key && (sort.dir === 1 ? " ▲" : " ▼")}</button></th>))}</tr></thead>
              <tbody>{rows.map((h) => (
                <tr key={h.symbol} className="row">
                  <td className="td"><Link href={`/holdings/${h.symbol}`} className="font-medium text-blue-700 underline">{h.symbol}</Link>
                    <span className="chip ml-2 bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">{TYPE_LABEL[h.asset_type] ?? h.asset_type}</span>
                    {!h.open && <span className="chip ml-1 bg-amber-100 text-amber-800">Closed</span>}
                    <div className="text-xs text-slate-500">{h.name} · {h.open ? `${qty(h.quantity)} units` : "sold"}{h.holding_days != null && ` · ${Math.round(h.holding_days / 30)} mo`}</div></td>
                  <td className="td text-right">{money(h.total_invested)}</td>
                  <td className="td text-right">{h.open ? money(h.current_value) : "—"}</td>
                  <td className={`td text-right ${signClass(h.unrealized_gain_loss)}`}>{h.open ? money(h.unrealized_gain_loss) : "—"}</td>
                  <td className={`td text-right ${signClass(h.realized_gain_loss)}`}>{money(h.realized_gain_loss)}</td>
                  <td className="td text-right">{money(h.dividends)}</td>
                  <td className={`td text-right font-semibold ${signClass(h.total_return)}`}>{money(h.total_return)}<div className="text-xs font-normal">{percent(h.total_return_pct)}</div></td>
                  <td className={`td text-right ${signClass(h.xirr)}`}>{percent(h.xirr)}</td>
                  <td className="td text-right">{percent(h.volatility_1y)}</td>
                  <td className="td text-right">{percent(h.max_drawdown_1y)}</td>
                  <td className="td text-right">{h.open ? percent(h.pct_from_high) : "—"}</td>
                  <td className="td text-right">{percent(h.weight)}</td>
                </tr>))}</tbody>
            </table>
          </section>

          <div className="grid gap-4 lg:grid-cols-3">
            <section className="card"><h2 className="font-semibold">By asset class</h2>
              <Donut title="Allocation by asset class" slices={data.by_class.map((b) => ({ key: TYPE_LABEL[b.asset_type] ?? b.asset_type, label: TYPE_LABEL[b.asset_type] ?? b.asset_type, value: b.value, weight: b.weight }))} /></section>
            <section className="card lg:col-span-2"><h2 className="mb-3 font-semibold">Drawdown from previous peak</h2>
              {data.drawdown.length ? <DrawdownChart points={data.drawdown} /> : <Empty>Needs more history.</Empty>}</section>
          </div>

          <section className="card"><h2 className="mb-1 font-semibold">Correlation of daily returns (1 year)</h2>
            <p className="mb-3 text-xs text-slate-500">Closer to 0 or negative means the holdings move more independently, which diversifies risk. Shown for up to 12 open holdings with 30+ shared trading days.</p>
            {data.correlation.symbols.length > 1 ? <CorrelationGrid symbols={data.correlation.symbols} matrix={data.correlation.matrix} /> : <Empty>Needs two or more open holdings.</Empty>}</section>
        </>)}
      <p className="text-xs text-slate-500">XIRR needs at least 30 days of history. Volatility and drawdown use the last year of the asset&apos;s own prices. Sample portfolios use synthetic prices.</p>
    </div>
  );
}
