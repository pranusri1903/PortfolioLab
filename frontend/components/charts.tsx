"use client";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ReferenceLine,
  ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from "recharts";
import { Accessible } from "@/components/ui";
import { money, moneyCompact, percent } from "@/lib/format";
import { GAIN, GRID, LAVENDER, LOSS, MINT, PASTEL, PEACH, PINK, PRIMARY } from "@/lib/palette";
import type { HoldingAnalytics, Performance, Slice } from "@/lib/types";

const TIP = { contentStyle: { borderRadius: 12, border: "1px solid #e2e8f0", fontSize: 12 } };
const every = (n: number, k = 15) => Math.max(1, Math.floor(n / k));
const Grid = () => <CartesianGrid strokeDasharray="3 3" stroke={GRID} strokeOpacity={0.25} />;
const Fade = ({ id, color }: { id: string; color: string }) => (
  <defs><linearGradient id={id} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity={0.55} /><stop offset="100%" stopColor={color} stopOpacity={0.05} /></linearGradient></defs>
);

export function ValueChart({ series }: { series: Performance["series"] }) {
  const data = series.map((p) => ({ date: p.date, value: Number(p.total_value) }));
  return (
    <Accessible label="Portfolio total value over time" rows={data.filter((_, i) => i % every(data.length) === 0).map((d) => [d.date, money(d.value)])}>
      <ResponsiveContainer width="100%" height={260}>
        <AreaChart data={data}>
          <Fade id="vfill" color={PRIMARY} /><Grid />
          <XAxis dataKey="date" minTickGap={40} />
          <YAxis tickFormatter={moneyCompact} width={64} domain={["auto", "auto"]} />
          <Tooltip {...TIP} formatter={(v) => money(Number(v))} />
          <Area dataKey="value" name="Total value" stroke={PRIMARY} strokeWidth={2} fill="url(#vfill)" dot={false} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </Accessible>
  );
}

export function BenchmarkChart({ series, benchmark }: { series: Performance["series"]; benchmark: string }) {
  const rows = series.filter((_, i) => i % every(series.length) === 0).map((p) => [p.date, p.portfolio_index.toFixed(1), p.benchmark_index?.toFixed(1) ?? "n/a"]);
  return (
    <Accessible label={`Portfolio versus ${benchmark} benchmark, both indexed to 100`} rows={rows}>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={series}>
          <Grid /><XAxis dataKey="date" minTickGap={40} /><YAxis domain={["auto", "auto"]} width={44} />
          <Tooltip {...TIP} formatter={(v) => Number(v).toFixed(1)} /><Legend />
          <Line dataKey="portfolio_index" name="Portfolio (excl. cash flows)" stroke={PRIMARY} strokeWidth={2.5} dot={false} isAnimationActive={false} />
          <Line dataKey="benchmark_index" name={`${benchmark} (benchmark)`} stroke={PEACH} strokeWidth={2.5} dot={false} strokeDasharray="5 3" isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </Accessible>
  );
}

export function PriceChart({ data, symbol }: { data: { date: string; close: string }[]; symbol: string }) {
  const pts = data.map((d) => ({ date: d.date, close: Number(d.close) }));
  return (
    <Accessible label={`${symbol} closing price history`} rows={pts.filter((_, i) => i % every(pts.length) === 0).map((d) => [d.date, money(d.close)])}>
      <ResponsiveContainer width="100%" height={260}>
        <AreaChart data={pts}>
          <Fade id="pfill" color={MINT} /><Grid />
          <XAxis dataKey="date" minTickGap={50} /><YAxis domain={["auto", "auto"]} width={56} tickFormatter={moneyCompact} />
          <Tooltip {...TIP} formatter={(v) => money(Number(v))} />
          <Area dataKey="close" name="Close / NAV" stroke={MINT} strokeWidth={2} fill="url(#pfill)" dot={false} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </Accessible>
  );
}

export function Donut({ title, slices }: { title: string; slices: Slice[] }) {
  const data = slices.map((s) => ({ name: s.key.replace("_", " "), value: Number(s.value) }));
  return (
    <Accessible label={title} rows={slices.map((s) => [s.label, money(s.value), percent(s.weight)])}>
      <ResponsiveContainer width="100%" height={270}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" cy="40%" innerRadius={52} outerRadius={82} paddingAngle={2} stroke="none" isAnimationActive={false}>
            {data.map((_, i) => <Cell key={i} fill={PASTEL[i % PASTEL.length]} />)}
          </Pie>
          <Tooltip {...TIP} formatter={(v) => money(Number(v))} /><Legend />
        </PieChart>
      </ResponsiveContainer>
    </Accessible>
  );
}

