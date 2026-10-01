import { percent } from "@/lib/format";
import type { MonthlyReturns } from "@/lib/types";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Green/red intensity scales with the return (display only). Cell text keeps it readable without colour. */
const tint = (v: number) => `rgb(${v >= 0 ? "16 185 129" : "239 68 68"} / ${Math.min(0.12 + Math.abs(v) * 6, 0.85)})`;

export function MonthlyHeatmap({ months }: { months: MonthlyReturns["months"] }) {
  const years = [...new Set(months.map((m) => m.month.slice(0, 4)))];
  const get = (y: string, i: number) => months.find((m) => m.month === `${y}-${String(i + 1).padStart(2, "0")}`)?.portfolio;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-separate border-spacing-1 text-center text-xs">
        <caption className="sr-only">Portfolio return by calendar month</caption>
        <thead><tr><th />{MONTHS.map((m) => <th key={m} scope="col" className="font-medium text-slate-500">{m}</th>)}</tr></thead>
        <tbody>{years.map((y) => (
          <tr key={y}><th scope="row" className="pr-2 text-right font-medium text-slate-500">{y}</th>
            {MONTHS.map((_, i) => { const v = get(y, i); return (
              <td key={i} className="rounded-md py-2" style={v == null ? undefined : { background: tint(v) }}>{v == null ? "" : percent(v).replace(".00", "")}</td>); })}
          </tr>))}
        </tbody>
      </table>
    </div>
  );
}
