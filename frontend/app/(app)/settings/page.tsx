"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useSWRConfig } from "swr";
import { usePid } from "../layout";
import { ErrorBox, Loading, SampleBadge } from "@/components/ui";
import { base, useApi, useData } from "@/lib/api";
import { CLERK } from "@/lib/auth";
import type { Portfolio, Summary } from "@/lib/types";

type Status = { stocks: boolean; mutual_funds: boolean };

export default function Settings() {
  const pid = usePid();
  const api = useApi();
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const [delError, setDelError] = useState<Error>();
  const p = useData<Portfolio>(base(pid));
  const s = useData<Summary>(`${base(pid)}/summary`);
  const live = useData<Status>("/api/v1/market/status").data;
  if (p.error) return <ErrorBox error={p.error} />;
  if (!p.data || !s.data) return <Loading />;
  async function remove() {
    const what = p.data!.is_demo ? "demo portfolio" : "portfolio and ALL its transactions, SIPs and history";
    if (!confirm(`Permanently delete this ${what}? This cannot be undone.`)) return;
    try {
      await api(base(pid), { method: "DELETE" });
      localStorage.removeItem("pl_pid");
      await mutate(() => true);
      router.push("/dashboard");
    } catch (e) { setDelError(e as Error); }
  }
  return (
    <div className="max-w-xl space-y-4">
      <h1 className="text-2xl font-semibold">Settings</h1>
      <section className="card space-y-1 text-sm">
        <h2 className="font-semibold">Profile</h2>
        <p>Portfolio: {p.data.name}</p>
        <p>Sign-in: {CLERK ? "Clerk" : "Local development sign-in (Clerk not configured)"}</p>
      </section>
      <section className="card space-y-1 text-sm">
        <h2 className="font-semibold">Portfolio currency</h2>
        <p>{p.data.base_currency === "INR" ? "₹ Indian Rupee (INR)" : "$ US Dollar (USD)"}. Each portfolio holds one currency and only assets that trade in it; use the portfolio switcher for the other.</p>
      </section>
      <section className="card space-y-1 text-sm">
        <h2 className="font-semibold">Data source</h2>
        <p>Source: {s.data.is_sample_data ? "Synthetic sample data (demo portfolios)" : "External provider"} <SampleBadge show={s.data.is_sample_data} /></p>
        {live && <p>Live providers: stocks &amp; ETFs {live.stocks ? "connected" : "not configured (sample data only)"} · Indian mutual funds {live.mutual_funds ? "connected (AMFI NAV)" : "off"}</p>}
        <p>Latest price date: {s.data.as_of ?? "none"}</p>
        <p>Status: {s.data.value_complete ? "All held assets have prices" : `Missing prices: ${s.data.unavailable_symbols.join(", ")}`}</p>
      </section>
      <section className="card space-y-2 border-red-200 text-sm dark:border-red-900/50">
        <h2 className="font-semibold text-red-700">Danger zone</h2>
        <p className="text-slate-500">{p.data.is_demo ? "Remove this demo portfolio. You can load it again later." : "Permanently delete this portfolio with all its transactions, SIPs and history."}</p>
        {delError && <ErrorBox error={delError} />}
        <button className="btn border-red-300 text-red-700" onClick={remove}>{p.data.is_demo ? "Abandon demo portfolio" : "Delete portfolio"}</button>
      </section>
    </div>
  );
}
