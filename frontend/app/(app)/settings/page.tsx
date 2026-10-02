"use client";
import { usePid } from "../layout";
import { ErrorBox, Loading, SampleBadge } from "@/components/ui";
import { base, useData } from "@/lib/api";
import { CLERK } from "@/lib/auth";
import type { Portfolio, Summary } from "@/lib/types";

type Status = { stocks: boolean; mutual_funds: boolean };

export default function Settings() {
  const pid = usePid();
  const p = useData<Portfolio & { base_currency: string }>(base(pid));
  const s = useData<Summary>(`${base(pid)}/summary`);
  const live = useData<Status>("/api/v1/market/status").data;
  if (p.error) return <ErrorBox error={p.error} />;
  if (!p.data || !s.data) return <Loading />;
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
    </div>
  );
}
