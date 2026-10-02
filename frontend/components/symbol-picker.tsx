"use client";
import { Search } from "lucide-react";
import { useEffect, useState } from "react";
import { TYPE_LABEL } from "@/lib/format";
import { useApi } from "@/lib/api";
import type { Asset, SearchResult } from "@/lib/types";

type Props = { currency: string; initial?: string; name?: string; required?: boolean; onSelect?: (a: Asset) => void; label?: string };

/** Type a ticker, company or fund name. Live results from the market-data provider are added on selection. */
export function SymbolPicker({ currency, initial = "", name, required, onSelect, label = "Symbol" }: Props) {
  const api = useApi();
  const [q, setQ] = useState(initial);
  const [picked, setPicked] = useState(initial);
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [note, setNote] = useState<string>();
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open || q.trim().length < 1 || q === picked) return;
    const t = setTimeout(async () => {
      try {
        const r = await api(`/api/v1/assets/search?q=${encodeURIComponent(q.trim())}&currency=${currency}`);
        setResults(r.results);
        setNote(r.warning ?? (r.results.length ? undefined : "No matches"));
      } catch (e) { setNote((e as Error).message); }
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, open, currency, picked]);

  async function choose(r: SearchResult) {
    setBusy(true);
    try {
      const asset: Asset = r.in_db ? r : await api("/api/v1/assets", { method: "POST", body: JSON.stringify({ symbol: r.symbol }) });
      setPicked(asset.symbol); setQ(asset.symbol); setOpen(false); setNote(undefined);
      onSelect?.(asset);
    } catch (e) { setNote((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <div className="relative">
      <label className="block text-sm">{label}
        <div className="relative mt-1">
          <Search size={14} className="pointer-events-none absolute left-2.5 top-2.5 text-slate-400" aria-hidden />
          <input role="combobox" aria-expanded={open} aria-controls="symbol-results" aria-autocomplete="list" autoComplete="off"
            className="input w-full pl-8" placeholder="e.g. AAPL, Reliance, Parag Parikh" value={q} required={required}
            onFocus={() => setOpen(true)} onChange={(e) => { setQ(e.target.value); setPicked(""); setOpen(true); }} />
        </div>
      </label>
      {name && <input type="hidden" name={name} value={picked} />}
      {open && (results.length > 0 || note || busy) && (
        <ul id="symbol-results" role="listbox" className="absolute z-20 mt-1 max-h-64 w-full min-w-72 overflow-auto rounded-xl border border-slate-200 bg-white p-1 shadow-lg dark:border-slate-700 dark:bg-slate-900">
          {busy && <li className="p-2 text-xs text-slate-500">Adding and loading price history…</li>}
          {results.map((r) => (
            <li key={r.symbol} role="option" aria-selected={false}>
              <button type="button" disabled={busy} onClick={() => choose(r)} className="flex w-full items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-800">
                <span><b>{r.symbol}</b> <span className="text-slate-500">{r.name}</span></span>
                <span className="shrink-0 text-xs text-slate-500">{TYPE_LABEL[r.asset_type] ?? r.asset_type}{r.sample && " · sample"}</span>
              </button>
            </li>))}
          {note && <li className="p-2 text-xs text-slate-500">{note}</li>}
        </ul>)}
    </div>
  );
}
