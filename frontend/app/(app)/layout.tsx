"use client";
import { BarChart3, BookOpen, Briefcase, LayoutDashboard, LogOut, Moon, Receipt, Settings, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { useSWRConfig } from "swr";
import { ErrorBox, Loading } from "@/components/ui";
import { useApi, useData } from "@/lib/api";
import { useSession } from "@/lib/auth";
import type { Portfolio } from "@/lib/types";

const PortfolioId = createContext("");
export const usePid = () => useContext(PortfolioId);

const LINKS = [
  ["Dashboard", "/dashboard", LayoutDashboard], ["Holdings", "/holdings", Briefcase], ["Transactions", "/transactions", Receipt],
  ["Methodology", "/methodology", BookOpen], ["Settings", "/settings", Settings],
] as const;

function Onboarding() {
  const api = useApi();
  const { mutate } = useSWRConfig();
  const [error, setError] = useState<Error>();
  const create = (load_demo_data: boolean) =>
    api("/api/v1/portfolios", { method: "POST", body: JSON.stringify({ name: load_demo_data ? "Demo Portfolio" : "My Portfolio", load_demo_data }) })
      .then(() => mutate("/api/v1/portfolios")).catch(setError);
  return (
    <div className="card mx-auto mt-16 max-w-md space-y-4 text-center">
      <BarChart3 className="mx-auto text-indigo-500" size={36} />
      <h1 className="text-xl font-bold">Create your portfolio</h1>
      <p className="text-sm text-slate-500">Start with a fully populated sample portfolio, or an empty one to add your own transactions. All market data is synthetic.</p>
      {error && <ErrorBox error={error} />}
      <div className="flex justify-center gap-2">
        <button className="btn-primary" onClick={() => create(true)}>Load demo portfolio</button>
        <button className="btn" onClick={() => create(false)}>Start empty</button>
      </div>
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
  useEffect(() => { if (ready && !signedIn) router.replace("/sign-in"); }, [ready, signedIn, router]);
  const { data, error } = useData<Portfolio[]>(signedIn ? "/api/v1/portfolios" : null);

  if (!ready || !signedIn) return <div className="p-8"><Loading /></div>;
  return (
    <div className="min-h-screen md:grid md:grid-cols-[15rem_1fr]">
      <aside className="flex flex-col gap-4 border-b border-slate-200 bg-white p-4 md:sticky md:top-0 md:h-screen md:border-b-0 md:border-r dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center gap-2 text-lg font-bold">
          <span className="grid size-8 place-items-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 text-white"><BarChart3 size={18} /></span>PortfolioLab
        </div>
        <nav aria-label="Main" className="flex gap-1 overflow-x-auto md:flex-col">
          {LINKS.map(([label, href, Icon]) => {
            const active = path.startsWith(href);
            return (
              <Link key={href} href={href} aria-current={active ? "page" : undefined}
                className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition ${active ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300" : "text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800"}`}>
                <Icon size={17} aria-hidden />{label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto hidden space-y-2 md:block">
          <ThemeToggle />
          <button className="btn w-full justify-center" onClick={signOut}><LogOut size={16} />Sign out</button>
        </div>
      </aside>
      <div className="min-w-0 p-4 md:p-8">
        <div className="mx-auto max-w-6xl">
          {error ? <ErrorBox error={error} /> : !data ? <Loading /> : data.length === 0 ? <Onboarding /> : (
            <PortfolioId.Provider value={data[0].id}>{children}</PortfolioId.Provider>
          )}
          <footer className="mt-10 flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 pt-4 text-xs text-slate-500 dark:border-slate-800">
            <span>Analytics only — not investment advice. Market data is synthetic sample data.</span>
            <span className="md:hidden"><button className="btn" onClick={signOut}>Sign out</button></span>
          </footer>
        </div>
      </div>
    </div>
  );
}
