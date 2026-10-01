"use client";
import { Coins, PiggyBank, Receipt, TrendingDown, TrendingUp, Wallet } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { usePid } from "../layout";
import { BenchmarkChart, Donut, Sparkline, ValueChart } from "@/components/charts";
import { MonthlyHeatmap } from "@/components/heatmap";
import { Empty, ErrorBox, Loading, PageTitle, SampleBadge, Stat } from "@/components/ui";
import { base, useData } from "@/lib/api";
import { money, percent, signClass } from "@/lib/format";
import type { Allocation, Holdings, Metric, MonthlyReturns, Performance, Summary, TxPage } from "@/lib/types";

const RANGES = ["1M", "3M", "1Y", "All"] as const;
const num = (v: number | null) => v?.toFixed(2) ?? "—";
const METRICS = [
  ["cumulative_return", "Cumulative return", "Time-weighted return over the selected range. Deposits/withdrawals are excluded.", percent],
  ["benchmark_cumulative_return", "Benchmark return", "Cumulative return of the sample benchmark ETF over the same dates.", percent],
  ["annualized_volatility", "Volatility (ann.)", "Standard deviation of daily returns × √252.", percent],
  ["sharpe_ratio", "Sharpe ratio", "Mean excess daily return ÷ its standard deviation × √252, using the stated risk-free rate.", num],
  ["max_drawdown", "Max drawdown", "Largest peak-to-trough decline of the return index in the range.", percent],
] as const;

