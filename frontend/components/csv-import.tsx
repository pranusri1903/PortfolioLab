"use client";
import { useState } from "react";
import { useSWRConfig } from "swr";
import { ErrorBox } from "@/components/ui";
import { base, useApi } from "@/lib/api";
import type { ImportResult } from "@/lib/types";

const COLOR = { valid: "text-emerald-700", invalid: "text-red-700", duplicate: "text-amber-700" };
const FIELDS = ["trade_date", "type", "symbol", "quantity", "price", "fee", "cash_amount", "notes"] as const;
const GUESS: Record<(typeof FIELDS)[number], RegExp> = {
  trade_date: /date/i, type: /type|action|side|transaction/i, symbol: /symbol|ticker|scrip|instrument|fund|name/i,
  quantity: /qty|quantity|units/i, price: /price|rate|nav/i, fee: /fee|brokerage|charge/i,
  cash_amount: /amount|value|net/i, notes: /note|remark|narration/i,
};
const DATE_FORMATS = [["%Y-%m-%d", "YYYY-MM-DD"], ["%d/%m/%Y", "DD/MM/YYYY"], ["%m/%d/%Y", "MM/DD/YYYY"], ["%d-%m-%Y", "DD-MM-YYYY"], ["%d-%b-%Y", "DD-Mon-YYYY"]];

const parseHeader = (line: string) => (line.match(/("([^"]*)"|[^,]+)/g) ?? []).map((c) => c.replace(/^"|"$/g, "").trim());

export function CsvImport({ pid, onClose }: { pid: string; onClose: () => void }) {
  const api = useApi();
  const { mutate } = useSWRConfig();
  const [file, setFile] = useState<File>();
  const [columns, setColumns] = useState<string[]>([]);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [dateFormat, setDateFormat] = useState("%Y-%m-%d");
  const [res, setRes] = useState<ImportResult>();
  const [error, setError] = useState<Error>();
  const custom = columns.length > 0 && FIELDS.join(",") !== columns.join(",");

  async function pick(f?: File) {
    setFile(f); setRes(undefined);
    if (!f) return;
    const cols = parseHeader((await f.text()).split(/\r?\n/)[0]);
    setColumns(cols);
    setMapping(Object.fromEntries(FIELDS.map((k) => [k, cols.find((c) => GUESS[k].test(c)) ?? ""])));
  }

  async function run(commit: boolean) {
    setError(undefined);
    const body = new FormData();
    body.set("file", file!);
    if (custom) { body.set("mapping", JSON.stringify(mapping)); body.set("date_format", dateFormat); }
    try {
      setRes(await api(`${base(pid)}/transactions/import?commit=${commit}`, { method: "POST", body }));
      if (commit) await mutate(() => true);
    } catch (e) { setError(e as Error); setRes(undefined); }
  }

  return (
    <section className="card space-y-3" aria-label="Import CSV">
      <h2 className="font-semibold">Import transactions from CSV</h2>
      <p className="text-xs text-slate-500">Use our format (<code>{FIELDS.join(",")}</code>) or upload a broker export and map its columns. Nothing is saved until you confirm the preview.</p>
      <input type="file" accept=".csv,text/csv" aria-label="CSV file" onChange={(e) => pick(e.target.files?.[0])} />
      {custom && (
        <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/50">
          <p className="mb-2 text-sm font-medium">Match your file&apos;s columns</p>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {FIELDS.map((k) => (
              <label key={k} className="block text-xs">{k.replace("_", " ")}
                <select className="input mt-1 w-full" value={mapping[k] ?? ""} onChange={(e) => setMapping({ ...mapping, [k]: e.target.value })}>
                  <option value="">— none —</option>{columns.map((c) => <option key={c}>{c}</option>)}
                </select>
              </label>))}
            <label className="block text-xs">date format
              <select className="input mt-1 w-full" value={dateFormat} onChange={(e) => setDateFormat(e.target.value)}>{DATE_FORMATS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
            </label>
          </div>
        </div>)}
      <button className="btn" disabled={!file || res?.committed} onClick={() => run(false)}>Preview</button>
      {error && <ErrorBox error={error} />}
      {res && (
        <>
          <p role="status" className="text-sm">
            {res.committed && res.result
              ? `Imported ${res.result.imported}, skipped ${res.result.skipped} duplicates, rejected ${res.result.rejected}.`
              : `${res.valid} valid, ${res.duplicate} duplicate (will be skipped), ${res.invalid} invalid (will be rejected).`}
          </p>
          <div className="max-h-64 overflow-auto">
            <table className="w-full"><thead><tr><th className="th">Row</th><th className="th">Status</th><th className="th">Details</th></tr></thead>
              <tbody>{res.rows.map((r) => (
                <tr key={r.row_number} className="row"><td className="td">{r.row_number}</td><td className={`td font-medium ${COLOR[r.status]}`}>{r.status}</td>
                  <td className="td">{r.reasons.join("; ") || `${r.data.type} ${r.data.symbol ?? ""} ${r.data.trade_date}`}</td></tr>))}</tbody></table>
          </div>
        </>
      )}
      <div className="flex gap-2">
        {res && !res.committed && <button className="btn-primary" disabled={res.valid === 0} onClick={() => run(true)}>Confirm import of {res.valid} rows</button>}
        <button className="btn" onClick={onClose}>{res?.committed ? "Done" : "Cancel"}</button>
      </div>
    </section>
  );
}
