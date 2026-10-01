"use client";
import { Area, AreaChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Accessible } from "@/components/ui";
import { money, percent } from "@/lib/format";
import type { Performance, Slice } from "@/lib/types";

const COLORS = ["#6366f1", "#14b8a6", "#f59e0b", "#ec4899", "#8b5cf6", "#64748b", "#84cc16"];
const TIP = { contentStyle: { borderRadius: 12, border: "1px solid #e2e8f0", fontSize: 12 } };
const every = (n: number, k = 15) => Math.max(1, Math.floor(n / k));

export function ValueChart({ series }: { series: Performance["series"] }) {
  const data = series.map((p) => ({ date: p.date, value: Number(p.total_value) }));
  return (
    <Accessible label="Portfolio total value over time" rows={data.filter((_, i) => i % every(data.length) === 0).map((d) => [d.date, money(d.value)])}>
      <ResponsiveContainer width="100%" height={260}>
        <AreaChart data={data}>
          <defs><linearGradient id="vfill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#6366f1" stopOpacity={0.35} /><stop offset="100%" stopColor="#6366f1" stopOpacity={0} /></linearGradient></defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#94a3b8" strokeOpacity={0.25} />
          <XAxis dataKey="date" minTickGap={40} />
          <YAxis tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} width={56} domain={["auto", "auto"]} />
          <Tooltip {...TIP} formatter={(v) => money(Number(v))} />
          <Area dataKey="value" name="Total value" stroke="#6366f1" strokeWidth={2} fill="url(#vfill)" dot={false} isAnimationActive={false} />
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
          <CartesianGrid strokeDasharray="3 3" stroke="#94a3b8" strokeOpacity={0.25} />
          <XAxis dataKey="date" minTickGap={40} />
          <YAxis domain={["auto", "auto"]} width={44} />
          <Tooltip {...TIP} formatter={(v) => Number(v).toFixed(1)} />
          <Legend />
          <Line dataKey="portfolio_index" name="Portfolio (excl. cash flows)" stroke="#6366f1" strokeWidth={2} dot={false} isAnimationActive={false} />
          <Line dataKey="benchmark_index" name={`${benchmark} (sample)`} stroke="#f59e0b" dot={false} strokeDasharray="5 3" isAnimationActive={false} />
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
        <LineChart data={pts}>
          <CartesianGrid strokeDasharray="3 3" stroke="#94a3b8" strokeOpacity={0.25} />
          <XAxis dataKey="date" minTickGap={50} />
          <YAxis domain={["auto", "auto"]} width={50} />
          <Tooltip {...TIP} formatter={(v) => money(Number(v))} />
          <Line dataKey="close" name="Close" stroke="#14b8a6" strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </Accessible>
  );
}

export function Donut({ title, slices }: { title: string; slices: Slice[] }) {
  const data = slices.map((s) => ({ name: s.key, value: Number(s.value) }));
  return (
    <Accessible label={title} rows={slices.map((s) => [s.label, money(s.value), percent(s.weight)])}>
      <ResponsiveContainer width="100%" height={270}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" cy="40%" innerRadius={52} outerRadius={82} paddingAngle={2} stroke="none" isAnimationActive={false}>
            {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
          </Pie>
          <Tooltip {...TIP} formatter={(v) => money(Number(v))} />
          <Legend />
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
