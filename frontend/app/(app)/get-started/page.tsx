"use client";
import { Receipt, Repeat } from "lucide-react";
import Link from "next/link";
import { usePid } from "../layout";
import { QuickStart } from "@/components/quick-start";
import { PageTitle } from "@/components/ui";

export default function GetStarted() {
  return (
    <div className="space-y-5">
      <PageTitle title="Set up your portfolio" sub="Choose the way that fits what you have." />
      <QuickStart pid={usePid()} />
      <div className="grid gap-3 md:grid-cols-2">
        <Link href="/transactions" className="card flex items-start gap-3 transition hover:shadow-md"><Receipt className="mt-0.5 text-indigo-400" /><span><b>Import your broker&apos;s CSV</b><br /><span className="text-sm text-slate-500">Exact history with real dates and fees. Map the columns once.</span></span></Link>
        <Link href="/sips" className="card flex items-start gap-3 transition hover:shadow-md"><Repeat className="mt-0.5 text-indigo-400" /><span><b>Add a SIP</b><br /><span className="text-sm text-slate-500">Monthly investments into a mutual fund or any stock, tracked automatically.</span></span></Link>
      </div>
    </div>
  );
}