export default function Dashboard() {
  const pid = usePid();
  const [range, setRange] = useState<(typeof RANGES)[number]>("1Y");
  const summary = useData<Summary>(`${base(pid)}/summary?range=${range}`);
  const perf = useData<Performance>(`${base(pid)}/performance?range=${range}`);
  const alloc = useData<Allocation>(`${base(pid)}/allocation`);
  const recent = useData<TxPage>(`${base(pid)}/transactions?page_size=5`);
  const monthly = useData<MonthlyReturns>(`${base(pid)}/performance/monthly`);
  const holdings = useData<Holdings>(`${base(pid)}/holdings`);

  if (summary.error) return <ErrorBox error={summary.error} />;
  if (!summary.data) return <Loading />;
  const s = summary.data;
  const gl = Number(s.total_gain_loss);
  const ranked = (holdings.data?.holdings ?? []).filter((h) => h.unrealized_gain_loss_pct != null)
    .sort((a, b) => b.unrealized_gain_loss_pct! - a.unrealized_gain_loss_pct!);
  const performers = [...ranked.slice(0, 3), ...ranked.slice(-3).filter((h) => !ranked.slice(0, 3).includes(h))];

  return (
    <div className="space-y-5">
      <PageTitle title="Dashboard" sub={<span className="flex items-center gap-2"><SampleBadge show={s.is_sample_data} />{s.as_of && <span>Prices as of {s.as_of}</span>}</span>}>
        <div role="group" aria-label="Date range" className="flex gap-1 rounded-xl bg-slate-200/60 p-1 dark:bg-slate-800">
          {RANGES.map((r) => (
            <button key={r} aria-pressed={r === range} onClick={() => setRange(r)}
              className={`rounded-lg px-3 py-1 text-sm font-medium transition ${r === range ? "bg-white text-indigo-700 shadow dark:bg-slate-700 dark:text-white" : "text-slate-600"}`}>{r}</button>
          ))}
        </div>
      </PageTitle>

      {!s.value_complete && (
        <p role="alert" className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm">
          No price available for {s.unavailable_symbols.join(", ")}; those positions are excluded from the total value.
        </p>
      )}

      <section className="hero relative overflow-hidden rounded-3xl bg-gradient-to-br from-indigo-600 via-violet-600 to-fuchsia-600 p-6 text-white shadow-lg" aria-label="Total portfolio value">
        <div className="grid items-end gap-4 md:grid-cols-[1fr_20rem]">
          <div>
            <div className="text-sm font-medium text-indigo-100">Total portfolio value</div>
            <div className="mt-1 text-4xl font-bold tracking-tight md:text-5xl">{money(s.total_value)}</div>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
              <span className="inline-flex items-center gap-1 rounded-full bg-white/20 px-3 py-1 font-medium">
                {gl >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}{money(s.total_gain_loss)} {s.total_gain_loss_pct != null && `(${percent(s.total_gain_loss_pct)})`}
              </span>
              <span className="text-indigo-100">all-time vs. net deposits</span>
            </div>
          </div>
          {perf.data && perf.data.series.length > 1 && <Sparkline values={perf.data.series.map((p) => Number(p.total_value))} />}
        </div>
      </section>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Invested" value={money(s.market_value)} icon={Wallet} />
        <Stat label="Cash balance" value={money(s.cash_balance)} icon={PiggyBank} />
        <Stat label={`Return (${range})`} value={s.period_return.value == null ? "—" : percent(s.period_return.value)} tone={s.period_return.value}
          sub={s.period_return.reason ?? undefined} icon={TrendingUp} hint="Time-weighted; excludes the effect of deposits and withdrawals." />
        <Stat label="Net deposits" value={money(s.net_contributions)} icon={Coins} hint="Deposits minus withdrawals." />
      </div>

      {perf.error ? <ErrorBox error={perf.error} /> : !perf.data ? <Loading /> : perf.data.series.length < 2 ? (
        <Empty>Not enough history for this range yet. Add transactions or choose a longer range.</Empty>
      ) : (
        <>
          {perf.data.partial && (
            <p className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm">
              History starts {perf.data.start_date}, after the start of the {range} window — showing available data only.
            </p>
          )}
          <div className="grid gap-4 lg:grid-cols-2">
            <section className="card"><h2 className="mb-3 font-semibold">Portfolio value</h2><ValueChart series={perf.data.series} /></section>
            <section className="card"><h2 className="mb-3 font-semibold">vs. benchmark <span className="text-xs font-normal text-slate-500">(indexed to 100)</span></h2>
              <BenchmarkChart series={perf.data.series} benchmark={perf.data.benchmark_symbol} /></section>
          </div>
          <section className="card">
            <h2 className="mb-3 font-semibold">Performance metrics <Link href="/methodology" className="ml-2 text-sm font-normal text-blue-700 underline">Methodology</Link></h2>
            <dl className="grid grid-cols-2 gap-4 md:grid-cols-5">
              {METRICS.map(([key, label, hint, fmt]) => {
                const m: Metric = perf.data!.metrics[key];
                return (
                  <div key={key} className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/50">
                    <dt className="text-xs uppercase tracking-wide text-slate-500" title={hint}>{label} ⓘ</dt>
                    <dd className={`mt-1 text-xl font-semibold ${key === "sharpe_ratio" ? "" : signClass(m.value)}`}>{m.value == null ? "—" : (fmt as (v: number | null) => string)(m.value)}</dd>
                    {m.reason && <dd className="text-xs text-slate-500">{m.reason}</dd>}
                  </div>
                );
              })}
            </dl>
            <p className="mt-3 text-xs text-slate-500">Risk-free rate assumption: {percent(perf.data.risk_free_rate)} annual. Cash flows assumed at end of day.</p>
          </section>
        </>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <section className="card lg:col-span-2">
          <h2 className="mb-3 font-semibold">Monthly returns</h2>
          {monthly.data && monthly.data.months.length > 0 ? <MonthlyHeatmap months={monthly.data.months} /> : <Empty>Monthly returns appear once there is history.</Empty>}
        </section>
        <section className="card space-y-3">
          <h2 className="font-semibold">Income &amp; costs</h2>
          {([["Realized gain/loss", s.realized_gain_loss, Coins], ["Dividends received", s.dividend_income, PiggyBank], ["Fees paid", s.fees_paid, Receipt]] as const).map(([label, v, Icon]) => (
            <div key={label} className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-2 text-slate-500"><Icon size={15} />{label}</span>
              <span className={`font-semibold ${label === "Fees paid" ? "" : signClass(v)}`}>{money(v)}</span>
            </div>))}
        </section>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <section className="card"><h2 className="font-semibold">By holding</h2>
          {alloc.data ? <Donut title="Allocation by holding" slices={alloc.data.by_holding} /> : <Loading />}</section>
        <section className="card"><h2 className="font-semibold">By asset type</h2>
          {alloc.data ? <Donut title="Allocation by asset type" slices={alloc.data.by_asset_type} /> : <Loading />}</section>
        <section className="card"><h2 className="mb-3 font-semibold">Best &amp; worst positions</h2>
          {performers.length === 0 ? <Empty>No open positions.</Empty> : (
            <ul className="space-y-2">{performers.map((h) => (
              <li key={h.symbol} className="flex items-center justify-between text-sm">
                <Link href={`/holdings/${h.symbol}`} className="font-medium text-blue-700 underline">{h.symbol}</Link>
                <span className={`font-semibold ${signClass(h.unrealized_gain_loss)}`}>{percent(h.unrealized_gain_loss_pct)}</span>
              </li>))}</ul>)}
        </section>
      </div>

      <section className="card">
        <h2 className="mb-2 font-semibold">Recent transactions <Link href="/transactions" className="ml-2 text-sm font-normal text-blue-700 underline">View all</Link></h2>
        {!recent.data ? <Loading /> : recent.data.items.length === 0 ? <Empty>No transactions yet.</Empty> : (
          <table className="w-full"><thead><tr><th className="th">Date</th><th className="th">Type</th><th className="th">Symbol</th><th className="th text-right">Amount</th></tr></thead>
            <tbody>{recent.data.items.map((t) => (
              <tr key={t.id} className="row"><td className="td">{t.trade_date.slice(0, 10)}</td><td className="td">{t.type}</td><td className="td">{t.symbol ?? "—"}</td>
                <td className="td text-right">{t.cash_amount ? money(t.cash_amount) : money(Number(t.quantity) * Number(t.price))}</td></tr>
            ))}</tbody></table>
        )}
      </section>
    </div>
  );
}