export function Sparkline({ values }: { values: number[] }) {
  return (
    <ResponsiveContainer width="100%" height={64}>
      <AreaChart data={values.map((v) => ({ v }))}>
        <defs><linearGradient id="spark" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#fff" stopOpacity={0.4} /><stop offset="100%" stopColor="#fff" stopOpacity={0} /></linearGradient></defs>
        <YAxis hide domain={["dataMin", "dataMax"]} />
        <Area dataKey="v" stroke="#fff" strokeWidth={2} fill="url(#spark)" dot={false} isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

/** Total return (unrealized + realized + dividends) per holding. */
export function ProfitBars({ rows }: { rows: HoldingAnalytics[] }) {
  const data = rows.filter((r) => r.total_return != null).map((r) => ({ symbol: r.symbol, value: Number(r.total_return) }))
    .sort((a, b) => b.value - a.value);
  return (
    <Accessible label="Total return by holding" rows={data.map((d) => [d.symbol, money(d.value)])}>
      <ResponsiveContainer width="100%" height={Math.max(180, data.length * 34)}>
        <BarChart data={data} layout="vertical" margin={{ left: 8 }}>
          <Grid /><XAxis type="number" tickFormatter={moneyCompact} /><YAxis type="category" dataKey="symbol" width={86} />
          <Tooltip {...TIP} formatter={(v) => money(Number(v))} /><ReferenceLine x={0} stroke={GRID} />
          <Bar dataKey="value" name="Total return" radius={6} isAnimationActive={false}>
            {data.map((d) => <Cell key={d.symbol} fill={d.value >= 0 ? GAIN : LOSS} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Accessible>
  );
}

/** Each bubble is a holding: x = 1-year volatility, y = 1-year price return, size = weight. */
export function RiskReturn({ rows }: { rows: HoldingAnalytics[] }) {
  const data = rows.filter((r) => r.open && r.volatility_1y != null && r.return_1y != null)
    .map((r, i) => ({ symbol: r.symbol, x: r.volatility_1y! * 100, y: r.return_1y! * 100, z: (r.weight ?? 0.02) * 100, fill: PASTEL[i % PASTEL.length] }));
  return (
    <Accessible label="Risk versus return by holding (1 year)" rows={data.map((d) => [d.symbol, `vol ${d.x.toFixed(1)}%`, `return ${d.y.toFixed(1)}%`])}>
      <ResponsiveContainer width="100%" height={300}>
        <ScatterChart margin={{ left: 0, right: 16 }}>
          <Grid />
          <XAxis type="number" dataKey="x" name="Volatility" unit="%" domain={[0, "auto"]} />
          <YAxis type="number" dataKey="y" name="Return" unit="%" width={48} />
          <ZAxis type="number" dataKey="z" range={[120, 700]} />
          <ReferenceLine y={0} stroke={GRID} />
          <Tooltip {...TIP} cursor={{ strokeDasharray: "3 3" }} formatter={(v) => `${Number(v).toFixed(1)}%`} labelFormatter={() => ""} />
          <Scatter data={data} isAnimationActive={false}>{data.map((d) => <Cell key={d.symbol} fill={d.fill} fillOpacity={0.85} />)}</Scatter>
        </ScatterChart>
      </ResponsiveContainer>
      <div className="mt-1 flex flex-wrap gap-3 text-xs">{data.map((d) => <span key={d.symbol} className="inline-flex items-center gap-1"><i className="size-2.5 rounded-full" style={{ background: d.fill }} />{d.symbol}</span>)}</div>
    </Accessible>
  );
}

export function DrawdownChart({ points }: { points: { date: string; drawdown: number }[] }) {
  return (
    <Accessible label="Portfolio drawdown from previous peak" rows={points.filter((_, i) => i % every(points.length) === 0).map((p) => [p.date, percent(p.drawdown)])}>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={points}>
          <Fade id="dd" color={PINK} /><Grid />
          <XAxis dataKey="date" minTickGap={50} /><YAxis tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} width={48} />
          <Tooltip {...TIP} formatter={(v) => percent(Number(v))} />
          <Area dataKey="drawdown" name="Drawdown" stroke={PINK} strokeWidth={2} fill="url(#dd)" dot={false} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </Accessible>
  );
}

/** Pastel diverging colours: lavender for positive correlation, peach for negative. */
export function CorrelationGrid({ symbols, matrix }: { symbols: string[]; matrix: (number | null)[][] }) {
  const tint = (v: number | null) => (v == null ? undefined : { background: `${v >= 0 ? "rgb(143 168 248" : "rgb(246 180 138"} / ${0.12 + Math.abs(v) * 0.7})` });
  return (
    <div className="overflow-x-auto">
      <table className="border-separate border-spacing-1 text-center text-xs">
        <caption className="sr-only">Correlation of daily returns between holdings</caption>
        <thead><tr><th />{symbols.map((s) => <th key={s} scope="col" className="px-2 font-medium text-slate-500">{s}</th>)}</tr></thead>
        <tbody>{matrix.map((row, i) => (
          <tr key={i}><th scope="row" className="pr-2 text-right font-medium text-slate-500">{symbols[i]}</th>
            {row.map((v, j) => <td key={j} className="min-w-12 rounded-md px-2 py-2" style={tint(v)}>{v == null ? "–" : v.toFixed(2)}</td>)}</tr>))}
        </tbody>
      </table>
    </div>
  );
}

export { LAVENDER };
