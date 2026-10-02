import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { signClass } from "@/lib/format";

export const SampleBadge = ({ show = true }: { show?: boolean }) =>
  show ? (
    <span className="chip bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200" title="Prices are synthetic demo data, not real market data.">
      Sample data
    </span>
  ) : null;

export const Skeleton = ({ className = "h-24" }: { className?: string }) => (
  <div className={`animate-pulse rounded-2xl bg-slate-200/70 dark:bg-slate-800 ${className}`} />
);

export const Loading = () => (
  <div role="status" aria-label="Loading" className="grid gap-3 md:grid-cols-4">
    <Skeleton className="h-28 md:col-span-4" /><Skeleton /><Skeleton /><Skeleton /><Skeleton />
  </div>
);

export const ErrorBox = ({ error }: { error: Error }) => (
  <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error.message}</p>
);

export const Empty = ({ children }: { children: ReactNode }) => (
  <p className="rounded-2xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500 dark:border-slate-700">{children}</p>
);

export const PageTitle = ({ title, sub, children }: { title: string; sub?: ReactNode; children?: ReactNode }) => (
  <div className="flex flex-wrap items-end justify-between gap-3">
    <div><h1 className="text-2xl font-bold tracking-tight">{title}</h1>{sub && <div className="mt-1 text-sm text-slate-500">{sub}</div>}</div>
    <div className="flex flex-wrap items-center gap-2">{children}</div>
  </div>
);

export function Stat({ label, value, sub, tone, hint, icon: Icon }: { label: string; value: ReactNode; sub?: ReactNode; tone?: string | number | null; hint?: string; icon?: LucideIcon }) {
  return (
    <div className="card">
      <div className="flex items-center justify-between text-xs font-medium uppercase tracking-wider text-slate-500" title={hint}>
        <span>{label}</span>{Icon && <Icon size={16} aria-hidden className="text-indigo-500" />}
      </div>
      <div className={`mt-2 text-2xl font-semibold tracking-tight ${signClass(tone)}`}>{value}</div>
      {sub && <div className={`mt-0.5 text-sm ${signClass(tone) || "text-slate-500"}`}>{sub}</div>}
    </div>
  );
}

/** Wraps a chart in a labelled region with a keyboard/screen-reader friendly table alternative. */
export function Accessible({ label, rows, children }: { label: string; rows: (string | number)[][]; children: ReactNode }) {
  return (
    <figure aria-label={label}>
      <div aria-hidden>{children}</div>
      <details className="mt-2 text-xs text-slate-500">
        <summary className="cursor-pointer">View data table</summary>
        <table className="mt-1 w-full"><caption className="sr-only">{label}</caption>
          <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className="pr-3">{c}</td>)}</tr>)}</tbody>
        </table>
      </details>
    </figure>
  );
}

/** Segmented toggle used for filters and ranges. */
export function Seg({ opts, value, set, label }: { opts: readonly (readonly string[])[]; value: string; set: (v: string) => void; label: string }) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-1 rounded-xl bg-slate-200/60 p-1 dark:bg-slate-800">
      {opts.map(([v, l]) => (
        <button key={v} aria-pressed={value === v} onClick={() => set(v)}
          className={`rounded-lg px-3 py-1 text-sm font-medium transition ${value === v ? "bg-white text-indigo-700 shadow dark:bg-slate-700 dark:text-white" : "text-slate-600"}`}>{l}</button>
      ))}
    </div>
  );
}
