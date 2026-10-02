"use client";
import { Activity, BarChart3, BookOpen, Briefcase, LayoutDashboard, LogOut, Moon, Plus, Receipt, Repeat, Settings, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { useSWRConfig } from "swr";
import { ErrorBox, Loading } from "@/components/ui";
import { useApi, useData } from "@/lib/api";
import { useSession } from "@/lib/auth";
import { setCurrency } from "@/lib/format";
import type { Portfolio } from "@/lib/types";

const Ctx = createContext<{ id: string; portfolio: Portfolio } | null>(null);
export const usePid = () => useContext(Ctx)!.id;
export const usePortfolio = () => useContext(Ctx)!.portfolio;

const LINKS = [
  ["Dashboard", "/dashboard", LayoutDashboard], ["Holdings", "/holdings", Briefcase], ["Analytics", "/analytics", Activity],
  ["SIPs", "/sips", Repeat], ["Transactions", "/transactions", Receipt], ["Methodology", "/methodology", BookOpen], ["Settings", "/settings", Settings],
] as const;

function Onboarding({ existing, onDone }: { existing: Portfolio[]; onDone: (id: string) => void }) {
  const api = useApi();
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const has = (c: string, demo: boolean) => existing.some((p) => p.base_currency === c && p.is_demo === demo);
  const [currency, setCurrencyChoice] = useState<"USD" | "INR">(has("USD", false) && !has("INR", false) ? "INR" : "USD");
  const realTaken = has(currency, false);
  const [error, setError] = useState<Error>();
  async function create(mode: "demo" | "quick" | "empty") {
    try {
      const p: Portfolio = await api("/api/v1/portfolios", { method: "POST", body: JSON.stringify({
        name: mode === "demo" ? `Demo ${currency} Portfolio` : `My ${currency} Portfolio`, currency, load_demo_data: mode === "demo" }) });
      await mutate("/api/v1/portfolios");
      onDone(p.id);
      router.push(mode === "quick" ? "/get-started" : "/dashboard");
    } catch (e) { setError(e as Error); }
  }
  return (
    <div className="card mx-auto mt-10 max-w-lg space-y-5 text-center">
      <BarChart3 className="mx-auto text-indigo-400" size={36} />
      <div><h1 className="text-xl font-bold">{existing.length ? "Add another portfolio" : "Create your portfolio"}</h1>
        <p className="mt-1 text-sm text-slate-500">Each portfolio has one currency, and holds assets that trade in it. You can have one in dollars and one in rupees.</p></div>
      <div role="group" aria-label="Currency" className="mx-auto flex w-fit gap-1 rounded-xl bg-slate-200/60 p-1 dark:bg-slate-800">
        {(["USD", "INR"] as const).map((c) => (
          <button key={c} aria-pressed={currency === c} onClick={() => setCurrencyChoice(c)}
            className={`rounded-lg px-4 py-1.5 text-sm font-medium transition ${currency === c ? "bg-white text-indigo-700 shadow dark:bg-slate-700 dark:text-white" : "text-slate-600"}`}>
            {c === "USD" ? "$ US Dollar" : "₹ Indian Rupee"}</button>))}
      </div>
      {error && <ErrorBox error={error} />}
      <div className="flex flex-wrap justify-center gap-2">
        <button className="btn-primary" disabled={realTaken} onClick={() => create("quick")}>Enter my holdings</button>
        <button className="btn" disabled={has(currency, true)} onClick={() => create("demo")}>Load demo portfolio</button>
        <button className="btn" disabled={realTaken} onClick={() => create("empty")}>Start empty</button>
      </div>
      {(realTaken || has(currency, true)) && (
        <p className="text-xs text-amber-700">
          {realTaken && `You already have your own ${currency} portfolio. `}{has(currency, true) && `The ${currency} demo already exists.`}
        </p>)}
      <p className="text-xs text-slate-500">Demo uses synthetic sample data. &ldquo;Enter my holdings&rdquo; builds your portfolio from what you own today.</p>
    </div>
  );
}

function DemoBanner({ portfolio, onGone }: { portfolio: Portfolio; onGone: () => void }) {
  const api = useApi();
  const { mutate } = useSWRConfig();
  const [error, setError] = useState<Error>();
  async function abandon() {
    if (!confirm("Abandon this demo portfolio? Its sample transactions and SIPs will be deleted. You can load the demo again later.")) return;
    try {
      await api(`/api/v1/portfolios/${portfolio.id}`, { method: "DELETE" });
      await mutate(() => true);
      onGone();
    } catch (e) { setError(e as Error); }
  }
  return (
    <div role="note" className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm dark:border-amber-900/50 dark:bg-amber-900/20">
      <span>You&apos;re exploring a <b>demo {portfolio.base_currency} portfolio</b> with synthetic data. Nothing here is real.</span>
      <span className="flex gap-2">{error && <span className="text-red-700">{error.message}</span>}
        <button className="btn" onClick={abandon}>Abandon demo</button></span>
    </div>
  );
}

function ThemeToggle() {
  const toggle = () => {
    const dark = document.documentElement.classList.toggle("dark");
    localStorage.setItem("pl_theme", dark ? "dark" : "light");
  };
  return (
    <button className="btn w-full justify-center" onClick={toggle} aria-label="Toggle dark mode">
      <Moon size={16} className="dark:hidden" /><Sun size={16} className="hidden dark:block" />Toggle theme
    </button>
  );
}

export default function AppLayout({ children }: { children: ReactNode }) {
  const { ready, signedIn, signOut } = useSession();
  const router = useRouter();
  const path = usePathname();
  const [sel, setSel] = useState<string | null>(() => (typeof window === "undefined" ? null : localStorage.getItem("pl_pid")));
  const [creating, setCreating] = useState(false);
  useEffect(() => { if (ready && !signedIn) router.replace("/sign-in"); }, [ready, signedIn, router]);
  const { data, error } = useData<Portfolio[]>(signedIn ? "/api/v1/portfolios" : null);

  if (!ready || !signedIn) return <div className="p-8"><Loading /></div>;
  const portfolio = data?.find((p) => p.id === sel) ?? data?.[0];
  if (portfolio) setCurrency(portfolio.base_currency);
  const choose = (id: string) => { localStorage.setItem("pl_pid", id); setSel(id); setCreating(false); };

  return (
    <div className="min-h-screen md:grid md:grid-cols-[15rem_1fr]">
      <aside className="flex flex-col gap-4 border-b border-slate-200 bg-white p-4 md:sticky md:top-0 md:h-screen md:border-b-0 md:border-r dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center gap-2 text-lg font-bold">
          <span className="grid size-8 place-items-center rounded-lg bg-gradient-to-br from-indigo-300 to-violet-400 text-white"><BarChart3 size={18} /></span>PortfolioLab
        </div>
        {data && data.length > 0 && (
          <div className="space-y-1">
            <select aria-label="Portfolio" className="input w-full" value={portfolio?.id} onChange={(e) => choose(e.target.value)}>
              {data.map((p) => <option key={p.id} value={p.id}>{p.base_currency === "INR" ? "₹" : "$"} {p.name}{p.is_demo ? " (demo)" : ""}</option>)}
            </select>
            <button className="btn w-full justify-center text-xs" onClick={() => setCreating(true)}><Plus size={14} />Add portfolio</button>
          </div>)}
        <nav aria-label="Main" className="flex gap-1 overflow-x-auto md:flex-col">
          {LINKS.map(([label, href, Icon]) => {
            const active = path.startsWith(href);
            return (
              <Link key={href} href={href} aria-current={active ? "page" : undefined} onClick={() => setCreating(false)}
                className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition ${active ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300" : "text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800"}`}>
                <Icon size={17} aria-hidden />{label}
              </Link>);
          })}
        </nav>
        <div className="mt-auto hidden space-y-2 md:block">
          <ThemeToggle />
          <button className="btn w-full justify-center" onClick={signOut}><LogOut size={16} />Sign out</button>
        </div>
      </aside>
      <div className="min-w-0 p-4 md:p-8">
        <div className="mx-auto max-w-6xl">
          {error ? <ErrorBox error={error} /> : !data ? <Loading /> : data.length === 0 || creating ? (
            <Onboarding existing={data} onDone={choose} />
          ) : (
            <Ctx.Provider value={{ id: portfolio!.id, portfolio: portfolio! }} key={portfolio!.id}>
              {portfolio!.is_demo && <DemoBanner portfolio={portfolio!} onGone={() => { localStorage.removeItem("pl_pid"); setSel(null); router.push("/dashboard"); }} />}
              {children}
            </Ctx.Provider>
          )}
          <footer className="mt-10 flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 pt-4 text-xs text-slate-500 dark:border-slate-800">
            <span>Analytics only — not investment advice. Demo portfolios use synthetic sample data.</span>
            <span className="md:hidden"><button className="btn" onClick={signOut}>Sign out</button></span>
          </footer>
        </div>
      </div>
    </div>
  );
}
